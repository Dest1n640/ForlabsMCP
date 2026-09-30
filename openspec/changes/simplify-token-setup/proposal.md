## Why

Getting the server registered is more complicated than it needs to be: two
helper scripts (`setup_config.py`, `print_mcp_config.py`), a TOML config in
`~/.config`, and a README that explains three ways to provide the token.
The user only ever has to do one thing - paste their own session token.
The authentication switch to a remember-cookie (`session-token-auth`) also
left stale username/password wording behind in code comments, error
docstrings, tests and reference docs.

## What Changes

- **Remove the setup tooling**: delete `scripts/setup_config.py`,
  `scripts/print_mcp_config.py` and their tests (`test_setup_config.py`,
  `test_print_mcp_config.py`); drop the now-empty `scripts/` directory.
- **Remove the TOML config source** (`~/.config/forlabs-mcp/config.toml`,
  `FORLABS_MCP_CONFIG`, `tomllib` loading). **BREAKING** for anyone who
  saved a token via the wizard: they must move it to the env var or the
  new JSON file.
- **Add a repo-local JSON token file**: a committed template
  `forlabs-session.example.json` (`{"session_token": "PASTE_..."}`); the
  user copies it to `forlabs-session.json` (gitignored) and pastes their
  own token. The server reads it when `FORLABS_SESSION_TOKEN` is unset.
  Precedence becomes: env var > JSON file > built-in default.
- **Rewrite the README setup section**: one copy-paste JSON block in the
  standard `mcpServers` shape (`command`/`args`/`env`) that works for all
  MCP agents, with a single `FORLABS_SESSION_TOKEN` placeholder the user
  replaces; plus a short "or use the JSON file" alternative. Remove the
  script/TOML/per-host (Claude Desktop, Claude Code, Hermes) subsections.
- **Purge username/password traces**: `AuthError` docstring, the
  `username` strings in `tests/test_errors.py`, the misleading
  `_mock_login_success` helper name in tests, and stale login/re-auth
  wording in `PROJECT-REFERENCE.md` and code comments. Add a test that the
  client never issues `POST /app/login`.
- Add `forlabs-session.json` to `.gitignore`; extend the repo privacy test
  so a tracked file containing a real-looking token fails.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `forlabs-diary-tools`: the "Layered, validated configuration" requirement
  changes its sources (env var, then repo-local JSON file, then default;
  TOML removed), and a requirement is added that the token can be supplied
  through a gitignored JSON file with a committed placeholder template.

## Impact

- Code: `src/forlabs_mcp/config.py`, `src/forlabs_mcp/errors.py`,
  `src/forlabs_mcp/client/session.py` (comments only).
- Removed: `scripts/*`, `tests/test_setup_config.py`,
  `tests/test_print_mcp_config.py`.
- Tests: `tests/test_config.py` (JSON source replaces TOML),
  `tests/test_errors.py`, `tests/test_session.py`, `test_client.py`,
  `test_repository.py`, `test_tools_register.py` (renames),
  `tests/test_repo_privacy.py`.
- Docs/config: `README.md`, `PROJECT-REFERENCE.md`, `.gitignore`, new
  `forlabs-session.example.json`.
- No change to the read-only tools, the backend allow-list, or the
  session-cookie auth flow itself.
