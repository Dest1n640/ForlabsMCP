"""Read-only RPC allow-list plus fixed, opt-in assignment write operations.

The generic read call rejects every unlisted action before any HTTP request.
Assignment writes have separate fixed methods and never use that call path.
"""

from __future__ import annotations

from typing import Any

from ..errors import ProgrammingError, UpstreamError
from .session import ForlabsSession

READ_ONLY_ACTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("sched", "get_grid"),
        ("sched", "get_schedule"),
        ("learning", "get_streams"),
        ("learning", "get_studies"),
        ("learning", "get_scores"),
        ("learning", "get_tasks"),
        ("learning", "get_task"),
        ("assignments", "get_comments"),
    }
)


class Repository:
    """Enforces read and dedicated assignment-write boundaries."""

    def __init__(self, session: ForlabsSession, *, assignment_writes_enabled: bool = False) -> None:
        self._session = session
        self._assignment_writes_enabled = assignment_writes_enabled

    def call(self, module: str, action: str, params: dict[str, Any] | None = None) -> Any:
        if (module, action) not in READ_ONLY_ACTIONS:
            raise ProgrammingError(
                f"Action '{module}/{action}' is not on the read-only allow-list."
            )

        response = self._session.request(
            "POST", f"/lm-vendor/repositories/{module}/{action}", params or {}
        )
        return self._parse_response(module, action, response)

    def post_assignment_comment(
        self,
        *,
        study_id: str,
        task_id: int,
        assignment_id: int,
        message: str,
        file_ids: list[int],
    ) -> Any:
        return self._assignment_write(
            "assignments",
            "post_comment",
            {
                "study_id": study_id,
                "task_id": task_id,
                "assignment_id": assignment_id,
                "message": message,
                "files": file_ids,
                "mode": "student",
            },
        )

    def store_uploads(self, file_ids: list[int]) -> Any:
        return self._assignment_write("uploads", "store", {"files": file_ids})

    def delete_uploads(self, file_ids: list[int]) -> Any:
        return self._assignment_write("uploads", "delete", {"files": file_ids})

    def check_flow_chunk(self, params: dict[str, str | int]) -> Any:
        self._require_assignment_submission()
        return self._session.request("GET", "/lm-vendor/upload", params=params)

    def upload_flow_chunk(
        self,
        params: dict[str, str | int],
        *,
        filename: str,
        chunk: bytes,
        mime_type: str,
    ) -> Any:
        self._require_assignment_submission()
        return self._session.request(
            "POST",
            "/lm-vendor/upload",
            data=params,
            files={"file": (filename, chunk, mime_type)},
            retry_auth=False,
        )

    def _require_assignment_submission(self) -> None:
        if not self._assignment_writes_enabled:
            raise ProgrammingError("Assignment submission is disabled.")

    def _assignment_write(self, module: str, action: str, params: dict[str, Any]) -> Any:
        allowed = {
            ("assignments", "post_comment"),
            ("uploads", "store"),
            ("uploads", "delete"),
        }
        if not self._assignment_writes_enabled:
            raise ProgrammingError("Assignment submission is disabled.")
        if (module, action) not in allowed:
            raise ProgrammingError(f"Assignment write '{module}/{action}' is not permitted.")
        response = self._session.request(
            "POST",
            f"/lm-vendor/repositories/{module}/{action}",
            params,
            retry_auth=False,
        )
        return self._parse_response(module, action, response)

    @staticmethod
    def _parse_response(module: str, action: str, response: Any) -> Any:
        try:
            body = response.json()
        except ValueError:
            body = None

        if response.status_code >= 400:
            raise UpstreamError(
                f"Forlabs returned status {response.status_code} for {module}/{action}.",
                module=module,
                action=action,
            )
        if isinstance(body, dict) and set(body.keys()) == {"message"}:
            raise UpstreamError(str(body["message"]), module=module, action=action)
        return body
