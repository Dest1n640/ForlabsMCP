import asyncio
import subprocess
import sys
import time

import pytest

from forlabs_mcp.server import build_server


def test_build_server_registers_four_tools_without_loading_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FORLABS_USERNAME", raising=False)
    monkeypatch.delenv("FORLABS_PASSWORD", raising=False)

    server = build_server()

    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"reference", "grades", "homework", "schedule"}


def test_server_process_starts_over_stdio_without_a_live_backend_connection() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "forlabs_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.5)
        # Still running (blocked reading stdio) rather than crashed on
        # startup - proves no eager network/config access at import time.
        assert proc.poll() is None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
