## Context

`ForlabsSession` (`src/forlabs_mcp/client/session.py`) wraps one
`httpx.Client`. At startup it loads the cookie jar from `session.json`, then
seeds `remember_lm_<hash>` from `config.session_token` only if the cache did
not already supply one. `_authenticated_send()` primes `XSRF-TOKEN` via
`GET /app/login` only when no such cookie is in the jar. `request()` raises
`AuthError` on the first `401`/`419` and persists the jar only after a
non-auth response. See proposal.md - Why for the failure this produces.

Confirmed live on 2026-10-03, using the same remember cookie in each case:

| Starting jar | Result |
|---|---|
| Cached `remember` + `XSRF-TOKEN` + `forlabs_session`, ~3 days old | `419 {"message": "CSRF token mismatch."}` |
| Empty (remember seeded from config) | `200`, fresh `XSRF-TOKEN` + `forlabs_session` set |
| Cached remember cookie only | `200`, fresh pair set |

A `401` for a truly dead remember cookie has still never been captured.

## Goals / Non-Goals

**Goals:**
- Fix both triggers with one mechanism: a stale cache at startup and an
  in-memory session that expires during a long-running process.
- Keep each call bounded: at most one priming `GET` and one retried call on
  top of the original request.

**Non-Goals:**
- Persisting cookie expiry, or dropping short-lived cookies from the cache
  (variants 2/3 from exploration). The reactive retry already covers those
  cases, and the cache format stays as it is.
- Proactive refresh before the ~2.4 h mark. That would need timing the
  backend never promised.
- Telling a dead remember cookie apart from other `401` causes beyond what
  the status code says.

## Decisions

**Reset to the remember cookie, not just re-prime XSRF.**
After a `419` the cheapest repair would be to re-prime only `XSRF-TOKEN`.
It is rejected because the stale `forlabs_session` would stay in the jar
and keep the request tied to the dead server-side session. Clearing the
whole jar and re-seeding the remember cookie from `config.session_token`
recreates exactly the state the live test proved works (row 2). Re-seeding
from config, not keeping the cached remember value, also means an updated
`session_token` wins over an old cached one on the first failure.

**One retry, on either `401` or `419`.**
Both statuses come from the stale-short-session path: Laravel returns
`419` when the CSRF token does not match the session and `401` from
`auth` middleware when the session is gone. The remember cookie usually
heals the second case before it shows, but not always. Retrying only on
`419` would leave the `401` variant of the same bug. The retry is capped
at one per `request()` call, so a really dead token costs one extra
round trip, not a loop.

**The status of the retry, not the first attempt, picks the message.**
The first `401`/`419` is expected and says nothing about the token. Once
the retry runs on fresh state, a `401` points at the remember cookie and
a `419` points at a CSRF problem that a new token cannot fix. These map
to two `AuthError` messages, and neither includes the token value.

**Persist only on success.**
`_persist_session()` stays where it is, after a non-auth response. A
successful retry overwrites the stale `session.json`, so the next run
starts clean. A failed retry leaves the file as it was, and the next run
pays the same one-retry cost before raising again. That keeps a broken
state from being written to disk as if it were good.

**Keep the retry inside `ForlabsSession.request()`.**
Callers (`repository.py`, `client.py`) already see one `request()` and
should not learn about cookies. A private `_reset_session()` helper
clears the jar and re-seeds the remember cookie. The existing cold-start
branch in `_authenticated_send()` then does the priming, because
`XSRF-TOKEN` is now missing.

## Risks / Trade-offs

- [A dead token now costs three requests (call, prime, retried call)
  instead of one before the error] → It happens rarely (about once per
  token lifetime) and is bounded. A clear message matters more here than
  the extra latency.
- [The retry resends a non-idempotent call] → Every allow-listed
  repository action is read-only (spec "Backend action allow-list"), and
  a `401`/`419` means the backend rejected the request before running it.
- [The backend may use another status (for example a `302` to
  `/app/login`) for an expired session in some path] → Out of scope. Only
  the observed `401`/`419` statuses are classified, as before.
- [Real `401` body never captured] → The `401` message stays best-effort,
  as documented in `session.py` today. Tests use mocked responses.

## Migration Plan

No user action is needed. After deploy, an existing stale `session.json`
heals itself on the first call. Rollback is a plain revert, and the cache
format is unchanged in both directions.
