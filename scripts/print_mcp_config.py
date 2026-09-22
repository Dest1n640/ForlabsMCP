#!/usr/bin/env python3
"""Print the config an MCP host needs to register this server (Claude
Desktop, Claude Code, Hermes Agent, or any other host that accepts a
command/args/env-shaped definition).

By default this prints the bare {command, args, env} object. Pass
--host to get a ready-to-paste form for a specific host instead:

  --host raw             the bare {command, args, env} object (default)
  --host claude-desktop  wrapped as {"mcpServers": {"forlabs": ...}}
  --host claude-code     a ready `claude mcp add-json forlabs '...'` command

If `scripts/setup_config.py` has already saved a session_token to the
local TOML config file, the "env" block is left out entirely - the
server will pick the token up from that file at runtime, so there is
nothing left to type into the pasted command. Otherwise "env" carries a
placeholder credential field - never a real value, even if
FORLABS_SESSION_TOKEN happens to be set in the environment this script
runs in - the user fills it in themselves (or runs setup_config.py
instead).

Dependency-free by design: only the standard library, so it runs even
before `uv sync` has been done.
"""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from pathlib import Path

_HOSTS = ("raw", "claude-desktop", "claude-code")
_DEFAULT_CONFIG_FILE = "~/.config/forlabs-mcp/config.toml"


def _config_file_path() -> Path:
    override = os.environ.get("FORLABS_MCP_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path(_DEFAULT_CONFIG_FILE).expanduser()


def has_saved_credentials() -> bool:
    """True if the local TOML config file already has a non-empty
    session_token (typically written by scripts/setup_config.py)."""
    path = _config_file_path()
    if not path.is_file():
        return False
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    table = data.get("forlabs", data)
    if not isinstance(table, dict):
        return False
    return bool(table.get("session_token"))


def build_config() -> dict:
    repo_root = Path(__file__).resolve().parent.parent
    config: dict = {
        "command": "uv",
        "args": ["--directory", str(repo_root), "run", "forlabs-mcp"],
    }
    if not has_saved_credentials():
        config["env"] = {
            "FORLABS_SESSION_TOKEN": "your-session-token",
        }
    return config


def render(host: str) -> str:
    config = build_config()
    if host == "claude-desktop":
        return json.dumps({"mcpServers": {"forlabs": config}}, indent=2, ensure_ascii=False)
    if host == "claude-code":
        compact = json.dumps(config, ensure_ascii=False)
        return f"claude mcp add-json forlabs '{compact}'"
    return json.dumps(config, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--host",
        choices=_HOSTS,
        default="raw",
        help="Print a ready-to-use form for this host instead of the bare object.",
    )
    args = parser.parse_args()
    print(render(args.host))


if __name__ == "__main__":
    main()
