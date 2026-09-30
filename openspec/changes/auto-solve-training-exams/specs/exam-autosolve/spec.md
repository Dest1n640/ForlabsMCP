## Purpose

Lets an MCP-capable assistant read the questions of a Forlabs/Lamotivo
training/self-check exam and submit its own chosen answers, as an opt-in
exception to the server's default read-only posture.

## ADDED Requirements

### Requirement: Exam-write actions require explicit opt-in
The system SHALL NOT register `submit_exam_answers`, nor call any exam
answer-submission RPC action, unless an explicit opt-in configuration value
(e.g. `FORLABS_ENABLE_EXAM_AUTOSOLVE`) is set to true at startup. With the
opt-in unset (the default), the server's externally observable behavior for
exam-related write actions SHALL be identical to a server that never shipped
this capability at all.

#### Scenario: Default configuration keeps exam writes disabled
- **WHEN** the server starts without the opt-in flag set (or set to a falsy
  value)
- **THEN** `submit_exam_answers` is not exposed as a callable tool, and any
  RPC action needed to submit exam answers is rejected before any HTTP
  request, the same way any other action outside the read-only allow-list is
  rejected today

#### Scenario: Explicit opt-in enables the write path
- **WHEN** the server starts with the opt-in flag explicitly set to true
- **THEN** `submit_exam_answers` becomes a callable tool and its allow-listed
  RPC action(s) may be invoked

### Requirement: List available exams for a study
`list_training_exams(stream_id?, study_id?)` SHALL return, for each exam
belonging to the resolved stream/study, at least: an exam identifier, title,
question count, time limit, attempts used, attempts allowed, and the most
recent score/status — mirroring what the "Экзамены" tab of the diary shows.

#### Scenario: Exams exist for the study
- **WHEN** called with a study that has one or more exams
- **THEN** the tool returns one entry per exam with the fields above

#### Scenario: No exams for the study
- **WHEN** called with a study that has no exams
- **THEN** the tool returns an empty list plus an explanatory note, not an
  error

### Requirement: Fetch questions for an exam attempt
`get_exam_questions(study_id, exam_id)` SHALL start a new attempt (or resume
an attempt already in progress) and return every question in it together
with its answer options and question type, without indicating which option
is correct. It SHALL NOT start a new attempt, or return questions, when no
attempts remain.

#### Scenario: Attempts remain
- **WHEN** the exam's attempts-used count is below its attempts-allowed
  count
- **THEN** the tool returns an attempt identifier and the full list of
  questions with their answer options

#### Scenario: No attempts remain
- **WHEN** the exam's attempts-used count has reached its attempts-allowed
  count
- **THEN** the tool returns a clear "no attempts remaining" result and does
  not start a new attempt or make any write call

### Requirement: Submit answers for an exam attempt
`submit_exam_answers(study_id, exam_id, attempt_id, answers)` SHALL submit
the caller-supplied answers for the given attempt and return the resulting
score and pass/fail status once the platform grades it. It SHALL validate
that `answers` covers every question returned for that `attempt_id` and
references only option identifiers that were actually offered, rejecting the
call before any HTTP request otherwise.

#### Scenario: Successful submission
- **WHEN** called with a valid `attempt_id` and exactly one answer per
  question returned for that attempt, each referencing an offered option
- **THEN** the platform grades the attempt and the tool returns the
  resulting score and pass/fail status

#### Scenario: Incomplete or malformed answers
- **WHEN** `answers` omits a question from the attempt, or references an
  option that was not offered for its question
- **THEN** the tool rejects the call before making any HTTP request, with a
  classified invalid-argument error, and does not submit partial answers

#### Scenario: Opt-in disabled
- **WHEN** the exam-write opt-in is not enabled
- **THEN** this tool is unavailable, per the opt-in requirement above

### Requirement: Errors stay classified and credential-free
Errors raised by the three new tools SHALL be mapped through the existing
error taxonomy (`ForlabsError` → classified `ToolError`) exactly like the
four existing tools — no raw exception, stack trace, or credential value may
reach tool output.

#### Scenario: Upstream error while submitting
- **WHEN** the backend returns a non-2xx status or an in-body error shape in
  response to a `submit_exam_answers` call
- **THEN** the tool raises a classified upstream-error result and never
  surfaces a raw exception, stack trace, or credential

### Requirement: Documented training-only trust boundary
The project's documentation (README and/or PROJECT-REFERENCE) SHALL state
that enabling the exam-write opt-in is the operator's own attestation that
every exam it is pointed at is ungraded self-check/training content, and
SHALL note explicitly whether the backend protocol is known, as of the
current implementation, to expose any machine-checkable distinction between
training and graded exams.

#### Scenario: Protocol capture reveals a graded/training distinction
- **WHEN** the traffic capture performed for this change confirms the
  backend exposes a machine-checkable flag distinguishing training from
  graded exams
- **THEN** `get_exam_questions` and `submit_exam_answers` SHALL enforce that
  distinction server-side (refusing to operate on an exam not flagged as
  training) rather than relying on documentation alone
