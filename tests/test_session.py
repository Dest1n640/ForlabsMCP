import httpx
import respx

from forlabs_mcp.client.session import ForlabsSession
from forlabs_mcp.config import ForlabsConfig
from forlabs_mcp.errors import AuthError

BASE_URL = "https://bki.forlabs.ru"


def _config(tmp_path, **overrides) -> ForlabsConfig:
    defaults = dict(
        username="student.login",
        password="super-secret-password",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
    )
    defaults.update(overrides)
    return ForlabsConfig(**defaults)


@respx.mock
def test_login_success_sets_authenticated_and_decodes_xsrf_header(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc%3D; Path=/")])
    )
    login_post = respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )

    session = ForlabsSession(_config(tmp_path))
    session.login()

    assert session.is_authenticated is True
    sent_headers = login_post.calls.last.request.headers
    assert sent_headers["x-xsrf-token"] == "abc="


@respx.mock
def test_rejected_credentials_raise_auth_error_without_leaking_password(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            422, json={"errors": {"username": ["Неверный логин или пароль"]}}
        )
    )

    config = _config(tmp_path)
    session = ForlabsSession(config)

    try:
        session.login()
        raise AssertionError("expected AuthError")
    except AuthError as exc:
        assert config.password not in str(exc)


@respx.mock
def test_session_cache_file_is_created_with_restricted_permissions(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )
    config = _config(tmp_path)
    session = ForlabsSession(config)

    session.login()

    mode = config.session_path.stat().st_mode & 0o777
    assert mode == 0o600


@respx.mock
def test_persisted_session_is_restored_without_relogging_in(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )
    config = _config(tmp_path)
    first_session = ForlabsSession(config)
    first_session.login()

    second_session = ForlabsSession(config)

    assert second_session.is_authenticated is True


@respx.mock
def test_expired_session_is_relogged_in_and_retried_once(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    login_post = respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )
    data_endpoint = respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        side_effect=[
            httpx.Response(419, json={"message": "session expired"}),
            httpx.Response(200, json={"grid": {}}),
        ]
    )

    session = ForlabsSession(_config(tmp_path))
    response = session.request("POST", "/lm-vendor/repositories/sched/get_grid", {})

    assert response.status_code == 200
    assert response.json() == {"grid": {}}
    assert data_endpoint.call_count == 2
    assert login_post.call_count == 2


def test_malformed_session_file_is_ignored_instead_of_crashing(tmp_path) -> None:
    config = _config(tmp_path)
    config.session_path.parent.mkdir(parents=True, exist_ok=True)
    # The old (pre-fix) persisted shape was a flat name->value dict, not a
    # list of {name, value, domain} records - no longer a shape this loader
    # accepts, and it must degrade to "not authenticated" rather than crash.
    config.session_path.write_text('{"cookies": {"forlabs_session": "xyz"}}')

    session = ForlabsSession(config)

    assert session.is_authenticated is False


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
def test_reauth_failure_surfaces_auth_error(tmp_path) -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )
    respx.post(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(
            200, json={}, headers=[("set-cookie", "forlabs_session=xyz123; Path=/")]
        )
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_grid").mock(
        side_effect=[
            httpx.Response(419, json={"message": "session expired"}),
            httpx.Response(419, json={"message": "session expired"}),
        ]
    )

    session = ForlabsSession(_config(tmp_path))

    try:
        session.request("POST", "/lm-vendor/repositories/sched/get_grid", {})
        raise AssertionError("expected AuthError")
    except AuthError:
        pass
