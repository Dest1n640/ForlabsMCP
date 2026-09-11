"""Registers the four read-only MCP tools onto an MCPServer instance.

Each tool: validate args (delegated to the client layer, which raises
before any backend call for bad arguments) -> call the client -> catch
ForlabsError -> raise ToolError with a classified, credential-free
message. No raw exception or stack trace ever reaches tool output.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..client.client import ForlabsClient
from ..errors import ForlabsError, to_tool_error


def register_tools(server: MCPServer, client_factory: Callable[[], ForlabsClient]) -> None:
    @server.tool()
    def reference(stream_id: int | None = None) -> dict[str, Any]:
        try:
            return client_factory().reference(stream_id=stream_id)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def grades(stream_id: int | None = None, study_id: int | None = None) -> dict[str, Any]:
        try:
            return client_factory().scores(stream_id=stream_id, study_id=study_id)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def homework(
        stream_id: int | None = None,
        study_id: int | None = None,
        only_outstanding: bool = False,
    ) -> dict[str, Any]:
        try:
            return client_factory().homework(
                stream_id=stream_id, study_id=study_id, only_outstanding=only_outstanding
            )
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def schedule(
        date: str | None = None, start: str | None = None, end: str | None = None
    ) -> dict[str, Any]:
        try:
            return client_factory().schedule_raw(date=date, start=start, end=end)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc
