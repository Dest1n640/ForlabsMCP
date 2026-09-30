## Context

`PROJECT-REFERENCE.md` in the repo root is a full protocol capture for the
Forlabs/Lamotivo backend (login flow, XSRF handling, the six read-only
repository actions, exact request/response JSON, a backend-key-to-model-field
map, and the four tool contracts) written specifically so this server could
be rebuilt without recapturing any live traffic. This design translates that
reference into a module layout; see `proposal.md` - Why/What Changes for
motivation and scope, and `specs/forlabs-diary-tools/spec.md` for the
externally observable behavior each module must satisfy.

Key external constraints, all already reverse-engineered in the reference
doc (§2-3):
- Laravel + AngularJS backend: CSRF via cookie-echoed `X-XSRF-TOKEN` header,
  session via `forlabs_session` cookie, login is `POST /app/login`.
- Every data call is `POST /lm-vendor/repositories/<module>/<action>`,
  success body is the payload directly (no envelope); a Laravel error can
  come back as `200 {"message": "..."}` with no other keys, or a non-2xx
  status.
- Two endpoints (`sched/get_schedule`, `learning/get_tasks`) require
  different parameter types (implicit `{}` vs explicit `stream_id`; the
  latter takes `stream_id`/`study_id` as **strings**), which the repository
  layer must not paper over incorrectly.
- No identity endpoint exists at all — `reference`'s `identity` field is
  permanently `{name: null, role: null}` by design, not a gap to fill later.
- Which calendar week is "week 0" vs "week 1" in the alternating-week grid is
  not stated by the backend anywhere; any date placement is provisional and
  must say so in its own output.

## Goals / Non-Goals

**Goals:**
- Mirror the reference doc's architecture layering exactly (§4), since it is
  already a clean separation and was designed by working backward from the
  MCP tool contracts.
- Keep every write-shaped backend action structurally unreachable, not just
  undocumented — enforced once, in the repository layer, ahead of every
  caller.
- Make partial/degraded results (a bad row, one failed per-study call) the
  normal path, not an exceptional one, since the four tools are read
  aggregations over several backend calls that can each independently fail.

**Non-Goals:**
- Building any write/mutation tool (posting comments, assessments,
  attendance) — explicitly out of scope per the reference doc's allow-list
  policy (§2.4), not deferred, forbidden.
- Implementing the five backlog endpoints in reference §11
  (`get_chapters`, `get_attendance`, `get_scoring`, `get_score`,
  `webinars/get_webinars`) — no payload has been captured for any of them,
  so nothing here can specify their shape. Tracked separately as the
  `forlabs-endpoint-backlog` change.
- Supporting any role other than student (the reference capture, login
  flow, and every fixture are all student-scoped).
- Multi-tenant / multi-account operation — one configured account per server
  process, matching the single-session design in reference §2.1/§7.

## Decisions

**Layering mirrors the reference doc's module table (§4) exactly**, rather
than collapsing it: `server.py` → `tools/register.py` → `client/client.py`
(domain layer) → `dates.py` + `client/parsers.py` → `client/models.py` →
`client/repository.py` → `client/session.py` → the network. Each layer has
exactly one reason to change (transport framing, tool-arg shaping, cross-
endpoint joins, calendar math / tolerant parsing, typed shape, allow-list
enforcement, auth/session). Alternative considered: a single flat
`ForlabsClient` doing HTTP + auth + parsing + joins inline — rejected because
the allow-list check and the credential-free error mapping both need to be
un-bypassable choke points, which requires them to be the *only* path to the
network, i.e. their own module.

**The allow-list lives in `client/repository.py`, checked before any HTTP
call is constructed**, not as a decorator on individual call sites and not
enforced only at the tool layer. Rationale: `tools/register.py` shapes
arguments per MCP tool, but `client/client.py` may need to make several
repository calls per tool (e.g. `homework` loops `get_tasks` per study) —
putting the check anywhere above `Repository.call()` means a future call site
could forget it. A single primitive that every caller must go through is the
only way "reject before any HTTP request" (spec requirement) is structurally
guaranteed rather than convention.

**Partial results are a first-class return type (`PartialResult[T]` in
`client/partial.py`: `data` + `warnings` + `is_partial`), not exceptions
with attached context.** Alternative considered: raise a custom
`PartialFailure` exception carrying the successful subset — rejected because
every caller up the stack (parsers → client → tools) would need a
try/except around otherwise-successful work, whereas a value type composes
naturally when `homework()` unions per-study results and needs to merge
both data and warnings from N calls.

