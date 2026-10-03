## ADDED Requirements

### Requirement: Recovery from a stale short-lived session
When an authenticated data call is answered with an
authentication-classified status (`401` or `419`), the system SHALL
assume first that its short-lived session state (the session cookie and
the CSRF token) is stale, not that the configured `session_token` is
dead. It SHALL discard all session state except the long-lived
remember cookie built from the configured `session_token`, obtain a
fresh CSRF token from the backend, and retry the same call exactly once.
A successful retry SHALL be returned to the caller as if the first
attempt had succeeded, and the renewed session state SHALL replace the
stale state in the local session cache. The recovery SHALL NOT submit a
password or issue `POST /app/login`, and SHALL NOT retry more than once
per call.

#### Scenario: Stale cached session recovers transparently
- **WHEN** the local session cache holds an expired short-lived session
  while the configured `session_token` is still valid, and a data call is
  answered with `419`
- **THEN** the call is retried once with fresh session state, returns the
  backend's data, and the session cache is rewritten with the renewed
  session state

#### Scenario: Long-running process outlives its short session
- **WHEN** a process that already made successful calls makes another
  call after the backend expired its short-lived session, and that call is
  answered with `401` or `419`
- **THEN** the call is retried once with fresh session state and succeeds
  without surfacing an error

#### Scenario: Recovery never logs in with credentials
- **WHEN** a data call is retried after an authentication-classified
  status
- **THEN** no `POST /app/login` request is sent and no password is
  transmitted

#### Scenario: A failure that is not authentication-classified is not retried
- **WHEN** a data call fails with a status other than `401` or `419`
- **THEN** the call is not retried by this recovery

## MODIFIED Requirements

### Requirement: Terminal error on session-token expiry
When an authenticated data call is still answered with an
authentication-classified status (`401` or `419`) after the single
stale-session recovery retry, the system SHALL surface one
authentication error and SHALL NOT retry again or attempt any
credential-based recovery, since no credential is configured. The error
message SHALL name the cause. A `401` on the retry means the backend
rejected the configured `session_token`, and the message SHALL tell the
user to get a fresh `session_token` from their browser and update their
configuration. A `419` on the retry means the backend refused the
request's CSRF token even with fresh session state, and the message SHALL
say so without telling the user to replace the `session_token`. The
message SHALL NOT contain the `session_token` value in either case.

#### Scenario: Expired session token surfaces an actionable error
- **WHEN** a data call is answered with `401` both on the first attempt
  and on the single recovery retry
- **THEN** the system raises an authentication error telling the user to
  supply a fresh `session_token`, after exactly one retry and without
  attempting to log in with credentials

#### Scenario: Persistent CSRF mismatch is not blamed on the token
- **WHEN** a data call is answered with `419` both on the first attempt
  and on the single recovery retry
- **THEN** the system raises an authentication error that reports a CSRF
  rejection and does not tell the user to replace their `session_token`

#### Scenario: Terminal error never leaks the token
- **WHEN** the system raises the terminal authentication error for either
  cause
- **THEN** the error message does not contain the configured
  `session_token` value
