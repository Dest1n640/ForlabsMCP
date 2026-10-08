# Proposal

## Why

The MCP currently returns the authenticated student's schedule only and does not expose assignment details or the response thread, so it cannot support the site's main assignment workflow end to end. Group selection is supported by the site for schedules only; subject, grade, and homework data must remain scoped to the authenticated student's own studies.

## What Changes

- **BREAKING** Remove `stream_id` from `reference`, `grades`, and `homework`; these tools operate only on the authenticated student's own studies. Keep `study_id` filters where applicable.
- Add `schedule_groups` and allow `schedule` to select one of those groups by its internal `stream_id`; the default remains the student's own schedule.
- Add assignment-detail and response-thread reads for tasks in the authenticated student's own studies.
- Add an opt-in assignment-response workflow for text and explicitly selected files. Submission is disabled by default, isolated from the read-only RPC allow-list, and supports creating a new response only; no edit, delete, grade, or assessment operations.
- Require a preview before submission, expose the write tool as non-read-only/non-idempotent, and never automatically retry an ambiguous write.
- Capture and anonymize live request/response fixtures before implementing newly observed backend contracts. Do not commit real student names, messages, tokens, or attachments.
- No exam-related behavior is included.

## Capabilities

### New Capabilities
- `assignment-workflows`: read a student's own task details and response thread, preview a response, and optionally submit a new text/file response through a separately gated write path.

### Modified Capabilities
- `forlabs-diary-tools`: add schedule-group selection while keeping subject, grade, and homework access own-account-only; revise the tool and backend-action boundaries accordingly.

## Impact

- MCP contracts and registration; `ForlabsClient` schedule, reference, grades, and homework behavior; assignment models/parsers and fixtures; repository read/write boundaries; configuration for disabled-by-default submission and the attachment root; tests and user documentation.
- External effects remain read-only unless the operator enables assignment submission and explicitly invokes its submission tool. The existing exam-related OpenSpec change is separate and remains untouched.
