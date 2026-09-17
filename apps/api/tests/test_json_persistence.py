import fcntl
import json
import multiprocessing
import sys
import types
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core import json_persistence  # noqa: E402
from core.json_persistence import FileLock, atomic_write_json  # noqa: E402


def _try_lock(path: str, queue: multiprocessing.Queue) -> None:
    with Path(path).open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            queue.put(False)
            return
        try:
            queue.put(True)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _assert_process_can_lock(lock_path: Path) -> None:
    queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_try_lock, args=(str(lock_path), queue))
    process.start()
    process.join(timeout=5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("lock acquisition process timed out")

    assert process.exitcode == 0
    assert queue.get(timeout=1) is True


def test_atomic_write_json_replaces_with_expected_json(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "artifact.json"

    atomic_write_json(output_path, {"b": 2, "a": 1})

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert output_path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}'


def test_atomic_write_json_failure_before_replace_preserves_destination(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "artifact.json"
    output_path.write_text('{"old": true}', encoding="utf-8")

    with pytest.raises(TypeError):
        atomic_write_json(output_path, {"bad": object()})

    assert output_path.read_text(encoding="utf-8") == '{"old": true}'
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"old": True}


def test_atomic_write_json_cleans_temp_files_after_failure(tmp_path: Path) -> None:
    output_path = tmp_path / "artifact.json"
    output_path.write_text('{"old": true}', encoding="utf-8")

    with pytest.raises(TypeError):
        atomic_write_json(output_path, {"bad": object()})

    assert list(tmp_path.glob(".artifact.json.*.tmp")) == []


def test_atomic_write_json_destination_never_contains_partial_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "artifact.json"
    output_path.write_text('{"old": true}', encoding="utf-8")

    def fail_fsync(_fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(json_persistence.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="fsync failed"):
        atomic_write_json(output_path, {"new": True})

    assert output_path.read_text(encoding="utf-8") == '{"old": true}'
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"old": True}


def test_file_lock_releases_after_normal_exit(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "artifact.lock"

    with FileLock(lock_path):
        assert lock_path.exists()

    _assert_process_can_lock(lock_path)


def test_file_lock_releases_after_exception(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "artifact.lock"

    with pytest.raises(RuntimeError, match="inside lock"):
        with FileLock(lock_path):
            raise RuntimeError("inside lock")

    _assert_process_can_lock(lock_path)


def test_file_lock_blocks_another_process_while_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "artifact.lock"
    queue: multiprocessing.Queue[Any] = multiprocessing.Queue()

    with FileLock(lock_path):
        process = multiprocessing.Process(target=_try_lock, args=(str(lock_path), queue))
        process.start()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            pytest.fail("lock acquisition process timed out")

    assert process.exitcode == 0
    assert queue.get(timeout=1) is False


def test_file_lock_closes_handle_when_flock_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = FileLock(tmp_path / "locks" / "artifact.lock")
    lock.path.parent.mkdir(parents=True)
    opened_handle = lock.path.open("a+", encoding="utf-8")

    def open_handle(_path: Path, *_args: Any, **_kwargs: Any) -> Any:
        return opened_handle

    def fail_flock(_fd: int, _operation: int) -> None:
        raise OSError("flock failed")

    monkeypatch.setattr(Path, "open", open_handle)
    monkeypatch.setattr(json_persistence.fcntl, "flock", fail_flock)

    with pytest.raises(OSError, match="flock failed"):
        lock.__enter__()

    assert opened_handle.closed
    assert lock._handle is None


def test_directory_sync_failure_is_reported_after_atomic_replace(tmp_path, monkeypatch):
    import stat

    output_path = tmp_path / "artifact.json"
    atomic_write_json(output_path, {"old": True})
    original_fsync = json_persistence.os.fsync

    def fail_directory_sync(fd):
        if stat.S_ISDIR(json_persistence.os.fstat(fd).st_mode):
            raise OSError("directory sync failed")
        original_fsync(fd)

    monkeypatch.setattr(json_persistence.os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="directory sync failed"):
        atomic_write_json(output_path, {"new": True})
    # A failed durability acknowledgement must still leave a complete JSON file.
    assert json.loads(output_path.read_text()) == {"new": True}
    assert list(tmp_path.glob(".artifact.json.*.tmp")) == []
