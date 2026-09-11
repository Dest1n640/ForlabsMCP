import importlib.util
import tomllib
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "setup_config.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("setup_config", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def setup_config():
    return _load_module()


def _scripted_input(responses: list[str]):
    it = iter(responses)

    def _input(prompt: str = "") -> str:
        return next(it)

    return _input


def test_render_toml_round_trips_special_characters(setup_config) -> None:
    rendered = setup_config.render_toml({"password": 'weird"pass\\word'})
    parsed = tomllib.loads(rendered)
    assert parsed["forlabs"]["password"] == 'weird"pass\\word'


def test_run_writes_credentials_with_restricted_permissions(
    tmp_path, monkeypatch: pytest.MonkeyPatch, setup_config
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(config_path))
    monkeypatch.setattr(
        setup_config, "input", _scripted_input(["student.login", "", ""]), raising=False
    )
    monkeypatch.setattr(setup_config.getpass, "getpass", lambda prompt="": "super-secret")

    setup_config.run()

    assert config_path.is_file()
    mode = config_path.stat().st_mode & 0o777
    assert mode == 0o600

    data = tomllib.loads(config_path.read_text())["forlabs"]
    assert data["username"] == "student.login"
    assert data["password"] == "super-secret"
    assert data["base_url"] == setup_config.DEFAULT_BASE_URL
    assert data["timezone"] == setup_config.DEFAULT_TZ


def test_run_accepts_custom_optional_values(
    tmp_path, monkeypatch: pytest.MonkeyPatch, setup_config
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(config_path))
    monkeypatch.setattr(
        setup_config,
        "input",
        _scripted_input(["student.login", "https://example.test", "Europe/Moscow"]),
        raising=False,
    )
    monkeypatch.setattr(setup_config.getpass, "getpass", lambda prompt="": "super-secret")

    setup_config.run()

    data = tomllib.loads(config_path.read_text())["forlabs"]
    assert data["base_url"] == "https://example.test"
    assert data["timezone"] == "Europe/Moscow"


def test_run_declining_overwrite_leaves_existing_file_untouched(
    tmp_path, monkeypatch: pytest.MonkeyPatch, setup_config
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[forlabs]\nusername = "old"\npassword = "old-pass"\n')
    original_content = config_path.read_text()

    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(config_path))
    monkeypatch.setattr(setup_config, "input", _scripted_input(["n"]), raising=False)

    setup_config.run()

    assert config_path.read_text() == original_content


def test_password_never_appears_in_captured_output(
    tmp_path, monkeypatch: pytest.MonkeyPatch, setup_config, capsys
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("FORLABS_MCP_CONFIG", str(config_path))
    monkeypatch.setattr(
        setup_config, "input", _scripted_input(["student.login", "", ""]), raising=False
    )
    monkeypatch.setattr(setup_config.getpass, "getpass", lambda prompt="": "super-secret-value")

    setup_config.run()

    captured = capsys.readouterr()
    assert "super-secret-value" not in captured.out
    assert "super-secret-value" not in captured.err
