import json
from pathlib import Path

import httpx
import pytest
import respx

from forlabs_mcp.client.client import ForlabsClient
from forlabs_mcp.config import ForlabsConfig
from forlabs_mcp.errors import InvalidArgumentError, UpstreamError

BASE_URL = "https://bki.forlabs.ru"
FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _config(tmp_path) -> ForlabsConfig:
    return ForlabsConfig(
        session_token="remember-cookie-value",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
    )


def _mock_xsrf_prime() -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )


def _mock_own_schedule():
    return respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=_load("sched_get_schedule.json"))
    )


def _mock_assignment_context(tasks_fixture: dict | None = None):
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    return respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(
            200, json=tasks_fixture or _load("learning_get_tasks_assignments.json")
        )
    )


@respx.mock
def test_reference_without_stream_id_uses_own_stream(tmp_path) -> None:
    _mock_xsrf_prime()
    schedule_fixture = _load("sched_get_schedule.json")
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=schedule_fixture)
    )
    studies_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.reference()

    assert result["identity"] == {"name": None, "role": None}
    assert result["own_stream_id"] == 205
    assert result["warnings"] == []

    own_streams = [s for s in result["streams"] if s["is_own"]]
    assert own_streams == [{"id": 205, "name": "14323-ДБ (ПИ)", "is_own": True}]
    other_streams = [s for s in result["streams"] if not s["is_own"]]
    assert len(other_streams) == 3

    assert len(result["studies"]) == len(studies_fixture["studies"])
    current_names = {s["name"] for s in result["studies"] if s["is_current"]}
    assert "Технологии интерактивных медиасистем" in current_names

    sent_body = json.loads(studies_route.calls.last.request.content)
    assert sent_body == {"stream_id": 205}


