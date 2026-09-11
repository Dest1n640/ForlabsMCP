import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from forlabs_mcp.client.client import ForlabsClient
from forlabs_mcp.config import ForlabsConfig
from forlabs_mcp.tools.register import register_tools

BASE_URL = "https://bki.forlabs.ru"
FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _config(tmp_path) -> ForlabsConfig:
    return ForlabsConfig(
        username="student.login",
        password="super-secret-password",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
    )


def _mock_login_success() -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )


def _run(coro):
    return asyncio.run(coro)


def _build_server(tmp_path) -> MCPServer:
    server = MCPServer("forlabs")
    register_tools(server, lambda: ForlabsClient(_config(tmp_path)))
    return server


def test_only_four_read_only_tools_are_registered(tmp_path) -> None:
    server = _build_server(tmp_path)
    tools = _run(server.list_tools())
    assert {t.name for t in tools} == {"reference", "grades", "homework", "schedule"}


@respx.mock
def test_each_tool_dispatches_and_matches_its_contract_shape(tmp_path) -> None:
    _mock_login_success()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json=_load("sched_get_grid.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=_load("sched_get_schedule.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=_load("learning_get_scores.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json=_load("learning_get_tasks.json"))
    )

    server = _build_server(tmp_path)

    reference_result = _run(server.call_tool("reference", {}))
    assert not reference_result.is_error
    assert set(reference_result.structured_content) == {
        "identity",
        "own_stream_id",
        "streams",
        "studies",
        "warnings",
    }

    grades_result = _run(server.call_tool("grades", {}))
    assert not grades_result.is_error
    assert {"scores", "warnings"} <= set(grades_result.structured_content)

    homework_result = _run(server.call_tool("homework", {}))
    assert not homework_result.is_error
    assert {"homework", "warnings"} <= set(homework_result.structured_content)

    schedule_result = _run(
        server.call_tool("schedule", {"start": "2026-03-02", "end": "2026-03-15"})
    )
    assert not schedule_result.is_error
    assert set(schedule_result.structured_content) == {
        "range",
        "timezone",
        "week_variants",
        "week_parity_basis",
        "lessons",
        "warnings",
    }


@respx.mock
def test_forlabs_error_surfaces_as_classified_tool_error(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            422, json={"errors": {"username": ["Неверный логин или пароль"]}}
        )
    )

    server = _build_server(tmp_path)

    with pytest.raises(ToolError) as exc_info:
        _run(server.call_tool("reference", {}))

    message = str(exc_info.value)
    assert "Authentication failed" in message
    assert "super-secret-password" not in message
