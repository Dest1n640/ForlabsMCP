"""Unit tests for tools/leakscan.py.

Secret-shaped test values are assembled at runtime so this file itself never
contains a string the scanner would flag.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.leakscan import PLACEHOLDER_TOKEN, Finding, main, scan_text

SCRIPT = Path(__file__).parent.parent / "tools" / "leakscan.py"

_A = "a" * 44
CASES = {
    "laravel-remember-value": "12" + "%7C" + _A,
    "encrypted-payload-or-jwt": "ey" + "J" + "a" * 30,
    "xsrf-cookie-value": "XSRF-TOKEN" + "=" + "b" * 30,
    "session-cookie-value": "forlabs_session" + "=" + "c" * 30,
    "github-token": "gh" + "p_" + "d" * 36,
    "openai-style-key": "sk" + "-" + "e" * 30,
    "aws-access-key": "AK" + "IA" + "F" * 16,
    "private-key-block": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "bearer-token": "Bearer" + " " + "g" * 30,
}


@pytest.mark.parametrize("rule", sorted(CASES))
def test_each_secret_rule_flags_its_shape(rule: str) -> None:
    findings = scan_text("doc.md", f"prefix\n{CASES[rule]}\n")
    assert [(f.rule, f.line) for f in findings] == [(rule, 2)]


@pytest.mark.parametrize(
    "text",
    [
        "remember_lm_59ba36addc2b2f9401580f014c7f58ea4e30989d",  # cookie *name* only
        PLACEHOLDER_TOKEN,
        "Bearer token",
        "XSRF-TOKEN=<value>",
        "Forlabs Diary",
        "Кравцова Наталья Игоревна",
    ],
)
def test_safe_text_is_not_flagged(text: str) -> None:
    assert scan_text("doc.md", text) == []


def test_unlisted_name_and_home_path_are_flagged() -> None:
    name = "Иванов" + " " + "Иван" + " " + "Иванович"
    path = "/Us" + "ers/" + "someone"
    rules = {f.rule for f in scan_text("a.md", f"{name}\n{path}/x")}
    assert rules == {"unlisted-personal-name", "absolute-home-path"}


def test_non_placeholder_session_token_in_json_is_flagged() -> None:
    findings = scan_text("cfg.json", '{"session_token": "real-looking"}')
    assert [f.rule for f in findings] == ["non-placeholder-session-token"]


def test_placeholder_session_token_in_json_is_accepted() -> None:
    assert scan_text("cfg.json", f'{{"session_token": "{PLACEHOLDER_TOKEN}"}}') == []


def test_findings_never_carry_or_print_the_matched_value() -> None:
    secret = CASES["github-token"]
    (finding,) = scan_text("doc.md", secret)
    assert isinstance(finding, Finding)
    assert not hasattr(finding, "value")
    assert secret not in str(finding) and secret not in repr(finding)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _run_staged(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--staged", "--root", str(repo)],
        capture_output=True,
        text=True,
    )


def test_staged_secret_is_reported_without_its_value(repo: Path) -> None:
    secret = CASES["github-token"]
    (repo / "notes.md").write_text(f"ok\n{secret}\n")
    _git(repo, "add", "notes.md")

    result = _run_staged(repo)

    assert result.returncode == 1
    assert "notes.md:2: github-token" in result.stdout
    assert secret not in result.stdout + result.stderr


def test_secret_only_in_working_tree_does_not_block(repo: Path) -> None:
    (repo / "notes.md").write_text("clean\n")
    _git(repo, "add", "notes.md")
    (repo / "notes.md").write_text(CASES["github-token"])  # unstaged edit

    assert _run_staged(repo).returncode == 0


def test_clean_staged_commit_passes(repo: Path) -> None:
    (repo / "notes.md").write_text("nothing to see\n")
    _git(repo, "add", "notes.md")

    assert _run_staged(repo).returncode == 0


def test_main_all_mode_flags_a_tracked_secret(repo: Path, capsys: pytest.CaptureFixture) -> None:
    (repo / "notes.md").write_text(CASES["aws-access-key"])
    _git(repo, "add", "notes.md")

    assert main(["--all", "--root", str(repo)]) == 1
    assert "notes.md:1: aws-access-key" in capsys.readouterr().out


def test_newly_added_directory_is_covered(repo: Path) -> None:
    (repo / "brand" / "new").mkdir(parents=True)
    (repo / "brand" / "new" / "f.txt").write_text(CASES["bearer-token"])
    _git(repo, "add", "-A")

    assert main(["--all", "--root", str(repo)]) == 1
