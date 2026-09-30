## 1. Tests first

- [x] 1.1 In `tests/test_config.py` add a test that `FORLABS_SESSION_TOKEN="${FORLABS_SESSION_TOKEN}"` with a JSON file holding `file-token` resolves to `file-token`; run `uv run pytest tests/test_config.py` and confirm it fails before the fix
- [x] 1.2 Add a test that an unexpanded placeholder in `FORLABS_SESSION_TOKEN` with no JSON file raises `ConfigError` with `key == "session_token"`
- [x] 1.3 Add a parametrized test that a placeholder in an optional variable (`FORLABS_BASE_URL`, `FORLABS_MAX_ITEMS`) yields the JSON value when present and the built-in default otherwise, including a composite value such as `https://${HOST}`
- [x] 1.4 Add a `caplog` test that the warning names the environment variable and that the skipped value (use a distinctive marker like `${SECRET-MARKER}`) does not appear in the captured log text

## 2. Implementation

- [x] 2.1 In `src/forlabs_mcp/config.py` add a module-level compiled regex for `\$\{[^}]*\}` and a module logger; in `load_config()`'s `resolve()` skip an env value that matches, logging a warning with the variable name only; verify with `uv run pytest tests/test_config.py` (all tests, old and new, pass)
- [x] 2.2 Update the module docstring / `load_config()` docstring precedence note to mention that unexpanded `${...}` env values count as unset; verify by reading the diff

## 3. Documentation

- [x] 3.1 In `README.md` "Альтернатива: JSON-файл в репозитории" state that with the JSON file the `env` block should be removed entirely rather than left empty or with a `${...}` placeholder, and that hosts which do not interpolate `${...}` pass it literally and the server ignores such values with a stderr warning; verify the wording matches spec behavior
- [x] 3.2 In the README "Настройки" section add one sentence that an env value containing an unexpanded `${...}` is treated as unset for every setting; verify the README stays free of real tokens and local paths

## 4. Final verification

- [x] 4.1 Run `uv run pytest` (includes the repo leak/privacy scan) and confirm the whole suite passes
- [x] 4.2 Run `openspec validate ignore-unexpanded-env-placeholders --strict` and confirm it passes
