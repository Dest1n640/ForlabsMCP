## Context

See `proposal.md` - Why for motivation. Relevant existing constraints (from
`PROJECT-REFERENCE.md`):

- Every backend call funnels through one primitive, `Repository.call(module,
  action, params)`, which checks `(module, action)` against a hardcoded
  `READ_ONLY_ACTIONS` allow-list *before* any HTTP request and raises
  `ProgrammingError` otherwise. This is the mechanism that makes "read-only"
  an architectural guarantee rather than a convention.
- No exam endpoint has ever been captured. `PROJECT-REFERENCE.md` §3 (full
  request/response reference) and §11 (capture backlog) don't mention exams
  at all — the only public state we have is the DevTools screenshot data:
  an "Экзамены" tab per study, entries like "Тест № 1 / 15 вопросов / 30
  минут / Сдан / 5.00 из 5.00 / 2 попытки", and an (uncaptured) SPA route
  `/app/learning/<stream_id>/studies/<study_id>/exams`.
- The existing four tools' error taxonomy (`errors.py`, `ForlabsError` →
  `to_tool_error()`) and config precedence (env > TOML > default,
  `config.py`) are the substrate this change extends, not replaces.

## Goals / Non-Goals

**Goals:**
- Let an MCP host's own model read a training exam's questions and submit
  its answers, entirely through MCP tool calls (no embedded/external LLM
  call inside `forlabs-mcp` itself).
- Keep the exam-write path structurally separate from, and off by default
  relative to, the existing read-only guarantee — flipping one config value
  back to false must restore today's exact behavior.
- Leave room to upgrade the "training-only" boundary from documentation to
  server-side enforcement once capture shows whether the backend exposes
  a checkable flag for it.

**Non-Goals:**
- Supporting graded/high-stakes exams, or any exam the operator has not
  personally attested is ungraded self-check content.
- Supporting free-text/essay question types — this change assumes
  fixed-option (single- or multi-select) questions, consistent with the
  screenshot data; if capture shows free-text questions exist, that's a
  follow-up change.
- Any LLM call, prompting, or "solving" logic living inside `forlabs-mcp` —
  the server only ever proxies questions out and answers in.
- Changing `READ_ONLY_ACTIONS`, or any of the four existing tools' behavior,
  in any way.

## Decisions

**Two tools for read (questions) vs. write (submit), not one combined tool.**
Mirrors the project's existing read/write separation and lets the opt-in
gate apply to exactly the write half. Alternative considered: a single
`take_exam(...)` tool that both fetches and submits in one call — rejected
because it would force the gate to cover the read path too (defeating "read
stays available even when writes are off" as a debugging/inspection aid) and
because MCP hosts naturally want to see the questions before choosing to
call a second tool with answers.

**Solving intelligence lives entirely in the MCP host's model.** The server
never calls out to any LLM API itself. Alternative considered: have
`forlabs-mcp` call an LLM API server-side to generate answers automatically
so the host only needs to invoke one tool — rejected because it adds a
second AI-provider dependency, its own API key/config surface, and a cost
model unrelated to this project's scope; the calling assistant already *is*
an LLM with access to this server's other read tools (`homework`,
`reference`) for course context if it needs them.

**A second allow-list, `EXAM_WRITE_ACTIONS`, gated by a startup-time config
flag (`FORLABS_ENABLE_EXAM_AUTOSOLVE`, default `false`), not a per-call
argument.** Gating at server startup means the read-only guarantee for a
default deployment is provable by inspecting config, the same way
`session_token` already is; it also means the flag-off state is trivially
testable by asserting the tools aren't even registered. Alternative
considered: a `confirm: bool` argument on `submit_exam_answers` itself —
rejected because a calling model can pass `true` every time with no real
friction, so it provides no meaningful gate; a config-level flag requires a
deliberate, out-of-band operator action to enable.

**`answers` is a mapping of `question_id` → list of selected option ids**
(not a single id), so both single-select and multi-select questions are
representable without a schema change once capture confirms which types
exist. Validation (every question covered, every option id actually offered)
happens client-side before any HTTP request, matching the existing pattern
of `InvalidArgumentError` being raised pre-network for bad tool arguments.

**Capture-before-code**, following the project's own established convention
(`PROJECT-REFERENCE.md` §11): the exam protocol is fully uncaptured, so the
first implementation task is a manual DevTools capture session against a
real training exam (list → start/resume attempt → questions → submit →
score), producing anonymized fixtures the same way every other endpoint in
this project was documented, before any allow-list entries, models, or
tools are written against a guessed shape.

## Risks / Trade-offs

- **Backend may not distinguish training from graded exams at the protocol
  level, so an operator could point this at a real graded exam by mistake**
  → Mitigation: documented trust boundary (spec requirement), tool
  descriptions surfaced to the calling model should say "training exams
  only", and the spec already commits to upgrading to server-side
  enforcement the moment capture reveals a usable flag.
- **The exam protocol is entirely unconfirmed as of this design** → every
  concrete detail below "list/questions/submit exist as three logical
  operations" is provisional → Mitigation: capture task happens before any
  fixture, model, or allow-list entry is written; specs/design describe
  externally observable behavior, not endpoint shapes, so they don't need to
  change once capture completes.
- **An agent could exhaust the platform's own attempt limit (e.g. 2 attempts
  as observed) by retrying after a transient error** → Mitigation:
  `get_exam_questions` must surface attempts-used/allowed and refuse to
  start a new attempt at the limit (see spec); exact retry/resubmit-safety
  semantics for a single in-flight attempt depend on backend behavior not
  yet observed (see Open Questions).
- **Adding the project's first write path could normalize loosening the
  allow-list carelessly in future changes** → Mitigation: `EXAM_WRITE_ACTIONS`
  stays a separate, narrowly-named constant and config flag — never merged
  into `READ_ONLY_ACTIONS` or a generic "unsafe/admin mode" toggle.

## Migration Plan

1. Manually capture live traffic for a training exam: listing, attempt
   start/resume, question payload, answer submission, and the resulting
   score — anonymize immediately per §12 of `PROJECT-REFERENCE.md` (no raw
   capture ever committed).
2. Document the captured protocol (module/action names, payload shapes) and
   add synthetic fixtures, mirroring the style of the existing four
   endpoints.
3. Add `client/models.py` types for exam/question/attempt/answer and
   tolerant parsers, plus the `enable_exam_autosolve` config field
   (default `false`).
4. Add the `EXAM_WRITE_ACTIONS` allow-list and wire the RPC primitive to
   accept it only when the config flag is on.
5. Implement and register the three tools, with registration itself
   conditional on the flag for `submit_exam_answers` at minimum.
6. Add fixture-based tests for: flag-off (tool absent / write action still
   rejected), flag-on happy path, and flag-on error paths (no attempts left,
   malformed answers, upstream error).
7. Update `README.md` and `PROJECT-REFERENCE.md` with the new flag and the
   training-only trust boundary.

No data migration or rollback complexity: unsetting the flag returns the
server to today's exact behavior, and the server persists nothing beyond its
existing session-cookie cache.

## Open Questions

- Exact `(module, action)` names and payload shapes for exam listing,
  attempt start/resume, question retrieval, and answer submission — answered
  by the capture task (step 1 of the migration plan), not before.
- Whether the backend exposes any machine-checkable flag distinguishing
  training/self-check exams from graded ones — answered by capture; the spec
  already defines both outcomes.
- Whether resubmitting the same `attempt_id` after a timeout/lost response
  re-grades, errors, or is a no-op — answered by capture; affects tasks.md's
  detailed test list but not the spec-level contract already written.
