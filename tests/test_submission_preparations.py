import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from forlabs_mcp.client.submissions import (
    MAX_ATTACHMENT_BYTES,
    PREPARATION_TTL_SECONDS,
    SubmissionPreparations,
)
from forlabs_mcp.errors import InvalidArgumentError


def _prepare(
    preparations: SubmissionPreparations,
    *,
    message: str = "answer",
    file_paths: list[str] | None = None,
):
    return preparations.prepare(
        study_id=11,
        task_id=22,
        assignment_id=33,
        task_title="Synthetic task",
        message=message,
        file_paths=file_paths,
    )


def test_text_only_preview_is_trimmed_and_preparation_can_be_consumed_once() -> None:
    preparations = SubmissionPreparations(None)

    preview = _prepare(preparations, message="  exact answer  ")

    assert preview.message == "exact answer"
    assert preparations.consume(preview.preparation_id) == preview
    with pytest.raises(InvalidArgumentError, match="already used"):
        preparations.consume(preview.preparation_id)


def test_empty_response_is_rejected() -> None:
    with pytest.raises(InvalidArgumentError, match="text or at least one attachment"):
        _prepare(SubmissionPreparations(None), message="  ")


def test_expired_preparation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1_000.0]
    monkeypatch.setattr("forlabs_mcp.client.submissions.time.monotonic", lambda: clock[0])
    preparations = SubmissionPreparations(None)
    preview = _prepare(preparations)
    clock[0] += PREPARATION_TTL_SECONDS + 1

    with pytest.raises(InvalidArgumentError, match="expired"):
        preparations.consume(preview.preparation_id)


def test_symlink_attachment_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not allowed")
    (root / "link.txt").symlink_to(outside)

    with pytest.raises(InvalidArgumentError, match="non-symlink path"):
        _prepare(SubmissionPreparations(root), file_paths=["link.txt"])


def test_unreadable_attachment_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "answer.txt").write_text("answer")

    def deny_open(path: str | bytes, flags: int, *args: object) -> int:
        raise PermissionError("synthetic permission failure")

    monkeypatch.setattr(os, "open", deny_open)
    with pytest.raises(InvalidArgumentError, match="readable regular files"):
        _prepare(SubmissionPreparations(root), file_paths=["answer.txt"])


def test_attachment_above_50_mib_is_rejected_without_reading_50_mib(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "large.bin").write_bytes(b"x")

    def oversized_fingerprint(file):
        info = os.fstat(file.fileno())
        return (
            "0" * 64,
            MAX_ATTACHMENT_BYTES + 1,
            SimpleNamespace(
                st_mode=info.st_mode,
                st_size=MAX_ATTACHMENT_BYTES + 1,
                st_mtime_ns=info.st_mtime_ns,
                st_dev=info.st_dev,
                st_ino=info.st_ino,
            ),
        )

    monkeypatch.setattr(SubmissionPreparations, "_fingerprint", staticmethod(oversized_fingerprint))
    with pytest.raises(InvalidArgumentError, match="50 MiB"):
        _prepare(SubmissionPreparations(root), file_paths=["large.bin"])
