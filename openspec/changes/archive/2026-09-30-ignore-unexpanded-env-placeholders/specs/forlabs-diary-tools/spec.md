## MODIFIED Requirements

### Requirement: Layered, validated configuration
The system SHALL resolve each setting (`session_token`, base URL, timeout,
timezone, session cache path, max list items) with precedence: environment
variable, then the repo-local JSON token file, then built-in default. An
environment variable whose value contains an unexpanded `${...}` placeholder
(as passed literally by an MCP host that does not interpolate its `env`
block) SHALL be treated as unset, so resolution continues to the next
source. When such a value is skipped, the system SHALL log a warning naming
the environment variable and SHALL NOT include its value. No other
configuration source (including any TOML file under the user's home
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

#### Scenario: Unexpanded placeholder in the environment falls through to the JSON file
- **WHEN** `FORLABS_SESSION_TOKEN` is set to the literal string
  `${FORLABS_SESSION_TOKEN}` and the JSON token file contains a
  non-placeholder `session_token`
- **THEN** the JSON file's value is used as the session token

#### Scenario: Unexpanded placeholder with no other source is a missing token
- **WHEN** `FORLABS_SESSION_TOKEN` is set to an unexpanded `${...}`
  placeholder and no JSON token file supplies a `session_token`
- **THEN** the system raises a configuration error naming `session_token`
  and makes no request to the backend

#### Scenario: Unexpanded placeholder in an optional setting falls back to the default
- **WHEN** an optional setting's environment variable (for example
  `FORLABS_BASE_URL`) is set to an unexpanded `${...}` placeholder and the
  JSON token file does not set it
- **THEN** the built-in default is used for that setting

#### Scenario: Skipped placeholder is reported without its value
- **WHEN** an environment variable is skipped because its value is an
  unexpanded `${...}` placeholder
- **THEN** a warning naming that environment variable is logged, and the
  skipped value does not appear in the log output

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
