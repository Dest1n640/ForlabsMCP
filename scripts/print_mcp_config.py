#!/usr/bin/env python3
"""Print the config an MCP host needs to register this server (Claude
Desktop, Claude Code, Hermes Agent, or any other host that accepts a
command/args/env-shaped definition).

By default this prints the bare {command, args, env} object. Pass
--host to get a ready-to-paste form for a specific host instead:

  --host raw             the bare {command, args, env} object (default)
  --host claude-desktop  wrapped as {"mcpServers": {"forlabs": ...}}
  --host claude-code     a ready `claude mcp add-json forlabs '...'` command

Dependency-free by design: only the standard library, so it runs even
before `uv sync` has been done. Credential fields are always
placeholders - never real values, even if FORLABS_USERNAME/
FORLABS_PASSWORD happen to be set in the environment this script runs
in - the user fills them in themselves.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_HOSTS = ("raw", "claude-desktop", "claude-code")


def build_config() -> dict:
    repo_root = Path(__file__).resolve().parent.parent
    return {
        "command": "uv",
        "args": ["--directory", str(repo_root), "run", "forlabs-mcp"],
        "env": {
            "FORLABS_USERNAME": "your.login",
            "FORLABS_PASSWORD": "your-password",
        },
    }


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
