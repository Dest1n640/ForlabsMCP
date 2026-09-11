"""Calendar math: turning the backend's abstract day/position lesson slots
into real calendar dates, and resolving the date range a `schedule` call
targets.

The backend never states which calendar week is "week_index 0" in its
alternating-week grid (PROJECT-REFERENCE.md §2.3) - `resolve_lessons()`
computes a provisional basis and always reports it, rather than silently
guessing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import timedelta

from .client.models import Lesson, ScheduleGrid
from .errors import InvalidArgumentError


def _parse_date(value: str, argument: str) -> date_cls:
    try:
        return date_cls.fromisoformat(value)
    except ValueError as exc:
        raise InvalidArgumentError(
            f"'{argument}' must be an ISO date (YYYY-MM-DD), got {value!r}.",
            argument=argument,
        ) from exc


def resolve_range(
    date: str | None = None, start: str | None = None, end: str | None = None
) -> tuple[date_cls, date_cls]:
    """Resolve an inclusive (start, end) date range.

    `date` and `start`/`end` are mutually exclusive. With no arguments, the
    default range is the current ISO week (Monday through Sunday).
    """
    if date is not None and (start is not None or end is not None):
        raise InvalidArgumentError(
            "'date' and 'start'/'end' are mutually exclusive.", argument="date"
        )

    if date is not None:
        resolved = _parse_date(date, "date")
        return resolved, resolved

    if start is not None or end is not None:
        if start is None or end is None:
            missing = "start" if start is None else "end"
            raise InvalidArgumentError(
                "'start' and 'end' must be provided together.", argument=missing
            )
        start_date = _parse_date(start, "start")
        end_date = _parse_date(end, "end")
        if end_date < start_date:
            raise InvalidArgumentError("'end' must not be before 'start'.", argument="end")
        return start_date, end_date

    today = date_cls.today()
    monday = today - timedelta(days=today.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


@dataclass
class PlacedLesson:
    date: date_cls
    weekday: int
    start: str
    end: str
    lesson: Lesson


@dataclass
class ResolvedSchedule:
    lessons: list[PlacedLesson]
    week_parity_basis: str


def resolve_lessons(
    entries: Iterable[Lesson],
    grid: ScheduleGrid,
    range_start: date_cls,
    range_end: date_cls,
) -> ResolvedSchedule:
    """Place abstract day/position lesson entries onto real calendar dates
    within [range_start, range_end], using the grid's clock-time positions
    and week_variants.
    """
    entries_by_slot: dict[tuple[int, int], list[Lesson]] = {}
    for entry in entries:
        weekday = (entry.day - 1) % 7
        week_index = (entry.day - 1) // 7
        entries_by_slot.setdefault((weekday, week_index), []).append(entry)

    placed: list[PlacedLesson] = []
    current = range_start
    while current <= range_end:
        weekday = current.weekday()
        iso_week = current.isocalendar()[1]
        week_slot = (iso_week - 1) % grid.week_variants
        for entry in entries_by_slot.get((weekday, week_slot), []):
            if not (1 <= entry.position <= len(grid.positions)):
                # Position out of range for this grid - nothing sane to place.
                continue
            position = grid.positions[entry.position - 1]
            placed.append(
                PlacedLesson(
                    date=current,
                    weekday=weekday,
                    start=position["start"],
                    end=position["end"],
                    lesson=entry,
                )
            )
        current += timedelta(days=1)

    placed.sort(key=lambda p: (p.date, p.lesson.position))

    week_parity_basis = (
        "week_index = (ISO week number - 1) % "
        f"{grid.week_variants} (the backend does not state which calendar "
        "week is week_index 0; this is a provisional assumption)"
    )
    return ResolvedSchedule(lessons=placed, week_parity_basis=week_parity_basis)
