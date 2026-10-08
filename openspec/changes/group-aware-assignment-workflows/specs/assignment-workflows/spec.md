# Spec Delta

## Purpose

Provides authenticated students with assignment prompts and response history for their own courses, plus a controlled, opt-in way to prepare and submit a new response.

## ADDED Requirements

### Requirement: Assignment details are scoped to the student's own studies
The system SHALL provide `assignment_details(study_id, task_id)` for a task in the authenticated student's own studies, returning its prompt and available due-date, grading, and attachment metadata.

#### Scenario: Own task details are returned
- **WHEN** the caller requests a task belonging to one of the student's own studies
- **THEN** the result contains the task prompt and available task metadata

#### Scenario: Task outside the student's own studies is rejected
- **WHEN** the caller requests a task for a study or task not in the authenticated student's own data
- **THEN** the request is rejected without fetching task details

### Requirement: Assignment response threads are readable
The system SHALL provide `assignment_thread(study_id, task_id)` with the comments, authors, timestamps, and attachments returned for that task's authenticated-student assignment.

#### Scenario: Existing response thread is returned
- **WHEN** a task has a resolvable assignment in the student's own study
- **THEN** the result contains its response thread without requiring the caller to supply an assignment identifier

#### Scenario: Assignment identifier cannot be resolved
- **WHEN** no unique assignment for the requested own-study task can be resolved
- **THEN** the tool reports that the thread is unavailable and makes no comments request

### Requirement: A response can be previewed before submission
The system SHALL provide `preview_assignment_response(study_id, task_id, message, file_paths)` with the exact response text and explicit attachment names and sizes, bound to a short-lived preparation identifier; previewing SHALL NOT write to Forlabs.

#### Scenario: Preview binds the exact response
- **WHEN** the caller prepares a response for an own-study task
- **THEN** the preview shows the selected task, exact text, and selected attachment metadata and returns a preparation identifier

#### Scenario: Changed or expired preparation is rejected
- **WHEN** the caller submits an expired preparation or an attachment has changed since preview
- **THEN** submission is rejected before any backend write

### Requirement: Assignment submission is disabled by default
The system SHALL expose no assignment-write tool unless `FORLABS_ENABLE_ASSIGNMENT_SUBMISSION` is explicitly enabled; enabling it SHALL NOT enable any other write action.

#### Scenario: Default configuration exposes no write tool
- **WHEN** the setting is unset or false
- **THEN** the MCP tool list contains no assignment-write tool and all existing reads remain available

#### Scenario: Explicit enablement exposes only assignment submission
- **WHEN** the setting is true
- **THEN** the MCP server exposes the assignment submission tool and no other write tool

### Requirement: Only a reviewed new response can be submitted
The system SHALL submit only the exact response bound to a valid preview after an explicit user approval step via `submit_assignment_response(preparation_id)`; the write tool SHALL be marked non-read-only and non-idempotent, and SHALL NOT accept arbitrary assignment/comment identifiers or an edit mode.

#### Scenario: Approved preview is submitted as a new response
- **WHEN** the user approves a valid preview and invokes `submit_assignment_response` with its preparation identifier
- **THEN** the system posts one new student response for the resolved own-study assignment and reads back the response thread

#### Scenario: Submission is not invoked without user approval
- **WHEN** the user has not explicitly approved the preview
- **THEN** the MCP host does not invoke the submission tool

### Requirement: Assignment attachments are explicit and bounded
The system SHALL accept only explicitly selected regular files under the configured `FORLABS_UPLOAD_ROOT`, reject files larger than 50 MiB, and preserve each accepted file's bytes and filename.

#### Scenario: File outside the configured root is rejected
- **WHEN** a selected path resolves outside `FORLABS_UPLOAD_ROOT` or the root is unset
- **THEN** the attachment is rejected before any upload request

#### Scenario: Oversized attachment is rejected
- **WHEN** a selected file exceeds 50 MiB
- **THEN** it is rejected before any upload request

#### Scenario: Failed upload does not post a response
- **WHEN** any attachment upload or finalization fails
- **THEN** no response comment is posted and temporary uploads are cleaned up when the backend permits

### Requirement: Ambiguous submission outcomes are never retried automatically
The system SHALL NOT automatically retry a response write after a timeout or other failure that may have occurred after the backend received it.

#### Scenario: Write outcome is ambiguous
- **WHEN** a response write times out or its outcome cannot be confirmed
- **THEN** the tool reports an uncertain outcome and directs the caller to inspect the response thread before any manual retry
