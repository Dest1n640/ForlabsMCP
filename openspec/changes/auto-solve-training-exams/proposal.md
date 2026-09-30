## Why

The Forlabs/Lamotivo diary exposes an "Экзамены" (exams) tab per study with
timed, multiple-attempt self-check tests (e.g. "Тест № 1" — 15 questions, 30
minutes, 2 attempts, scored). These are training/self-check quizzes that do
not count toward the final course grade — the student wants an MCP-capable
assistant to read the questions for such a test and submit its own answers,
so it can be used as an autonomous self-check/practice run rather than
something the student has to click through by hand.

This is a deliberate, scoped exception to `forlabs-mcp`'s current
architecture: today the server is read-only *by construction* — a single
allow-listed RPC primitive (`Repository.call`) rejects any `(module,
action)` pair outside a hardcoded read-only list, and the README states
plainly that write actions "must never be added to this list." Submitting
exam answers is a write action. This change does not weaken that guarantee
for the four existing tools; it adds a second, explicitly separate,
opt-in-only write path that is scoped to training exams and does not touch
the existing allow-list at all.

## What Changes

- Add a new MCP tool `list_training_exams(stream_id?, study_id?)` (read) that
  lists the exams available for a study/stream — title, question count, time
  limit, attempts used/allowed, and last score — mirroring the "Экзамены" tab
  shown in the diary UI.
- Add a new MCP tool `get_exam_questions(study_id, exam_id)` (read) that
  starts or resumes an attempt and returns its questions with their answer
  options, so the calling assistant can reason about the correct answers
  itself (the "solving" intelligence is the MCP host's model — this server
  never embeds or calls out to a separate LLM).
- Add a new MCP tool `submit_exam_answers(study_id, exam_id, attempt_id,
  answers)` (**write** — new capability class for this project) that submits
  the assistant's chosen answers for grading and returns the resulting
  score.
- Add a second, independent RPC allow-list (`EXAM_WRITE_ACTIONS`) separate
  from the existing `READ_ONLY_ACTIONS`, wired through a **new, off-by-default
  config flag** (e.g. `FORLABS_ENABLE_EXAM_AUTOSOLVE`). With the flag unset,
  `submit_exam_answers` (and the write RPC actions it needs) must not be
  registered/callable at all — the server's default posture stays exactly as
  read-only as it is today.
- Add an explicit, documented trust boundary: the backend has not yet been
  observed to distinguish "training/self-check" exams from graded ones at
  the protocol level. Until traffic capture confirms otherwise, enabling
  `FORLABS_ENABLE_EXAM_AUTOSOLVE` is the user's own attestation that every
  exam it will be pointed at is ungraded self-check content — this is
  documented in README/PROJECT-REFERENCE.md, not silently assumed.
- Capture and document the previously-uncaptured exam protocol (exam
  listing, attempt start/resume, question payload shape, answer submission,
  scoring response) as fixtures, following this project's existing
  capture-before-spec convention (see `PROJECT-REFERENCE.md` §11).

No **BREAKING** changes to the four existing read-only tools or the existing
`READ_ONLY_ACTIONS` allow-list — this change is additive and disabled by
default.

## Capabilities

### New Capabilities
- `exam-autosolve`: the three new tools (`list_training_exams`,
  `get_exam_questions`, `submit_exam_answers`), the new opt-in write
  allow-list, the off-by-default config gate, and the exam-protocol
  fixtures/parsing needed to back them. One capability because all three
  tools share the same opt-in gate, session/config substrate, and exam
  data model, and are meaningless without each other (listing without
  questions, or questions without submission, is not a usable self-check
  loop).

### Modified Capabilities
(none — the existing four read-only tools and their allow-list are
untouched; this change only adds a new, separately-gated capability)

## Impact

- **New code**: `client/exam_repository.py` (or equivalent) for the new
  write-capable RPC path, new models in `client/models.py` for exams/
  questions/attempts, new parsers, a new `tools/register_exams.py` (or
  extension of `tools/register.py`), a new config field
  (`enable_exam_autosolve`, default `false`) in `config.py`.
- **New tests**: new synthetic fixtures for the exam endpoints (list,
  questions, submit), `respx`-mocked unit tests for both the gate-off
  (tools absent/rejected) and gate-on (happy path) cases, and an extension of
  `tests/test_repo_privacy.py` coverage if new fixtures introduce any
  name-shaped content.
- **External system**: this is the project's first **write** path to
  `https://bki.forlabs.ru` — it submits exam answers via the allow-listed
  write actions, only when `FORLABS_ENABLE_EXAM_AUTOSOLVE` is set.
- **Documentation**: README.md and PROJECT-REFERENCE.md need a new section
  spelling out the opt-in flag, the "training exams only" trust boundary,
  and the fact that this is the first documented exception to the
  project's read-only guarantee.
- **No impact** on the existing four tools, their allow-list, or any
  consumer relying on today's read-only guarantee when the new flag is left
  unset (the default).
