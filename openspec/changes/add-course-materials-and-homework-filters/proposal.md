# Proposal

## Why

Working against a real 1C course exposed four gaps in the read tools:

1. The response thread was the only way to see a teacher's feedback, and
   attachments posted by `submit_assignment_response` were silently dropped: the
   platform wants the full attachment objects in `assignments/post_comment`, but
   the client sent bare ids, so a posted comment kept `attachments: []` and the
   teacher saw no pictures.
2. Course materials (lecture guides, methodical handbooks, templates) were not
   reachable at all, even though tasks explicitly point at "the methodical
   handbook".
3. A task's own attached files were not exposed on their own.
4. `homework` returned every study at once (~682 rows) with no search, no
   pagination, and no way to find what actually needs attention (deadline,
   feedback).

## What Changes

- **Fix attachment linking** in the opt-in assignment submission: upload the
  file, keep the whole returned attachment object, and send those objects (not
  ids) in `assignments/post_comment`; `uploads/store` still takes ids. Add the
  attachments back to the read-back check.
- Add **`study_materials(study_id, include_content?)`** — course header plus
  chapters, enriched with annotation, HTML content and files from
  `learning/get_chapter`.
- Add **`task_files(study_id, task_id)`** — the files attached to one task.
- Extend **`homework`** with `study_ids`, `query`, `limit`/`offset`, `has_due`,
  `due_from`/`due_to`, and `has_feedback`, plus `assignment_id`/`responses_count`
  on each row and a `total` count. `has_feedback` reads `GET /app/profile/user`
  for the student's own id and compares it with each comment's `user_id`, so
  feedback is "a reply that is not mine".
- Extend the read-only allow-list with `learning/get_chapters` and
  `learning/get_chapter`; document `GET /app/profile/user` as the one deliberate
  non-RPC read (own id only).

Captured live contracts were anonymized into new fixtures before implementing.

## Capabilities

### Modified Capabilities
- `forlabs-diary-tools`: add course-materials and task-files tools, extend the
  homework tool, extend the allow-list, keep own-study scope.
- `assignment-workflows`: make attachment linking actually work by sending the
  full attachment objects in the response comment.

## Impact

- Tool surface, `ForlabsClient` (homework filters, `study_materials`,
  `task_files`, attachment upload), models/parsers, repository allow-list and the
  profile read, fixtures, tests, README and `PROJECT-REFERENCE.md`.
- Still read-only except the existing opt-in assignment submission; no new write
  action and no assessment/attendance/edit path.
