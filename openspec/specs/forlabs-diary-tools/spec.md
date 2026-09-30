# forlabs-diary-tools Specification

## Purpose

Lets an MCP-capable assistant answer questions about a real Forlabs/Lamotivo
school diary (schedule, grades, homework, enrolment reference data) on behalf
of a logged-in student, without ever writing back to the diary.

## Requirements

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
The system SHALL authenticate to the Forlabs backend by seeding its HTTP
client's cookie jar with a configured `session_token` - the value of the
long-lived Laravel remember-me cookie (`remember_lm_<hash>`, obtained by
the user from an already logged-in browser session) - instead of
submitting a username and password to the login endpoint. The system
SHALL never submit a password to Forlabs, and no username/password
setting SHALL exist anywhere in the configuration surface. Ordinary
authenticated data calls SHALL rely on the backend's own remember-me
handling to establish and renew the short-lived session cookies as
needed, without any dedicated keep-alive mechanism in this client.

#### Scenario: Configured session token establishes a session
- **WHEN** a `session_token` is configured
- **THEN** the system holds a session usable for subsequent data calls
  without ever issuing a `POST /app/login` request

#### Scenario: A data call renews the short-lived session cookies
- **WHEN** a data call is made with only the long-lived `session_token`
  cookie present (no cached `forlabs_session`)
- **THEN** the call succeeds and the backend's response establishes a
  fresh short-lived session, with no separate renewal request needed

#### Scenario: Invalid session token is rejected without leaking its value
- **WHEN** the configured `session_token` is rejected by the backend on
  the first authenticated data call
- **THEN** the system raises an authentication error whose message never
  contains the submitted `session_token` value

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
The system SHALL resolve each setting (`session_token`, base URL, timeout,
timezone, session cache path, max list items) with precedence: environment
variable, then the repo-local JSON token file, then built-in default. No
other configuration source (including any TOML file under the user's home
directory) SHALL be read. It SHALL validate that `session_token` is present
before making any network call, and SHALL be able to render its own
configuration with the `session_token` value redacted for logging.

#### Scenario: Environment variable overrides the JSON file
- **WHEN** a setting is present both as an environment variable and in the
  JSON token file
- **THEN** the environment variable's value is used

#### Scenario: JSON file supplies the token when no environment variable is set
- **WHEN** `FORLABS_SESSION_TOKEN` is unset and the JSON token file
  contains a non-placeholder `session_token`
- **THEN** that value is used as the session token

#### Scenario: A leftover TOML config file is ignored
- **WHEN** a file exists at `~/.config/forlabs-mcp/config.toml`
- **THEN** none of its values influence the resolved configuration

#### Scenario: Missing session token fails before any network call
- **WHEN** the `session_token` setting is absent from every configuration
  source
- **THEN** the system raises a configuration error and makes no request to
  the backend

#### Scenario: Placeholder token is treated as missing
- **WHEN** the JSON token file still contains the committed placeholder
  value and no environment variable is set
- **THEN** the system raises a configuration error naming `session_token`
  and makes no request to the backend

#### Scenario: Redacted configuration never exposes the session token
- **WHEN** the system's configuration is rendered for logging or
  diagnostics
- **THEN** the `session_token` value does not appear in that output

### Requirement: Portable MCP client registration
The repository SHALL document a single copy-paste `{command, args, env}`
descriptor that an MCP host can use to register this server, and that
descriptor SHALL contain only placeholder values for every credential
field - the user fills in their own session token. No generator or wizard
script SHALL be required to produce it.

#### Scenario: Documented registration descriptor never embeds real credentials
- **WHEN** the registration descriptor documented in the README is
  inspected
- **THEN** its credential fields are placeholder strings, and the
  repository's leak checks reject a real token in that file

### Requirement: Terminal error on session-token expiry
When a data call fails because the configured `session_token` itself has
been rejected or has expired, the system SHALL surface a single
authentication error instructing the user to obtain a fresh
`session_token` from their browser and update their configuration. The
system SHALL NOT retry the call and SHALL NOT attempt any credential-based
recovery, since no credential is configured.

#### Scenario: Expired session token surfaces an actionable error
- **WHEN** a data call fails because the backend rejects the configured
  `session_token`
- **THEN** the system raises an authentication error telling the user to
  supply a fresh `session_token`, without retrying the call and without
  attempting to log in with credentials

### Requirement: Repo-local JSON token file with committed placeholder template
The repository SHALL contain a committed template file
`forlabs-session.example.json` holding only a placeholder `session_token`
value. The system SHALL read the user's own token from the sibling file
`forlabs-session.json`, and that file SHALL be excluded from version
control. The repository SHALL NOT contain a real session token in any
tracked file.

#### Scenario: Template contains only a placeholder
- **WHEN** the tracked `forlabs-session.example.json` is inspected
- **THEN** its `session_token` is the placeholder value and no real token

#### Scenario: User token file is never tracked
- **WHEN** the user creates `forlabs-session.json` with their own token
- **THEN** git treats the file as ignored and it cannot be staged by
  default

#### Scenario: Tracked JSON files carrying a non-placeholder token fail the privacy check
- **WHEN** a tracked JSON file contains a `session_token` other than the
  placeholder
- **THEN** the repository privacy test fails

#### Scenario: Malformed token file gives a clear configuration error
- **WHEN** `forlabs-session.json` exists but is not valid JSON or is not
  an object
- **THEN** the system raises a configuration error that does not include
  the file's contents
