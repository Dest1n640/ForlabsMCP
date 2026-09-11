"""ForlabsClient: the only class the tools call.

Joins studies to scores/tasks, resolves the account's "own stream" from
sched/get_schedule's meta.stream_ids, and returns the typed results the
four MCP tools serve.
"""

from __future__ import annotations

from typing import Any

from ..config import ForlabsConfig
from ..errors import ForlabsError
from .models import Identity, Stream, Study, TaskFile
from .parsers import parse_assignments, parse_scores, parse_streams, parse_studies, parse_tasks
from .partial import PartialResult, combine
from .repository import Repository
from .session import ForlabsSession

SCORE_STATUS_LABELS = {1: "in progress", 2: "in progress", 5: "completed"}
HOMEWORK_DONE_STATUSES = {3}


def _stream_to_dict(stream: Stream) -> dict[str, Any]:
    return {"id": stream.id, "name": stream.name, "is_own": stream.is_own}


def _task_file_to_dict(task_file: TaskFile) -> dict[str, Any]:
    return {
        "id": task_file.id,
        "filename": task_file.filename,
        "url": task_file.url,
        "size": task_file.size,
        "human_size": task_file.human_size,
    }


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

    def _discover_own_stream(self) -> tuple[int | None, PartialResult[list[Stream]]]:
        """Return (own_stream_id, all known streams with is_own flagged)."""
        schedule_payload = self._repository.call("sched", "get_schedule", {})
        meta = schedule_payload.get("meta", {}) if isinstance(schedule_payload, dict) else {}
        stream_ids = meta.get("stream_ids") or []
        own_stream_id = stream_ids[0] if stream_ids else None

        streams_result = parse_streams(schedule_payload.get("streams", []))
        for stream in streams_result.data:
            stream.is_own = stream.id in stream_ids
        return own_stream_id, streams_result

    def _fetch_studies(self, stream_id: int | None) -> PartialResult[list[Study]]:
        studies_payload = self._repository.call("learning", "get_studies", {"stream_id": stream_id})
        raw_studies = (
            studies_payload.get("studies", []) if isinstance(studies_payload, dict) else []
        )
        return parse_studies(raw_studies)

    def reference(self, stream_id: int | None = None) -> dict[str, Any]:
        warnings: list[str] = []

        own_stream_id, streams_result = self._discover_own_stream()
        warnings.extend(streams_result.warnings)

        target_stream_id = stream_id if stream_id is not None else own_stream_id
        studies_result = self._fetch_studies(target_stream_id)
        warnings.extend(studies_result.warnings)

        return {
            "identity": Identity().model_dump(),
            "own_stream_id": own_stream_id,
            "streams": [_stream_to_dict(s) for s in streams_result.data],
            "studies": [_study_to_dict(s) for s in studies_result.data],
            "warnings": warnings,
        }

    def scores(self, stream_id: int | None = None, study_id: int | None = None) -> dict[str, Any]:
        warnings: list[str] = []

        if stream_id is not None:
            target_stream_id = stream_id
        else:
            own_stream_id, _ = self._discover_own_stream()
            target_stream_id = own_stream_id

        scores_payload = self._repository.call(
            "learning", "get_scores", {"stream_id": target_stream_id}
        )
        raw_scores = scores_payload.get("scores", {}) if isinstance(scores_payload, dict) else {}
        scores_result = parse_scores(raw_scores)
        warnings.extend(scores_result.warnings)

        studies_result = self._fetch_studies(target_stream_id)
        warnings.extend(studies_result.warnings)
        studies_by_id = {study.id: study for study in studies_result.data}

        rows: list[dict[str, Any]] = []
        for score in scores_result.data:
            if study_id is not None and score.study_id != study_id:
                continue
            study = studies_by_id.get(score.study_id)
            row: dict[str, Any] = {
                "study_id": score.study_id,
                "study_name": study.name if study is not None else None,
                "credits": score.credits,
                "status": score.status,
                "status_label": SCORE_STATUS_LABELS.get(score.status, "unknown"),
                "grade": score.grade,
            }
            if study is None:
                row["name_note"] = "name not found"
            rows.append(row)

        result: dict[str, Any] = {"scores": rows, "warnings": warnings}
        if not rows:
            result["note"] = "No grades found for the given filters."
        return result

    def homework(
        self,
        stream_id: int | None = None,
        study_id: int | None = None,
        only_outstanding: bool = False,
    ) -> dict[str, Any]:
        if stream_id is not None:
            target_stream_id = stream_id
        else:
            own_stream_id, _ = self._discover_own_stream()
            target_stream_id = own_stream_id

        studies_result = self._fetch_studies(target_stream_id)
        warnings: list[str] = list(studies_result.warnings)
        studies_by_id = {study.id: study for study in studies_result.data}

        target_study_ids = (
            [study_id] if study_id is not None else [study.id for study in studies_result.data]
        )

        per_study_results = [
            self._homework_for_study(target_stream_id, sid, studies_by_id)
            for sid in target_study_ids
        ]
        combined = combine(per_study_results)
        warnings.extend(combined.warnings)
        rows = combined.data

        if only_outstanding:
            rows = [row for row in rows if not row["is_done"]]

        result: dict[str, Any] = {"homework": rows, "warnings": warnings}
        if not rows:
            result["note"] = "No homework found for the given filters."
        return result

    def _homework_for_study(
        self, stream_id: int | None, study_id: int, studies_by_id: dict[int, Study]
    ) -> PartialResult[list[dict[str, Any]]]:
        try:
            payload = self._repository.call(
                "learning",
                "get_tasks",
                {"stream_id": str(stream_id), "study_id": str(study_id)},
            )
        except ForlabsError as exc:
            return PartialResult(
                data=[], warnings=[f"Failed to fetch homework for study {study_id}: {exc}"]
            )

        raw_tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        raw_assignments = payload.get("assignments", []) if isinstance(payload, dict) else []
        tasks_result = parse_tasks(raw_tasks)
        assignments_result = parse_assignments(raw_assignments)
        warnings = list(tasks_result.warnings) + list(assignments_result.warnings)

        assignments_by_task_id = {a.task_id: a for a in assignments_result.data}
        study = studies_by_id.get(study_id)

        rows: list[dict[str, Any]] = []
        for task in tasks_result.data:
            assignment = assignments_by_task_id.get(task.id)
            status = assignment.status if assignment is not None else None
            rows.append(
                {
                    "task_id": task.id,
                    "title": task.name,
                    "study_id": study_id,
                    "study_name": study.name if study is not None else None,
                    "status": status,
                    "is_done": status in HOMEWORK_DONE_STATUSES,
                    "credits_earned": assignment.credits if assignment is not None else None,
                    "max_credits": task.max_credits,
                    "due_at": task.due_at,
                    "assessed_at": assignment.assessed_at if assignment is not None else None,
                    "chapter": task.chapter_title,
                    "files": [_task_file_to_dict(f) for f in task.files],
                }
            )
        return PartialResult(data=rows, warnings=warnings)
