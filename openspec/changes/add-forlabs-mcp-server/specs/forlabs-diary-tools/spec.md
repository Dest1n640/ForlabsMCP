## Purpose

Lets an MCP-capable assistant answer questions about a real Forlabs/Lamotivo
school diary (schedule, grades, homework, enrolment reference data) on behalf
of a logged-in student, without ever writing back to the diary.

## ADDED Requirements

### Requirement: Read-only tool surface
The system SHALL expose exactly four MCP tools — `reference`, `schedule`,
`grades`, `homework` — and no tool that can create, update, or delete any
data on the Forlabs/Lamotivo backend.

#### Scenario: Only read-only tools are registered
- **WHEN** an MCP client lists the tools this server provides
- **THEN** the list contains exactly `reference`, `schedule`, `grades`,
  `homework`, and no other tool

### Requirement: Backend action allow-list
The system SHALL only call backend actions on a fixed allow-list
(`sched/get_grid`, `sched/get_schedule`, `learning/get_streams`,
`learning/get_studies`, `learning/get_scores`, `learning/get_tasks`). Any
attempt to call a `(module, action)` pair outside this list SHALL be rejected
before any HTTP request is made, and SHALL never reach the network layer.

#### Scenario: Non-allow-listed action is rejected locally
- **WHEN** internal code attempts to call a backend action not on the
  allow-list (for example a write action like `assignments/post_comment`)
- **THEN** the system raises a programming error without making any HTTP
  request to the backend

#### Scenario: Allow-listed action is permitted
- **WHEN** internal code calls one of the six allow-listed actions with valid
  parameters
- **THEN** the system sends the request to the backend and returns its
  response

### Requirement: Session authentication
The system SHALL authenticate to the Forlabs backend using a username and
password by priming the CSRF cookie, then submitting the login request with
the decoded CSRF token echoed in the `X-XSRF-TOKEN` header. On success it
SHALL retain the resulting session for subsequent requests; on rejected
credentials it SHALL surface an authentication error without leaking the
submitted password.

#### Scenario: Successful login establishes a session
- **WHEN** the configured username and password are accepted by the backend
- **THEN** the system holds a valid session usable for subsequent data calls

#### Scenario: Rejected credentials surface a classified error
- **WHEN** the backend rejects the configured username/password
- **THEN** the system raises an authentication error whose message never
  contains the submitted password

### Requirement: Transparent re-authentication on session expiry
The system SHALL detect an expired session on a data call and transparently
re-authenticate exactly once before retrying that call. If re-authentication
also fails, the system SHALL surface an authentication error rather than
retrying indefinitely.

#### Scenario: Expired session is retried once
- **WHEN** a data call fails because the cached session has expired
- **THEN** the system logs in again and retries the original call exactly
  once, returning its result on success

#### Scenario: Re-authentication failure is surfaced
- **WHEN** a data call fails due to session expiry and the subsequent
  re-authentication attempt also fails
- **THEN** the system raises an authentication error instead of retrying
  again

### Requirement: Local session cache confidentiality
The system SHALL persist session state to a local cache file with
permissions restricted to the owning user only (mode `0600`), and SHALL
never write raw credentials to that file.

#### Scenario: Session cache file is created with restricted permissions
- **WHEN** the system persists a session to its local cache path
- **THEN** the resulting file is readable and writable only by the owning
  user

