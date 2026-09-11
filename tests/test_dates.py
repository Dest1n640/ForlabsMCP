import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from forlabs_mcp.client.models import Lesson, ScheduleGrid
from forlabs_mcp.client.parsers import parse_lessons, parse_schedule_grid
from forlabs_mcp.dates import resolve_lessons, resolve_range
from forlabs_mcp.errors import InvalidArgumentError

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _grid() -> ScheduleGrid:
    return parse_schedule_grid(_load("sched_get_grid.json")["grid"])


def _lessons() -> list[Lesson]:
    return parse_lessons(_load("sched_get_schedule.json")["entries"]).data


def test_default_range_is_current_iso_week_monday_to_sunday() -> None:
    start, end = resolve_range()
    assert start.weekday() == 0
    assert (end - start).days == 6
    today = date.today()
    assert start <= today <= end


def test_date_argument_returns_single_day_range() -> None:
    start, end = resolve_range(date="2026-03-02")
    assert start == end == date(2026, 3, 2)


def test_start_end_returns_inclusive_range() -> None:
    start, end = resolve_range(start="2026-03-02", end="2026-03-08")
    assert start == date(2026, 3, 2)
    assert end == date(2026, 3, 8)


def test_date_and_start_end_together_is_rejected() -> None:
    with pytest.raises(InvalidArgumentError):
        resolve_range(date="2026-03-02", start="2026-03-02", end="2026-03-08")


def test_start_without_end_is_rejected() -> None:
    with pytest.raises(InvalidArgumentError):
        resolve_range(start="2026-03-02")


def test_end_before_start_is_rejected() -> None:
    with pytest.raises(InvalidArgumentError):
        resolve_range(start="2026-03-08", end="2026-03-02")


def test_invalid_date_format_is_rejected() -> None:
    with pytest.raises(InvalidArgumentError):
        resolve_range(date="not-a-date")


def test_resolve_lessons_places_every_entry_exactly_once_over_two_weeks() -> None:
    grid = _grid()
    lessons = _lessons()
    range_start = date(2026, 3, 2)  # a Monday
    range_end = range_start + timedelta(days=13)

    resolved = resolve_lessons(lessons, grid, range_start, range_end)

    assert len(resolved.lessons) == len(lessons)
    placed_keys = {(p.lesson.day, p.lesson.position) for p in resolved.lessons}
    source_keys = {(entry.day, entry.position) for entry in lessons}
    assert placed_keys == source_keys


def test_resolve_lessons_uses_grid_clock_times_and_correct_weekday() -> None:
    grid = _grid()
    lessons = _lessons()
    range_start = date(2026, 3, 2)
    range_end = range_start + timedelta(days=13)

    resolved = resolve_lessons(lessons, grid, range_start, range_end)

    placed = next(p for p in resolved.lessons if p.lesson.day == 1 and p.lesson.position == 2)
    assert placed.weekday == 0
    assert placed.start == "10:10"
    assert placed.end == "11:40"


def test_resolve_lessons_reports_week_parity_basis() -> None:
    grid = _grid()
    resolved = resolve_lessons(_lessons(), grid, date(2026, 3, 2), date(2026, 3, 15))
    assert "week_index" in resolved.week_parity_basis
    assert str(grid.week_variants) in resolved.week_parity_basis


def test_resolve_lessons_skips_entries_with_out_of_range_position() -> None:
    grid = _grid()
    bad_lesson = Lesson.model_validate(
        {
            "day": 1,
            "position": 99,
            "type": 1,
            "study_id": 1,
            "study_name": "x",
        }
    )
    resolved = resolve_lessons([bad_lesson], grid, date(2026, 3, 2), date(2026, 3, 8))
    assert resolved.lessons == []
