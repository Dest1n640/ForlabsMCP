#!/usr/bin/env python3
"""Leak scanner for git-tracked files: secret-shaped values, personal names
and absolute home paths.

Used by tests/test_repo_privacy.py (whole tracked tree) and by
.githooks/pre-commit (staged content). Findings carry file, line and rule
name only - the matched text is never stored or printed, so a failure can't
become the leak.

Stdlib only, so the hook runs without `uv sync`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PLACEHOLDER_TOKEN = "PASTE_YOUR_remember_lm_COOKIE_VALUE_HERE"

# Synthetic names used in tests/fixtures/*.json - never real people.
# Keep in sync whenever a new synthetic name is introduced into a fixture.
ALLOWED_NAMES = {
    "Голубев Артём Николаевич",
    "Кравцова Наталья Игоревна",
    "Орлов Пётр Андреевич",
    "Семёнов Владимир Игоревич",
    "Тихонов Максим Олегович",
    "Фомина Ольга Викторовна",
}

# Files that are large, generated, or not text worth scanning.
SKIP_FILES = {"uv.lock"}

# High-confidence secret shapes only. A bare `remember_lm_<hash>` cookie *name*
# is deliberately not a rule: it is the same for every account on this
# deployment, and only the *value* is secret.
SECRET_RULES: dict[str, re.Pattern[str]] = {
    "laravel-remember-value": re.compile(r"\b\d{1,10}(?:\||%7C)[A-Za-z0-9]{40,}"),
    "encrypted-payload-or-jwt": re.compile(r"eyJ[A-Za-z0-9_%\-]{20,}"),
    "xsrf-cookie-value": re.compile(r"XSRF-TOKEN=[A-Za-z0-9%_\-]{20,}"),
    "session-cookie-value": re.compile(r"forlabs_session=[A-Za-z0-9%_\-]{20,}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "openai-style-key": re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "bearer-token": re.compile(r"Bearer [A-Za-z0-9._\-]{20,}"),
}

NAME_SHAPE_RE = re.compile(r"[А-ЯЁ][а-яё]+(?:[ \t]+[А-ЯЁ][а-яё]+){1,2}")
ABSOLUTE_PATH_RE = re.compile(r"(?:/Users/|/home/)[A-Za-z0-9_.\-]+")
SESSION_TOKEN_KEY = "session_token"


@dataclass(frozen=True)
class Finding:
    """Deliberately has no `value` field: callers cannot print the match."""

    path: str
    line: int
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(path: str, text: str) -> list[Finding]:
    """Return findings for one file's text (empty if clean)."""
    findings: list[Finding] = []
    for rule, pattern in SECRET_RULES.items():
        for match in pattern.finditer(text):
            findings.append(Finding(path, _line_of(text, match.start()), rule))
    for match in NAME_SHAPE_RE.finditer(text):
        if match.group() not in ALLOWED_NAMES:
            findings.append(Finding(path, _line_of(text, match.start()), "unlisted-personal-name"))
    for match in ABSOLUTE_PATH_RE.finditer(text):
        findings.append(Finding(path, _line_of(text, match.start()), "absolute-home-path"))
    if path.endswith(".json"):
        findings.extend(_scan_json_token(path, text))
    return sorted(set(findings), key=lambda f: (f.path, f.line, f.rule))


def _scan_json_token(path: str, text: str) -> list[Finding]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if (
        isinstance(data, dict)
        and data.get(SESSION_TOKEN_KEY, PLACEHOLDER_TOKEN) != PLACEHOLDER_TOKEN
    ):
        match = re.search(rf'"{SESSION_TOKEN_KEY}"', text)
        line = _line_of(text, match.start()) if match else 1
        return [Finding(path, line, "non-placeholder-session-token")]
    return []


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def _decode(raw: bytes) -> str | None:
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def tracked_paths(root: Path = REPO_ROOT) -> list[str]:
    out = _git(root, "ls-files", "-z").decode("utf-8")
    return [p for p in out.split("\0") if p and Path(p).name not in SKIP_FILES]


def staged_paths(root: Path = REPO_ROOT) -> list[str]:
    out = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode("utf-8")
    return [p for p in out.split("\0") if p and Path(p).name not in SKIP_FILES]


def scan_tracked(root: Path = REPO_ROOT) -> list[Finding]:
    """Scan the working-tree copy of every tracked file."""
    findings: list[Finding] = []
    for path in tracked_paths(root):
        file = root / path
        if not file.is_file():
            continue
        text = _decode(file.read_bytes())
        if text is not None:
            findings.extend(scan_text(path, text))
    return findings


def scan_staged(root: Path = REPO_ROOT) -> list[Finding]:
    """Scan the index (staged) version of each staged file."""
    findings: list[Finding] = []
    for path in staged_paths(root):
        text = _decode(_git(root, "show", f":{path}"))
        if text is not None:
            findings.extend(scan_text(path, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", help="scan every tracked file (default)")
    mode.add_argument("--staged", action="store_true", help="scan staged content only")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    findings = scan_staged(args.root) if args.staged else scan_tracked(args.root)
    for finding in findings:
        print(finding)
    if findings:
        print(
            f"leakscan: {len(findings)} finding(s); values are not shown. "
            "Fix the file(s) above or, for a deliberate constant, extend the allow-list.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
