# Tasks

## 1. Capture and verify backend contracts

- [x] 1.1 Capture `learning/get_chapters`, `learning/get_chapter` and `GET /app/profile/user` request/response shapes; add anonymized fixtures (`learning_get_chapters.json`, `learning_get_chapter.json`, `profile_user.json`) and document them in `PROJECT-REFERENCE.md`.
- [x] 1.2 Confirm the string-vs-int parameter forms for the chapter calls (both accepted; the SPA sends strings) and that the detail chapter omits `has_content`.
- [x] 1.3 Confirm from live traffic that the web client sends attachment objects to `post_comment` and ids to `uploads/store`; keep the fix covered by fixtures, not a live upload.

## 2. Fix attachment linking in the submission workflow

- [x] 2.1 Return the whole attachment object from `_upload_attachment`; derive ids for `store`/`delete` and pass the objects to `post_assignment_comment`; verify the submission workflow test asserts `files == [{"id": 9100}]` on `post_comment` and `{"files": [9100]}` on `store`.

## 3. Course materials and task files

- [x] 3.1 Add `Chapter`/`Course` models and parsers; add `learning/get_chapters` and `learning/get_chapter` to the read-only allow-list.
- [x] 3.2 Implement `study_materials(study_id, include_content?)` merging chapter details onto the list; verify tests cover the merge, `include_content=False`, a non-own study rejected before any chapter call, and per-chapter failure tolerance.
- [x] 3.3 Implement `task_files(study_id, task_id)` from the full task detail; verify tests cover the file list and zero assignment writes.
- [x] 3.4 Register and document both tools.

## 4. Homework filters

- [x] 4.1 Add `assignment_id`/`responses_count` to homework rows and a `total` count; verify tests.
- [x] 4.2 Add `study_ids`, `query`, `limit`/`offset`, `has_due`, `due_from`/`due_to`; verify tests cover each and that malformed filters raise before any backend call.
- [x] 4.3 Implement `has_feedback` via `GET /app/profile/user` + `assignments/get_comments`; verify a teacher reply is kept, the student's own reply excluded, and a missing profile degrades to a warning.
- [x] 4.4 Update README and `PROJECT-REFERENCE.md`; verify documented argument names match the registered schemas.

## 5. End-to-end verification

- [x] 5.1 Run the full fixture suite, `ruff check .` and `ruff format --check .`; verify all pass without live network calls.
- [x] 5.2 Exercise `study_materials`/`task_files`/filtered `homework` against the real backend once to confirm live shapes match the fixtures (read-only; no writes).
