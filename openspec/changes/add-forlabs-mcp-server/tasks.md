## 1. Project scaffolding

- [x] 1.1 Initialize the Python package (`pyproject.toml` with the
  `forlabs-mcp` project name and entry point, `src/` layout matching the
  module table in `design.md` - Decisions) and verify `uv sync` (or
  equivalent) installs cleanly
- [x] 1.2 Add runtime dependencies (an MCP server SDK for stdio transport,
  `httpx`, `pydantic`) and dev dependencies (`pytest`, `respx`, `ruff`) and
  verify `uv run ruff check .` runs with zero findings on the empty
  scaffold
- [x] 1.3 Create `tests/fixtures/` and copy the five synthetic JSON payloads
  from `PROJECT-REFERENCE.md` §3 (`sched/get_grid`, `sched/get_schedule`,
  `learning/get_scores`, `learning/get_studies`, `learning/get_tasks` — the
  latter includes its `assignments[]` array, which is part of the same
  response, not a separate fixture) and verify each file is valid JSON
  (`python -m json.tool <file>`)

## 2. Configuration and error taxonomy

- [x] 2.1 Implement `config.py` (`ForlabsConfig` dataclass, `load_config()`
  with env var > TOML file > default precedence per reference §7,
  `redacted()` for safe logging) and verify unit tests cover: env override
  of TOML, missing-credential failure, and that `redacted()` never contains
  the password (spec: Layered, validated configuration)
- [x] 2.2 Implement `errors.py` (`ForlabsError` base and the eight
  subclasses in reference §8: `ConfigError`, `InvalidArgumentError`,
  `AuthError`, `ConnectivityError`, `TimeoutError`, `RateLimitError`,
  `UpstreamError`, `ProgrammingError`) with `to_tool_error()` mapping each to
  a classified, single-line, credential-free message, and verify unit tests
  cover an unrecognized exception collapsing to a generic message (spec:
  Credential-free, classified error surface)
- [x] 2.3 Implement `client/partial.py` (`PartialResult[T]`: `data` +
  `warnings` + `is_partial`) and verify unit tests cover constructing a
  result from mixed successful/failed rows

## 3. Session and repository layer

- [x] 3.1 Implement `client/session.py` (`ForlabsSession`: one `httpx.Client`,
  `GET /app/login` to prime the `XSRF-TOKEN` cookie, `POST /app/login` with
  the URL-decoded token in `X-XSRF-TOKEN`, cookie jar persisted to
  `session_path` at mode `0600`) and verify `respx`-mocked tests cover
  successful login and a rejected-credentials `422` mapping to `AuthError`
  without the password appearing in the exception message (spec: Session
  authentication, Local session cache confidentiality)
- [x] 3.2 Add transparent re-auth-once behavior to `ForlabsSession` and
  verify a `respx`-mocked test covers: first data call fails as expired,
  session re-logs in, retried call succeeds; and a second test covers
  re-auth itself failing and surfacing `AuthError` (spec: Transparent
  re-authentication on session expiry)
- [x] 3.3 Implement `client/repository.py` (`Repository.call(module, action,
  params)` posting to `/lm-vendor/repositories/<module>/<action>`, checking
  the six-action allow-list from reference §2.4 before constructing any
  request, raising `UpstreamError` for a non-2xx status or a body shaped
  like `{"message": ...}` with no other keys) and verify unit tests cover:
  a non-allow-listed action raises `ProgrammingError` with zero HTTP calls
  made (assert via the `respx` mock router seeing no requests), and each
  error-shaped response maps to `UpstreamError` (spec: Backend action
  allow-list)

## 4. Models, parsing, and date resolution

- [x] 4.1 Implement `client/models.py` (pydantic models with `extra="ignore"`
  for `Stream`, `Study`, `ScheduleGrid`, `Lesson`, `Score`, `Task`,
  `TaskFile`, `Assignment`, `Identity`, using the backend-key mapping in
  reference §5) and verify a unit test constructs each model from its
  fixture and asserts an unexpected extra field does not raise
- [x] 4.2 Implement `client/parsers.py` (tolerant `payload -> model`
  functions returning `PartialResult`) and verify a unit test feeds one
  malformed row alongside valid rows from a fixture and asserts the
  malformed row becomes a warning while valid rows are still returned
  (spec: Partial results on malformed data)
