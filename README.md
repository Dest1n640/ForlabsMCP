# forlabs-mcp

A local [MCP](https://modelcontextprotocol.io) server that logs into the
Forlabs/Lamotivo school-diary SPA (`bki.forlabs.ru/app`) as a student and
exposes four **read-only** tools — `reference`, `schedule`, `grades`,
`homework` — so an MCP-capable assistant can answer questions against a
real diary.

**Read-only, by construction.** Every backend call goes through a single
primitive that checks a hardcoded allow-list of six read actions before
making any request — nothing this server does can write to, modify, or
delete anything on Forlabs. The only file it writes locally is a
session-cookie cache (mode `0600`).

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- A Forlabs/Lamotivo student account (the login/password you use at
  `bki.forlabs.ru/app/login` — not an email address)

## Setup

```bash
git clone <this-repo-url>
cd forlabs-mcp
uv sync
```

## Configuration

Every setting is resolved with this precedence: **environment variable >
TOML config file > built-in default.**

| Setting | Env var | Default | Required |
|---|---|---|---|
| Username | `FORLABS_USERNAME` | — | yes |
| Password | `FORLABS_PASSWORD` | — | yes |
| Base URL | `FORLABS_BASE_URL` | `https://bki.forlabs.ru` | no |
| Timeout (seconds) | `FORLABS_TIMEOUT_SECONDS` | `30` | no |
| Time zone | `FORLABS_TZ` | `Asia/Irkutsk` | no |
| Session cache path | `FORLABS_SESSION_PATH` | `~/.local/state/forlabs-mcp/session.json` | no |
| Max list items | `FORLABS_MAX_ITEMS` | `200` | no |

The username/password check happens before any network request — if
they're missing from every source, the server fails immediately with a
configuration error rather than trying to log in.

### Option A: environment variables

Set `FORLABS_USERNAME` and `FORLABS_PASSWORD` (and any optional overrides)
in the environment the server runs in. This is what
`scripts/print_mcp_config.py` (below) generates a template for.

### Option B: a TOML config file

By default the server looks for `~/.config/forlabs-mcp/config.toml`
(override the path with `FORLABS_MCP_CONFIG`). Either a `[forlabs]` table
or a bare top-level table works:

```toml
[forlabs]
username = "your.login"
password = "your-password"
# base_url, timeout_seconds, timezone, session_path, max_items are all optional
```

## Registering with an MCP host

Every MCP host wants the same three things: a **command**, its **args**,
and the **env** vars it needs. Generate that object with:

```bash
uv run python scripts/print_mcp_config.py
```

which prints (credential fields are always placeholders — fill in your
own login/password after pasting):

```json
{
  "command": "uv",
  "args": ["--directory", "<absolute-path-to-this-repo>", "run", "forlabs-mcp"],
  "env": {
    "FORLABS_USERNAME": "your.login",
    "FORLABS_PASSWORD": "your-password"
  }
}
```

### Claude Desktop

Paste the object under `mcpServers.forlabs` in your
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "forlabs": {
      "command": "uv",
      "args": ["--directory", "<absolute-path-to-this-repo>", "run", "forlabs-mcp"],
      "env": {
        "FORLABS_USERNAME": "your.login",
        "FORLABS_PASSWORD": "your-password"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add-json forlabs '{"command":"uv","args":["--directory","<absolute-path-to-this-repo>","run","forlabs-mcp"],"env":{"FORLABS_USERNAME":"your.login","FORLABS_PASSWORD":"your-password"}}'
```

### Hermes Agent

Use the same three fields as a YAML entry:

```yaml
forlabs:
  command: uv
  args: ["--directory", "<absolute-path-to-this-repo>", "run", "forlabs-mcp"]
  env:
    FORLABS_USERNAME: your.login
    FORLABS_PASSWORD: your-password
```

### Any other MCP client

Any host that accepts a command/args/env-shaped server definition can use
the same generated object directly — no project change needed to support
a new, previously undocumented client.

## Tools

- **`reference(stream_id?)`** — identity placeholder, own stream id, all
  known streams, and the student's full enrolment history.
- **`schedule(date?, start?, end?)`** — lessons placed on real calendar
  dates for a range (default: the current week). `date` and `start`/`end`
  are mutually exclusive.
- **`grades(stream_id?, study_id?)`** — scores joined to study names with
  human-readable status labels.
- **`homework(stream_id?, study_id?, only_outstanding?)`** — homework
  tasks across a stream's studies (or one study), optionally filtered to
  outstanding items only.

## Testing

```bash
uv run pytest              # fixture-backed unit tests, no live network
uv run ruff check .        # lint
uv run ruff format --check .  # format check
```
