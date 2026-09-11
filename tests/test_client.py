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
