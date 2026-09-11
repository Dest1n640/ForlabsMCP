import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "print_mcp_config.py"
REPO_ROOT = Path(__file__).parent.parent


def _run(
    cwd: Path,
    args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    config_path: Path | None = None,
) -> str:
    env = os.environ.copy()
    # Hermetic by default: never let this test depend on whatever might
    # already exist at the real default config path on the machine running it.
    env["FORLABS_MCP_CONFIG"] = str(config_path or (cwd / "does-not-exist.toml"))
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *(args or [])],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_prints_correct_absolute_directory_from_a_different_cwd(tmp_path) -> None:
    config = json.loads(_run(cwd=tmp_path))

    assert config["command"] == "uv"
    assert config["args"] == ["--directory", str(REPO_ROOT), "run", "forlabs-mcp"]


def test_placeholder_env_shown_when_no_toml_credentials_exist(tmp_path) -> None:
    config = json.loads(_run(cwd=tmp_path))

    assert config["env"]["FORLABS_USERNAME"] == "your.login"
    assert config["env"]["FORLABS_PASSWORD"] == "your-password"


def test_never_embeds_real_credentials_even_when_set_in_the_environment(tmp_path) -> None:
    extra_env = {
        "FORLABS_USERNAME": "a.real.student.login",
        "FORLABS_PASSWORD": "a-real-password-value",
    }
    output = _run(cwd=tmp_path, extra_env=extra_env)
    config = json.loads(output)

    assert config["env"]["FORLABS_USERNAME"] == "your.login"
    assert config["env"]["FORLABS_PASSWORD"] == "your-password"
    assert "a.real.student.login" not in output
    assert "a-real-password-value" not in output


def test_env_block_is_omitted_when_setup_config_already_saved_credentials(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[forlabs]\nusername = "student.login"\npassword = "saved-pass"\n')

    output = _run(cwd=tmp_path, config_path=config_path)
    config = json.loads(output)

    assert "env" not in config
    assert "student.login" not in output
    assert "saved-pass" not in output


def test_env_block_still_shown_when_toml_has_only_username(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[forlabs]\nusername = "student.login"\n')

    output = _run(cwd=tmp_path, config_path=config_path)
    config = json.loads(output)

    assert config["env"]["FORLABS_USERNAME"] == "your.login"


def test_host_raw_is_the_default(tmp_path) -> None:
    default_output = _run(cwd=tmp_path)
    explicit_output = _run(cwd=tmp_path, args=["--host", "raw"])
    assert default_output == explicit_output


def test_host_claude_desktop_wraps_under_mcp_servers_forlabs(tmp_path) -> None:
    output = _run(cwd=tmp_path, args=["--host", "claude-desktop"])
    parsed = json.loads(output)

    assert set(parsed.keys()) == {"mcpServers"}
    forlabs_config = parsed["mcpServers"]["forlabs"]
    assert forlabs_config["command"] == "uv"
    assert forlabs_config["args"] == ["--directory", str(REPO_ROOT), "run", "forlabs-mcp"]
    assert forlabs_config["env"]["FORLABS_USERNAME"] == "your.login"


def test_host_claude_desktop_omits_env_when_credentials_already_saved(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[forlabs]\nusername = "student.login"\npassword = "saved-pass"\n')

    output = _run(cwd=tmp_path, args=["--host", "claude-desktop"], config_path=config_path)
    parsed = json.loads(output)

    assert "env" not in parsed["mcpServers"]["forlabs"]


def test_host_claude_code_prints_a_ready_add_json_command(tmp_path) -> None:
    output = _run(cwd=tmp_path, args=["--host", "claude-code"]).strip()

    assert output.startswith("claude mcp add-json forlabs '")
    assert output.endswith("'")
    inline_json = output.removeprefix("claude mcp add-json forlabs '").removesuffix("'")
    config = json.loads(inline_json)
    assert config["command"] == "uv"
    assert config["env"]["FORLABS_PASSWORD"] == "your-password"


def test_host_claude_code_never_embeds_real_credentials(tmp_path) -> None:
    extra_env = {
        "FORLABS_USERNAME": "a.real.student.login",
        "FORLABS_PASSWORD": "a-real-password-value",
    }
    output = _run(cwd=tmp_path, args=["--host", "claude-code"], extra_env=extra_env)

    assert "a.real.student.login" not in output
    assert "a-real-password-value" not in output


def test_host_claude_code_omits_env_when_credentials_already_saved(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[forlabs]\nusername = "student.login"\npassword = "saved-pass"\n')

    output = _run(cwd=tmp_path, args=["--host", "claude-code"], config_path=config_path).strip()
    inline_json = output.removeprefix("claude mcp add-json forlabs '").removesuffix("'")
    config = json.loads(inline_json)

    assert "env" not in config
