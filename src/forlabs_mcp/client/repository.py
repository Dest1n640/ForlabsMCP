"""The one RPC primitive: POST /lm-vendor/repositories/<module>/<action>.

The read-only allow-list is checked here, before any HTTP request is
constructed, so it is the single choke point every caller must go through -
see PROJECT-REFERENCE.md §2.3-2.4 and design.md's "allow-list lives in
client/repository.py" decision.
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
    }
)


class Repository:
    """Enforces the read-only allow-list and interprets the RPC envelope."""

    def __init__(self, session: ForlabsSession) -> None:
        self._session = session

    def call(self, module: str, action: str, params: dict[str, Any] | None = None) -> Any:
        if (module, action) not in READ_ONLY_ACTIONS:
            raise ProgrammingError(
                f"Action '{module}/{action}' is not on the read-only allow-list."
            )

        response = self._session.request(
            "POST", f"/lm-vendor/repositories/{module}/{action}", params or {}
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
