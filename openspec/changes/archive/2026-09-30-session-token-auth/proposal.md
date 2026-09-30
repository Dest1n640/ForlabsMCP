## Why

Storing the student's Forlabs username and password in the MCP config
(TOML file or env vars) is the current authentication model. A single
long-lived cookie — Laravel's "remember me" cookie (`remember_lm_<hash>`,
set because the captured login POST sends `"remember": true`) — can be
pasted into the config instead, so the server never needs the account
password at all.

This was verified live against the real backend: a request carrying only
the `remember_lm_<hash>` cookie (no `forlabs_session`, just a freshly
primed `XSRF-TOKEN`) was accepted by `sched/get_schedule` and the server
transparently issued a fresh `forlabs_session` cookie in response. The
three cookies observed from a real login have very different lifetimes:
`XSRF-TOKEN` and `forlabs_session` expire in ~2.4 hours, while
`remember_lm_<hash>` is valid for ~5 years. Seeding from the long-lived
cookie means ordinary data calls keep working indefinitely with no
separate refresh mechanism needed - Laravel's own remember-me handling
does it as a side effect of a normal authenticated request.

## What Changes

- **BREAKING**: Remove `username`/`password` from `ForlabsConfig` and from
  every config source (`FORLABS_USERNAME`/`FORLABS_PASSWORD` env vars, the
  `username`/`password` TOML keys). Existing configs stop working and must
  be redone.
- Add a required `session_token` setting (env var `FORLABS_SESSION_TOKEN`,
  TOML key `session_token`), holding the raw `remember_lm_<hash>` cookie
  value the user copies out of their own logged-in browser session
  (Application/Storage tab in DevTools - it does not appear in
  `document.cookie` since it's `HttpOnly`, but DevTools' cookie list shows
  it regardless).
- `ForlabsSession` no longer POSTs `/app/login` with credentials. On
  startup it seeds its cookie jar with `config.session_token` under the
  `remember_lm_<hash>` cookie name (still layered with whatever
  `session.json` already has cached from a prior run). Ordinary
  authenticated requests then rely on Laravel's own remember-me handling
  to mint a fresh `forlabs_session`/`XSRF-TOKEN` pair as needed - no
  separate keep-alive mechanism is required, since this was confirmed to
  happen as a side effect of a normal data call.
- When a call still comes back `401`/`419` (meaning the `remember_lm`
  cookie itself has been rejected or has expired - not the short session,
  which renews on its own), raise `AuthError` telling the user to obtain a
  fresh `session_token` from their browser and update their config. There
  is no automatic recovery path once the configured long-lived cookie is
  dead - the previous password-based relogin safety net is gone, but given
  the ~5-year lifetime this is expected to be a rare event, not a routine
  one.
- Update `scripts/setup_config.py`'s interactive wizard to prompt for a
  pasted `remember_lm_<hash>` cookie value (with instructions for finding
  it in browser DevTools) instead of username/password.
- Update `scripts/print_mcp_config.py` to emit `FORLABS_SESSION_TOKEN` in
  generated MCP host configs instead of `FORLABS_USERNAME`/`FORLABS_PASSWORD`.
- Update `README.md` and `PROJECT-REFERENCE.md` to describe the new
  token-based auth model, the three cookies' measured lifetimes, and the
  no-recovery-on-expiry caveat.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `forlabs-diary-tools`: the "Session authentication", "Transparent
  re-authentication on session expiry", and "Layered, validated
  configuration" requirements change from username/password login to
  long-lived remember-cookie seeding, with a terminal error (no automatic
  recovery) if that cookie itself is ever rejected.

## Impact

- `src/forlabs_mcp/config.py` - drop `username`/`password`, add
  `session_token`; update validation and `redacted()`.
- `src/forlabs_mcp/client/session.py` - remove the credentialed
  `login()`/relogin-on-expiry flow; seed the `remember_lm_<hash>` cookie
  from `session_token`; change expiry handling to a terminal `AuthError`.
- `scripts/setup_config.py` - wizard prompt changes from
  username/password to the remember-cookie value.
- `scripts/print_mcp_config.py` - generated env block changes.
- `README.md`, `PROJECT-REFERENCE.md` - auth model documentation, including
  the measured cookie lifetimes.
- `tests/test_config.py`, `tests/test_session.py`,
  `tests/test_setup_config.py`, `tests/test_print_mcp_config.py` - rewritten
  for the new auth model.
- Existing deployed configs with username/password (**BREAKING**): every
  current user must re-run setup with a `session_token` before the server
  works again.
- **Security note**: a leaked `remember_lm_<hash>` value grants the same
  practical account access as a leaked password, for up to ~5 years - it
  is not inherently "safer" to store than a password, it just means this
  server itself never transmits or holds the raw password. Treat the
  config file and `session.json` with the same care as a password store.
