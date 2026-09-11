import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "print_mcp_config.py"
REPO_ROOT = Path(__file__).parent.parent


def _run(cwd: Path, env: dict[str, str] | None = None) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_prints_correct_absolute_directory_from_a_different_cwd(tmp_path) -> None:
    config = _run(cwd=tmp_path)

    assert config["command"] == "uv"
    assert config["args"] == ["--directory", str(REPO_ROOT), "run", "forlabs-mcp"]


def test_never_embeds_real_credentials_even_when_set_in_the_environment(tmp_path) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "FORLABS_USERNAME": "a.real.student.login",
        "FORLABS_PASSWORD": "a-real-password-value",
    }
    config = _run(cwd=tmp_path, env=env)

    assert config["env"]["FORLABS_USERNAME"] == "your.login"
    assert config["env"]["FORLABS_PASSWORD"] == "your-password"
    assert "a.real.student.login" not in json.dumps(config)
    assert "a-real-password-value" not in json.dumps(config)
