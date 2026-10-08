# Spec Delta

## ADDED Requirements

### Requirement: `schedule_groups` tool
The `schedule_groups` tool SHALL return the groups selectable for schedules, each with an internal `stream_id`, display name, and own-group flag. It SHALL NOT return subject lists for those groups.

#### Scenario: Schedule group options are listed
- **WHEN** `schedule_groups` is called
- **THEN** the result contains the available schedule groups with their identifiers and display names

#### Scenario: Group options do not expose group subjects
- **WHEN** a caller requests schedule group options
- **THEN** the result contains no subject or assignment data for any non-own group

## MODIFIED Requirements

### Requirement: Read-only tool surface
The system SHALL expose exactly `reference`, `schedule_groups`, `schedule`, `grades`, `homework`, `assignment_details`, `assignment_thread`, and `preview_assignment_response`, plus `submit_assignment_response` only when enabled under the `assignment-workflows` capability. No other backend write tool SHALL be exposed.

#### Scenario: Only read-only tools are registered
- **WHEN** assignment submission is disabled
- **THEN** the tool list contains the eight read/preview tools and no write tool

#### Scenario: Enabled tool list has only the specified write
- **WHEN** assignment submission is enabled
- **THEN** the tool list additionally contains `submit_assignment_response` and no other write tool

### Requirement: Backend action allow-list
The system SHALL allow read-only repository calls only to `sched/get_grid`, `sched/get_schedule`, `learning/get_streams`, `learning/get_studies`, `learning/get_scores`, `learning/get_tasks`, `learning/get_task`, and `assignments/get_comments`. Every other read action SHALL be rejected before an HTTP request. Write requests SHALL NOT use the read-only call path; only the gated assignment workflow may perform its explicitly specified writes.

#### Scenario: Non-allow-listed action is rejected locally
- **WHEN** internal code attempts a read action outside the read-only allow-list
- **THEN** the system raises a programming error without making an HTTP request

#### Scenario: Assignment write is rejected through the read-only path
- **WHEN** internal code attempts `assignments/post_comment` through the read-only call path
- **THEN** the system rejects it without making an HTTP request

#### Scenario: Allow-listed action is permitted
- **WHEN** internal code calls an allow-listed read action with valid parameters
- **THEN** the system sends the request and returns its response

### Requirement: `reference` tool
The `reference` tool SHALL accept no `stream_id` and return the student's identity placeholder, own stream id, the list of known streams (each flagged whether it is the student's own), and the authenticated student's full enrolment history with teachers, year, semester, and current-status flag. Because no identity endpoint exists on the backend, `identity` SHALL always be returned as `{name: null, role: null}`.

#### Scenario: Reference without arguments returns the student's own context
- **WHEN** `reference` is called with no arguments
- **THEN** the result includes `own_stream_id`, the known streams with the own stream flagged, and the complete studies history for the authenticated student only

#### Scenario: Reference rejects a stream selector
- **WHEN** a caller supplies `stream_id` to `reference`
- **THEN** the tool rejects the unsupported argument and makes no subject-data request for that stream

#### Scenario: Identity is always the documented placeholder
- **WHEN** `reference` is called successfully
- **THEN** `identity` in the result is always `{name: null, role: null}`

### Requirement: `grades` tool
The `grades` tool SHALL accept an optional `study_id` filter and SHALL return scores only for the authenticated student's own studies, joined to study names with a human-readable status label. An unresolved study id SHALL still be returned with a name-not-found note. When no scores match, the result SHALL explain that no grades were found.

#### Scenario: Grades are joined to study names with status labels
- **WHEN** `grades` is called with or without an own `study_id` filter
- **THEN** each returned score includes its `study_name` and a `status_label` consistent with the backend's numeric `status`, and no other student's studies are queried

#### Scenario: Unresolvable study id degrades gracefully
- **WHEN** a score references a `study_id` that has no matching entry in the student's own studies
- **THEN** that score is still returned with its numeric id and a name-not-found note, and the call as a whole succeeds

#### Scenario: No matching grades produces an explanatory note
- **WHEN** the requested own-study filter matches no scores
- **THEN** the result has an empty `scores` list and a `note` explaining that no grades were found

### Requirement: `homework` tool
The `homework` tool SHALL accept optional `study_id` and `only_outstanding` filters, but no `stream_id`. When `study_id` is omitted, it SHALL gather homework across every study in the authenticated student's own enrolment and union the results; failure for one study SHALL become a warning rather than failing the whole call. Each item SHALL indicate whether it is done based on backend assignment status.

#### Scenario: Homework across the whole stream is unioned
- **WHEN** `homework` is called without `study_id`
- **THEN** the result contains homework from every study in the authenticated student's own enrolment and none from another group

#### Scenario: One study's failure does not fail the whole call
- **WHEN** retrieving homework for one own study fails while others succeed
- **THEN** the result contains successful studies' homework plus a warning describing the failed study

#### Scenario: Outstanding-only filter excludes done items
- **WHEN** `homework` is called with `only_outstanding` set to true
- **THEN** the result excludes any homework item whose status marks it done

### Requirement: `schedule` tool
The `schedule` tool SHALL accept an optional `stream_id` from `schedule_groups`, in addition to either a single `date` or a `start`/`end` range, but not both. With no `stream_id`, it SHALL default to the authenticated student's own schedule; with a selected group, it SHALL return that group's schedule and identify the selected group in the result. With no date arguments it SHALL default to the current ISO week (Monday through Sunday). It SHALL place each lesson on a real calendar date and clock time using the backend's day/position grid, and SHALL state its week-parity assumption in every result.

#### Scenario: Mutually exclusive date arguments are rejected early
- **WHEN** `schedule` is called with both `date` and `start`/`end` specified
- **THEN** the system raises an invalid-argument error without making any backend call

#### Scenario: Default range is the current ISO week
- **WHEN** `schedule` is called without `stream_id` or date arguments
- **THEN** the result covers the current ISO week for the authenticated student's own schedule

#### Scenario: Selected group schedule is returned
- **WHEN** `schedule` is called with a `stream_id` from `schedule_groups`
- **THEN** the request selects that group and the result identifies its `stream_id` and display name

#### Scenario: Unknown group is rejected before its schedule is fetched
- **WHEN** `schedule` is called with a `stream_id` that is not in the schedule group options
- **THEN** the system rejects the selection without requesting that group's schedule

#### Scenario: Every schedule result discloses its week-parity assumption
- **WHEN** `schedule` returns any lessons
- **THEN** the result includes a `week_parity_basis` field stating the assumption used to map the backend's alternating-week data onto real calendar weeks

#### Scenario: Empty range produces an explanatory note
- **WHEN** `schedule` is called for a range with no lessons
- **THEN** the result has an empty `lessons` list and a `note` explaining that no lessons were found
