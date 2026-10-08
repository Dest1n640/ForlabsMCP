"""ForlabsClient: the only class the tools call.

It resolves the authenticated student's own studies, maps schedule groups
separately, and orchestrates bounded assignment reads and opt-in submissions.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from ..config import ForlabsConfig
from ..dates import PlacedLesson, resolve_lessons, resolve_range
from ..errors import (
    ForlabsError,
    InvalidArgumentError,
    ProgrammingError,
    UpstreamError,
)
from .models import Assignment, Identity, Stream, Study, Task, TaskFile
from .parsers import (
    parse_assignment_comments,
    parse_assignments,
    parse_lessons,
    parse_schedule_grid,
    parse_scores,
    parse_streams,
    parse_studies,
    parse_tasks,
)
from .partial import PartialResult, combine
from .repository import Repository
from .session import ForlabsSession
from .submissions import (
    PREPARATION_TTL_SECONDS,
    PreparedFile,
    PreparedResponse,
    SubmissionPreparations,
)

SCORE_STATUS_LABELS = {1: "in progress", 2: "in progress", 5: "completed"}
HOMEWORK_DONE_STATUSES = {3}
FLOW_CHUNK_SIZE = 1024 * 1024
FLOW_SUCCESS_STATUSES = {200, 201, 202}


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


def _placed_lesson_to_dict(placed: PlacedLesson) -> dict[str, Any]:
    lesson = placed.lesson
    return {
        "date": placed.date.isoformat(),
        "weekday": placed.weekday,
        "start": placed.start,
        "end": placed.end,
        "position": lesson.position,
        "subject": lesson.study_name,
        "study_id": lesson.study_id,
        "kind": lesson.kind,
        "teacher": lesson.lecturer_name,
        "room": lesson.room_name,
        "subgroup": lesson.subgroup,
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
        self._repository = Repository(
            self._session,
            assignment_writes_enabled=config.assignment_submission_enabled,
        )
        self._preparations = SubmissionPreparations(config.upload_root)

    @staticmethod
    def _streams_from_schedule_payload(
        schedule_payload: Any,
    ) -> tuple[int | None, PartialResult[list[Stream]]]:
        payload = schedule_payload if isinstance(schedule_payload, dict) else {}
        meta = payload.get("meta", {})
        raw_stream_ids = meta.get("stream_ids", []) if isinstance(meta, dict) else []
        own_stream_ids = (
            [
                stream_id
                for stream_id in raw_stream_ids
                if isinstance(stream_id, int) and not isinstance(stream_id, bool)
            ]
            if isinstance(raw_stream_ids, list)
            else []
        )
        own_stream_id = own_stream_ids[0] if own_stream_ids else None

        streams_result = parse_streams(payload.get("streams", []))
        for stream in streams_result.data:
            stream.is_own = stream.id in own_stream_ids
        return own_stream_id, streams_result

    def _discover_own_stream(self) -> tuple[int | None, PartialResult[list[Stream]]]:
        """Return the own stream ID and schedule groups with own-group flags."""
        schedule_payload = self._repository.call("sched", "get_schedule", {})
        return self._streams_from_schedule_payload(schedule_payload)

    def _require_own_stream(self) -> tuple[int, PartialResult[list[Stream]]]:
        own_stream_id, streams_result = self._discover_own_stream()
        if own_stream_id is None:
            raise UpstreamError("The schedule response did not identify the authenticated stream.")
        return own_stream_id, streams_result

    def _fetch_studies(self, stream_id: int) -> PartialResult[list[Study]]:
        studies_payload = self._repository.call("learning", "get_studies", {"stream_id": stream_id})
        raw_studies = (
            studies_payload.get("studies", []) if isinstance(studies_payload, dict) else []
        )
        return parse_studies(raw_studies)

    def schedule_groups(self) -> dict[str, Any]:
        own_stream_id, streams_result = self._discover_own_stream()
        return {
            "own_stream_id": own_stream_id,
            "groups": [_stream_to_dict(stream) for stream in streams_result.data],
            "warnings": streams_result.warnings,
        }

    def reference(self) -> dict[str, Any]:
        own_stream_id, streams_result = self._require_own_stream()
        studies_result = self._fetch_studies(own_stream_id)
        return {
            "identity": Identity().model_dump(),
            "own_stream_id": own_stream_id,
            "streams": [_stream_to_dict(stream) for stream in streams_result.data],
            "studies": [_study_to_dict(study) for study in studies_result.data],
            "warnings": streams_result.warnings + studies_result.warnings,
        }

    def scores(self, study_id: int | None = None) -> dict[str, Any]:
        own_stream_id, _ = self._require_own_stream()
        scores_payload = self._repository.call(
            "learning", "get_scores", {"stream_id": own_stream_id}
        )
        raw_scores = scores_payload.get("scores", {}) if isinstance(scores_payload, dict) else {}
        scores_result = parse_scores(raw_scores)

        studies_result = self._fetch_studies(own_stream_id)
        studies_by_id = {study.id: study for study in studies_result.data}
        warnings = scores_result.warnings + studies_result.warnings

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
        study_id: int | None = None,
        only_outstanding: bool = False,
    ) -> dict[str, Any]:
        own_stream_id, _ = self._require_own_stream()
        studies_result = self._fetch_studies(own_stream_id)
        warnings: list[str] = list(studies_result.warnings)
        studies_by_id = {study.id: study for study in studies_result.data}

        if study_id is not None and study_id not in studies_by_id:
            raise InvalidArgumentError(
                "study_id must identify one of the authenticated student's studies.",
                argument="study_id",
            )
        target_study_ids = (
            [study_id] if study_id is not None else [study.id for study in studies_result.data]
        )

        per_study_results = [
            self._homework_for_study(own_stream_id, sid, studies_by_id) for sid in target_study_ids
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
        self, stream_id: int, study_id: int, studies_by_id: dict[int, Study]
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

        assignments_by_task_id = {
            assignment.task_id: assignment for assignment in assignments_result.data
        }
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
                    "files": [_task_file_to_dict(file) for file in task.files],
                }
            )
        return PartialResult(data=rows, warnings=warnings)

    def _own_task_context(
        self, study_id: int, task_id: int, *, require_assignment: bool
    ) -> tuple[int, Study, Task, Assignment | None, list[str]]:
        if (
            isinstance(study_id, bool)
            or not isinstance(study_id, int)
            or study_id <= 0
            or isinstance(task_id, bool)
            or not isinstance(task_id, int)
            or task_id <= 0
        ):
            raise InvalidArgumentError(
                "study_id and task_id must be positive integers.",
                argument="study_id/task_id",
            )

        own_stream_id, _ = self._require_own_stream()
        studies_result = self._fetch_studies(own_stream_id)
        study = next((item for item in studies_result.data if item.id == study_id), None)
        if study is None:
            raise InvalidArgumentError(
                "study_id must identify one of the authenticated student's studies.",
                argument="study_id",
            )

        payload = self._repository.call(
            "learning",
            "get_tasks",
            {"stream_id": str(own_stream_id), "study_id": str(study_id)},
        )
        raw_tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        raw_assignments = payload.get("assignments", []) if isinstance(payload, dict) else []
        tasks_result = parse_tasks(raw_tasks)
        assignments_result = parse_assignments(raw_assignments)
        matching_tasks = [task for task in tasks_result.data if task.id == task_id]
        if len(matching_tasks) != 1:
            raise InvalidArgumentError(
                "task_id must identify one task in the authenticated student's selected study.",
                argument="task_id",
            )

        matching_assignments = [
            assignment for assignment in assignments_result.data if assignment.task_id == task_id
        ]
        if len(matching_assignments) > 1:
            raise InvalidArgumentError(
                "The task has an ambiguous assignment mapping.",
                argument="task_id",
            )
        assignment = matching_assignments[0] if matching_assignments else None
        if require_assignment and assignment is None:
            raise InvalidArgumentError(
                "No unique assignment exists for this task.",
                argument="task_id",
            )
        warnings = studies_result.warnings + tasks_result.warnings + assignments_result.warnings
        return own_stream_id, study, matching_tasks[0], assignment, warnings

    def assignment_details(self, study_id: int, task_id: int) -> dict[str, Any]:
        own_stream_id, study, _, listed_assignment, warnings = self._own_task_context(
            study_id, task_id, require_assignment=False
        )
        payload = self._repository.call(
            "learning",
            "get_task",
            {
                "stream_id": str(own_stream_id),
                "study_id": str(study_id),
                "task_id": str(task_id),
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("task"), dict):
            raise UpstreamError("Forlabs returned a malformed task detail.")

        task_result = parse_tasks([payload["task"]])
        if not task_result.data or task_result.data[0].id != task_id:
            raise UpstreamError("Forlabs returned a task detail for a different task.")
        task = task_result.data[0]

        assignment: Assignment | None = None
        assignment_raw = payload.get("assignment")
        if isinstance(assignment_raw, dict):
            assignment_result = parse_assignments([assignment_raw])
            if assignment_result.data:
                assignment = assignment_result.data[0]
        if listed_assignment is not None and (
            assignment is None
            or assignment.id != listed_assignment.id
            or assignment.task_id != task_id
        ):
            raise UpstreamError("Forlabs task detail disagrees with the own-study assignment list.")

        warnings.extend(task_result.warnings)
        return {
            "study_id": study.id,
            "study_name": study.name,
            "task_id": task.id,
            "task": task.model_dump(),
            "assignment": assignment.model_dump() if assignment is not None else None,
            "warnings": warnings,
        }

    def _assignment_comments(
        self, study_id: int, task_id: int, assignment_id: int
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payload = self._repository.call(
            "assignments",
            "get_comments",
            {
                "study_id": str(study_id),
                "task_id": task_id,
                "assignment_id": assignment_id,
            },
        )
        raw_comments = payload.get("comments", []) if isinstance(payload, dict) else []
        if not isinstance(raw_comments, list):
            raw_comments = []
        result = parse_assignment_comments(raw_comments)
        return [comment.model_dump() for comment in result.data], result.warnings

    def assignment_thread(self, study_id: int, task_id: int) -> dict[str, Any]:
        _, study, task, assignment, warnings = self._own_task_context(
            study_id, task_id, require_assignment=True
        )
        if assignment is None:
            raise InvalidArgumentError(
                "No unique assignment exists for this task.", argument="task_id"
            )
        comments, comment_warnings = self._assignment_comments(study_id, task_id, assignment.id)
        result: dict[str, Any] = {
            "study_id": study.id,
            "study_name": study.name,
            "task_id": task.id,
            "task_title": task.name,
            "assignment_id": assignment.id,
            "status": assignment.status,
            "responses_count": assignment.responses_count,
            "comments": comments,
            "warnings": warnings + comment_warnings,
        }
        if not comments:
            result["note"] = "No responses have been sent for this assignment."
        return result

    def preview_assignment_response(
        self,
        study_id: int,
        task_id: int,
        message: str,
        file_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        _, study, task, assignment, warnings = self._own_task_context(
            study_id, task_id, require_assignment=True
        )
        if assignment is None:
            raise InvalidArgumentError(
                "No unique assignment exists for this task.", argument="task_id"
            )
        prepared = self._preparations.prepare(
            study_id=study.id,
            task_id=task.id,
            assignment_id=assignment.id,
            task_title=task.name,
            message=message,
            file_paths=file_paths,
        )
        return {
            "preparation_id": prepared.preparation_id,
            "study_id": study.id,
            "study_name": study.name,
            "task_id": task.id,
            "task_title": task.name,
            "assignment_id": assignment.id,
            "message": prepared.message,
            "attachments": [
                {
                    "name": file.name,
                    "size_bytes": file.size,
                    "mime_type": file.mime_type,
                }
                for file in prepared.files
            ],
            "expires_in_seconds": PREPARATION_TTL_SECONDS,
            "warnings": warnings,
        }

    def _upload_attachment(self, item: PreparedFile, file_ids: list[int]) -> None:
        total_chunks = max(1, math.ceil(item.size / FLOW_CHUNK_SIZE))
        digest = hashlib.sha256()
        attachment_id: int | None = None
        with self._preparations.open_prepared_file(item) as file:
            for chunk_number in range(1, total_chunks + 1):
                chunk = file.read(FLOW_CHUNK_SIZE)
                digest.update(chunk)
                params: dict[str, str | int] = {
                    "flowChunkNumber": chunk_number,
                    "flowChunkSize": FLOW_CHUNK_SIZE,
                    "flowCurrentChunkSize": len(chunk),
                    "flowTotalSize": item.size,
                    "flowIdentifier": item.flow_identifier,
                    "flowFilename": item.name,
                    "flowRelativePath": item.name,
                    "flowTotalChunks": total_chunks,
                }
                existing = self._repository.check_flow_chunk(params)
                if existing.status_code != 204:
                    raise UpstreamError(
                        "Could not confirm that the attachment chunk is absent.",
                        module="uploads",
                        action="check_chunk",
                    )
                response = self._repository.upload_flow_chunk(
                    params,
                    filename=item.name,
                    chunk=chunk,
                    mime_type=item.mime_type,
                )
                if response.status_code not in FLOW_SUCCESS_STATUSES:
                    raise UpstreamError(
                        f"Forlabs returned status {response.status_code} for uploads/chunk.",
                        module="uploads",
                        action="chunk",
                    )
                if chunk_number == total_chunks:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise UpstreamError(
                            "Forlabs did not return the uploaded attachment identifier.",
                            module="uploads",
                            action="chunk",
                        ) from exc
                    attachment = payload.get("attachment") if isinstance(payload, dict) else None
                    value = attachment.get("id") if isinstance(attachment, dict) else None
                    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                        raise UpstreamError(
                            "Forlabs did not return the uploaded attachment identifier.",
                            module="uploads",
                            action="chunk",
                        )
                    attachment_id = value
        if attachment_id is None:
            raise UpstreamError(
                "Forlabs did not return the uploaded attachment identifier.",
                module="uploads",
                action="chunk",
            )
        file_ids.append(attachment_id)
        if digest.hexdigest() != item.sha256:
            raise InvalidArgumentError(
                f"Attachment {item.name!r} changed during upload.", argument="file_paths"
            )

    def _cleanup_uploads(self, file_ids: list[int]) -> str:
        if not file_ids:
            return "not_needed"
        try:
            self._repository.delete_uploads(file_ids)
        except ForlabsError:
            return "failed"
        return "deleted"

    @staticmethod
    def _response_is_visible(
        comments: list[dict[str, Any]],
        previous_ids: set[int],
        prepared: PreparedResponse,
        file_ids: list[int],
    ) -> bool:
        for comment in comments:
            if comment.get("id") in previous_ids:
                continue
            if comment.get("message") != prepared.message:
                continue
            attachments = comment.get("attachments", [])
            attachment_ids = {
                attachment.get("id") for attachment in attachments if isinstance(attachment, dict)
            }
            if set(file_ids).issubset(attachment_ids):
                return True
        return False

    def _submission_readback(
        self,
        prepared: PreparedResponse,
        previous_ids: set[int],
        file_ids: list[int],
        *,
        request_accepted: bool,
        initial_warnings: list[str],
    ) -> dict[str, Any]:
        try:
            comments, warnings = self._assignment_comments(
                prepared.study_id, prepared.task_id, prepared.assignment_id
            )
        except ForlabsError:
            return {
                "submission_status": "accepted" if request_accepted else "uncertain",
                "read_back_status": "failed",
                "study_id": prepared.study_id,
                "task_id": prepared.task_id,
                "assignment_id": prepared.assignment_id,
                "comments": [],
                "warnings": initial_warnings,
                "note": (
                    "The response request was not retried. Read the assignment thread "
                    "before attempting another submission."
                ),
            }

        confirmed = self._response_is_visible(comments, previous_ids, prepared, file_ids)
        if confirmed:
            status = "confirmed"
            note = None
        elif request_accepted:
            status = "accepted"
            note = (
                "Forlabs accepted the request, but the response is not yet visible. "
                "Inspect the thread before attempting another submission."
            )
        else:
            status = "uncertain"
            note = (
                "The response request had an ambiguous outcome and was not retried. "
                "Inspect the thread before attempting another submission."
            )
        result = {
            "submission_status": status,
            "read_back_status": "confirmed" if confirmed else "not_visible",
            "study_id": prepared.study_id,
            "task_id": prepared.task_id,
            "assignment_id": prepared.assignment_id,
            "comments": comments,
            "warnings": initial_warnings + warnings,
        }
        if note is not None:
            result["note"] = note
        return result

    def submit_assignment_response(self, preparation_id: str) -> dict[str, Any]:
        if not self._config.assignment_submission_enabled:
            raise ProgrammingError("Assignment submission is disabled.")
        prepared = self._preparations.consume(preparation_id)
        _, _, _, assignment, warnings = self._own_task_context(
            prepared.study_id, prepared.task_id, require_assignment=True
        )
        if assignment is None or assignment.id != prepared.assignment_id:
            raise InvalidArgumentError(
                "The assignment changed after preview; prepare the response again.",
                argument="preparation_id",
            )

        self._preparations.verify_files(prepared)
        comments_before, thread_warnings = self._assignment_comments(
            prepared.study_id, prepared.task_id, prepared.assignment_id
        )
        previous_ids = {
            comment["id"] for comment in comments_before if isinstance(comment.get("id"), int)
        }
        initial_warnings = warnings + thread_warnings
        file_ids: list[int] = []
        try:
            for item in prepared.files:
                self._upload_attachment(item, file_ids)
            if file_ids:
                self._repository.store_uploads(file_ids)
        except ForlabsError:
            cleanup_status = self._cleanup_uploads(file_ids)
            if prepared.files and not file_ids:
                cleanup_status = "unknown"
            return {
                "submission_status": "not_sent",
                "upload_status": "failed",
                "cleanup_status": cleanup_status,
                "study_id": prepared.study_id,
                "task_id": prepared.task_id,
                "assignment_id": prepared.assignment_id,
                "warnings": initial_warnings,
                "note": (
                    "Attachment upload or finalization failed. No response was posted; "
                    "the preview was consumed."
                ),
            }

        try:
            self._repository.post_assignment_comment(
                study_id=str(prepared.study_id),
                task_id=prepared.task_id,
                assignment_id=prepared.assignment_id,
                message=prepared.message,
                file_ids=file_ids,
            )
        except ForlabsError:
            return self._submission_readback(
                prepared,
                previous_ids,
                file_ids,
                request_accepted=False,
                initial_warnings=initial_warnings,
            )
        return self._submission_readback(
            prepared,
            previous_ids,
            file_ids,
            request_accepted=True,
            initial_warnings=initial_warnings,
        )

    def schedule_raw(
        self,
        date: str | None = None,
        start: str | None = None,
        end: str | None = None,
        stream_id: int | None = None,
    ) -> dict[str, Any]:
        # Raises InvalidArgumentError before any backend call if date and
        # start/end are both given.
        range_start, range_end = resolve_range(date=date, start=start, end=end)
        if stream_id is not None and (
            isinstance(stream_id, bool) or not isinstance(stream_id, int) or stream_id <= 0
        ):
            raise InvalidArgumentError(
                "stream_id must be a positive integer.", argument="stream_id"
            )

        if stream_id is None:
            schedule_payload = self._repository.call("sched", "get_schedule", {})
            target_stream_id, streams_result = self._streams_from_schedule_payload(schedule_payload)
        else:
            _, streams_result = self._discover_own_stream()
            matches = [stream for stream in streams_result.data if stream.id == stream_id]
            if len(matches) != 1:
                raise InvalidArgumentError(
                    "stream_id must be one of the groups returned by schedule_groups.",
                    argument="stream_id",
                )
            target_stream_id = stream_id
            schedule_payload = self._repository.call(
                "sched", "get_schedule", {"stream_id": stream_id}
            )

        selected_stream = next(
            (stream for stream in streams_result.data if stream.id == target_stream_id), None
        )
        grid_payload = self._repository.call("sched", "get_grid", {})
        raw_grid = grid_payload.get("grid", {}) if isinstance(grid_payload, dict) else {}
        grid = parse_schedule_grid(raw_grid)
        raw_entries = (
            schedule_payload.get("entries", []) if isinstance(schedule_payload, dict) else []
        )
        lessons_result = parse_lessons(raw_entries)
        warnings = streams_result.warnings + lessons_result.warnings

        resolved = resolve_lessons(lessons_result.data, grid, range_start, range_end)
        lessons = [_placed_lesson_to_dict(placed) for placed in resolved.lessons]

        result: dict[str, Any] = {
            "range": f"{range_start.isoformat()} - {range_end.isoformat()}",
            "timezone": self._config.timezone,
            "week_variants": grid.week_variants,
            "week_parity_basis": resolved.week_parity_basis,
            "stream_id": target_stream_id,
            "stream_name": selected_stream.name if selected_stream is not None else None,
            "lessons": lessons,
            "warnings": warnings,
        }
        if not lessons:
            result["note"] = "No lessons found for the given range."
        return result
