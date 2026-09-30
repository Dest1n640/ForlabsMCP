import json

import pytest

from forlabs_mcp.config import TOKEN_PLACEHOLDER, ForlabsConfig, load_config
from forlabs_mcp.errors import ConfigError

_ALL_ENV_VARS = [
    "FORLABS_SESSION_TOKEN",
    "FORLABS_BASE_URL",
    "FORLABS_TIMEOUT_SECONDS",
    "FORLABS_TZ",
    "FORLABS_SESSION_PATH",
    "FORLABS_MAX_ITEMS",
    "FORLABS_TOKEN_FILE",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _write_json(tmp_path, contents: str, name: str = "forlabs-session.json"):
    path = tmp_path / name
    path.write_text(contents)
    return path


def test_env_overrides_json_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_json(tmp_path, '{"session_token": "file-token"}')
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(path))
    monkeypatch.setenv("FORLABS_SESSION_TOKEN", "env-token")

    assert load_config().session_token == "env-token"


def test_json_file_supplies_token_and_optional_overrides(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_json(tmp_path, '{"session_token": "file-token", "max_items": 5}')
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(path))

    config = load_config()

    assert config.session_token == "file-token"
    assert config.max_items == 5


def test_leftover_toml_file_is_ignored(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.toml").write_text('session_token = "toml-token"\n')
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(tmp_path / "absent.json"))

    with pytest.raises(ConfigError):
        load_config()


def test_placeholder_token_is_treated_as_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_json(tmp_path, json.dumps({"session_token": TOKEN_PLACEHOLDER}))
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(path))

    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert excinfo.value.key == "session_token"


@pytest.mark.parametrize("contents", ["{not json secret-abc", '["secret-abc"]'])
def test_malformed_token_file_raises_without_leaking_contents(
    tmp_path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    path = _write_json(tmp_path, contents)
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(path))

    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert "secret-abc" not in str(excinfo.value)


def test_missing_session_token_raises_config_error_before_any_network_call(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(tmp_path / "does-not-exist.json"))

    with pytest.raises(ConfigError):
        load_config()


def test_defaults_are_applied_when_optional_settings_absent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORLABS_TOKEN_FILE", str(tmp_path / "does-not-exist.json"))
    monkeypatch.setenv("FORLABS_SESSION_TOKEN", "token")

    config = load_config()

    assert config.base_url == "https://bki.forlabs.ru"
    assert config.timeout_seconds == 30.0
    assert config.timezone == "Asia/Irkutsk"
    assert config.max_items == 200


def test_redacted_never_contains_the_session_token() -> None:
    config = ForlabsConfig(session_token="super-secret-value")

    redacted = config.redacted()

    assert "super-secret-value" not in repr(redacted)
    assert redacted["session_token"] == "***"
