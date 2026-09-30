## MODIFIED Requirements

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

### Requirement: Layered, validated configuration
The system SHALL resolve each setting (`session_token`, base URL, timeout,
timezone, session cache path, max list items) with precedence: environment
variable, then TOML config file, then built-in default. It SHALL validate
that `session_token` is present before making any network call, and SHALL
be able to render its own configuration with the `session_token` value
redacted for logging.

#### Scenario: Environment variable overrides the TOML file
- **WHEN** a setting is present both as an environment variable and in the
  TOML config file
- **THEN** the environment variable's value is used

#### Scenario: Missing session token fails before any network call
- **WHEN** the `session_token` setting is absent from every configuration
  source
- **THEN** the system raises a configuration error and makes no request to
  the backend

#### Scenario: Redacted configuration never exposes the session token
- **WHEN** the system's configuration is rendered for logging or
  diagnostics
- **THEN** the `session_token` value does not appear in that output

## REMOVED Requirements

### Requirement: Transparent re-authentication on session expiry
**Reason**: Re-authentication required submitting the configured
username/password to `/app/login`. With username/password removed from
the configuration surface (see the modified "Session authentication"
requirement), the system has no credential it can use to silently obtain
a new session once the long-lived `session_token` itself is rejected -
there is nothing left to "re-authenticate" with. (Renewal of the
short-lived session cookies while the `session_token` is still valid is
now covered by the modified "Session authentication" requirement's "A
data call renews the short-lived session cookies" scenario, and needs no
retry logic of its own.)
**Migration**: Replaced by the "Terminal error on session-token expiry"
requirement below. Operators who relied on unattended recovery from
session expiry must instead handle the resulting `AuthError` by supplying
a fresh `session_token`.

## ADDED Requirements

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
