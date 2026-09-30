## Why

Students on the Forlabs/Lamotivo school-diary SPA (`bki.forlabs.ru/app`) can only
read their schedule, grades, and homework by logging into the web app manually.
There is no way for an MCP-capable assistant to answer questions against a real
diary. This project (`forlabs-mcp`) rebuilds a local MCP server, from a fully
captured protocol reference (`PROJECT-REFERENCE.md`), that logs in as the
student and exposes that data as read-only MCP tools — no write path is ever
implemented, so there is no risk of the assistant modifying diary state.

## What Changes

- Add a Python MCP server (`forlabs-mcp`, stdio transport) with four read-only
  tools: `reference`, `schedule`, `grades`, `homework`.
- Add a session/auth layer (`client/session.py`) that performs the Forlabs
  login flow (XSRF-cookie priming, `X-XSRF-TOKEN` header, `forlabs_session`
  cookie), transparently re-authenticates once on session expiry, and persists
  the cookie jar to a `0600` local cache file.
- Add a repository RPC primitive (`client/repository.py`) that calls
  `POST /lm-vendor/repositories/<module>/<action>` and enforces a hardcoded
  read-only allow-list (`sched/get_grid`, `sched/get_schedule`,
  `learning/get_streams`, `learning/get_studies`, `learning/get_scores`,
  `learning/get_tasks`) — any other `(module, action)` pair is rejected before
  any HTTP request is made.
- Add tolerant parsing (`client/parsers.py`, `client/models.py`,
  `client/partial.py`) so a malformed or unexpected row becomes a warning
  string on the result rather than an exception that discards the rest of the
  response.
- Add calendar-math helpers (`dates.py`) that place the abstract `day`/
  `position` lesson slots from `sched/get_schedule` onto real calendar dates
  using `sched/get_grid`, under an explicitly stated ISO-week-parity
  assumption (the backend does not say which week is "week 0").
- Add a domain client (`client/client.py`) that joins studies to
  scores/tasks, resolves the account's "own stream" from
  `sched/get_schedule`'s `meta.stream_ids`, and returns the typed results the
  tools serve.
- Add a credential-free error taxonomy (`errors.py`) so no raw exception,
  stack trace, or credential ever reaches tool output.
- Add layered configuration (`config.py`): env var > TOML file > built-in
  default, for credentials, base URL, timeout, timezone, session cache path,
  and max list items.
- Add a fixture-based test suite (mocked HTTP via `respx`, no live network by
  default), a real-backend smoke test gated on credentials being present, and
  a repo-privacy guardrail test that scans git-tracked fixtures/docs for
  name-shaped or absolute-path leakage.
- Add `scripts/print_mcp_config.py`, a dependency-free generator that prints
  the `{command, args, env}` object any MCP host (Claude Desktop, Claude Code,
  Hermes Agent, etc.) needs to register the server, with credential fields
  always left as placeholders.

No **BREAKING** changes — this is the first implementation of the server.

## Capabilities

### New Capabilities
- `forlabs-diary-tools`: the four read-only MCP tools (`reference`,
  `schedule`, `grades`, `homework`) backed by the Forlabs/Lamotivo session,
  repository RPC allow-list, parsing, date-resolution, and error-taxonomy
  layers described above. One capability because all four tools share the
  same session/auth/config/error substrate and are meaningless without it.

### Modified Capabilities
(none — greenfield rebuild, no existing specs in this repo)

## Impact

- **New code**: `server.py`, `config.py`, `errors.py`, `dates.py`,
  `client/session.py`, `client/repository.py`, `client/models.py`,
  `client/parsers.py`, `client/partial.py`, `client/client.py`,
  `tools/register.py`, `scripts/print_mcp_config.py`.
- **New tests**: `tests/fixtures/*.json` (synthetic payloads), `respx`-mocked
  unit tests, an opt-in integration smoke test, `tests/test_repo_privacy.py`.
- **New runtime dependency**: an MCP server SDK (stdio transport), `httpx`,
  `pydantic`; dev dependency on `respx`, `pytest`, `ruff`.
- **External system**: reads from `https://bki.forlabs.ru` only (via the
  allow-listed repository actions); never writes to it.
- **Local filesystem**: writes one session-cookie cache file (mode `0600`) at
  `FORLABS_SESSION_PATH` (default `~/.local/state/forlabs-mcp/session.json`);
  reads optional config from `$FORLABS_MCP_CONFIG` or
  `~/.config/forlabs-mcp/config.toml`.
- **No impact** on any other project or repository — this is a new, standalone
  server with no consumers yet.
