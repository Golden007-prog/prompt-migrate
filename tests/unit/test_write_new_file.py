"""PR 10 (cycle 2): `project.write_new_file` publishes a new file atomically and never overwrites (I17).

The bytes go to a temp file in the target directory (prefix ".", suffix ".tmp", so the `*.json` glob never sees it),
are flushed and fsynced, then published with `os.link`, which fails if the target exists. On any failure the temp
file is removed and no target is left behind. Where hard links are unsupported, an `O_CREAT | O_EXCL` write is the
fallback: still no-clobber, but not atomic against a crash.
"""
import errno
import os
import stat
from pathlib import Path

import pytest

from promptmigrate import project
from promptmigrate.errors import StorageError

TEXT = '{\n  "a": "é"\n}\n'
DATA = TEXT.encode("utf-8")


def leftovers(directory):
    return sorted(p.name for p in directory.iterdir())


def test_writes_utf8_with_lf_line_endings(tmp_path):
    target = tmp_path / "r.json"
    assert project.write_new_file(target, TEXT) is None
    assert target.read_bytes() == DATA
    assert b"\r" not in target.read_bytes()
    assert leftovers(tmp_path) == ["r.json"]


def test_existing_target_is_never_overwritten(tmp_path):
    target = tmp_path / "r.json"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        project.write_new_file(target, TEXT)
    assert target.read_bytes() == b"original"
    assert leftovers(tmp_path) == ["r.json"]


def test_temp_file_is_hidden_from_the_json_glob(tmp_path, monkeypatch):
    seen = []
    real = project._write_all

    def spy(fd, data):
        if not seen:  # the first write is the temp file; a no-hard-link fallback writes a second time
            seen.append(leftovers(tmp_path))
        real(fd, data)

    monkeypatch.setattr(project, "_write_all", spy)
    project.write_new_file(tmp_path / "r.json", TEXT)
    [[temp]] = seen
    assert temp.startswith(".") and temp.endswith(".tmp")
    assert list(tmp_path.glob("*.json")) == [tmp_path / "r.json"]


def test_never_reads_or_changes_the_process_umask(tmp_path, monkeypatch):
    """os.umask is process-wide: reading it means setting it, which races with other threads in an embedding app."""
    def forbidden(*_args):
        raise AssertionError("write_new_file must not call os.umask")

    monkeypatch.setattr(os, "umask", forbidden)
    project.write_new_file(tmp_path / "r.json", TEXT)
    assert (tmp_path / "r.json").read_bytes() == DATA


def test_a_taken_temp_name_is_skipped_and_left_alone(tmp_path, monkeypatch):
    (tmp_path / ".taken.tmp").write_bytes(b"someone else's temp")
    tokens = iter(["taken", "fresh"])
    monkeypatch.setattr(project.secrets, "token_hex", lambda _n: next(tokens))
    project.write_new_file(tmp_path / "r.json", TEXT)
    assert (tmp_path / "r.json").read_bytes() == DATA
    assert (tmp_path / ".taken.tmp").read_bytes() == b"someone else's temp"
    assert leftovers(tmp_path) == [".taken.tmp", "r.json"]


def _fail_write(fd, data):
    os.write(fd, data[:3])
    raise OSError(errno.ENOSPC, "No space left on device")


def _fail(*_args, **_kwargs):
    raise OSError(errno.EIO, "Input/output error")


@pytest.mark.parametrize("name,target_attr,replacement", [
    ("write", project, ("_write_all", _fail_write)),
    ("fsync", os, ("fsync", _fail)),
    ("link", os, ("link", _fail)),
])
def test_injected_failure_leaves_nothing_and_is_a_storage_error(tmp_path, monkeypatch, name, target_attr, replacement):
    monkeypatch.setattr(target_attr, *replacement)
    with pytest.raises(StorageError, match=r"^Cannot write r\.json: "):
        project.write_new_file(tmp_path / "r.json", TEXT)
    assert leftovers(tmp_path) == []


