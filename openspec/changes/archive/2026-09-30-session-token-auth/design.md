## Context

`ForlabsSession` (`src/forlabs_mcp/client/session.py`) currently does two
things around one `httpx.Client`: primes the `XSRF-TOKEN` cookie, then
POSTs `/app/login` with the configured `username`/`password` to obtain the
`forlabs_session` cookie. It caches that cookie jar to `session.json`
(mode `0600`) and reuses it across process runs; on a `401`/`419` it
re-logs-in once with the same credentials and retries. `ForlabsConfig`
(`src/forlabs_mcp/config.py`) requires `username`/`password` from
env/TOML/default before any network call. See `proposal.md` - Why.

A real login was captured live (not just read from `PROJECT-REFERENCE.md`)
and inspected for cookie lifetimes:

| Cookie | Domain | Measured lifetime |
|---|---|---|
| `XSRF-TOKEN` | `bki.forlabs.ru` | ~2.4 hours |
| `forlabs_session` | `bki.forlabs.ru` | ~2.4 hours |
| `remember_lm_<hash>` | `bki.forlabs.ru` | ~5 years (~1825 days) |

The `<hash>` suffix on the remember cookie's name is a Laravel
`Auth::viaRemember()` guard identifier baked into this application's own
configuration - it is the same for every user of this Forlabs deployment,
not something derived from the individual account.

A follow-up live test confirmed the mechanism this design relies on: a
request carrying **only** `remember_lm_<hash>` (no `forlabs_session`, just
a freshly primed `XSRF-TOKEN` from `GET /app/login`) against
`POST /lm-vendor/repositories/sched/get_schedule` returned `200` with real
data, and the response's `Set-Cookie` headers minted a fresh
`forlabs_session`. This is standard Laravel remember-me behavior operating
transparently on an ordinary authenticated request - no special keep-alive
call, endpoint, or timing is needed to trigger it.

## Goals / Non-Goals

**Goals:**
- Remove `username`/`password` from the configuration surface entirely.
- Let the server authenticate from a `session_token` (the `remember_lm_<hash>`
  cookie value) the user pastes in from their own browser session.
- Rely on Laravel's confirmed remember-me renewal for ordinary session
  continuity, so the common case needs no special-cased refresh logic at
  all - just seed the cookie and make normal calls.
- Make the (now rare, ~5-year-horizon) failure mode explicit and
  actionable: a clear error and no silent retry loop once the remember
  cookie itself is ever rejected.

**Non-Goals:**
- Discovering or reverse-engineering additional Forlabs cookies/endpoints
  beyond what's already captured in `PROJECT-REFERENCE.md` and confirmed
  by this design's live tests.
- Any credential-based fallback or recovery once the configured
  `remember_lm_<hash>` value is itself rejected - there is no credential
  configured to fall back to, by design.
- Detecting or working around a future change to the `remember_lm_<hash>`
  cookie's name/hash suffix - if this Forlabs deployment's auth guard
  configuration changes, the wizard's DevTools instructions may need a
  follow-up update, but that is out of scope here.

## Decisions

**Session token replaces credentials outright, not additively.**
Considered keeping `username`/`password` as an optional fallback alongside
`session_token`. Rejected per explicit user decision: the goal is to
remove the password-storage obligation completely, accepting that a dead
remember cookie becomes a manual, out-of-band fix (get a new cookie value
from the browser, update config) instead of a transparent background
relogin. Given the ~5-year measured lifetime, this trade-off is far less
costly than it would have been against the ~2.4-hour short session cookie
originally (incorrectly) assumed to be the thing to paste in.

**Seed the `remember_lm_<hash>` cookie directly, no login POST.**
`ForlabsSession.__init__` sets the `remember_lm_<hash>` cookie on the
`httpx.Client` from `config.session_token` (same domain-qualified
`cookies.set()` call already used in `_load_persisted_session()`),
instead of calling `login()`. The existing `session.json` persistence
stays as-is - it caches whatever cookies the client currently holds
(including any `forlabs_session`/`XSRF-TOKEN` Laravel mints along the
way), so a resumed process can skip straight to a data call without even
needing the remember cookie to do its job again, as long as the cached
short-lived cookies are still fresh.

**No separate keep-alive mechanism.**
An earlier version of this design considered an opportunistic keep-alive
call (touching an authenticated endpoint before/around data calls) because
the remember-me behavior was, at the time, unconfirmed. That call is no
longer needed: the live test above confirms an ordinary data call, made
with only the remember cookie present, already triggers Laravel's
remember-me renewal as a side effect - `sched/get_schedule` itself was the
"keep-alive" in that test, with no distinct mechanism involved. Adding a
separate call would just duplicate work the normal request path already
does for free.

**No retry-with-backoff on expiry.**
The current code retries the wrapped call exactly once after a relogin.
With no relogin possible, retrying the same call after a `401`/`419`
would just reproduce the same error - and a `401`/`419` at this point
means the remember cookie itself was rejected (the short session renews
transparently on its own, per the Decisions above), which retrying cannot
fix. `request()` raises `AuthError` immediately on the first
expiry-classified status instead of retrying.

## Risks / Trade-offs

- [Users must manually extract an `HttpOnly` cookie from browser DevTools
  to set up or recover from expiry] → Meaningfully more friction than the
  current interactive username/password wizard for the *initial* setup,
  but - unlike the short session cookie this design initially (incorrectly)
  targeted - this is a roughly once-per-5-years action, not a recurring
  one. `scripts/setup_config.py`'s wizard prompt includes copy/paste-ready
  DevTools instructions (Application/Storage tab) to lower first-time
  friction.
- [**BREAKING**: every existing deployed config stops working] → Called
  out in the proposal; no migration shim is planned since the old
  credential fields are being removed outright, per the user's explicit
  choice.
- [A leaked `remember_lm_<hash>` value grants the same practical account
  access as a leaked password, for its full ~5-year measured lifetime] →
  Same file-permission protection (`0600`) as before; document plainly
  (not hedged) that a leaked value should be treated exactly like a leaked
  password. Whether Forlabs offers a "sign out other sessions" action that
  would invalidate it early is not confirmed and is called out as a known
  gap - the practical remediation is a full password change on the
  account, which invalidates existing Laravel remember tokens tied to it.
- [The `remember_lm_<hash>` cookie name's hash suffix is specific to this
  Forlabs deployment's current auth guard configuration] → If Forlabs ever
  changes this, the wizard's "look for a cookie starting with
  `remember_lm_`" instruction keeps working (prefix match), but a renamed
  prefix entirely would need a follow-up doc/wizard update.

## Migration Plan

No automated migration: `username`/`password` config keys are simply no
longer read. Deploying this change requires every user to:
1. Log into `https://bki.forlabs.ru/app` in their browser with "remember
   me" behavior in effect (the standard login form already sends this).
2. Copy the `remember_lm_<hash>` cookie's value via DevTools
   (Application/Storage tab - it is `HttpOnly`, so it will not appear via
   `document.cookie` in the Console, but DevTools' own cookie list shows
   it regardless).
3. Re-run `scripts/setup_config.py` (updated wizard) or set
   `FORLABS_SESSION_TOKEN`/the TOML `session_token` key directly.

This is expected to be a one-time action good for roughly 5 years, not a
recurring maintenance task.

Rollback is a plain revert of this change's commits; it re-enables the
username/password flow with no data migration needed in either direction,
since neither config format carries state the other depends on.
