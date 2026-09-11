import json
from pathlib import Path

from forlabs_mcp.client.parsers import (
    parse_assignments,
    parse_lessons,
    parse_schedule_grid,
    parse_scores,
    parse_streams,
    parse_studies,
    parse_tasks,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_parse_studies_skips_one_malformed_row_and_keeps_the_rest() -> None:
    studies = _load("learning_get_studies.json")["studies"]
    malformed = {**studies[1], "curr_sem": "not-a-number"}
    rows = [studies[0], malformed, studies[2], studies[3]]

    result = parse_studies(rows)

    assert len(result.data) == 3
    assert result.is_partial is True
    assert len(result.warnings) == 1
    assert "study" in result.warnings[0]


def test_parse_studies_with_all_valid_rows_is_not_partial() -> None:
    studies = _load("learning_get_studies.json")["studies"]

    result = parse_studies(studies)

    assert len(result.data) == len(studies)
    assert result.is_partial is False


def test_parse_scores_skips_one_malformed_value_and_keeps_the_rest() -> None:
    scores = _load("learning_get_scores.json")["scores"]
    scores_with_bad_row = dict(scores)
    scores_with_bad_row["8919"] = {**scores["8919"], "credits": "not-a-number"}

    result = parse_scores(scores_with_bad_row)

    assert len(result.data) == len(scores) - 1
    assert result.is_partial is True
    assert "score" in result.warnings[0]


def test_parse_streams_all_valid() -> None:
    streams = _load("sched_get_schedule.json")["streams"]
    result = parse_streams(streams)
    assert len(result.data) == len(streams)
    assert result.is_partial is False


def test_parse_lessons_all_valid() -> None:
    entries = _load("sched_get_schedule.json")["entries"]
    result = parse_lessons(entries)
    assert len(result.data) == len(entries)
    assert result.is_partial is False


def test_parse_tasks_and_assignments_all_valid() -> None:
    data = _load("learning_get_tasks.json")
    tasks_result = parse_tasks(data["tasks"])
    assignments_result = parse_assignments(data["assignments"])

    assert len(tasks_result.data) == len(data["tasks"])
    assert tasks_result.is_partial is False
    assert len(assignments_result.data) == len(data["assignments"])
    assert assignments_result.is_partial is False


def test_parse_schedule_grid_builds_from_grid_fixture() -> None:
    grid_raw = _load("sched_get_grid.json")["grid"]
    grid = parse_schedule_grid(grid_raw)
    assert grid.week_variants == 2