@respx.mock
def test_schedule_groups_come_from_schedule_response_without_subject_data(tmp_path) -> None:
    _mock_xsrf_prime()
    schedule_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=_load("sched_get_schedule_groups.json"))
    )

    result = ForlabsClient(_config(tmp_path)).schedule_groups()

    assert result["own_stream_id"] == 210
    assert result["groups"] == [
        {"id": 210, "name": "Synthetic own group", "is_own": True},
        {"id": 211, "name": "Synthetic schedule group", "is_own": False},
    ]
    assert all(type(group["id"]) is int for group in result["groups"])
    assert json.loads(schedule_route.calls.last.request.content) == {}
    assert not any("/learning/" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_scores_joins_study_name_and_status_label(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    scores_fixture = _load("learning_get_scores.json")
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=scores_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    result = ForlabsClient(_config(tmp_path)).scores()

    assert result["warnings"] == []
    assert "note" not in result
    row = next(r for r in result["scores"] if r["study_id"] == 8975)
    assert row["study_name"] == "Основы государственного управления"
    assert row["status_label"] == "completed"
    assert "name_note" not in row


@respx.mock
def test_scores_with_unresolvable_study_id_still_succeeds(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    scores_fixture = _load("learning_get_scores.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=scores_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    result = ForlabsClient(_config(tmp_path)).scores()

    assert len(result["scores"]) == len(scores_fixture["scores"])
    for row in result["scores"]:
        assert row["study_name"] is None
        assert row["name_note"] == "name not found"


@respx.mock
def test_scores_filtered_by_study_id_narrows_to_one_row(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    scores_fixture = _load("learning_get_scores.json")
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=scores_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    result = ForlabsClient(_config(tmp_path)).scores(study_id=8975)

    assert len(result["scores"]) == 1
    assert result["scores"][0]["study_id"] == 8975


@respx.mock
def test_scores_with_no_matches_returns_note(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json={"scores": {}})
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    result = ForlabsClient(_config(tmp_path)).scores()

    assert result["scores"] == []
    assert "note" in result


@respx.mock
def test_scores_always_uses_discovered_own_stream(tmp_path) -> None:
    _mock_xsrf_prime()
    schedule_route = _mock_own_schedule()
    scores_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json={"scores": {}})
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    ForlabsClient(_config(tmp_path)).scores()

    assert json.loads(schedule_route.calls.last.request.content) == {}
    assert json.loads(scores_route.calls.last.request.content) == {"stream_id": 205}


@respx.mock
def test_assignment_details_resolves_task_only_from_own_study(tmp_path) -> None:
    _mock_xsrf_prime()
    tasks_route = _mock_assignment_context()
    detail_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_task").mock(
        return_value=httpx.Response(200, json=_load("learning_get_task.json"))
    )

    result = ForlabsClient(_config(tmp_path)).assignment_details(10823, 7001)

    assert result["task_id"] == 7001
    assert result["task"]["description_html"] == "<p>Complete the synthetic exercise.</p>"
    assert result["assignment"]["id"] == 8001
    assert json.loads(tasks_route.calls.last.request.content) == {
        "stream_id": "205",
        "study_id": "10823",
    }
    assert json.loads(detail_route.calls.last.request.content) == {
        "stream_id": "205",
        "study_id": "10823",
        "task_id": "7001",
    }


@respx.mock
def test_assignment_details_rejects_non_own_study_before_task_requests(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )

    with pytest.raises(InvalidArgumentError):
        ForlabsClient(_config(tmp_path)).assignment_details(999, 7001)

    assert not any(
        "/learning/get_tasks" in str(call.request.url)
        or "/learning/get_task" in str(call.request.url)
        for call in respx.calls
    )


@respx.mock
@pytest.mark.parametrize(
    "detail_payload",
    [
        {"task": "not-an-object"},
        {"task": {**_load("learning_get_task.json")["task"], "id": 7002}},
    ],
)
def test_assignment_details_rejects_malformed_or_mismatched_task_detail(
    tmp_path, detail_payload: dict
) -> None:
    _mock_xsrf_prime()
    _mock_assignment_context()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_task").mock(
        return_value=httpx.Response(200, json=detail_payload)
    )

    with pytest.raises(UpstreamError):
        ForlabsClient(_config(tmp_path)).assignment_details(10823, 7001)

    assert not any("/assignments/" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_assignment_thread_uses_own_assignment_id_and_reads_comments_only(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_assignment_context()
    comments_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        return_value=httpx.Response(200, json=_load("assignments_get_comments.json"))
    )

    result = ForlabsClient(_config(tmp_path)).assignment_thread(10823, 7001)

    assert result["assignment_id"] == 8001
    assert result["comments"][0]["message"] == "Synthetic response text"
    assert result["comments"][0]["user"]["name"] == "Synthetic Student"
    assert json.loads(comments_route.calls.last.request.content) == {
        "study_id": "10823",
        "task_id": 7001,
        "assignment_id": 8001,
    }
    assert not any(
        action in str(call.request.url)
        for call in respx.calls
        for action in ("/assignments/post_comment", "/uploads/store", "/uploads/delete", "/upload")
    )


@respx.mock
def test_assignment_thread_rejects_missing_assignment_before_comments_request(tmp_path) -> None:
    _mock_xsrf_prime()
    tasks_route = _mock_assignment_context()

    with pytest.raises(InvalidArgumentError):
        ForlabsClient(_config(tmp_path)).assignment_thread(10823, 7002)

    assert tasks_route.called
    assert not any("/assignments/get_comments" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_assignment_thread_rejects_ambiguous_assignment_mapping(tmp_path) -> None:
    _mock_xsrf_prime()
    task_data = _load("learning_get_tasks_assignments.json")
    duplicate = {**task_data["assignments"][0], "id": 8002}
    task_data["assignments"].append(duplicate)
    _mock_assignment_context(task_data)

    with pytest.raises(InvalidArgumentError):
        ForlabsClient(_config(tmp_path)).assignment_thread(10823, 7001)

    assert not any("/assignments/get_comments" in str(call.request.url) for call in respx.calls)


def _tasks_side_effect_only_for_study(target_study_id: str, tasks_fixture: dict):
    def _side_effect(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["study_id"] == target_study_id:
            return httpx.Response(200, json=tasks_fixture)
        return httpx.Response(200, json={"tasks": [], "assignments": []})

    return _side_effect


@respx.mock
def test_homework_without_study_id_unions_across_own_studies(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    studies_fixture = _load("learning_get_studies.json")
    tasks_fixture = _load("learning_get_tasks.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )
    tasks_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        side_effect=_tasks_side_effect_only_for_study("10823", tasks_fixture)
    )

    result = ForlabsClient(_config(tmp_path)).homework()

    assert result["warnings"] == []
    assert len(result["homework"]) == len(tasks_fixture["tasks"])
    assert all(row["study_id"] == 10823 for row in result["homework"])
    assert all(row["study_name"] == "Управление базами данных" for row in result["homework"])
    assert all(row["is_done"] is True for row in result["homework"])
    assert tasks_route.call_count == len(studies_fixture["studies"])


@respx.mock
def test_homework_one_failing_study_becomes_a_warning_not_a_failure(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    studies_fixture = _load("learning_get_studies.json")
    tasks_fixture = _load("learning_get_tasks.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    def _side_effect(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["study_id"] == "11590":
            return httpx.Response(500, json={"error": "internal"})
        if body["study_id"] == "10823":
            return httpx.Response(200, json=tasks_fixture)
        return httpx.Response(200, json={"tasks": [], "assignments": []})

    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        side_effect=_side_effect
    )

    result = ForlabsClient(_config(tmp_path)).homework()

    assert len(result["homework"]) == len(tasks_fixture["tasks"])
    assert len(result["warnings"]) == 1
    assert "11590" in result["warnings"][0]


@respx.mock
def test_homework_only_outstanding_excludes_done_items(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    studies_fixture = _load("learning_get_studies.json")
    tasks_fixture = _load("learning_get_tasks.json")
    partial_tasks_fixture = {
        "tasks": tasks_fixture["tasks"],
        "assignments": tasks_fixture["assignments"][:1],
    }
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        side_effect=_tasks_side_effect_only_for_study("10823", partial_tasks_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    all_result = client.homework()
    outstanding_result = client.homework(only_outstanding=True)

    assert len(all_result["homework"]) == 3
    assert len(outstanding_result["homework"]) == 2
    assert all(row["is_done"] is False for row in outstanding_result["homework"])


@respx.mock
def test_homework_with_own_study_id_calls_get_tasks_once(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    studies_fixture = _load("learning_get_studies.json")
    tasks_fixture = _load("learning_get_tasks.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )
    tasks_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json=tasks_fixture)
    )

    result = ForlabsClient(_config(tmp_path)).homework(study_id=10823)

    assert tasks_route.call_count == 1
    sent_body = json.loads(tasks_route.calls.last.request.content)
    assert sent_body == {"stream_id": "205", "study_id": "10823"}
    assert len(result["homework"]) == len(tasks_fixture["tasks"])


@respx.mock
def test_homework_with_no_own_studies_returns_note(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    result = ForlabsClient(_config(tmp_path)).homework()

    assert result["homework"] == []
    assert "note" in result


@respx.mock
def test_homework_rejects_study_outside_own_enrolment_before_get_tasks(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )

    with pytest.raises(InvalidArgumentError):
        ForlabsClient(_config(tmp_path)).homework(study_id=999)

    assert not any("/learning/get_tasks" in str(call.request.url) for call in respx.calls)


@respx.mock(assert_all_called=False)
def test_schedule_raw_mutual_exclusion_rejects_without_any_backend_call(tmp_path) -> None:
    client = ForlabsClient(_config(tmp_path))

    with pytest.raises(InvalidArgumentError):
        client.schedule_raw(date="2026-03-02", start="2026-03-02", end="2026-03-08")

    assert len(respx.calls) == 0


@respx.mock
def test_schedule_raw_places_lessons_and_reports_week_parity_basis(tmp_path) -> None:
    _mock_xsrf_prime()
    grid_fixture = _load("sched_get_grid.json")
    schedule_fixture = _load("sched_get_schedule.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json=grid_fixture)
    )
    schedule_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=schedule_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.schedule_raw(start="2026-03-02", end="2026-03-15")
    assert json.loads(schedule_route.calls.last.request.content) == {}
    assert result["stream_id"] == 205
    assert result["stream_name"] == "14323-ДБ (ПИ)"

    assert len(result["lessons"]) == len(schedule_fixture["entries"])
    assert result["week_variants"] == 2
    assert "week_index" in result["week_parity_basis"]
    assert result["timezone"] == "Asia/Irkutsk"
    assert result["warnings"] == []
    assert "note" not in result

    lesson = next(item for item in result["lessons"] if item["study_id"] == 11590)
    assert lesson["subject"] == "Экономическая теория"
    assert lesson["start"] == "10:10"
    assert lesson["weekday"] == 0


@respx.mock
def test_schedule_raw_fetches_selected_group_after_validating_group_list(tmp_path) -> None:
    _mock_xsrf_prime()
    group_fixture = _load("sched_get_schedule_groups.json")
    selected_schedule = _load("sched_get_schedule.json")

    def _schedule_response(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body == {}:
            return httpx.Response(200, json=group_fixture)
        assert body == {"stream_id": 211}
        return httpx.Response(200, json=selected_schedule)

    schedule_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        side_effect=_schedule_response
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json=_load("sched_get_grid.json"))
    )

    result = ForlabsClient(_config(tmp_path)).schedule_raw(date="2026-03-02", stream_id=211)

    assert schedule_route.call_count == 2
    assert [json.loads(call.request.content) for call in schedule_route.calls] == [
        {},
        {"stream_id": 211},
    ]
    assert result["stream_id"] == 211
    assert result["stream_name"] == "Synthetic schedule group"


@respx.mock
def test_schedule_raw_rejects_unknown_group_before_grid_or_group_request(tmp_path) -> None:
    _mock_xsrf_prime()
    schedule_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=_load("sched_get_schedule_groups.json"))
    )
    grid_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json=_load("sched_get_grid.json"))
    )

    with pytest.raises(InvalidArgumentError):
        ForlabsClient(_config(tmp_path)).schedule_raw(date="2026-03-02", stream_id=999)

    assert schedule_route.call_count == 1
    assert json.loads(schedule_route.calls.last.request.content) == {}
    assert grid_route.call_count == 0


@respx.mock
def test_schedule_raw_empty_range_returns_note(tmp_path) -> None:
    _mock_xsrf_prime()
    grid_fixture = _load("sched_get_grid.json")
    schedule_fixture = _load("sched_get_schedule.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json=grid_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=schedule_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    # 2026-03-08 is a Sunday; no fixture entry has that weekday.
    result = client.schedule_raw(date="2026-03-08")

    assert result["lessons"] == []
    assert "note" in result


def _mock_homework(tmp_path):
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    return respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        side_effect=_tasks_side_effect_only_for_study("10823", _load("learning_get_tasks.json"))
    )


@respx.mock
def test_homework_rows_carry_assignment_id_and_response_count(tmp_path) -> None:
    _mock_homework(tmp_path)

    rows = ForlabsClient(_config(tmp_path)).homework(study_id=10823)["homework"]

    by_task = {row["task_id"]: row for row in rows}
    assert by_task[5]["assignment_id"] == 940203
    assert by_task[5]["responses_count"] == 1
    assert by_task[41]["responses_count"] == 2


@respx.mock
def test_homework_query_pagination_and_total(tmp_path) -> None:
    _mock_homework(tmp_path)
    client = ForlabsClient(_config(tmp_path))

    assert client.homework(study_id=10823)["total"] == 3

    first_page = client.homework(study_id=10823, limit=2)
    assert len(first_page["homework"]) == 2
    assert first_page["total"] == 3

    second_page = client.homework(study_id=10823, limit=2, offset=2)
    assert [row["task_id"] for row in second_page["homework"]] == [41]

    found = client.homework(study_id=10823, query="курсовой")
    assert [row["task_id"] for row in found["homework"]] == [41]


@respx.mock
def test_homework_due_filters(tmp_path) -> None:
    _mock_homework(tmp_path)
    client = ForlabsClient(_config(tmp_path))

    with_due = client.homework(study_id=10823, has_due=True)
    assert {row["task_id"] for row in with_due["homework"]} == {5, 251}

    without_due = client.homework(study_id=10823, has_due=False)
    assert {row["task_id"] for row in without_due["homework"]} == {41}

    in_range = client.homework(study_id=10823, due_from="2026-03-01", due_to="2026-03-05")
    assert {row["task_id"] for row in in_range["homework"]} == {5}


@respx.mock
def test_homework_has_feedback_reads_thread_and_excludes_own_replies(tmp_path) -> None:
    _mock_homework(tmp_path)
    respx.get(f"{BASE_URL}/app/profile/user").mock(
        return_value=httpx.Response(200, json=_load("profile_user.json"))
    )

    # A teacher reply (user 329) on the first assignment, the student's own
    # reply (user 3149) on the rest.
    def _comments(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_id = 329 if body["assignment_id"] == 940203 else 3149
        return httpx.Response(
            200,
            json={
                "comments": [
                    {
                        "id": 1,
                        "user_id": user_id,
                        "message": "Synthetic reply",
                        "created_at": "2026-03-01 10:00:00",
                        "user": {"id": user_id, "name": "Synthetic User"},
                        "attachments": [],
                    }
                ]
            },
        )

    comments_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        side_effect=_comments
    )
    client = ForlabsClient(_config(tmp_path))

    with_feedback = client.homework(study_id=10823, has_feedback=True)
    assert [row["task_id"] for row in with_feedback["homework"]] == [5]
    assert with_feedback["homework"][0]["has_feedback"] is True

    without_feedback = client.homework(study_id=10823, has_feedback=False)
    assert {row["task_id"] for row in without_feedback["homework"]} == {251, 41}
    assert all(row["has_feedback"] is False for row in without_feedback["homework"])
    assert comments_route.call_count == 6


@respx.mock(assert_all_called=False)
def test_homework_rejects_bad_filters_before_any_backend_call(tmp_path) -> None:
    client = ForlabsClient(_config(tmp_path))

    with pytest.raises(InvalidArgumentError):
        client.homework(limit=0)
    with pytest.raises(InvalidArgumentError):
        client.homework(offset=-1)
    with pytest.raises(InvalidArgumentError):
        client.homework(due_from="2026-05-01", due_to="2026-03-01")
    with pytest.raises(InvalidArgumentError):
        client.homework(has_due="yes")  # type: ignore[arg-type]

    assert len(respx.calls) == 0


@respx.mock
def test_homework_accepts_multiple_own_studies(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )
    tasks_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json=_load("learning_get_tasks.json"))
    )

    result = ForlabsClient(_config(tmp_path)).homework(study_ids=[10823, 8975])

    assert tasks_route.call_count == 2
    assert {json.loads(call.request.content)["study_id"] for call in tasks_route.calls} == {
        "10823",
        "8975",
    }
    assert result["total"] == len(_load("learning_get_tasks.json")["tasks"]) * 2


@respx.mock
def test_study_materials_merges_chapter_details_and_course(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    chapters_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_chapters").mock(
        return_value=httpx.Response(200, json=_load("learning_get_chapters.json"))
    )
    chapter_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_chapter").mock(
        return_value=httpx.Response(200, json=_load("learning_get_chapter.json"))
    )

    result = ForlabsClient(_config(tmp_path)).study_materials(10823)

    assert result["study_name"] == "Управление базами данных"
    assert result["course"]["name"] == "Synthetic course"
    assert [file["filename"] for file in result["course"]["files"]] == ["sample-guide.doc"]
    assert [chapter["id"] for chapter in result["chapters"]] == [589, 590]
    # Only the chapter that advertises content is enriched with a detail call.
    assert result["chapters"][0]["annotation"] == "<p>Synthetic chapter annotation.</p>"
    assert [file["filename"] for file in result["chapters"][0]["files"]] == ["sample-lecture.pdf"]
    assert result["chapters"][1]["annotation"] is None
    assert result["chapters"][1]["files"] == []
    assert chapter_route.call_count == 1
    assert json.loads(chapters_route.calls.last.request.content) == {
        "stream_id": "205",
        "study_id": "10823",
    }
    assert json.loads(chapter_route.calls.last.request.content) == {
        "stream_id": "205",
        "study_id": "10823",
        "chapter_id": "589",
    }


@respx.mock
def test_study_materials_without_content_skips_chapter_detail(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_chapters").mock(
        return_value=httpx.Response(200, json=_load("learning_get_chapters.json"))
    )

    result = ForlabsClient(_config(tmp_path)).study_materials(10823, include_content=False)

    assert [chapter["id"] for chapter in result["chapters"]] == [589, 590]
    assert not any(
        str(call.request.url).split("?")[0].endswith("/learning/get_chapter")
        for call in respx.calls
    )


@respx.mock
def test_study_materials_rejects_non_own_study_before_chapter_calls(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_own_schedule()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )

    with pytest.raises(InvalidArgumentError):
        ForlabsClient(_config(tmp_path)).study_materials(999)

    assert not any("/learning/get_chapters" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_task_files_returns_files_from_task_detail(tmp_path) -> None:
    _mock_xsrf_prime()
    _mock_assignment_context()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_task").mock(
        return_value=httpx.Response(200, json=_load("learning_get_task.json"))
    )

    result = ForlabsClient(_config(tmp_path)).task_files(10823, 7001)

    assert result["task_title"] == "Synthetic task"
    assert [file["filename"] for file in result["files"]] == ["sample.txt"]
    assert not any("/assignments/" in str(call.request.url) for call in respx.calls)