def test_interrupt_removes_the_temp_file_and_propagates(tmp_path, monkeypatch):
    def interrupted(fd, data):
        raise KeyboardInterrupt

    monkeypatch.setattr(project, "_write_all", interrupted)
    with pytest.raises(KeyboardInterrupt):
        project.write_new_file(tmp_path / "r.json", TEXT)
    assert leftovers(tmp_path) == []


@pytest.mark.parametrize("code", [errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP])
def test_link_unsupported_falls_back_to_exclusive_create(tmp_path, monkeypatch, code):
    def unsupported(*_args, **_kwargs):
        raise OSError(code, "hard links not supported")

    monkeypatch.setattr(os, "link", unsupported)
    target = tmp_path / "r.json"
    project.write_new_file(target, TEXT)
    assert target.read_bytes() == DATA  # binary mode: no CRLF translation on Windows
    assert leftovers(tmp_path) == ["r.json"]


def test_fallback_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EPERM, "no links")))
    target = tmp_path / "r.json"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        project.write_new_file(target, TEXT)
    assert target.read_bytes() == b"original"
    assert leftovers(tmp_path) == ["r.json"]


def test_failed_fallback_write_removes_the_partial_target(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EPERM, "no links")))
    real = project._write_all
    calls = []

    def second_fails(fd, data):
        calls.append(fd)
        if len(calls) == 2:
            _fail_write(fd, data)
        real(fd, data)

    monkeypatch.setattr(project, "_write_all", second_fails)
    with pytest.raises(StorageError, match=r"^Cannot write r\.json: "):
        project.write_new_file(tmp_path / "r.json", TEXT)
    assert len(calls) == 2
    assert leftovers(tmp_path) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_new_file_gets_the_umask_mode_not_the_temp_files_0600(tmp_path):
    umask = os.umask(0o022)
    try:
        target = tmp_path / "r.json"
        project.write_new_file(target, TEXT)
    finally:
        os.umask(umask)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific CreateHardLink winerror mapping")
@pytest.mark.parametrize("winerror", [1, 50])
def test_windows_winerror_not_supported_falls_back_to_exclusive_create(tmp_path, monkeypatch, winerror):
    def unsupported(*_args, **_kwargs):
        raise OSError(None, "not supported", None, winerror)

    monkeypatch.setattr(os, "link", unsupported)
    target = tmp_path / "r.json"
    project.write_new_file(target, TEXT)
    assert target.read_bytes() == DATA
    assert leftovers(tmp_path) == ["r.json"]


def test_missing_target_directory_is_a_storage_error(tmp_path):
    target = tmp_path / "missing" / "r.json"
    with pytest.raises(StorageError, match=r"^Cannot write r\.json: "):
        project.write_new_file(target, TEXT)
    assert not target.parent.exists()


def test_fsync_dir_failure_after_publish_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(project, "_fsync_dir", _fail)
    target = tmp_path / "r.json"
    assert project.write_new_file(target, TEXT) is None
    assert target.read_bytes() == DATA


def _flaky_tmp_unlink(self, missing_ok=False):
    if self.name.endswith(".tmp"):
        raise PermissionError(errno.EACCES, "temp file busy")
    return _REAL_UNLINK(self, missing_ok=missing_ok)


_REAL_UNLINK = Path.unlink


def test_temp_unlink_failure_does_not_fail_a_successful_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "unlink", _flaky_tmp_unlink)
    target = tmp_path / "r.json"
    assert project.write_new_file(target, TEXT) is None
    assert target.read_bytes() == DATA
    assert list(tmp_path.glob("*.json")) == [target]


def test_temp_unlink_failure_does_not_mask_file_exists_error(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "unlink", _flaky_tmp_unlink)
    target = tmp_path / "r.json"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        project.write_new_file(target, TEXT)
    assert target.read_bytes() == b"original"
