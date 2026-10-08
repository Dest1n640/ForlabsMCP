"""Register the safe tools and the separately gated assignment-write tool.

Every call converts classified ``ForlabsError`` instances to ``ToolError``;
the submit tool is present only when the explicit submission switch is true.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..client.client import ForlabsClient
from ..errors import ForlabsError, to_tool_error


def register_tools(
    server: MCPServer,
    client_factory: Callable[[], ForlabsClient],
    *,
    submission_enabled: bool = False,
) -> None:
    @server.tool()
    def reference() -> dict[str, Any]:
        try:
            return client_factory().reference()
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def schedule_groups() -> dict[str, Any]:
        try:
            return client_factory().schedule_groups()
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def grades(study_id: int | None = None) -> dict[str, Any]:
        try:
            return client_factory().scores(study_id=study_id)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def homework(
        study_id: int | None = None,
        study_ids: list[int] | None = None,
        only_outstanding: bool = False,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        has_due: bool | None = None,
        due_from: str | None = None,
        due_to: str | None = None,
        has_feedback: bool | None = None,
    ) -> dict[str, Any]:
        try:
            return client_factory().homework(
                study_id=study_id,
                study_ids=study_ids,
                only_outstanding=only_outstanding,
                query=query,
                limit=limit,
                offset=offset,
                has_due=has_due,
                due_from=due_from,
                due_to=due_to,
                has_feedback=has_feedback,
            )
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def study_materials(study_id: int, include_content: bool = True) -> dict[str, Any]:
        try:
            return client_factory().study_materials(
                study_id=study_id, include_content=include_content
            )
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def task_files(study_id: int, task_id: int) -> dict[str, Any]:
        try:
            return client_factory().task_files(study_id=study_id, task_id=task_id)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def schedule(
        date: str | None = None,
        start: str | None = None,
        end: str | None = None,
        stream_id: int | None = None,
    ) -> dict[str, Any]:
        try:
            return client_factory().schedule_raw(
                date=date, start=start, end=end, stream_id=stream_id
            )
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def assignment_details(study_id: int, task_id: int) -> dict[str, Any]:
        try:
            return client_factory().assignment_details(study_id=study_id, task_id=task_id)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool()
    def assignment_thread(study_id: int, task_id: int) -> dict[str, Any]:
        try:
            return client_factory().assignment_thread(study_id=study_id, task_id=task_id)
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def preview_assignment_response(
        study_id: int,
        task_id: int,
        message: str,
        file_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return client_factory().preview_assignment_response(
                study_id=study_id,
                task_id=task_id,
                message=message,
                file_paths=file_paths,
            )
        except ForlabsError as exc:
            raise ToolError(to_tool_error(exc)) from exc

    if submission_enabled:

        @server.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        def submit_assignment_response(preparation_id: str) -> dict[str, Any]:
            try:
                return client_factory().submit_assignment_response(preparation_id=preparation_id)
            except ForlabsError as exc:
                raise ToolError(to_tool_error(exc)) from exc
