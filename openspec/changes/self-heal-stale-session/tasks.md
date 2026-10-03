## 1. Tests first (red)

- [x] 1.1 In `tests/test_session.py`, replace `test_expired_session_token_raises_auth_error_without_any_retry` with a test where the data route always returns `401`. Assert `AuthError`, exactly 2 data calls, a message asking for a fresh `session_token`, and zero `POST /app/login` requests. Verify that it fails against the current code.
- [x] 1.2 Add a test where the data route always returns `419`. Assert `AuthError` after exactly 2 data calls, with a message about the CSRF rejection that does not tell the user to replace the token. Verify that it fails against the current code.
- [x] 1.3 Add a stale-cache recovery test. Write a `session.json` holding remember, `XSRF-TOKEN=old` and `forlabs_session=old`. The data route returns `419` once, then `200` with a fresh `forlabs_session`. Assert a `200` response, one priming `GET /app/login`, the retried request carrying the new `X-XSRF-TOKEN` and no `forlabs_session=old`, and a rewritten `session.json` without the old values. Verify that it fails against the current code.
- [x] 1.4 Add an in-process test: a successful call, then `401` once, then `200`. Assert the second `request()` returns `200` with no error. Verify that it fails against the current code.
- [x] 1.5 Add a test where the cached remember value differs from `config.session_token`. After a `419`, the retried request must carry the configured value. Verify that it fails against the current code.
- [x] 1.6 Add a test that a `500` (not auth-classified) gets no retry, meaning exactly 1 data call. Verify that it passes on both the old and the new code.

## 2. Implementation (green)

- [x] 2.1 In `src/forlabs_mcp/client/session.py`, add `_reset_session()`. It clears the cookie jar and re-seeds `REMEMBER_COOKIE_NAME` from `config.session_token` under the base URL's host. Verify with test 1.5.
- [x] 2.2 Change `request()`: on a `401`/`419`, call `_reset_session()` and resend through `_authenticated_send()` exactly once, which primes XSRF because the cookie is now missing. Persist only after a non-auth response. Verify that tests 1.3, 1.4 and 1.6 pass.
- [x] 2.3 Pick the `AuthError` message from the retry's status: `401` asks for a fresh `session_token`, `419` reports a CSRF rejection. Neither includes the token value. Verify that tests 1.1 and 1.2 and `test_auth_error_never_leaks_the_configured_token_value` pass.
- [x] 2.4 Update the module docstring and the `_SESSION_EXPIRED_STATUSES` comment so they describe the reset-and-retry-once behavior, and verify by reading the diff.

## 3. Docs and full check

- [x] 3.1 Update `PROJECT-REFERENCE.md` §2.2a (the "If a call ever comes back `401`/`419`" paragraph) and the `client/session.py` row in the module table to describe the one-retry recovery and the two error causes. Verify that `grep -n "401" PROJECT-REFERENCE.md` no longer claims a single `401`/`419` means a dead token.
- [x] 3.2 Run `uv run pytest` and `uv run ruff check .` and verify the whole suite passes, including the unchanged persistent-`419` test in `tests/test_tools_register.py`.
- [x] 3.3 Run a live check without touching the real cache: copy the stale `~/.local/state/forlabs-mcp/session.json` into the scratchpad, point `FORLABS_SESSION_PATH` at the copy, and make one `schedule` call. Verify that it returns data and that the copy is rewritten.