### Requirement: `reference` tool
The `reference` tool SHALL accept an optional `stream_id` and return the
student's identity placeholder, own stream id, the list of known streams
(each flagged whether it is the student's own), and the student's full
enrolment history (current and past studies) with teachers, year, semester,
and current-status flag. Because no identity endpoint exists on the backend,
`identity` SHALL always be returned as `{name: null, role: null}`.

#### Scenario: Reference without arguments returns the student's own context
- **WHEN** `reference` is called with no `stream_id`
- **THEN** the result includes `own_stream_id`, the full `streams` list with
  the student's own stream flagged, and the student's complete `studies`
  history

#### Scenario: Identity is always the documented placeholder
- **WHEN** `reference` is called successfully
- **THEN** `identity` in the result is always `{name: null, role: null}`

### Requirement: `grades` tool
The `grades` tool SHALL accept optional `stream_id` and `study_id` filters
and return each matching score joined to its study name, with a
human-readable status label derived from the backend's numeric status. A
study id that cannot be resolved to a name SHALL still be returned, carrying
the numeric id plus a note that the name could not be found, rather than
failing the whole call. When no scores match the filters, the result SHALL
include a note stating that no grades were found instead of an empty result
with no explanation.

#### Scenario: Grades are joined to study names with status labels
- **WHEN** `grades` is called for a stream that has scored studies
- **THEN** each returned score includes its `study_name` and a
  `status_label` consistent with the backend's numeric `status`

#### Scenario: Unresolvable study id degrades gracefully
- **WHEN** a score references a `study_id` that has no matching entry in the
  student's studies
- **THEN** that score is still returned, with the numeric id and a
  name-not-found note, and the call as a whole still succeeds

#### Scenario: No matching grades produces an explanatory note
- **WHEN** `grades` is called with filters that match no scores
- **THEN** the result has an empty `scores` list and a `note` explaining
  that no grades were found

### Requirement: `homework` tool
The `homework` tool SHALL accept optional `stream_id`, `study_id`, and
`only_outstanding` filters. When `study_id` is omitted, it SHALL gather
homework across every study in the target stream's enrolment and union the
results; a failure retrieving homework for one study SHALL become a warning
on the result rather than failing the entire call. Each returned homework
item SHALL indicate whether it is done, based on the backend's assignment
status.

#### Scenario: Homework across the whole stream is unioned
- **WHEN** `homework` is called with a `stream_id` but no `study_id`
- **THEN** the result contains homework items from every study in that
  stream's enrolment, not just one

#### Scenario: One study's failure does not fail the whole call
- **WHEN** retrieving homework for one study in the stream fails while others
  succeed
- **THEN** the result still contains the successfully retrieved studies'
  homework, plus a warning describing the failed study

#### Scenario: Outstanding-only filter excludes done items
- **WHEN** `homework` is called with `only_outstanding` set to true
- **THEN** the result excludes any homework item whose status marks it done

### Requirement: `schedule` tool
The `schedule` tool SHALL accept either a single `date`, or a `start`/`end`
range, but not both — supplying both SHALL be rejected as an invalid
argument before any backend call is made. With no arguments it SHALL default
to the current ISO week (Monday through Sunday). It SHALL place each lesson
on a real calendar date and clock time using the backend's day/position grid,
and SHALL explicitly state, in every result, the assumption it makes about
which calendar week corresponds to the backend's internal week parity.

#### Scenario: Mutually exclusive date arguments are rejected early
- **WHEN** `schedule` is called with both `date` and `start`/`end` specified
- **THEN** the system raises an invalid-argument error without making any
  backend call

#### Scenario: Default range is the current ISO week
- **WHEN** `schedule` is called with no arguments
- **THEN** the result covers Monday through Sunday of the current ISO week

#### Scenario: Every schedule result discloses its week-parity assumption
- **WHEN** `schedule` returns any lessons
- **THEN** the result includes a `week_parity_basis` field stating the
  assumption used to map the backend's alternating-week data onto real
  calendar weeks

#### Scenario: Empty range produces an explanatory note
- **WHEN** `schedule` is called for a range with no lessons
- **THEN** the result has an empty `lessons` list and a `note` explaining
  that no lessons were found

### Requirement: Partial results on malformed data
When the backend returns a row that fails to parse into the expected shape,
the system SHALL record a warning describing that row and continue
processing the rest of the response, rather than raising an exception that
discards an entire otherwise-valid result.

#### Scenario: One malformed row does not discard the rest of the response
- **WHEN** a backend response contains one row that fails to parse and
  several rows that parse successfully
- **THEN** the tool result contains the successfully parsed rows plus a
  warning describing the malformed one

### Requirement: Credential-free, classified error surface
The system SHALL classify every failure (configuration, invalid argument,
authentication, connectivity, timeout, rate limit, upstream application
error, or internal programming error) into a single-line, human-readable
message. No raw exception message, stack trace, or credential value SHALL
ever reach tool output; an unrecognized failure SHALL collapse to a generic
error message rather than leaking implementation detail.

#### Scenario: An unexpected internal exception is never leaked verbatim
- **WHEN** an unclassified exception occurs while serving a tool call
- **THEN** the tool returns a generic error message with no stack trace or
  internal exception text

#### Scenario: Rate limiting is surfaced with retry guidance
- **WHEN** the backend responds indicating it is rate-limiting requests
- **THEN** the tool returns a rate-limit error that includes retry-after
  guidance when the backend supplied one

### Requirement: Layered, validated configuration
The system SHALL resolve each setting (credentials, base URL, timeout,
timezone, session cache path, max list items) with precedence: environment
variable, then TOML config file, then built-in default. It SHALL validate
all required settings (username, password) before making any network call,
and SHALL be able to render its own configuration with credentials redacted
for logging.

#### Scenario: Environment variable overrides the TOML file
- **WHEN** a setting is present both as an environment variable and in the
  TOML config file
- **THEN** the environment variable's value is used

#### Scenario: Missing required credential fails before any network call
- **WHEN** the username or password setting is absent from every
  configuration source
- **THEN** the system raises a configuration error and makes no request to
  the backend

#### Scenario: Redacted configuration never exposes the password
- **WHEN** the system's configuration is rendered for logging or diagnostics
- **THEN** the password value does not appear in that output

### Requirement: Portable MCP client registration
The system SHALL provide a way to generate the `{command, args, env}`
descriptor an MCP host needs to register this server, and that descriptor
SHALL never contain real credentials — credential fields SHALL always be
placeholders that the user fills in themselves.

#### Scenario: Generated registration config never embeds real credentials
- **WHEN** the registration descriptor is generated for this server
- **THEN** its credential fields are placeholder strings, regardless of what
  credentials are configured in the local environment
