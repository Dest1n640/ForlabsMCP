## MODIFIED Requirements

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

## ADDED Requirements

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
