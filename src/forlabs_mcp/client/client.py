"""ForlabsClient: the only class the tools call.

Joins studies to scores/tasks, resolves the account's "own stream" from
sched/get_schedule's meta.stream_ids, and returns the typed results the
four MCP tools serve.
"""

from __future__ import annotations

from typing import Any

from ..config import ForlabsConfig
from .models import Identity, Stream, Study
from .parsers import parse_streams, parse_studies
from .repository import Repository
from .session import ForlabsSession


def _stream_to_dict(stream: Stream) -> dict[str, Any]:
    return {"id": stream.id, "name": stream.name, "is_own": stream.is_own}


def _study_to_dict(study: Study) -> dict[str, Any]:
    return {
        "id": study.id,
        "name": study.name,
        "teachers": study.teachers,
        "year": study.study_year,
        "semester": study.semester,
        "is_current": study.is_current,
        "tasks_count": study.tasks_count,
        "exams_count": study.exams_count,
    }


class ForlabsClient:
    def __init__(self, config: ForlabsConfig) -> None:
        self._config = config
        self._session = ForlabsSession(config)
        self._repository = Repository(self._session)

    def reference(self, stream_id: int | None = None) -> dict[str, Any]:
        warnings: list[str] = []

        schedule_payload = self._repository.call("sched", "get_schedule", {})
        meta = schedule_payload.get("meta", {}) if isinstance(schedule_payload, dict) else {}
        stream_ids = meta.get("stream_ids") or []
        own_stream_id = stream_ids[0] if stream_ids else None

        streams_result = parse_streams(schedule_payload.get("streams", []))
        warnings.extend(streams_result.warnings)
        streams = streams_result.data
        for stream in streams:
            stream.is_own = stream.id in stream_ids

        target_stream_id = stream_id if stream_id is not None else own_stream_id
        studies_payload = self._repository.call(
            "learning", "get_studies", {"stream_id": target_stream_id}
        )
        studies_result = parse_studies(
            studies_payload.get("studies", []) if isinstance(studies_payload, dict) else []
        )
        warnings.extend(studies_result.warnings)

        return {
            "identity": Identity().model_dump(),
            "own_stream_id": own_stream_id,
            "streams": [_stream_to_dict(s) for s in streams],
            "studies": [_study_to_dict(s) for s in studies_result.data],
            "warnings": warnings,
        }
