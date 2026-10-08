# Design

## Context

`ForlabsClient.schedule_raw()` currently calls `sched/get_schedule` with `{}`. Live inspection confirmed that this returns the own schedule plus `meta.stream_ids`, an `entries` array, and a `streams` array of 42 selectable schedule groups. The schedule UI sends `{"stream_id": 0}` for its default and `{"stream_id": <integer>}` for a selected group; `{}` also returns the own schedule. `learning/get_streams` returns only the authenticated student's own stream, including student metadata, so it is not the schedule-group source.

`reference`, grades, and homework currently accept `stream_id` and use it to fetch studies or scores. The new contracts remove that selector from these tools; only schedule may select another group's stream. `learning/get_task` was captured with string `stream_id`, `study_id`, and `task_id` and returns `{task, assignment}`. `assignments/get_comments` uses string `study_id` plus integer `task_id` and `assignment_id`, returning `{comments: [...]}`; an empty thread was captured live.

The current homework model parses assignment IDs and task IDs, but the homework result drops most assignment metadata. Deployed UI source confirms that a new response uses `assignments/post_comment({study_id, task_id, assignment_id, message, files, mode})`, omitting `id` to avoid editing. The user authorized exactly one live text response, `.` to the first task in their own 1C course, after implementation; no other response or live file upload is authorized. The attachment UI uses FlowJS at `/lm-vendor/upload` (1 MiB chunks, `file` field, chunk metadata, XSRF header), then `uploads.store({files: ids})`; removal uses `uploads.delete({files: ids})`. This attachment sequence is source-confirmed but not live-upload-tested.

## Goals / Non-Goals

**Goals:**
- Keep group selection limited to schedule reads and subject/assignment reads limited to the authenticated student's own study IDs.
- Preserve a structural boundary between read RPCs and the opt-in assignment write flow.
- Make response content and selected attachments reviewable before a write, and avoid duplicate writes after ambiguous network failures.

**Non-Goals:**
- Any exam, assessment, grading, attendance, arbitrary post, edit, or delete workflow.
- A generic backend write API or arbitrary local-file upload access.

## Decisions

**Keep schedule group selection separate from own-study resolution.** `schedule_groups` reads the `streams` array and own IDs from `meta.stream_ids` returned by `sched/get_schedule`; `learning/get_streams` is not used because it returns only the authenticated student's stream. `schedule(stream_id=...)` accepts one of those scheduler IDs; without it, the existing own-schedule request remains `{}`. Non-schedule tools have no `stream_id` input and resolve studies from the authenticated student's own stream. The displayed group number/name is not assumed to equal the backend ID.

**Keep the repository read path read-only.** Add `learning/get_task` and `assignments/get_comments` to the read-only allow-list only after their request/response shapes have been captured. The existing read call must continue rejecting every unlisted action before HTTP construction. Assignment submission uses a dedicated, narrow path rather than adding writes to that allow-list or exposing a generic `(module, action)` method. That path can call only the captured comment-post operation and the minimum upload/finalization/cleanup operations required for attachments, and only while `FORLABS_ENABLE_ASSIGNMENT_SUBMISSION` is true.

**Resolve assignment identifiers from own-study data.** MCP callers provide `study_id` and `task_id`; they do not provide `assignment_id`, comment `id`, or `mode`. Resolve the task and its unique assignment from the authenticated student's own `learning/get_tasks` result. The current model already parses assignment/task IDs, but the homework output discards some fields. If no unique assignment is found, fail closed before requesting comments or writing. Preserve backend parameter types: the existing task-list call uses string stream/study IDs; the observed comments call uses string `study_id` and integer task/assignment IDs.

**Use a short-lived, one-use preparation record for submissions.** `preview_assignment_response` validates the task, response text, and selected files and returns a preview plus an opaque preparation ID. The ID binds the exact task, text, and file content fingerprints; it is not proof of user consent. `submit_assignment_response` accepts only that ID, is registered only when the feature flag is enabled, and is marked non-read-only/non-idempotent. The MCP host must obtain explicit user approval before invoking it; hosts that cannot provide that approval must leave submission disabled. Omit the comment `id` and force the student mode so the operation creates a new response rather than editing an existing one. After a successful write, read the thread back; report write acceptance and read-back verification separately. Never retry a possibly delivered write automatically.

**Constrain file access before upload.** File paths must resolve beneath `FORLABS_UPLOAD_ROOT`; if it is unset, allow text-only responses and reject attachments locally. Accept only explicitly named regular files, reject path escapes and files over the observed 50 MiB per-file UI limit, and verify that each file still matches its preview before upload. Upload only after preview and approval. If an upload/finalization step fails, do not post the response and attempt best-effort cleanup of temporary uploads. Do not log file contents or commit live attachments.

**Capture protocol before implementation.** Read-only schedule, task-detail, and comment-thread requests are captured with anonymized fixtures. The user has explicitly authorized one post of the exact text `.` to the first own 1C task; capture its real `post_comment` request and verify its thread read-back only after code and fixture checks pass. Do not retry or submit anything else. Attachment transport is derived from the deployed FlowJS source and covered by fixture-backed protocol tests; do not make a live file upload or claim the upload endpoint has been live-verified.

## Risks / Trade-offs

- **[Risk] `learning/get_streams` exposes only one own stream, while schedule options live in `sched/get_schedule`.** → Derive group options only from the schedule response and never use those IDs for subject, grade, or homework queries.
- **[Risk] A task has no unique assignment ID or comments are not immediately visible after posting.** → Fail closed when IDs cannot be resolved; distinguish backend write acceptance from thread read-back and never infer success from a missing response body.
- **[Risk] A write timeout can create a duplicate if retried.** → No automatic retry; instruct the caller to inspect `assignment_thread` before any manual retry.
- **[Risk] MCP tool annotations do not force every host to request human approval.** → Keep the feature off by default and document that it may only be enabled with a host policy that prompts for approval; the preparation ID is not an approval token.
- **[Risk] Attachment upload is source-confirmed but not live-tested.** → Keep writes disabled by default, require preview plus host-side approval, test the upload/finalize/cleanup sequence with fixtures, and exclude files from the single authorized live smoke.
- **[Trade-off] Removing `stream_id` from `reference`, `grades`, and `homework` breaks existing clients using those arguments.** → Treat this as a clean contract cutover, update README/tool descriptions, and do not retain a misleading compatibility shim.

## Migration Plan

1. Capture and anonymize the live read contracts; derive the fixed FlowJS attachment sequence from deployed source and capture the text post through the single user-authorized dot smoke. Do not upload a real file.
2. Implement group schedule and own-only subject behavior; update the MCP schemas and remove `stream_id` from the three non-schedule tools.
3. Implement assignment detail/thread reads and add their fixtures without user data.
4. Implement preview and the separately gated write path; keep the setting false by default and require host-side confirmation policy before enabling it.
5. Update setup/tool documentation and call out the breaking argument removal. Rollback is a code revert; no diary data migration is required. Any response already posted remains on the Forlabs site and cannot be rolled back by this MCP.
