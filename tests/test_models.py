import json
from pathlib import Path

from forlabs_mcp.client.models import (
    Assignment,
    AssignmentComment,
    Identity,
    Lesson,
    ScheduleGrid,
    Score,
    Stream,
    Study,
    Task,
    TaskFile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_identity_defaults_to_null_name_and_role() -> None:
    identity = Identity()
    assert identity.name is None
    assert identity.role is None


def test_stream_builds_from_schedule_fixture() -> None:
    data = _load("sched_get_schedule.json")
    stream = Stream.model_validate(data["streams"][0])
    assert stream.id == 199
    assert stream.name == "14321-ДБ (ПИ)"
    assert stream.is_own is False


def test_study_builds_from_studies_fixture_with_derived_fields() -> None:
    data = _load("learning_get_studies.json")
    current = Study.model_validate(data["studies"][0])
    past = Study.model_validate(data["studies"][2])

    assert current.name == "Технологии интерактивных медиасистем"
    assert current.study_year == 3
    assert current.semester == 5
    assert current.is_current is True
    assert current.teachers == ["Орлов Пётр Андреевич"]

    assert past.is_current is False


def test_schedule_grid_builds_from_grid_fixture_with_active_weekdays() -> None:
    data = _load("sched_get_grid.json")
    grid = ScheduleGrid.model_validate(data["grid"])

    assert grid.week_variants == 2
    assert grid.positions[0] == {"start": "08:30", "end": "10:00"}
    # sun is the only inactive day in the fixture -> weekday index 6 excluded
    assert grid.active_weekdays == [0, 1, 2, 3, 4, 5]


def test_lesson_builds_from_schedule_entry_with_kind_alias() -> None:
    data = _load("sched_get_schedule.json")
    lesson = Lesson.model_validate(data["entries"][0])

    assert lesson.day == 1
    assert lesson.position == 2
    assert lesson.kind == 1
    assert lesson.study_name == "Экономическая теория"


def test_score_builds_from_scores_fixture() -> None:
    data = _load("learning_get_scores.json")
    score = Score.model_validate(data["scores"]["8919"])

    assert score.study_id == 8919
    assert score.credits == 1
    assert score.status == 1
    assert score.grade == 0


def test_task_file_and_task_build_from_tasks_fixture() -> None:
    data = _load("learning_get_tasks.json")
    task_data = data["tasks"][0]
    task = Task.model_validate(task_data)

    assert task.id == 5
    assert task.due_at == "2026-03-02T16:00:00.000000Z"
    assert task.max_credits == 2
    assert task.description_html.startswith("<p>Подготовительный этап")
    assert len(task.files) == 1
    assert isinstance(task.files[0], TaskFile)
    assert task.files[0].filename == "customers.sql"


def test_assignment_builds_from_tasks_fixture_with_credit_aliases() -> None:
    data = _load("learning_get_tasks.json")
    assignment = Assignment.model_validate(data["assignments"][0])

    assert assignment.task_id == 5
    assert assignment.credits == 2
    assert assignment.assessed_at == "2026-03-12"


def test_assignment_detail_fixture_builds_typed_task_and_assignment() -> None:
    data = _load("learning_get_task.json")
    task = Task.model_validate(data["task"])
    assignment = Assignment.model_validate(data["assignment"])

    assert task.id == 7001
    assert task.description_html == "<p>Complete the synthetic exercise.</p>"
    assert assignment.id == 8001
    assert assignment.task_id == task.id


def test_assignment_comment_fixture_keeps_typed_response_fields() -> None:
    data = _load("assignments_get_comments.json")
    comment = AssignmentComment.model_validate(data["comments"][0])

    assert comment.id == 9001
    assert comment.user_id == 3210
    assert comment.message == "Synthetic response text"
    assert comment.created_at == "2026-04-02 12:30:00"
    assert comment.attachments[0]["filename"] == "answer.txt"


def test_unexpected_extra_field_does_not_raise() -> None:
    data = _load("learning_get_studies.json")["studies"][0]
    data = {**data, "some_future_backend_field": {"nested": True}}

    study = Study.model_validate(data)

    assert study.id == data["id"]
