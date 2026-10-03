## Why

A few hours after its first successful run the server stops working and
never recovers on its own, even though the long-lived `session_token`
(`remember_lm_<hash>`) is still valid. The session cache stores the
short-lived `XSRF-TOKEN`/`forlabs_session` pair without its expiry. A
later run loads that dead pair and skips XSRF priming, and the backend
answers `419 CSRF token mismatch.` (confirmed live). The client treats
every `401`/`419` as "your session_token was rejected" and raises at once.
The cache is only rewritten after a success, so every later run fails the
same way. A single long-running process hits the same failure once its
in-memory short session outlives the backend's (~2.4 h).

## What Changes

- When an authenticated call gets a `401`/`419`, the session drops every
  cookie except the remember cookie (re-seeded from the configured
  `session_token`), primes a fresh `XSRF-TOKEN` via `GET /app/login`, and
  retries the same call **exactly once**. A successful retry returns
  normally and is persisted, which replaces the stale cache.
- `AuthError` is raised only when that single retry also fails.
- The `AuthError` message tells the two causes apart. A `401` says the
  `session_token` was rejected and must be replaced. A `419` says the
  backend refused the CSRF token even with a fresh session, and that
  replacing the token is not the fix.
- This **reverses** the "no retry on expiry" decision from
  `session-token-auth`. That decision assumed a `401`/`419` could only mean
  a dead remember cookie, and live testing proved otherwise.

Unchanged: the configuration surface, the no-password guarantee (no
`POST /app/login` is ever sent), the cache file format, and its `0600`
mode.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `forlabs-diary-tools`: "Terminal error on session-token expiry" now
  allows one session-reset retry before raising, and its message differs
  for a rejected token (`401`) and a persistent CSRF mismatch (`419`). A
  new requirement covers recovery from a stale short-lived session.

## Impact

- Code: `src/forlabs_mcp/client/session.py` (`ForlabsSession.request()`
  plus a new session-reset helper).
- Tests: `tests/test_session.py`, where the "without any retry" test is
  replaced, and `tests/test_tools_register.py`, where a persistent `419`
  must still surface as an authentication failure.
- Docs: `PROJECT-REFERENCE.md` §2.2a and the `client/session.py` row, which
  both say any `401`/`419` means the remember cookie is dead.
- Tools, configuration, and the persisted cache shape are untouched.