- [x] 4.3 Implement `dates.py` (`resolve_range()` for `YYYY-MM-DD` parsing,
  inclusive ranges, and the current-ISO-week default; `resolve_lessons()`
  placing `day`/`position` entries onto calendar dates via the grid, and
  computing `week_parity_basis = (ISO week number - 1) % week_variants`)
  and verify unit tests cover: default range is Mon-Sun of the current ISO
  week, a lesson's `day`/`position` maps to the correct weekday/clock-time
  from the `sched/get_grid` fixture, and `week_parity_basis` is present in
  the computed result (spec: `schedule` tool)

## 5. Domain client

- [x] 5.1 Implement `client/client.py` `reference()` (discovers own stream
  from `sched/get_schedule`'s `meta.stream_ids`, returns identity
  placeholder + streams + full `learning/get_studies` history) and verify a
  `respx`-mocked test using the fixtures asserts `identity ==
  {"name": null, "role": null}` and the own stream is flagged (spec:
  `reference` tool)
- [x] 5.2 Implement `client/client.py` `scores()` (joins `learning/get_scores`
  to `learning/get_studies` by `study_id`, applies the
  `SCORE_STATUS_LABELS = {1: "in progress", 2: "in progress", 5:
  "completed"}` map, degrades an unresolved `study_id` to id + name-not-found
  note, adds a "no grades found" note on empty results) and verify unit
  tests cover a resolved score, an unresolved `study_id`, and an empty-result
  note (spec: `grades` tool)
- [x] 5.3 Implement `client/client.py` `homework()` (loops
  `learning/get_tasks` per study when `study_id` is omitted, passing
  `stream_id`/`study_id` as strings per reference §3, unions results,
  converts one study's failure into a warning via `PartialResult`, derives
  `is_done` from `HOMEWORK_DONE_STATUSES = {3}`, applies `only_outstanding`)
  and verify unit tests cover: multi-study union, one failing study
  producing a warning without failing the call, and `only_outstanding`
  filtering (spec: `homework` tool)
- [x] 5.4 Implement `client/client.py` `schedule_raw()` (fetches grid +
  schedule, validates `date` is mutually exclusive with `start`/`end` before
  any backend call, delegates placement to `dates.py`, adds a "no lessons"
  note on empty results) and verify unit tests cover the mutual-exclusion
  rejection making zero backend calls, and an empty-range note (spec:
  `schedule` tool)

## 6. MCP tool registration and server entry point

- [x] 6.1 Implement `tools/register.py` registering the four tools
  (`reference`, `grades`, `homework`, `schedule`) with the JSON output
  shapes in reference §6, validating arguments before calling the client,
  and converting any `ForlabsError` to `to_tool_error()`'s classified
  message, and verify an integration-style test (mocked HTTP, real tool
  dispatch) calls each of the four tools once and asserts the top-level
  response keys match reference §6 (spec: Read-only tool surface, all four
  tool-contract requirements)
- [x] 6.2 Implement `server.py` (CLI entry point `forlabs-mcp`, builds the
  MCP server with a lazily-created `ForlabsClient` via a client factory, runs
  stdio transport) and verify `uv run forlabs-mcp --help` (or the
  equivalent no-network smoke invocation) starts without requiring a live
  backend connection at import time

## 7. Registration tooling and docs

- [x] 7.1 Implement `scripts/print_mcp_config.py` (resolves its own repo
  path at runtime, prints the `{command, args, env}` object with credential
  fields always left as placeholders) and verify running it from a
  different working directory still prints a correct absolute
  `--directory` and never embeds the real `FORLABS_USERNAME`/
  `FORLABS_PASSWORD` values even when they are set in the environment
  (spec: Portable MCP client registration)
- [x] 7.2 Write `README.md` covering setup, configuration precedence, and
  how to hand `scripts/print_mcp_config.py`'s output to Claude Desktop,
  Claude Code (`claude mcp add-json`), and Hermes Agent, and verify the
  documented commands are copy-pasteable (no unresolved placeholders beyond
  the intentional credential fields)

## 8. Privacy guardrail and full test suite

- [x] 8.1 Implement `tests/test_repo_privacy.py` scanning `git ls-files`
  output for `tests/fixtures/*.json` and `docs/*.md` against a Title-Case-
  Cyrillic name-shaped regex (excluding a maintained synthetic-name
  allow-list) and absolute `/Users/<name>` or `/home/<name>` paths, and
  verify it passes against the current tracked fixtures and fails when a
  temporary test file with a real-looking name is added to the allow-list
  check (removed after verifying the failure path)
- [ ] 8.2 Run the full suite and verify `uv run pytest` passes with zero
  live network calls (no `FORLABS_USERNAME`/`FORLABS_PASSWORD` set in the
  test environment)
- [ ] 8.3 Verify `uv run ruff check .` and `uv run ruff format --check .`
  both pass with zero findings across the full implementation
