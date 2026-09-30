## Context

`load_config()` in `src/forlabs_mcp/config.py` resolves every setting through
an inner `resolve(key, env_var, default)`: a truthy env value wins, else the
JSON file's key, else the default. A truthy check already makes an *empty*
env value fall through, but a literal `${FORLABS_SESSION_TOKEN}` (what hosts
like Hermes Agent pass when they do not interpolate `env`) is truthy and is
used as the token. See proposal.md - Why.

Constraints observed in the code:

- The server speaks MCP over stdio, so stdout is the protocol channel; any
  diagnostics must go to stderr.
- The project has no logging setup today (no `logging` usage in `src/`), and
  config is loaded lazily on the first tool call, not at process start.
- Real session tokens (`remember_lm_` cookie values) are URL-safe/hex-like
  strings and cannot contain `$`, `{` or `}`.

## Goals / Non-Goals

**Goals:**

- A literal `${...}` env value never becomes a setting; resolution falls
  through to the JSON file, then the default.
- The behaviour is diagnosable without echoing values.

**Non-Goals:**

- Interpolating `${VAR}` ourselves (expanding it from `os.environ` is
  pointless: the variable is by definition not set in our process).
- Handling `$VAR` (no braces), `%VAR%`, or `{{VAR}}` syntaxes.
- Validating token *shape* beyond the placeholder check.
- Changing how a placeholder inside `forlabs-session.json` is handled (the
  existing `PASTE_...` template check stays as is).

## Decisions

**1. Fix in code, and document, rather than documentation only.** The issue
offered either. Documentation alone leaves a silent failure mode: the user
has a valid `forlabs-session.json` and still gets an auth error caused by
host config they may not control. A small guard in `resolve()` removes the
failure; the README note explains the cleaner setup (omit `env` when using
the JSON file).

**2. Detect with one module-level regex, `\$\{[^}]*\}`, using `search`.**
`search` rather than `fullmatch` so partial values like `Bearer ${TOKEN}` or
`https://${HOST}` are also rejected: any surviving `${...}` is by definition
an uninterpolated template, and no legitimate value for any of the six
settings contains one. Alternatives considered:

- `fullmatch` on the whole value: narrower, but misses composite values.
- Reject any `$`: would be simpler but broader than the reported problem and
  could in theory reject a legitimate path.

**3. Apply the check to all env-backed settings inside `resolve()`, not only
the token.** The same host misbehaviour hits `FORLABS_BASE_URL`, `FORLABS_TZ`
etc. Doing it in the single shared `resolve()` keeps one code path and
avoids a token-only special case.

**4. Warn via stdlib `logging` (`logging.getLogger(__name__).warning`).** The
message names the env var only (e.g. "FORLABS_SESSION_TOKEN contains an
unexpanded ${...} placeholder; ignoring it"). The value is never logged
because a composite value could carry a partially real secret. With no
handler configured, Python's last-resort handler writes warnings to stderr,
which is safe for stdio MCP and needs no new setup. Alternatives:
`warnings.warn` (deduplicated per location, wrong tool for runtime config
hints) and `print(..., file=sys.stderr)` (not testable via `caplog`, no level).

**5. No change to precedence or to the missing-token error.** After the
placeholder is skipped, an absent JSON token yields the existing
`ConfigError(key="session_token")`, which already happens before any network
call.

## Risks / Trade-offs

- [Warning is emitted on each `load_config()` call] → `load_config()` runs
  once per client creation (the client is cached in `server.py`), so this is
  a single line per process in practice.
- [A legitimate value containing `${...}` is silently ignored] → Extremely
  unlikely for these settings; the warning names the variable so it is not
  silent.
- [Host omits `env` interpolation *and* user has no JSON file] → They get the
  standard "Missing required setting: session_token" error, plus the
  warning explaining why the env value was skipped.
