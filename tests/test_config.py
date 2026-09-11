import pytest

from forlabs_mcp.config import ForlabsConfig, load_config
from forlabs_mcp.errors import ConfigError

_ALL_ENV_VARS = [
    "FORLABS_USERNAME",
    "FORLABS_PASSWORD",
    "FORLABS_BASE_URL",
    "FORLABS_TIMEOUT_SECONDS",
    "FORLABS_TZ",
    "FORLABS_SESSION_PATH",
    "FORLABS_MAX_ITEMS",
    "FORLABS_MCP_CONFIG",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _write_toml(tmp_path, contents: str):
    path = tmp_path / "config.toml"
    path.write_text(contents)
    return path


def test_env_overrides_toml_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = _write_toml(
        tmp_path,
        """
        [forlabs]
        username = "toml-user"
        password = "toml-pass"
        """,
    )
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(toml_path))
    monkeypatch.setenv("FORLABS_USERNAME", "env-user")

    config = load_config()

    assert config.username == "env-user"
    assert config.password == "toml-pass"


def test_toml_without_forlabs_table_is_accepted(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = _write_toml(
        tmp_path,
        """
        username = "bare-user"
        password = "bare-pass"
        """,
    )
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(toml_path))

    config = load_config()

    assert config.username == "bare-user"
    assert config.password == "bare-pass"


def test_missing_credentials_raises_config_error_before_any_network_call(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(tmp_path / "does-not-exist.toml"))

    with pytest.raises(ConfigError):
        load_config()


def test_defaults_are_applied_when_optional_settings_absent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(tmp_path / "does-not-exist.toml"))
    monkeypatch.setenv("FORLABS_USERNAME", "user")
    monkeypatch.setenv("FORLABS_PASSWORD", "pass")

    config = load_config()

    assert config.base_url == "https://bki.forlabs.ru"
    assert config.timeout_seconds == 30.0
    assert config.timezone == "Asia/Irkutsk"
    assert config.max_items == 200


def test_redacted_never_contains_the_password() -> None:
    config = ForlabsConfig(username="user", password="super-secret-value")

    redacted = config.redacted()

    assert "super-secret-value" not in repr(redacted)
    assert redacted["password"] == "***"
