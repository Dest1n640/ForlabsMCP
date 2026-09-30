import json
from pathlib import Path

import httpx
import respx

from forlabs_mcp.client.repository import Repository
from forlabs_mcp.client.session import ForlabsSession
from forlabs_mcp.config import ForlabsConfig
from forlabs_mcp.errors import ProgrammingError, UpstreamError

BASE_URL = "https://bki.forlabs.ru"
FIXTURES = Path(__file__).parent / "fixtures"


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


@respx.mock(assert_all_called=False)
def test_disallowed_action_raises_without_any_http_request(tmp_path) -> None:
    session = ForlabsSession(_config(tmp_path))
    repository = Repository(session)

    try:
        repository.call("assignments", "post_comment", {})
        raise AssertionError("expected ProgrammingError")
    except ProgrammingError:
        pass

    assert len(respx.calls) == 0


@respx.mock
def test_allowed_action_returns_parsed_payload(tmp_path) -> None:
    _mock_xsrf_prime()
    grid_fixture = json.loads((FIXTURES / "sched_get_grid.json").read_text())
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json=grid_fixture)
    )

    session = ForlabsSession(_config(tmp_path))
    repository = Repository(session)

    result = repository.call("sched", "get_grid", {})

    assert result == grid_fixture


@respx.mock
def test_message_only_body_maps_to_upstream_error(tmp_path) -> None:
    _mock_xsrf_prime()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(200, json={"message": "Something went wrong."})
    )

    session = ForlabsSession(_config(tmp_path))
    repository = Repository(session)

    try:
        repository.call("sched", "get_grid", {})
        raise AssertionError("expected UpstreamError")
    except UpstreamError as exc:
        assert exc.module == "sched"
        assert exc.action == "get_grid"


@respx.mock
def test_non_2xx_status_maps_to_upstream_error(tmp_path) -> None:
    _mock_xsrf_prime()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        return_value=httpx.Response(500, json={"error": "internal"})
    )

    session = ForlabsSession(_config(tmp_path))
    repository = Repository(session)

    try:
        repository.call("sched", "get_grid", {})
        raise AssertionError("expected UpstreamError")
    except UpstreamError:
        pass
