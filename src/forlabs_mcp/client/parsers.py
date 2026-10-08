"""Tolerant payload -> model parsing.

A row that fails to validate becomes a warning on the returned
PartialResult; the rest of the payload is still returned. See
design.md's "Tolerant parsing uses pydantic models" decision and
specs/forlabs-diary-tools/spec.md's "Partial results on malformed data".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TypeVar

from pydantic import ValidationError

from .models import (
    Assignment,
    AssignmentComment,
    Chapter,
    Course,
    CurrentUser,
    Lesson,
    ScheduleGrid,
    Score,
    Stream,
    Study,
    Task,
)
from .partial import PartialResult

ModelT = TypeVar("ModelT")


def _parse_rows(
    rows: Iterable[Mapping[str, Any]], model: type[ModelT], label: str
) -> PartialResult[list[ModelT]]:
    data: list[ModelT] = []
    warnings: list[str] = []
    for row in rows:
        try:
            data.append(model.model_validate(row))  # type: ignore[attr-defined]
        except ValidationError as exc:
            identifier = row.get("id") if isinstance(row, Mapping) else None
            detail = exc.errors()[0]["msg"] if exc.errors() else str(exc)
            warnings.append(f"Skipped malformed {label} row (id={identifier}): {detail}")
    return PartialResult(data=data, warnings=warnings)


def parse_streams(raw: Iterable[Mapping[str, Any]]) -> PartialResult[list[Stream]]:
    return _parse_rows(raw, Stream, "stream")


def parse_studies(raw: Iterable[Mapping[str, Any]]) -> PartialResult[list[Study]]:
    return _parse_rows(raw, Study, "study")


def parse_lessons(raw: Iterable[Mapping[str, Any]]) -> PartialResult[list[Lesson]]:
    return _parse_rows(raw, Lesson, "lesson")


def parse_tasks(raw: Iterable[Mapping[str, Any]]) -> PartialResult[list[Task]]:
    return _parse_rows(raw, Task, "task")


def parse_assignments(raw: Iterable[Mapping[str, Any]]) -> PartialResult[list[Assignment]]:
    return _parse_rows(raw, Assignment, "assignment")


def parse_scores(raw: Mapping[str, Mapping[str, Any]]) -> PartialResult[list[Score]]:
    return _parse_rows(raw.values(), Score, "score")


def parse_schedule_grid(raw: Mapping[str, Any]) -> ScheduleGrid:
    """Grid is a single object, not a row list - a malformed grid has no
    partial subset to salvage, so this simply validates and lets a bad
    payload raise."""
    return ScheduleGrid.model_validate(raw)


def parse_assignment_comments(
    raw: Iterable[Mapping[str, Any]],
) -> PartialResult[list[AssignmentComment]]:
    return _parse_rows(raw, AssignmentComment, "assignment comment")


def parse_chapters(raw: Iterable[Mapping[str, Any]]) -> PartialResult[list[Chapter]]:
    return _parse_rows(raw, Chapter, "chapter")


def parse_course(raw: Mapping[str, Any]) -> Course:
    """A course is a single object; a malformed one has no partial subset, so
    validate and let a bad payload raise (mirrors ``parse_schedule_grid``)."""
    return Course.model_validate(raw)


def parse_current_user(raw: Mapping[str, Any]) -> CurrentUser:
    """The profile endpoint returns one user object; validate or raise."""
    return CurrentUser.model_validate(raw)
