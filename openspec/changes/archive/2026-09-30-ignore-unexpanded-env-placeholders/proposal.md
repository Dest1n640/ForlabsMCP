## Why

Some MCP hosts (e.g. Hermes Agent) do not interpolate `${VAR}` inside the
`env` block of their server config and pass the literal string through, so
the server is started with `FORLABS_SESSION_TOKEN="${FORLABS_SESSION_TOKEN}"`.
`load_config()` treats any non-empty env value as valid, so that literal
string wins over `forlabs-session.json` and is sent to the backend as the
session token. The user's real token in the JSON file is never consulted,
and the failure surfaces as a confusing authentication error instead of a
configuration problem.

## What Changes

- Treat an environment value that contains an unexpanded `${...}`
  placeholder as **unset** when resolving any setting, so resolution falls
  through to the JSON token file and then the built-in default. This mirrors
  how an empty env value is already ignored.
- Emit a one-line warning to stderr naming the affected environment
  variable (never its value) when a placeholder value is skipped, so a
  misconfigured host is diagnosable.
- Document in the README that hosts which do not interpolate `${...}` will
  have that value ignored, and that the cleanest setup with the JSON file is
  to omit the `env` block entirely.

Not changing: precedence order, the JSON file format, the `PASTE_...`
template placeholder handling, or `$VAR` (no braces) syntax.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `forlabs-diary-tools`: the "Layered, validated configuration" requirement
  gains the rule that an environment value that is an unexpanded `${...}`
  placeholder is treated as absent.

## Impact

- Code: `src/forlabs_mcp/config.py` (`load_config()` inner `resolve()`).
- Tests: `tests/test_config.py`.
- Docs: `README.md` (setup and settings sections).
- No change to tools, the client, or the session flow.
