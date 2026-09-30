"""Guardrail: scans git-tracked fixtures/docs for leaked real names or
absolute local paths.

Deliberately scans `git ls-files` output, not the filesystem glob - a
gitignored local scratch file is never flagged or forced to be
sanitized. See PROJECT-REFERENCE.md §12 for why this exists: real
names and a real local path were committed once early in this
project's history and had to be scrubbed after the fact.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

PLACEHOLDER_TOKEN = "PASTE_YOUR_remember_lm_COOKIE_VALUE_HERE"

NAME_SHAPE_RE = re.compile(r"[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2}")
ABSOLUTE_PATH_RE = re.compile(r"(?:/Users/|/home/)[A-Za-z0-9_.\-]+")

# Synthetic names already used in tests/fixtures/*.json - never real people.
# Keep this in sync whenever a new synthetic name is introduced into a fixture.
ALLOWED_NAMES = {
    "Голубев Артём Николаевич",
    "Кравцова Наталья Игоревна",
    "Орлов Пётр Андреевич",
    "Семёнов Владимир Игоревич",
    "Тихонов Максим Олегович",
    "Фомина Ольга Викторовна",
}


def _tracked_files(patterns: list[str]) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def find_privacy_violations(text: str) -> list[str]:
    """Return violation descriptions found in `text` (empty if none)."""
    violations: list[str] = []
    for match in NAME_SHAPE_RE.finditer(text):
        name = match.group()
        if name not in ALLOWED_NAMES:
            violations.append(f"name-shaped text not on the allow-list: {name!r}")
    for match in ABSOLUTE_PATH_RE.finditer(text):
        violations.append(f"absolute local path: {match.group()!r}")
    return violations


def test_tracked_fixtures_and_docs_have_no_privacy_violations() -> None:
    files = _tracked_files(["tests/fixtures/*.json", "docs/*.md"])
    all_violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for violation in find_privacy_violations(text):
            all_violations.append(f"{path.relative_to(REPO_ROOT)}: {violation}")
    assert all_violations == []


def test_find_privacy_violations_catches_a_name_not_on_the_allow_list() -> None:
    text = '{"lecturer_name": "Иванов Иван Иванович"}'
    violations = find_privacy_violations(text)
    assert len(violations) == 1
    assert "Иванов Иван Иванович" in violations[0]


def test_find_privacy_violations_catches_an_absolute_home_path() -> None:
    text = '{"note": "see /Users/someone/scratch.txt for details"}'
    violations = find_privacy_violations(text)
    assert any("absolute local path" in v for v in violations)


def test_find_privacy_violations_allows_known_synthetic_names() -> None:
    text = '{"lecturer_name": "Кравцова Наталья Игоревна"}'
    assert find_privacy_violations(text) == []


def find_token_violations(text: str) -> list[str]:
    """Return a violation if `text` is JSON carrying a non-placeholder session_token."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict) and data.get("session_token", PLACEHOLDER_TOKEN) != PLACEHOLDER_TOKEN:
        return ["non-placeholder session_token"]
    return []


def test_tracked_json_files_carry_no_real_session_token() -> None:
    violations = [
        str(path.relative_to(REPO_ROOT))
        for path in _tracked_files(["*.json"])
        if find_token_violations(path.read_text(encoding="utf-8"))
    ]
    assert violations == []


def test_find_token_violations_flags_a_real_looking_token() -> None:
    assert find_token_violations('{"session_token": "eyJabc123"}') != []


def test_find_token_violations_accepts_the_placeholder() -> None:
    assert find_token_violations(f'{{"session_token": "{PLACEHOLDER_TOKEN}"}}') == []
