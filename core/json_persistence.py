"""Small JSON persistence helpers for local artifact files."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def atomic_write_json(path: Path | str, payload: Any) -> None:
    """Write JSON by replacing the destination with a same-directory temp file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, output_path)
        temp_path = None
        # Persist the rename as well as the file contents before acknowledging it.
        directory_fd = os.open(output_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


class FileLock:
    """Process-safe exclusive file lock for macOS/Linux local filesystems."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._handle: Any = None

    def __enter__(self) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            self._handle.close()
            self._handle = None
            raise
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
