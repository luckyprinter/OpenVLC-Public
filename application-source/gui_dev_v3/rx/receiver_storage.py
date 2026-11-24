"""Storage primitives shared by receiver history and experiments."""

from __future__ import annotations

import json
from hashlib import sha256
import os
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QLockFile


_STATE_LOCK = threading.Lock()
HISTORY_FILENAME = "transfer_history.json"
EXPERIMENTS_FILENAME = "experiments.json"
RESTORE_JOURNAL = ".receiver-db-restore.json"
STATE_LOCK_NAME = ".receiver-db.lock"
_DATABASE_FILES = {HISTORY_FILENAME, EXPERIMENTS_FILENAME}


class ReceiverStorageError(RuntimeError):
    """A receiver database operation could not complete safely."""


@contextmanager
def lock_state(directory: Path) -> Iterator[None]:
    """Serialize receiver database reads and writes across application processes."""
    with _STATE_LOCK:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ReceiverStorageError(f"Could not open receiver database storage: {directory}") from exc
        lock = QLockFile(str(directory / STATE_LOCK_NAME))
        if not lock.tryLock(2000):
            raise ReceiverStorageError(f"Receiver database storage is locked or unavailable: {directory}")
        try:
            _recover_pending_restore(directory)
            yield
        finally:
            lock.unlock()


def read_rows(
    current: Path, legacy: Path, validate: Callable[[object], list[dict]],
) -> list[dict]:
    for source in (current, legacy):
        try:
            raw = source.read_bytes()
        except FileNotFoundError as exc:
            if not source.is_symlink():
                continue
            raise ReceiverStorageError(f"Could not read receiver data: {source}") from exc
        except OSError as exc:
            raise ReceiverStorageError(f"Could not read receiver data: {source}") from exc
        try:
            return validate(json.loads(raw))
        except (ValueError, RecursionError, ReceiverStorageError) as exc:
            raise ReceiverStorageError(f"Receiver data is malformed: {source}") from exc
    return []


def _json_bytes(data: object) -> bytes:
    return (json.dumps(data, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _stage(target: Path, data: bytes, suffix: str = ".tmp") -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", suffix=suffix, delete=False,
        ) as stream:
            staged = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return staged
    except OSError:
        if staged is not None:
            _remove_temporary(staged)
        raise


def _remove_temporary(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def write_json(target: Path, data: object) -> None:
    if target.is_symlink():
        raise ReceiverStorageError(f"Refusing to replace a symbolic link: {target}")
    _write_bytes(target, _json_bytes(data))


def _write_bytes(target: Path, data: bytes) -> None:
    staged = _stage(target, data)
    try:
        os.replace(staged, target)
    finally:
        _remove_temporary(staged)


@dataclass(frozen=True)
class _RestoreFile:
    target: Path
    replacement: Path
    preimage: Path | None
    original_hash: str | None

    def as_json(self) -> dict[str, str | None]:
        return {
            "target": self.target.name,
            "replacement": self.replacement.name,
            "preimage": self.preimage.name if self.preimage else None,
            "original_hash": self.original_hash,
        }


def _sync_directory(directory: Path) -> None:
    # Windows does not support fsync on an open directory handle.
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _existing_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ReceiverStorageError(f"Refusing to replace a symbolic link: {path}")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _stage_restore(target: Path, data: object) -> _RestoreFile:
    original = _existing_bytes(target)
    replacement = _stage(target, _json_bytes(data))
    preimage = None
    try:
        if original is None:
            return _RestoreFile(target, replacement, None, None)
        preimage = _stage(target, original, ".before-restore.bak")
        if preimage.read_bytes() != original:
            raise ReceiverStorageError(f"Could not verify recovery copy for {target}")
        return _RestoreFile(target, replacement, preimage, sha256(original).hexdigest())
    except (OSError, ReceiverStorageError):
        _remove_temporary(replacement)
        if preimage is not None:
            _remove_temporary(preimage)
        raise


def _journal_path(directory: Path, name: object, target: Path, suffix: str) -> Path:
    if (
        not isinstance(name, str) or Path(name).name != name or "\\" in name
        or not name.startswith(f".{target.name}.") or not name.endswith(suffix)
    ):
        raise ReceiverStorageError("Receiver database recovery journal has an invalid file name")
    return directory / name


def _read_restore_plan(directory: Path, raw: bytes) -> list[_RestoreFile]:
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or not data:
            raise ValueError("Missing restore files")
        targets = set()
        files = []
        for record in data:
            name = record["target"]
            if name not in _DATABASE_FILES or name in targets:
                raise ValueError("Invalid restore destination")
            targets.add(name)
            target = directory / name
            replacement = _journal_path(directory, record["replacement"], target, ".tmp")
            preimage_name = record["preimage"]
            preimage = (
                _journal_path(directory, preimage_name, target, ".before-restore.bak")
                if preimage_name is not None else None
            )
            files.append(_RestoreFile(target, replacement, preimage, record["original_hash"]))
        return files
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ReceiverStorageError("Receiver database recovery journal is malformed") from exc


def _recover_pending_restore(directory: Path) -> None:
    journal = directory / RESTORE_JOURNAL
    try:
        raw = _existing_bytes(journal)
        if raw is None:
            return
        files = _read_restore_plan(directory, raw)
        originals = []
        # Validate every preimage before changing either database file.
        for entry in files:
            original = _existing_bytes(entry.preimage) if entry.preimage else None
            digest = sha256(original).hexdigest() if original is not None else None
            if digest != entry.original_hash or (entry.preimage is not None and original is None):
                raise ReceiverStorageError(f"Could not verify recovery copy for {entry.target}")
            originals.append(original)

        for entry, original in zip(files, originals, strict=True):
            if _existing_bytes(entry.target) == original:
                continue
            if original is None:
                entry.target.unlink()
            else:
                _write_bytes(entry.target, original)
        _sync_directory(directory)
        journal.unlink()
    except (OSError, ReceiverStorageError) as exc:
        raise ReceiverStorageError(f"Receiver database recovery is pending at {journal}: {exc}") from exc

    # Keep verified preimages. They are needed again if a power interruption
    # prevents the journal deletion from reaching disk.
    _sync_directory(directory)
    for entry in files:
        _remove_temporary(entry.replacement)


def restore_json(replacements: Mapping[Path, object]) -> tuple[Path, ...]:
    """Commit staged database files under the caller's lock or recover the originals."""
    directory = next(iter(replacements)).parent
    if any(target.parent != directory or target.name not in _DATABASE_FILES for target in replacements):
        raise ReceiverStorageError("Restore destinations must be known files in one receiver state folder")
    journal = directory / RESTORE_JOURNAL
    files = []
    try:
        for target, data in replacements.items():
            files.append(_stage_restore(target, data))
        write_json(journal, [entry.as_json() for entry in files])
        _sync_directory(directory)
        for entry in files:
            os.replace(entry.replacement, entry.target)
        _sync_directory(directory)
        journal.unlink()
    except (OSError, ValueError, ReceiverStorageError) as exc:
        if journal.exists():
            _recover_pending_restore(directory)
        else:
            for entry in files:
                _remove_temporary(entry.replacement)
                if entry.preimage is not None:
                    _remove_temporary(entry.preimage)
        raise ReceiverStorageError(f"Restore failed: {exc}") from exc

    _sync_directory(directory)
    return tuple(entry.preimage for entry in files if entry.preimage is not None)
