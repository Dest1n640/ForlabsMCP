## 1. Protocol capture (must happen before any code)

- [ ] 1.1 Capture live DevTools traffic for a training exam's full lifecycle
      against your own account: exam listing for a study, attempt
      start/resume, question payload, answer submission, and the resulting
      score — verify by having the raw (uncleaned) capture saved only in a
      local, gitignored scratch location, never staged or committed
- [ ] 1.2 Anonymize the capture per `PROJECT-REFERENCE.md` §12 (replace any
      real names/ids that aren't already synthetic) and add a new
      `## Exams` section to `PROJECT-REFERENCE.md` §3 documenting the
      confirmed `(module, action)` pairs, request/response shapes, and
      question/option field names — verify by re-reading the new section
      for any remaining non-synthetic name-shaped or path-shaped strings
      before it's committed
- [ ] 1.3 Determine from the capture whether the backend exposes any
      machine-checkable flag distinguishing training/self-check exams from
      graded ones, and record the finding directly in the new
      `PROJECT-REFERENCE.md` section — verify the finding is stated as a
      plain fact ("confirmed: no such flag" or "confirmed: field `X`
      distinguishes them"), not left open
- [ ] 1.4 Determine from the capture whether every observed question is
      fixed-option (single/multi-select) or whether free-text questions
      exist, and record the finding — verify by listing the concrete
      `question type` values seen in the capture

## 2. Fixtures

- [ ] 2.1 Add synthetic fixtures under `tests/fixtures/` for exam listing,
      question retrieval, and answer submission, shaped like the anonymized
      capture from Task 1 — verify `tests/test_repo_privacy.py` still passes
      against the new fixtures
- [ ] 2.2 Add the new fixtures' any newly-introduced synthetic names to the
      allow-list in `tests/test_repo_privacy.py` if applicable — verify by
      running `uv run pytest tests/test_repo_privacy.py`

## 3. Config and allow-list plumbing

- [ ] 3.1 Add `enable_exam_autosolve: bool` to `ForlabsConfig` (default
      `False`), resolved with the same env > TOML > default precedence as
      every other setting (env var `FORLABS_ENABLE_EXAM_AUTOSOLVE`) — verify
      with a `test_config.py` case asserting the default is `False` and each
      source can override it
- [ ] 3.2 Add an `EXAM_WRITE_ACTIONS` allow-list, structurally separate from
      `READ_ONLY_ACTIONS`, containing the `(module, action)` pairs confirmed
      in Task 1.2 — verify `Repository.call` rejects an exam-write action
      with `ProgrammingError` when `enable_exam_autosolve` is `False`, and
      permits it when `True` (new `test_repository.py` cases)

## 4. Models and parsers

- [ ] 4.1 Add pydantic models (`extra="ignore"`) for `Exam`, `ExamAttempt`,
      `ExamQuestion`, `ExamOption` in `client/models.py`, matching the
      confirmed shapes from Task 1.2 — verify with model-level unit tests
      constructing each from a fixture
- [ ] 4.2 Add tolerant parsers in `client/parsers.py` (bad row → warning
      string, never a lost response) for the three new payload shapes —
      verify with `test_parsers.py` cases covering both well-formed and
      malformed rows

## 5. Client and tools

- [ ] 5.1 Add the exam RPC calls to the client layer (`client/client.py` or
      a new `client/exam_client.py`): list exams, start/resume attempt +
      fetch questions, submit answers — verify with `respx`-mocked
      `test_client.py` cases for each call against its fixture
- [ ] 5.2 Register `list_training_exams(stream_id?, study_id?)` as an
      always-available (read) MCP tool — verify with a `test_server.py` /
      `test_tools_register.py` case that it's registered regardless of
      `enable_exam_autosolve`
- [ ] 5.3 Register `get_exam_questions(study_id, exam_id)` as an
      always-available (read) MCP tool that refuses to start a new attempt
      when attempts-used has reached attempts-allowed — verify with a case
      asserting no write RPC is attempted in that scenario
- [ ] 5.4 Register `submit_exam_answers(study_id, exam_id, attempt_id,
      answers)` as an MCP tool that is only registered/callable when
      `enable_exam_autosolve` is `True` — verify with a case asserting the
      tool is absent (or immediately errors without any HTTP call) when the
      flag is off
- [ ] 5.5 Implement pre-network validation on `submit_exam_answers`
      (`answers` covers every question of `attempt_id`; every referenced
      option id was actually offered) raising `InvalidArgumentError` before
      any HTTP request otherwise — verify with unit tests for a missing
      question and for an unknown option id, asserting zero HTTP calls were
      made (respx assert_all_called or call-count check)
- [ ] 5.6 Map upstream/backend errors from all three tools through the
      existing `ForlabsError` → `to_tool_error()` taxonomy — verify with a
      `test_errors.py` case per tool asserting no raw exception or stack
      trace string reaches the tool error message

## 6. Documentation

- [ ] 6.1 Add a section to `README.md` (Russian, matching the existing
      style) describing the three new tools, the `FORLABS_ENABLE_EXAM_AUTOSOLVE`
      flag and its default, and an explicit warning that enabling it is the
      operator's own attestation that only ungraded/self-check exams will be
      targeted — verify by re-reading the finished section for the warning
      being present and unambiguous
- [ ] 6.2 Update `PROJECT-REFERENCE.md` §6 (tool contracts) with the three
      new tools' exact input/output shapes, and §7 (configuration table)
      with the new flag — verify the new tool contracts match what
      `tools/register.py` actually implements after Task 5

## 7. Full verification

- [ ] 7.1 Run `uv run pytest` and confirm the full suite passes, including
      all new exam tests and the pre-existing four-tool suite unmodified —
      verify via the command's exit code and a scan of its output for zero
      failures
- [ ] 7.2 Run `uv run ruff check .` and `uv run ruff format --check .` and
      confirm both pass with zero issues on the new files
- [ ] 7.3 Manually run the MCP server with `FORLABS_ENABLE_EXAM_AUTOSOLVE`
      unset against a real (or fixture-backed smoke) session and confirm
      `submit_exam_answers` does not appear in the tool list — verify by
      inspecting the server's advertised tool list
