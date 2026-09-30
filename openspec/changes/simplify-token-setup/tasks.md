## 1. Branch setup

- [x] 1.1 Create and check out branch `simplify-token-setup` off an
      up-to-date `main`; verify with `git branch --show-current`.

## 2. Remove setup tooling and TOML source

- [x] 2.1 Delete `scripts/setup_config.py`, `scripts/print_mcp_config.py`,
      `tests/test_setup_config.py`, `tests/test_print_mcp_config.py`;
      verify `scripts/` no longer exists and `uv run pytest` still collects
      without import errors.
- [x] 2.2 In `src/forlabs_mcp/config.py` remove `tomllib`,
      `_ENV_CONFIG_FILE`, `_DEFAULT_CONFIG_FILE`, `_config_file_path`,
      `_load_toml_table`; verify `grep -rni "toml" src` finds nothing
      (except none expected in `pyproject.toml` deps).

## 3. JSON token file

- [x] 3.1 Add `forlabs-session.example.json` with only
      `{"session_token": "PASTE_YOUR_remember_lm_COOKIE_VALUE_HERE"}` and
      add `forlabs-session.json` to `.gitignore`; verify
      `git check-ignore forlabs-session.json` prints the path and
      `git ls-files` lists only the example.
- [x] 3.2 Implement JSON loading in `config.py`: default path is
      `<repo root>/forlabs-session.json` (from the package location),
      overridable via `FORLABS_TOKEN_FILE`; precedence env > JSON >
      default; placeholder value treated as missing; invalid JSON or
      non-object raises `ConfigError` without echoing file contents.
      Verify with the tests in 3.3.
- [x] 3.3 Rewrite `tests/test_config.py`: env overrides JSON, JSON
      supplies token, leftover TOML ignored, placeholder rejected,
      malformed JSON gives `ConfigError` with no file content in the
      message, defaults still applied; verify `uv run pytest
      tests/test_config.py` passes.
- [x] 3.4 Extend `tests/test_repo_privacy.py`: tracked `*.json` files must
      have no `session_token` other than the placeholder; include a
      positive and a negative unit case; verify the test passes and fails
      on a synthetic bad input.

## 4. Purge username/password traces

- [x] 4.1 Fix `AuthError` docstring in `errors.py`, the `username` strings
      in `tests/test_errors.py`, and stale login wording in comments in
      `client/session.py`; verify
      `grep -rniE "username|password|re-auth" src tests` returns only the
      intentional "no password" assertions.
- [x] 4.2 Rename `_mock_login_success` to `_mock_xsrf_prime` in
      `test_client.py`, `test_repository.py`, `test_tools_register.py`;
      verify `uv run pytest` passes.
- [x] 4.3 Add a test in `tests/test_session.py` that runs a cold-start
      authenticated call and asserts no `POST` to `/app/login` was made;
      verify it passes.

## 5. Docs

- [x] 5.1 Rewrite the README configuration/registration sections: one
      `mcpServers` JSON block with a single token placeholder, the
      JSON-file alternative, a short "Upgrading from the TOML/wizard
      setup" note; remove script/TOML/per-host subsections; verify no
      references to `scripts/` or `config.toml` remain (`grep`).
- [x] 5.2 Update `PROJECT-REFERENCE.md`: section 7 precedence and file
      description, section 8 `AuthError` row, section 4 architecture rows
      (session, config), section 10 (replace generator-script text with
      the README JSON approach), section 2.1 session wording; verify no
      "form login", "re-auth-once" or `scripts/` mentions remain.

## 6. Verification and delivery

- [x] 6.1 Run `uv run pytest`, `uv run ruff check .`,
      `uv run ruff format --check .`; verify all pass.
- [x] 6.2 Manually verify: copy the example to `forlabs-session.json`
      with a dummy token, confirm `git status` stays clean, and confirm
      the server starts past config validation.
- [x] 6.3 Open a PR from `simplify-token-setup` to `main` and merge it
      (per the project's per-stage auto-PR/merge convention); verify
      `git log main` shows the merge.
