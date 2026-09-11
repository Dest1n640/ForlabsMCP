#!/usr/bin/env python3
"""Print the {command, args, env} object an MCP host needs to register
this server (Claude Desktop, Claude Code, Hermes Agent, or any other
host that accepts a command/args/env-shaped definition).

Dependency-free by design: only the standard library, so it runs even
before `uv sync` has been done. Credential fields are always
placeholders - never real values, even if FORLABS_USERNAME/
FORLABS_PASSWORD happen to be set in the environment this script runs
in - the user fills them in themselves.
"""

from __future__ import annotations

import json
from pathlib import Path


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


def main() -> None:
    print(json.dumps(build_config(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
