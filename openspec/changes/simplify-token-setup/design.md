## Context

Today the token can come from `FORLABS_SESSION_TOKEN` or from a TOML file
written by `scripts/setup_config.py`; `scripts/print_mcp_config.py`
generates per-host registration snippets (see `config.py`, `README.md`,
PROJECT-REFERENCE.md sections 7 and 10). Registration is always
`uv --directory <repo> run forlabs-mcp`, so the server process starts with
the repo as its working directory. Scope and motivation: see proposal.md.

## Goals / Non-Goals

**Goals:**
- One copy-paste JSON in the README that works for any MCP agent; the user
  only replaces the token placeholder.
- A second, equally simple option: a JSON file in the repo the user fills
  in, safe against accidental commits.
- Zero remaining username/password wording or dead helper code.

**Non-Goals:**
- No change to tools, the read-only allow-list, or cookie auth mechanics.
- No new CLI, wizard or migration script for old TOML users.
- No handling of token expiry beyond the existing `AuthError`.

## Decisions

**1. Token file location: `forlabs-session.json` at the repo root,
resolved from the package location, not from the process cwd.**
`Path(__file__).resolve().parents[2]` works for the editable `uv` install
and does not depend on how the host sets cwd. Alternative: cwd-relative -
simpler but breaks in hosts that ignore `--directory`. An optional
`FORLABS_TOKEN_FILE` env var overrides the path (also what tests use);
it replaces the removed `FORLABS_MCP_CONFIG`.

**2. Template + gitignore, not a single committed file.** Committing
`forlabs-session.example.json` and ignoring `forlabs-session.json` makes
"edit the file" safe: a real token never shows up in `git status`. A
single tracked file would invite accidental commits (see the privacy
lessons in PROJECT-REFERENCE.md section 12).

**3. Placeholder = missing.** If the file's `session_token` equals the
placeholder string (`PASTE_YOUR_remember_lm_COOKIE_VALUE_HERE`), config
treats it as absent so a user who copied the template but forgot to edit
gets the normal "Missing required setting" error instead of a confusing
backend 401/419.

**4. Same flat keys in JSON as before in TOML.** The JSON file accepts
`session_token` plus the optional overrides (`base_url`, `timeout_seconds`,
`timezone`, `session_path`, `max_items`); env still wins. `tomllib` and
the `[forlabs]` table handling are deleted. Alternative: JSON file holds
only the token - fewer moving parts, but drops optional overrides that
were previously file-configurable; the shared `resolve()` helper makes
keeping them free.

**5. README shape.** A single `mcpServers`-form block
(`command` / `args` / `env.FORLABS_SESSION_TOKEN`) is the primary path,
with a one-line note that hosts using another wrapper (Claude Code's
`add-json`, YAML hosts) take the same three fields. No per-host
subsections, no scripts. The `--directory` value stays a
`<absolute-path-to-this-repo>` placeholder; JSON has no way to
self-resolve it.

**6. Trace purge is mechanical.** Change stale wording only (docstrings,
test strings, `_mock_login_success` -> `_mock_xsrf_prime`, reference-doc
architecture rows). `_XSRF_PRIME_PATH = "/app/login"` stays: it is a GET
that primes the XSRF cookie, not a login. A new test asserts no request in
a full session flow uses `POST` to `/app/login`.

## Risks / Trade-offs

- [Users with a saved TOML lose their token silently] -> Startup error
  already names the missing `session_token`; README states the change
  under a short "Upgrading" note.
- [Placeholder value accidentally matches a real token] -> Impossible in
  practice; placeholder contains non-cookie characters.
- [Privacy check only sees tracked files] -> Intentional; the gitignore
  entry covers the untracked user file. The check scans tracked `*.json`
  for a non-placeholder `session_token`.
- [MODIFIED delta targets a requirement not yet in `openspec/specs/`]
  Earlier changes (`add-forlabs-mcp-server`, `session-token-auth`) were
  never archived, so main specs are empty. -> Archive/sync them first,
  in order, before archiving this one.