**Tolerant parsing uses `pydantic` models with `extra="ignore"`**, per the
reference doc's explicit note (§5) that "a new backend field never breaks
parsing." Alternative considered: hand-rolled `TypedDict` + manual
validation — rejected as more code for the same guarantee, and pydantic's
per-field validation errors map directly to "this row becomes a warning"
without a custom validator loop.

**Date placement (`dates.py`) states its week-parity assumption in every
result rather than trying to resolve it.** The reference doc is explicit
that the backend does not expose which calendar week is "week 0" (§2.3) —
guessing silently would produce schedules that are occasionally off-by-one-
week with no signal to the user. `resolve_lessons()` computes a basis
(`(ISO week number - 1) % week_variants`) and the `schedule` tool always
returns it as `week_parity_basis`, satisfying the spec's disclosure
requirement without pretending to solve an unsolvable ambiguity.

**Session cookies persist to a `0600` local file (`FORLABS_SESSION_PATH`),
re-auth is retried exactly once per call, not with backoff/retry loops.**
One retry matches the actual failure mode (session expired since last
persisted) — anything beyond one retry would mean credentials are actually
wrong, which is an `AuthError`, not a transient condition worth retrying.

**Errors are classified into a closed taxonomy (`errors.py`) mapped by a
single `to_tool_error()` boundary function**, rather than letting
tools/register.py catch and format exceptions ad hoc per tool. This is the
only way to guarantee the spec's "no raw exception or stack trace reaches
tool output" requirement across four tools without four separate,
divergent try/except blocks.

**Configuration precedence (env var > TOML > default) is resolved once at
startup by `config.py`, not read lazily per setting.** Keeps validation
("required credential missing → fail before any network call") a single
check at one call site (`load_config()`) instead of scattered guards.

**MCP client registration is a standalone generator script
(`scripts/print_mcp_config.py`), not documentation snippets per host.**
Every MCP host wants the same `{command, args, env}` shape; resolving the
repo's own absolute path at runtime and always emitting placeholder
credential fields means a new, previously undocumented host needs zero
project changes to register against — it just needs to accept that shape.

## Risks / Trade-offs

- **[Risk] The backend can change its response shape or add a repository
  action with no warning.** → Mitigation: `extra="ignore"` models absorb new
  fields; the allow-list is a manual edit for new actions by design (never
  auto-expanded from observed traffic), so a new write-shaped action can
  never silently become callable.
- **[Risk] The week-parity assumption in `dates.py` could be wrong for some
  accounts/semesters (no backend ground truth exists to verify it).** →
  Mitigation: every `schedule` result states the assumption explicitly
  (`week_parity_basis`) so a wrong placement is visible and correctable by
  the user, rather than silently trusted.
- **[Risk] Session cookie cache file on disk is a standing credential-
  adjacent artifact.** → Mitigation: mode `0600`, no raw password ever
  written to it, and it is regenerated transparently on expiry rather than
  needing manual deletion.
- **[Trade-off] One retry-once re-auth policy, no configurable retry/backoff.**
  Simpler and matches the real failure mode (§ Decisions), but a genuinely
  flaky network during the retry window surfaces as a `ConnectivityError`
  or `AuthError` rather than eventually succeeding — acceptable for a local,
  interactively-invoked MCP tool rather than a background service.
- **[Trade-off] `homework` without `study_id` makes one `get_tasks` call per
  study in the stream (reference §3 confirms this is not batchable).** For a
  student with a long enrolment history this is O(n) backend calls per tool
  invocation; acceptable given typical enrolment sizes (a handful of studies
  per semester) and because a per-study failure only produces a warning, not
  a total failure.

## Migration Plan

Greenfield addition — no existing deployment, data, or consumers to migrate.
Sequencing: config → errors/partial-result vocabulary → session → repository
(allow-list) → models/parsers → dates → client → tools → server entry point,
mirroring the dependency direction in `proposal.md` - Impact. Tests
(fixture-backed unit tests first, then the opt-in integration smoke test,
then the repo-privacy guardrail) land alongside each layer rather than at
the end, per reference §9's testing approach. No rollback concerns beyond
reverting the change, since nothing external depends on this server yet.
