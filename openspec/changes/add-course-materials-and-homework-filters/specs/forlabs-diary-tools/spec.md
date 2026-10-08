# Spec Delta

## ADDED Requirements

### Requirement: `study_materials` tool
The system SHALL provide `study_materials(study_id, include_content?)` returning the authenticated student's own study's course header and chapter list; with `include_content` true (the default) each chapter that advertises content SHALL be enriched with its annotation, HTML content and attached files. A chapter that fails to load SHALL become a warning rather than failing the call.

#### Scenario: Course materials for an own study are returned
- **WHEN** `study_materials` is called with one of the student's own `study_id`s
- **THEN** the result contains the course header with its files and the chapter list

#### Scenario: Chapter content is merged when requested
- **WHEN** `include_content` is true and a chapter advertises content
- **THEN** that chapter is enriched with its annotation, content and files from the chapter-detail endpoint

#### Scenario: Chapters without content are not fetched
- **WHEN** a chapter advertises no content
- **THEN** no chapter-detail request is made for it

#### Scenario: A study outside the student's own studies is rejected
- **WHEN** `study_materials` is called with a `study_id` that is not one of the student's own studies
- **THEN** the request is rejected before any chapter request

#### Scenario: One chapter's failure does not fail the call
- **WHEN** a chapter-detail request fails while the chapter list succeeds
- **THEN** the result still contains the chapters plus a warning describing the failed chapter

### Requirement: `task_files` tool
The system SHALL provide `task_files(study_id, task_id)` returning the files attached to one task in the student's own studies, read from the full task detail, without performing any assignment write.

#### Scenario: Task files are returned
- **WHEN** `task_files` is called for a task in one of the student's own studies
- **THEN** the result contains that task's title and files and no assignment write is made

## MODIFIED Requirements

### Requirement: Read-only tool surface
The system SHALL expose exactly `reference`, `schedule_groups`, `schedule`, `grades`, `homework`, `study_materials`, `task_files`, `assignment_details`, `assignment_thread`, and `preview_assignment_response`, plus `submit_assignment_response` only when enabled under the `assignment-workflows` capability. No other backend write tool SHALL be exposed.

#### Scenario: Only read-only tools are registered
- **WHEN** assignment submission is disabled
- **THEN** the tool list contains the ten read/preview tools and no write tool

#### Scenario: Enabled tool list has only the specified write
- **WHEN** assignment submission is enabled
- **THEN** the tool list additionally contains `submit_assignment_response` and no other write tool

### Requirement: Backend action allow-list
The system SHALL allow read-only repository calls only to `sched/get_grid`, `sched/get_schedule`, `learning/get_streams`, `learning/get_studies`, `learning/get_scores`, `learning/get_tasks`, `learning/get_task`, `learning/get_chapters`, `learning/get_chapter`, and `assignments/get_comments`. Every other read action SHALL be rejected before an HTTP request. Write requests SHALL NOT use the read-only call path; only the gated assignment workflow may perform its explicitly specified writes. The authenticated account read at the app's own profile endpoint SHALL be the only non-RPC read, and SHALL be used only to obtain the student's own user id.

#### Scenario: Non-allow-listed action is rejected locally
- **WHEN** internal code attempts a read action outside the read-only allow-list
- **THEN** the system raises a programming error without making an HTTP request

#### Scenario: Assignment write is rejected through the read-only path
- **WHEN** internal code attempts `assignments/post_comment` through the read-only call path
- **THEN** the system rejects it without making an HTTP request

#### Scenario: Allow-listed action is permitted
- **WHEN** internal code calls an allow-listed read action with valid parameters
- **THEN** the system sends the request and returns its response

### Requirement: `homework` tool
The `homework` tool SHALL accept optional `study_id`, `study_ids`, `only_outstanding`, `query`, `limit`, `offset`, `has_due`, `due_from`, `due_to`, and `has_feedback` filters, but no `stream_id`. When no study is selected, it SHALL gather homework across every study in the authenticated student's own enrolment and union the results; failure for one study SHALL become a warning rather than failing the whole call. Each item SHALL indicate whether it is done, and SHALL carry its assignment id and response count. The result SHALL include the pre-pagination `total`. A malformed filter value SHALL be rejected before any backend call. `has_feedback` SHALL keep only items whose response thread holds a reply not written by the authenticated student.

#### Scenario: Homework across the whole stream is unioned
- **WHEN** `homework` is called without a study selection
- **THEN** the result contains homework from every study in the authenticated student's own enrolment and none from another group

#### Scenario: One study's failure does not fail the whole call
- **WHEN** retrieving homework for one own study fails while others succeed
- **THEN** the result contains successful studies' homework plus a warning describing the failed study

#### Scenario: Several own studies are selected at once
- **WHEN** `homework` is called with `study_ids`
- **THEN** only the selected own studies' homework is returned

#### Scenario: Text search and pagination are applied
- **WHEN** `homework` is called with `query` and/or `limit`/`offset`
- **THEN** only matching items are returned, paginated, and `total` reports the count before pagination

#### Scenario: Outstanding-only filter excludes done items
- **WHEN** `homework` is called with `only_outstanding` set to true
- **THEN** the result excludes any homework item whose status marks it done

#### Scenario: Due-date filters narrow by deadline
- **WHEN** `homework` is called with `has_due` and/or `due_from`/`due_to`
- **THEN** only items whose due date matches the filter are returned

#### Scenario: Feedback filter keeps only teacher replies
- **WHEN** `homework` is called with `has_feedback` true
- **THEN** only items whose response thread contains a reply not written by the authenticated student are returned, and each result carries `has_feedback`

#### Scenario: Feedback filter degrades when the account id is unavailable
- **WHEN** `has_feedback` is requested but the authenticated user id cannot be read
- **THEN** the filter is skipped and a warning explains why

#### Scenario: Malformed filters are rejected before any backend call
- **WHEN** `homework` is called with a non-positive `limit`, a negative `offset`, a non-boolean `has_due`/`has_feedback`, a malformed date, or a reversed date range
- **THEN** an invalid-argument error is raised without any backend call
