"""The .promptmigrate/ project directory: layout, drafts and the reviewed secret allowlist."""

from __future__ import annotations

import errno
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import protocol, secretscan
from .errors import InitializationError, SchemaError, StorageError

ALLOWLIST_FILE = "secret-allowlist.json"
# os.link failures that mean "this filesystem has no hard links" (e.g. FAT/exFAT), not "the publish failed".
_NO_LINKS = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP}
# CreateHardLink's own "not supported" codes (FAT/exFAT, many SMB shares); CPython maps these failures to errno
# EINVAL, which isn't in _NO_LINKS above, so the winerror has to be checked too on Windows.
_NO_LINKS_WINERROR = {1, 50}  # ERROR_INVALID_FUNCTION, ERROR_NOT_SUPPORTED


def pretty(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _umask_mode() -> int:
    """The mode a plain new file gets: mkstemp's 0600 would make a tracked source file unreadable to others."""
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _fsync_dir(directory: Path) -> None:
    if os.name != "nt":  # Windows cannot open a directory for fsync; NTFS journals the new entry itself
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _link_unsupported(exc: OSError) -> bool:
    """Whether `exc` means "this filesystem has no hard links", on POSIX or on Windows."""
    if exc.errno in _NO_LINKS:
        return True
    return os.name == "nt" and getattr(exc, "winerror", None) in _NO_LINKS_WINERROR


def _write_exclusive(path: Path, data: bytes) -> None:
    """No-clobber fallback without hard links: still never overwrites, but a crash can leave a partial file."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), _umask_mode())
    try:
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        path.unlink(missing_ok=True)  # we created it (O_EXCL), so removing it removes only our partial bytes
        raise


def write_new_file(path: Path, text: str) -> None:
    """Publish `text` as UTF-8 at `path` (a new file) atomically, never overwriting an existing one.

    Raises FileExistsError if `path` exists; any other OSError becomes StorageError. No temp file survives.
    """
    data = text.encode("utf-8")
    try:
        fd, name = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=path.parent)
        temp = Path(name)
        try:
            try:
                _write_all(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(temp, _umask_mode())
            try:
                os.link(temp, path)
            except FileExistsError:
                raise
            except OSError as exc:
                if not _link_unsupported(exc):
                    raise
                _write_exclusive(path, data)
        finally:
            # Best-effort: once published, a leftover/failed-to-remove temp file must not turn success into
            # StorageError, nor replace an in-flight exception (e.g. the FileExistsError above) with its own.
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
    except FileExistsError:
        raise
    except OSError as exc:
        raise StorageError(f"Cannot write {path.name}: {exc}") from exc
    try:
        _fsync_dir(path.parent)  # the file is already visible; directory durability beyond this is best effort
    except OSError:
        pass


def root_dir(project_dir: Path) -> Path:
    return Path(project_dir).resolve() / ".promptmigrate"


def require_init(project_dir: Path) -> Path:
    """Return the .promptmigrate directory, or raise InitializationError if the project is not initialized."""
    root = root_dir(project_dir)
    if not (root / "versions").is_dir() or not (root / "drafts").is_dir():
        raise InitializationError("Not initialized. Run: promptmigrate init")
    return root


def read_drafts(project_dir: Path) -> dict[str, dict[str, Any]]:
    root = require_init(project_dir)
    drafts = {}
    for path in sorted((root / "drafts").iterdir()):
        if path.is_dir() or path.suffix != ".json":
            continue
        name = path.stem
        value, _raw, _rules = protocol.load_json(path, kind="draft", root=root)
        protocol.validate_config(name, value)
        found = protocol.config_violations(name, value)
        if found:
            raise SchemaError(f"Invalid draft {path.name}: {', '.join(found)}")
        drafts[name] = value
    collisions = protocol.case_collisions(drafts)
    if collisions:
        raise SchemaError(f"Invalid drafts: case-collision {collisions[0]}")
    return drafts


def load_allowlist(project_dir: Path) -> list[secretscan.AllowEntry]:
    """The reviewed secret allowlist (.promptmigrate/secret-allowlist.json); empty when the file is absent."""
    root = require_init(project_dir)
    path = root / ALLOWLIST_FILE
    if not path.exists() and not path.is_symlink():
        return []
    value, _raw, _rules = protocol.load_json(path, kind="allowlist", root=root)
    return secretscan.parse_allowlist(value, path.name)
