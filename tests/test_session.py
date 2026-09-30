import httpx
import respx

from forlabs_mcp.client.session import REMEMBER_COOKIE_NAME, ForlabsSession
from forlabs_mcp.config import ForlabsConfig
from forlabs_mcp.errors import AuthError

BASE_URL = "https://bki.forlabs.ru"


def _config(tmp_path, **overrides) -> ForlabsConfig:
    defaults = dict(
        session_token="remember-cookie-value",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
    )
    defaults.update(overrides)
    return ForlabsConfig(**defaults)


def test_config_only_token_authenticates_without_any_http_call(tmp_path) -> None:
    session = ForlabsSession(_config(tmp_path))
    assert session.is_authenticated is True


def test_seeds_remember_cookie_under_the_configured_domain(tmp_path) -> None:
    session = ForlabsSession(_config(tmp_path, session_token="the-remember-value"))
    matches = [c for c in session._client.cookies.jar if c.name == REMEMBER_COOKIE_NAME]
    assert len(matches) == 1
    assert matches[0].value == "the-remember-value"
    assert matches[0].domain == "bki.forlabs.ru"


@respx.mock
def test_data_call_primes_xsrf_and_establishes_a_fresh_session(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc%3D; Path=/")])
    )
    data_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(
            200, json={"meta": {}}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )

    session = ForlabsSession(_config(tmp_path))
    response = session.request("POST", "/lm-vendor/repositories/sched/get_schedule", {})

    assert response.status_code == 200
    assert "forlabs_session" in session._client.cookies
    sent_headers = data_route.calls.last.request.headers
    assert sent_headers["x-xsrf-token"] == "abc="


@respx.mock
def test_expired_session_token_raises_auth_error_without_any_retry(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    data_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(419, json={"message": "session expired"})
    )

    session = ForlabsSession(_config(tmp_path))

    try:
        session.request("POST", "/lm-vendor/repositories/sched/get_schedule", {})
        raise AssertionError("expected AuthError")
    except AuthError:
        pass

    # Exactly one attempt at the data call - no relogin/retry.
    assert data_route.call_count == 1


@respx.mock
def test_auth_error_never_leaks_the_configured_token_value(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(401, json={"message": "unauthenticated"})
    )

    config = _config(tmp_path, session_token="super-secret-remember-value")
    session = ForlabsSession(config)

    try:
        session.request("POST", "/lm-vendor/repositories/sched/get_schedule", {})
        raise AssertionError("expected AuthError")
    except AuthError as exc:
        assert config.session_token not in str(exc)


@respx.mock
def test_persisted_session_is_restored_without_a_priming_call(tmp_path) -> None:
    prime_route = respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    data_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(
            200, json={"meta": {}}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )

    config = _config(tmp_path)
    first_session = ForlabsSession(config)
    first_session.request("POST", "/lm-vendor/repositories/sched/get_schedule", {})
    assert prime_route.call_count == 1

    second_session = ForlabsSession(config)
    assert "forlabs_session" in second_session._client.cookies
    assert "XSRF-TOKEN" in second_session._client.cookies

    response = second_session.request("POST", "/lm-vendor/repositories/sched/get_schedule", {})
    assert response.status_code == 200
    assert data_route.call_count == 2
    # The restored XSRF-TOKEN meant no second priming GET was needed.
    assert prime_route.call_count == 1


def test_malformed_session_file_is_ignored_instead_of_crashing(tmp_path) -> None:
    config = _config(tmp_path)
    config.session_path.parent.mkdir(parents=True, exist_ok=True)
    # The old (pre-fix) persisted shape was a flat name->value dict, not a
    # list of {name, value, domain} records - no longer a shape this loader
    # accepts, and it must degrade to "not authenticated" rather than crash.
    config.session_path.write_text('{"cookies": {"forlabs_session": "xyz"}}')

    session = ForlabsSession(config)

    # Malformed cache is ignored, but the configured token still authenticates.
    assert session.is_authenticated is True
    assert "forlabs_session" not in session._client.cookies


def test_session_file_with_one_bad_cookie_entry_still_restores_the_rest(tmp_path) -> None:
    config = _config(tmp_path)
    config.session_path.parent.mkdir(parents=True, exist_ok=True)
    config.session_path.write_text(
        '{"cookies": ['
        '{"name": "XSRF-TOKEN", "value": 12345, "domain": "bki.forlabs.ru"},'
        '{"name": "forlabs_session", "value": "xyz", "domain": "bki.forlabs.ru"}'
        "]}"
    )

    session = ForlabsSession(config)

    assert session.is_authenticated is True


def test_persist_and_restore_round_trip_keeps_same_name_cookies_on_different_domains(
    tmp_path,
) -> None:
    config = _config(tmp_path)
    first_session = ForlabsSession(config)
    first_session._client.cookies.set("XSRF-TOKEN", "value-a", domain="bki.forlabs.ru")
    first_session._client.cookies.set("XSRF-TOKEN", "value-b", domain="www.bki.forlabs.ru")
    first_session._client.cookies.set("forlabs_session", "xyz", domain="bki.forlabs.ru")

    first_session._persist_session()
    second_session = ForlabsSession(config)

    matches = {
        cookie.domain: cookie.value
        for cookie in second_session._client.cookies.jar
        if cookie.name == "XSRF-TOKEN"
    }
    assert matches == {"bki.forlabs.ru": "value-a", "www.bki.forlabs.ru": "value-b"}
    assert second_session.is_authenticated is True


@respx.mock
def test_cold_start_call_never_posts_to_the_login_endpoint(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json={"meta": {}})
    )
    login_post = respx.post(f"{BASE_URL}/app/login").mock(return_value=httpx.Response(500))

    session = ForlabsSession(_config(tmp_path))
    session.request("POST", "/lm-vendor/repositories/sched/get_schedule", {})

    assert login_post.call_count == 0
