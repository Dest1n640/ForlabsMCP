"""Typed models for Forlabs backend payloads.

Every model ignores unknown fields (`extra="ignore"`) so a new backend
field never breaks parsing - see PROJECT-REFERENCE.md §5 for the exact
backend-key -> model-field mapping these follow.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class _ForlabsModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Identity(_ForlabsModel):
    """No identity endpoint exists on the backend; always {name: None, role: None}."""

    name: str | None = None
    role: str | None = None


class Stream(_ForlabsModel):
    id: int
    name: str
    is_own: bool = False


class Study(_ForlabsModel):
    id: int
    stream_id: int | None = None
    subject_id: int | None = None
    course_id: int | None = None
    semester: int = Field(alias="curr_sem")
    study_year: int = Field(alias="curr_year")
    status: int
    name: str = Field(alias="verbose_name")
    short_name: str | None = None
    type: int | None = None
    year_id: int | None = None
    year_name: str | None = None
    session: int | None = None
    lecturers: list[dict[str, Any]] = Field(default_factory=list)
    lecturers_count: int = 0
    posts_count: int = 0
    chapters_count: int = 0
    tasks_count: int = 0
    exams_count: int = 0
    attendance_count: int = 0

    @property
    def is_current(self) -> bool:
        return self.status == 2

    @property
    def teachers(self) -> list[str]:
        return [lecturer.get("verbose_name", "") for lecturer in self.lecturers]


class ScheduleGrid(_ForlabsModel):
    days: dict[str, dict[str, Any]] = Field(default_factory=dict)
    positions: list[dict[str, str]] = Field(default_factory=list)
    lesson_name: str | None = None
    type: int | None = None
    week_variants: int = Field(alias="upperweek")

    @property
    def active_weekdays(self) -> list[int]:
        return [
            index for index, key in enumerate(_DAY_ORDER) if self.days.get(key, {}).get("active")
        ]


class Lesson(_ForlabsModel):
    day: int
    position: int
    kind: int = Field(alias="type")
    room_name: str | None = None
    lecturer_name: str | None = None
    study_id: int
    study_name: str
    subgroup: str = ""
    streams: list[dict[str, Any]] = Field(default_factory=list)


class Score(_ForlabsModel):
    study_id: int
    credits: float
    status: int
    grade: int


class TaskFile(_ForlabsModel):
    id: int
    type: str | None = None
    filename: str
    mime_type: str | None = None
    size: int | None = None
    url: str
    human_size: str | None = None


class Task(_ForlabsModel):
    id: int
    name: str
    description_html: str | None = Field(alias="content", default=None)
    type: int | None = None
    course_id: int | None = None
    chapter_id: int | None = None
    chapter_title: str | None = None
    chapter_has_content: bool = False
    level: int | None = None
    files: list[TaskFile] = Field(default_factory=list)
    pivot_status: int | None = None
    max_credits: float | None = Field(alias="pivot_cost", default=None)
    pivot_sort: int | None = None
    pivot_type: int | None = None
    pivot_start_at: str | None = None
    due_at: str | None = Field(alias="pivot_end_at", default=None)
    pivot_description: str | None = None


class Assignment(_ForlabsModel):
    id: int
    task_id: int
    status: int
    choice: Any | None = None
    variant: Any | None = None
    options: Any | None = None
    last_replied_at: str | None = None
    credits: float | None = Field(alias="assessment_credits", default=None)
    assessed_at: str | None = Field(alias="assessment_date", default=None)
    assessment_lecturer_id: int | None = None
    responses_count: int = 0


class AssignmentComment(_ForlabsModel):
    id: int
    user_id: int | None = None
    message: str
    created_at: str | None = None
    user: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
