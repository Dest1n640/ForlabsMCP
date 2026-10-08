import asyncio
import subprocess
import sys
import time

import pytest

from forlabs_mcp.server import build_server


def test_build_server_registers_safe_tools_without_loading_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FORLABS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FORLABS_ENABLE_ASSIGNMENT_SUBMISSION", raising=False)

    server = build_server()

    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "reference",
        "schedule_groups",
        "schedule",
        "grades",
        "homework",
        "study_materials",
        "task_files",
        "assignment_details",
        "assignment_thread",
        "preview_assignment_response",
    }


def test_build_server_registers_write_tool_only_when_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FORLABS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("FORLABS_ENABLE_ASSIGNMENT_SUBMISSION", "true")

    tools = asyncio.run(build_server().list_tools())

    assert "submit_assignment_response" in {tool.name for tool in tools}


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
