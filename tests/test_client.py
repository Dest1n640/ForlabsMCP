import json
from pathlib import Path

import httpx
import respx

from forlabs_mcp.client.client import ForlabsClient
from forlabs_mcp.config import ForlabsConfig

BASE_URL = "https://bki.forlabs.ru"
FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _config(tmp_path) -> ForlabsConfig:
    return ForlabsConfig(
        username="student.login",
        password="super-secret-password",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
    )


def _mock_login_success() -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )


@respx.mock
def test_reference_without_stream_id_uses_own_stream(tmp_path) -> None:
    _mock_login_success()
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
def test_reference_with_explicit_stream_id_filters_studies_call(tmp_path) -> None:
    _mock_login_success()
    schedule_fixture = _load("sched_get_schedule.json")
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=schedule_fixture)
    )
    studies_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.reference(stream_id=199)

    # own_stream_id is still discovered from sched/get_schedule regardless
    # of the explicit filter.
    assert result["own_stream_id"] == 205
    own_streams = [s for s in result["streams"] if s["is_own"]]
    assert own_streams == [{"id": 205, "name": "14323-ДБ (ПИ)", "is_own": True}]

    sent_body = json.loads(studies_route.calls.last.request.content)
    assert sent_body == {"stream_id": 199}


@respx.mock
def test_scores_joins_study_name_and_status_label(tmp_path) -> None:
    _mock_login_success()
    scores_fixture = _load("learning_get_scores.json")
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=scores_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.scores(stream_id=205)

    assert result["warnings"] == []
    assert "note" not in result
    row = next(r for r in result["scores"] if r["study_id"] == 8975)
    assert row["study_name"] == "Основы государственного управления"
    assert row["status_label"] == "completed"
    assert "name_note" not in row


@respx.mock
def test_scores_with_unresolvable_study_id_still_succeeds(tmp_path) -> None:
    _mock_login_success()
    scores_fixture = _load("learning_get_scores.json")
    # No matching entry in the studies fixture for any of these study_ids
    # under stream 205 alone would already be a stretch; force the case by
    # using a stream whose studies fixture is empty.
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=scores_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.scores(stream_id=205)

    assert len(result["scores"]) == len(scores_fixture["scores"])
    for row in result["scores"]:
        assert row["study_name"] is None
        assert row["name_note"] == "name not found"


@respx.mock
def test_scores_filtered_by_study_id_narrows_to_one_row(tmp_path) -> None:
    _mock_login_success()
    scores_fixture = _load("learning_get_scores.json")
    studies_fixture = _load("learning_get_studies.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json=scores_fixture)
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.scores(stream_id=205, study_id=8975)

    assert len(result["scores"]) == 1
    assert result["scores"][0]["study_id"] == 8975


@respx.mock
def test_scores_with_no_matches_returns_note(tmp_path) -> None:
    _mock_login_success()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json={"scores": {}})
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.scores(stream_id=205)

    assert result["scores"] == []
    assert "note" in result


@respx.mock
def test_scores_with_explicit_stream_id_never_discovers_own_stream(tmp_path) -> None:
    _mock_login_success()
    # No sched/get_schedule route is registered at all - if the client
    # called it, respx would raise for the unmatched request.
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_scores").mock(
        return_value=httpx.Response(200, json={"scores": {}})
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )

    client = ForlabsClient(_config(tmp_path))
    client.scores(stream_id=205)


def _tasks_side_effect_only_for_study(target_study_id: str, tasks_fixture: dict):
    def _side_effect(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["study_id"] == target_study_id:
            return httpx.Response(200, json=tasks_fixture)
        return httpx.Response(200, json={"tasks": [], "assignments": []})

    return _side_effect


@respx.mock
def test_homework_without_study_id_unions_across_studies(tmp_path) -> None:
    _mock_login_success()
    studies_fixture = _load("learning_get_studies.json")
    tasks_fixture = _load("learning_get_tasks.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )
    tasks_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        side_effect=_tasks_side_effect_only_for_study("10823", tasks_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.homework(stream_id=205)

    assert result["warnings"] == []
    assert len(result["homework"]) == len(tasks_fixture["tasks"])
    assert all(row["study_id"] == 10823 for row in result["homework"])
    assert all(row["study_name"] == "Управление базами данных" for row in result["homework"])
    assert all(row["is_done"] is True for row in result["homework"])
    # one learning/get_tasks call per study in the studies fixture
    assert tasks_route.call_count == len(studies_fixture["studies"])


@respx.mock
def test_homework_one_failing_study_becomes_a_warning_not_a_failure(tmp_path) -> None:
    _mock_login_success()
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

    client = ForlabsClient(_config(tmp_path))
    result = client.homework(stream_id=205)

    assert len(result["homework"]) == len(tasks_fixture["tasks"])
    assert len(result["warnings"]) == 1
    assert "11590" in result["warnings"][0]


@respx.mock
def test_homework_only_outstanding_excludes_done_items(tmp_path) -> None:
    _mock_login_success()
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
    all_result = client.homework(stream_id=205)
    outstanding_result = client.homework(stream_id=205, only_outstanding=True)

    assert len(all_result["homework"]) == 3
    assert len(outstanding_result["homework"]) == 2
    assert all(row["is_done"] is False for row in outstanding_result["homework"])


@respx.mock
def test_homework_with_explicit_study_id_calls_get_tasks_once(tmp_path) -> None:
    _mock_login_success()
    studies_fixture = _load("learning_get_studies.json")
    tasks_fixture = _load("learning_get_tasks.json")
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=studies_fixture)
    )
    tasks_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json=tasks_fixture)
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.homework(stream_id=205, study_id=10823)

    assert tasks_route.call_count == 1
    sent_body = json.loads(tasks_route.calls.last.request.content)
    assert sent_body == {"stream_id": "205", "study_id": "10823"}
    assert len(result["homework"]) == len(tasks_fixture["tasks"])


@respx.mock
def test_homework_with_no_results_returns_note(tmp_path) -> None:
    _mock_login_success()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json={"studies": []})
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json={"tasks": [], "assignments": []})
    )

    client = ForlabsClient(_config(tmp_path))
    result = client.homework(stream_id=205, study_id=999)

    assert result["homework"] == []
    assert "note" in result
