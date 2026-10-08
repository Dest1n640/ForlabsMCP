"""One-use, short-lived assignment submission preparations and file checks."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import secrets
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ..errors import InvalidArgumentError

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
PREPARATION_TTL_SECONDS = 600
_PREPARATION_LIMIT = 128
_HASH_READ_SIZE = 1024 * 1024


@dataclass(frozen=True)
class PreparedFile:
    path: Path
    name: str
    size: int
    mtime_ns: int
    device: int
    inode: int
    sha256: str
    mime_type: str
    flow_identifier: str


@dataclass(frozen=True)
class PreparedResponse:
    preparation_id: str
    study_id: int
    task_id: int
    assignment_id: int
    task_title: str
    message: str
    files: tuple[PreparedFile, ...]
    expires_at: float


class SubmissionPreparations:
    """Keeps previews in process memory; tokens are opaque and consumed once."""

    def __init__(self, upload_root: Path | None) -> None:
        self._upload_root = upload_root
        self._records: dict[str, PreparedResponse] = {}

    def prepare(
        self,
        *,
        study_id: int,
        task_id: int,
        assignment_id: int,
        task_title: str,
        message: str,
        file_paths: list[str] | None,
    ) -> PreparedResponse:
        now = time.monotonic()
        self._prune(now)
        if len(self._records) >= _PREPARATION_LIMIT:
            raise InvalidArgumentError(
                "Too many unexpired previews; submit or wait for an earlier preview to expire."
            )
        if not isinstance(message, str):
            raise InvalidArgumentError("message must be text.", argument="message")
        selected_paths = file_paths or []
        if not message.strip() and not selected_paths:
            raise InvalidArgumentError(
                "A response must contain text or at least one attachment.", argument="message"
            )

        files = tuple(self._snapshot_file(path) for path in selected_paths)
        preparation_id = secrets.token_urlsafe(32)
        prepared = PreparedResponse(
            preparation_id=preparation_id,
            study_id=study_id,
            task_id=task_id,
            assignment_id=assignment_id,
            task_title=task_title,
            message=message.strip(),
            files=files,
            expires_at=now + PREPARATION_TTL_SECONDS,
        )
        self._records[preparation_id] = prepared
        return prepared

    def consume(self, preparation_id: str) -> PreparedResponse:
        if not isinstance(preparation_id, str) or not preparation_id:
            raise InvalidArgumentError("preparation_id is required.", argument="preparation_id")
        prepared = self._records.pop(preparation_id, None)
        if prepared is None or prepared.expires_at <= time.monotonic():
            raise InvalidArgumentError(
                "The preview is unknown, expired, or already used.", argument="preparation_id"
            )
        return prepared

    def verify_files(self, prepared: PreparedResponse) -> None:
        for item in prepared.files:
            with self.open_prepared_file(item) as file:
                digest, size, info = self._fingerprint(file)
            if (
                digest != item.sha256
                or size != item.size
                or info.st_mtime_ns != item.mtime_ns
                or info.st_dev != item.device
                or info.st_ino != item.inode
            ):
                raise InvalidArgumentError(
                    f"Attachment {item.name!r} changed after preview.", argument="file_paths"
                )

    @contextmanager
    def open_prepared_file(self, item: PreparedFile) -> Iterator[BinaryIO]:
        try:
            with self._open_prepared_file(item) as file:
                yield file
        except OSError as exc:
            raise InvalidArgumentError(
                "The previewed attachment is no longer readable.", argument="file_paths"
            ) from exc

    def _snapshot_file(self, selected_path: str) -> PreparedFile:
        if self._upload_root is None:
            raise InvalidArgumentError(
                "Set FORLABS_UPLOAD_ROOT before selecting attachments.", argument="file_paths"
            )
        path = self._resolve_selected_path(selected_path)
        try:
            with self._open_regular_file(path) as file:
                if os.fstat(file.fileno()).st_size > MAX_ATTACHMENT_BYTES:
                    raise InvalidArgumentError(
                        "Each attachment must be no larger than 50 MiB.",
                        argument="file_paths",
                    )
                digest, size, info = self._fingerprint(file)
        except OSError as exc:
            raise InvalidArgumentError(
                "Attachments must be readable regular files under FORLABS_UPLOAD_ROOT.",
                argument="file_paths",
            ) from exc
        if size > MAX_ATTACHMENT_BYTES:
            raise InvalidArgumentError(
                "Each attachment must be no larger than 50 MiB.", argument="file_paths"
            )
        if not stat.S_ISREG(info.st_mode):
            raise InvalidArgumentError("Attachments must be regular files.", argument="file_paths")
        name = path.name
        if not name or any(ord(character) < 32 for character in name) or "\\" in name:
            raise InvalidArgumentError(
                "The attachment filename is not supported.", argument="file_paths"
            )
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return PreparedFile(
            path=path,
            name=name,
            size=size,
            mtime_ns=info.st_mtime_ns,
            device=info.st_dev,
            inode=info.st_ino,
            sha256=digest,
            mime_type=mime_type,
            flow_identifier=f"{size}-{secrets.token_urlsafe(18)}",
        )

    def _resolve_selected_path(self, selected_path: str) -> Path:
        if not isinstance(selected_path, str) or not selected_path:
            raise InvalidArgumentError(
                "file_paths entries must be non-empty paths.", argument="file_paths"
            )
        try:
            root = self._upload_root.resolve(strict=True)
            if not root.is_dir():
                raise OSError
            candidate = Path(selected_path).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
            candidate = Path(os.path.abspath(candidate))
            relative = candidate.relative_to(root)
            current = root
            for component in relative.parts:
                current = current / component
                if current.is_symlink():
                    raise OSError
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise OSError
            return resolved
        except (OSError, ValueError) as exc:
            raise InvalidArgumentError(
                "Each attachment must resolve to a non-symlink path under FORLABS_UPLOAD_ROOT.",
                argument="file_paths",
            ) from exc

    def _open_prepared_file(self, item: PreparedFile) -> BinaryIO:
        if self._upload_root is None:
            raise InvalidArgumentError(
                "FORLABS_UPLOAD_ROOT is required for attachments.", argument="file_paths"
            )
        path = self._resolve_selected_path(str(item.path))
        try:
            file = self._open_regular_file(path)
            info = os.fstat(file.fileno())
        except OSError as exc:
            raise InvalidArgumentError(
                "The previewed attachment is no longer readable.", argument="file_paths"
            ) from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size != item.size
            or info.st_mtime_ns != item.mtime_ns
            or info.st_dev != item.device
            or info.st_ino != item.inode
        ):
            file.close()
            raise InvalidArgumentError(
                f"Attachment {item.name!r} changed after preview.", argument="file_paths"
            )
        return file

    @staticmethod
    def _open_regular_file(path: Path) -> BinaryIO:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        file = os.fdopen(descriptor, "rb")
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            file.close()
            raise OSError("not a regular file")
        return file

    @staticmethod
    def _fingerprint(file: BinaryIO) -> tuple[str, int, os.stat_result]:
        before = os.fstat(file.fileno())
        digest = hashlib.sha256()
        size = 0
        while chunk := file.read(_HASH_READ_SIZE):
            digest.update(chunk)
            size += len(chunk)
            if size > MAX_ATTACHMENT_BYTES:
                raise InvalidArgumentError(
                    "Each attachment must be no larger than 50 MiB.",
                    argument="file_paths",
                )
        after = os.fstat(file.fileno())
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or size != after.st_size
        ):
            raise InvalidArgumentError(
                "An attachment changed while it was being read.", argument="file_paths"
            )
        return digest.hexdigest(), size, after

    def _prune(self, now: float) -> None:
        expired = [
            preparation_id
            for preparation_id, record in self._records.items()
            if record.expires_at <= now
        ]
        for preparation_id in expired:
            del self._records[preparation_id]
