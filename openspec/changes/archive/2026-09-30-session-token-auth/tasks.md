## 1. Branch setup

- [x] 1.1 Create and check out a dedicated feature branch (e.g.
      `session-token-auth`) off `main` before making any change; verify
      with `git branch --show-current`. Do **not** open or merge a PR for
      this change when implementation finishes — leave the branch as-is
      for manual review, per explicit instruction for this change.

## 2. Configuration (`src/forlabs_mcp/config.py`)

- [x] 2.1 Replace `username`/`password` fields on `ForlabsConfig` with a
      single `session_token: str` field; verify the dataclass no longer
      references `username`/`password` anywhere in the module.
- [x] 2.2 Replace `_ENV_USERNAME`/`_ENV_PASSWORD` with
      `_ENV_SESSION_TOKEN = "FORLABS_SESSION_TOKEN"` and the TOML key from
      `username`/`password` to `session_token`; update `load_config()`'s
      resolution and required-setting check accordingly; verify
      `ConfigError` is raised with `key="session_token"` when it is absent
      from every source.
- [x] 2.3 Update `redacted()` to mask `session_token` instead of
      `password`; verify the masked dict never contains the raw token
      value.

## 3. Session/auth client (`src/forlabs_mcp/client/session.py`)

- [x] 3.1 Remove the credentialed `login()` method and its `_LOGIN_PATH`
      POST; verify no code path in the module submits `username`/
      `password` to the backend.
- [x] 3.2 In `__init__`, after `_load_persisted_session()`, seed the
      cookie jar's `remember_lm_<hash>`-named cookie from
      `config.session_token` for any cookie name not already restored
      from the session cache (domain-qualified `cookies.set()`, matching
      the existing pattern in `_load_persisted_session`); the exact
      `remember_lm_<hash>` name is a fixed constant for this deployment
      (capture it once, e.g. as a module-level constant, from the live
      test rather than re-deriving it per call); set `_authenticated =
      True` once that cookie is present from either source; verify with a
      unit test that a config-only token (no cache file) yields
      `is_authenticated is True` without any HTTP call.
- [x] 3.3 Replace the relogin-and-retry-once branch in `request()` with an
      immediate `AuthError` on a `401`/`419` response that tells the user
      to supply a fresh `session_token`; verify via unit test that no
      second request is made after an expiry-classified status, and that
      an ordinary data call made with only the remember cookie present
      still succeeds without hitting this branch at all (mocked
      `Set-Cookie` response establishing a fresh `forlabs_session`).
- [x] 3.4 Update `ensure_authenticated()` (or remove it if seeding in
      `__init__` makes it redundant) so it never calls the removed
      `login()`; verify no remaining reference to `login()` exists in the
      module or its tests.

## 4. Setup wizard (`scripts/setup_config.py`)

- [x] 4.1 Replace the username/password prompts with a single
      session-token prompt, including inline instructions for finding the
      `remember_lm_<hash>` cookie's value in browser DevTools
      (Application/Storage tab - it is `HttpOnly` so it will not appear
      via `document.cookie` in the Console); verify the wizard writes
      `session_token` (not `username`/`password`) to the generated TOML.
- [x] 4.2 Verify existing "credentials already saved" detection (see
      `9b2a8e9`) is updated to check for `session_token` instead of
      `username`/`password`.

## 5. MCP config generator (`scripts/print_mcp_config.py`)

- [x] 5.1 Replace the `FORLABS_USERNAME`/`FORLABS_PASSWORD` entries in the
      generated `env` block with `FORLABS_SESSION_TOKEN`; verify the
      placeholder value never contains a real token, matching the
      existing "no real credentials in generated config" guarantee.

## 6. Tests

- [x] 6.1 Update `tests/test_config.py` for the `session_token` field:
      env/TOML precedence, missing-setting error, redaction; verify
      `pytest tests/test_config.py` passes.
- [x] 6.2 Update `tests/test_session.py`: remove login-flow tests, add
      tests for config-seeded authentication (remember cookie only ->
      `is_authenticated is True`), a data call renewing the short session
      transparently (mocked `Set-Cookie` for `forlabs_session` on a
      successful response), and terminal `AuthError` on expiry without
      retry; verify `pytest tests/test_session.py` passes.
- [x] 6.3 Update `tests/test_setup_config.py` for the session-token prompt
      and TOML output; verify `pytest tests/test_setup_config.py` passes.
- [x] 6.4 Update `tests/test_print_mcp_config.py` for the
      `FORLABS_SESSION_TOKEN` env entry; verify
      `pytest tests/test_print_mcp_config.py` passes.
- [x] 6.5 Run the full suite with zero live network calls and confirm it
      is still clean: `pytest` (repo convention per `c388c9a`).

## 7. Documentation

- [x] 7.1 Update `PROJECT-REFERENCE.md` §2.1-2.2 and the config section to
      describe session-token authentication: the three cookies' measured
      lifetimes (`XSRF-TOKEN`/`forlabs_session` ~2.4h, `remember_lm_<hash>`
      ~5 years), and that ordinary data calls renew the short session
      transparently via the remember cookie (confirmed live, no longer
      "unconfirmed best-effort").
- [x] 7.2 Update `README.md`'s setup instructions to match the new wizard
      flow and config keys.

## 8. Final verification

- [x] 8.1 Run `ruff check` and `ruff format --check` and confirm both are
      clean (repo convention per `ef6c6de`).
- [x] 8.2 Grep the diff for any remaining `username`/`password` reference
      outside of historical/archived text (`git grep -n
      "FORLABS_USERNAME\|FORLABS_PASSWORD"`) and confirm none remain in
      `src/`, `scripts/`, or active tests.
