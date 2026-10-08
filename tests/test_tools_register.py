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
        session_token="remember-cookie-value",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
    )


def _mock_xsrf_prime() -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )


def _run(coro):
    return asyncio.run(coro)


def _build_server(tmp_path) -> MCPServer:
    server = MCPServer("forlabs")
    register_tools(server, lambda: ForlabsClient(_config(tmp_path)))
    return server


def test_only_schedule_and_own_scope_read_tools_are_registered_by_default(
    tmp_path,
) -> None:
    server = _build_server(tmp_path)
    tools = _run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "reference",
        "schedule_groups",
        "schedule",
        "grades",
        "homework",
        "assignment_details",
        "assignment_thread",
        "preview_assignment_response",
    }
    properties = {tool.name: tool.input_schema.get("properties", {}) for tool in tools}
    assert "stream_id" not in properties["reference"]
    assert "stream_id" not in properties["grades"]
    assert "stream_id" not in properties["homework"]
    assert "stream_id" in properties["schedule"]


def test_submit_tool_is_opt_in_and_marked_as_non_idempotent_write(tmp_path) -> None:
    disabled = _build_server(tmp_path)
    assert "submit_assignment_response" not in {tool.name for tool in _run(disabled.list_tools())}

    enabled = MCPServer("forlabs")
    register_tools(
        enabled,
        lambda: ForlabsClient(
            ForlabsConfig(
                session_token="remember-cookie-value",
                base_url=BASE_URL,
                session_path=tmp_path / "enabled-session.json",
                assignment_submission_enabled=True,
            )
        ),
        submission_enabled=True,
    )
    submit_tool = next(
        tool for tool in _run(enabled.list_tools()) if tool.name == "submit_assignment_response"
    )

    assert submit_tool.annotations.read_only_hint is False
    assert submit_tool.annotations.destructive_hint is True
    assert submit_tool.annotations.idempotent_hint is False
    assert submit_tool.annotations.open_world_hint is True
    assert set(submit_tool.input_schema["properties"]) == {"preparation_id"}


@respx.mock
def test_each_tool_dispatches_and_matches_its_contract_shape(tmp_path) -> None:
    _mock_xsrf_prime()
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

    groups_result = _run(server.call_tool("schedule_groups", {}))
    assert not groups_result.is_error
    assert {"groups", "own_stream_id", "warnings"} == set(groups_result.structured_content)

    schedule_result = _run(
        server.call_tool("schedule", {"start": "2026-03-02", "end": "2026-03-15"})
    )
    assert not schedule_result.is_error
    assert set(schedule_result.structured_content) == {
        "range",
        "timezone",
        "week_variants",
        "week_parity_basis",
        "stream_id",
        "stream_name",
        "lessons",
        "warnings",
    }


@respx.mock
def test_assignment_read_tools_dispatch_without_write_access(tmp_path) -> None:
    _mock_xsrf_prime()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=_load("sched_get_schedule.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json=_load("learning_get_tasks_assignments.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_task").mock(
        return_value=httpx.Response(200, json=_load("learning_get_task.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        return_value=httpx.Response(200, json=_load("assignments_get_comments.json"))
    )

    server = _build_server(tmp_path)
    details = _run(server.call_tool("assignment_details", {"study_id": 10823, "task_id": 7001}))
    thread = _run(server.call_tool("assignment_thread", {"study_id": 10823, "task_id": 7001}))

    assert not details.is_error
    assert details.structured_content["task"]["id"] == 7001
    assert not thread.is_error
    assert thread.structured_content["comments"][0]["id"] == 9001
    assert not any(
        action in str(call.request.url)
        for call in respx.calls
        for action in ("/assignments/post_comment", "/uploads/store", "/uploads/delete", "/upload")
    )

    preview = _run(
        server.call_tool(
            "preview_assignment_response",
            {"study_id": 10823, "task_id": 7001, "message": "synthetic preview"},
        )
    )
    assert not preview.is_error
    assert preview.structured_content["message"] == "synthetic preview"


@respx.mock
def test_forlabs_error_surfaces_as_classified_tool_error(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(419, json={"message": "session expired"})
    )

    server = _build_server(tmp_path)

    with pytest.raises(ToolError) as exc_info:
        _run(server.call_tool("reference", {}))

    message = str(exc_info.value)
    assert "Authentication failed" in message
    assert "remember-cookie-value" not in message
