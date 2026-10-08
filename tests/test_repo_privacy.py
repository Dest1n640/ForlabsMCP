"""Guardrail: scans every git-tracked text file for leaked secrets, real
names and absolute local paths via tools/leakscan.py.

Deliberately scans `git ls-files` output, not a filesystem glob - a
gitignored local file (forlabs-session.json) is never read. Failure output
is `path:line: rule` only; the matched value is never shown. See
PROJECT-REFERENCE.md §12 for why this exists: real names and a real local
path were committed once early in this project's history and had to be
scrubbed after the fact.
"""

from __future__ import annotations

import subprocess

from tools.leakscan import REPO_ROOT, scan_text, scan_tracked, tracked_paths


def test_tracked_files_have_no_leaks() -> None:
    assert [str(f) for f in scan_tracked()] == []


def test_scan_covers_readme_reference_and_source() -> None:
    paths = set(tracked_paths())
    assert {"README.md", "PROJECT-REFERENCE.md", "src/forlabs_mcp/config.py"} <= paths


def test_gitignored_token_file_is_not_scanned() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "forlabs-session.json"], cwd=REPO_ROOT
    ).returncode
    assert ignored == 0
    assert "forlabs-session.json" not in tracked_paths()


def test_workflow_fixtures_are_anonymized() -> None:
    fixture_names = [
        "sched_get_schedule_groups.json",
        "learning_get_streams.json",
        "learning_get_task.json",
        "learning_get_tasks_assignments.json",
        "assignments_get_comments.json",
    ]
    for name in fixture_names:
        path = REPO_ROOT / "tests" / "fixtures" / name
        assert scan_text(str(path.relative_to(REPO_ROOT)), path.read_text()) == []


def test_synthetic_names_are_allowed() -> None:
    assert scan_text("f.json", '{"lecturer_name": "Кравцова Наталья Игоревна"}') == []
