# Tasks

## 1. Capture and verify backend contracts

- [x] 1.1 Capture own and selected-group `sched/get_schedule` request/response shapes; confirm `streams`/`meta.stream_ids` supply schedule groups and `learning/get_streams` returns only the own stream. Add anonymized fixtures and update `PROJECT-REFERENCE.md`; verify integer IDs and no identifying data.
- [x] 1.2 Capture `learning/get_task`, `assignments/get_comments`, and the task-to-assignment mapping; add anonymized fixtures and verify field types and privacy scan.
- [x] 1.3 After implementation and fixture checks, use the user's authorization for exactly one text post `.` to the first own 1C task; capture the real request and verify thread read-back. Do not retry, post elsewhere, or upload a file. Test attachment upload/finalization/cleanup from the deployed FlowJS source with fixtures; do not claim a live upload.

## 2. Add schedule groups and enforce own-study scope

- [x] 2.1 Implement `schedule_groups` and `schedule(stream_id=...)`; verify tests cover the default `{}` own-schedule request, a selected group's integer `stream_id`, returned group identity, and rejection of an unknown group before its schedule request.
- [x] 2.2 Remove `stream_id` from `reference`, `grades`, and `homework` and constrain their study queries to the authenticated student's own enrolment; verify tests reject the removed arguments and prevent non-own study requests, then update the tool documentation for the breaking change.

## 3. Add assignment detail and response-thread reads

- [x] 3.1 Add typed parsing and read-only access for task details and response threads, resolving assignment IDs only from own-study data; verify tests cover valid IDs, missing/ambiguous assignment IDs, malformed rows, and zero write requests.
- [x] 3.2 Register `assignment_details` and `assignment_thread` and document their inputs/outputs; verify MCP tool-list/schema tests and fixture-backed tool-dispatch tests pass.

## 4. Add preview and opt-in response submission

- [x] 4.1 Add `FORLABS_ENABLE_ASSIGNMENT_SUBMISSION` (default false), `FORLABS_UPLOAD_ROOT`, and `preview_assignment_response`; verify tests cover the default tool surface, one-use/expired preparations, attachment changes, path escapes, symlinks, unreadable files, and the 50 MiB limit; document the host approval requirement.
- [x] 4.2 Implement the captured attachment upload/finalization/cleanup sequence behind the dedicated assignment write boundary; verify tests prove uploads occur only after approval, failed uploads never post a comment, temporary uploads are cleaned up when possible, and no other write action is reachable.
- [x] 4.3 Implement `submit_assignment_response` for a new student response only, followed by thread read-back; verify tests cover exact-preview binding, omission of edit identifiers, disabled-by-default behavior, ambiguous-write no-retry, and separately reported write/read-back outcomes.
- [x] 4.4 Update README and protocol documentation with opt-in setup, upload-root limits, preview/approval flow, failure recovery, and the breaking tool arguments; verify every documented configuration example and tool name matches the registered schemas.

## 5. End-to-end verification

- [x] 5.1 Run the full fixture-backed suite, `uv run ruff check .`, and `uv run ruff format --check .`; verify all pass without live network calls.
- [x] 5.2 Use the user's explicit authorization for one previewed `.` response to the first assignment in their own 1C course; verify the exact thread read-back and do not retry or attach a file.
