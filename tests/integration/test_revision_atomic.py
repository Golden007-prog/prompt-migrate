"""PR 10 (cycle 2): `revision` writes atomically, never overwrites, and is collision-safe (I17).

The whole read-diff-write sequence runs under the project lock, so history is loaded inside it. A generated id that
already exists in history is regenerated (at most 5 attempts). A file that appears at the target path before the
publish is never overwritten: `revision` fails with StorageError and leaves no `.tmp` behind.
"""
import errno
import os
import uuid
from contextlib import contextmanager

import pytest

from pmtest import CFG, create, pm_dir, run_cli, set_draft, tree_snapshot, write_revision
from promptmigrate import core, project, revisions
from promptmigrate.core import load_revisions, revision
from promptmigrate.errors import StorageError
from promptmigrate.store import lock

A, B = "a" * 12, "b" * 12
EDIT = {"messages": [{"role": "system", "content": "B"}]}


def ids(*hexes):
    """uuid.uuid4 stand-in returning UUIDs whose first 12 hex digits are each of `hexes`, in order."""
    queue = [uuid.UUID(h + "0" * (32 - len(h))) for h in hexes]
    return lambda: queue.pop(0)


def versions(project_dir):
    return sorted(p.name for p in (pm_dir(project_dir) / "versions").iterdir())


@pytest.fixture
def with_a(project):
    """History holds revision A creating `assistant`; the draft now differs from head."""
    write_revision(project, A, None, {"assistant": create(CFG)})
    set_draft(project, "assistant", EDIT)
    return project


def test_an_existing_id_is_regenerated(with_a, monkeypatch):
    monkeypatch.setattr(uuid, "uuid4", ids(A, B))
    created = revision(with_a, "edit")
    assert (created.revision, created.down_revision) == (B, A)
    assert [r.revision for r in load_revisions(with_a)] == [A, B]


def test_five_colliding_ids_are_a_storage_error_and_write_nothing(with_a, monkeypatch):
    monkeypatch.setattr(uuid, "uuid4", ids(*[A] * 5))
    before = tree_snapshot(with_a)
    with pytest.raises(StorageError, match="^Could not generate a unique revision id after 5 attempts$"):
        revision(with_a, "edit")
    assert tree_snapshot(with_a) == before


def test_four_collisions_then_a_fresh_id_succeeds(with_a, monkeypatch):
    monkeypatch.setattr(uuid, "uuid4", ids(*[A] * 4, B))
    assert revision(with_a, "edit").revision == B


def test_a_file_appearing_at_the_target_is_never_overwritten(with_a, monkeypatch):
    """Something else creates the target between the history load and the publish: it keeps its bytes."""
    monkeypatch.setattr(uuid, "uuid4", ids(B))
    real = project.write_new_file

    def racing(path, text):
        path.write_bytes(b"someone else's bytes")
        real(path, text)

    monkeypatch.setattr(project, "write_new_file", racing)
    target = pm_dir(with_a) / "versions" / f"{B}_edit.json"
    with pytest.raises(StorageError, match=f"^Revision file already exists: {B}_edit.json$"):
        revision(with_a, "edit")
    assert target.read_bytes() == b"someone else's bytes"
    assert not [name for name in versions(with_a) if name.endswith(".tmp")]


def test_a_failed_write_leaves_history_unchanged(with_a, monkeypatch):
    def full(*_args):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "fsync", full)
    before = versions(with_a)
    with pytest.raises(StorageError, match="^Cannot write "):
        revision(with_a, "edit")
    assert versions(with_a) == before


def test_history_is_loaded_and_written_under_the_project_lock(with_a, monkeypatch):
    held = []
    real_lock, real_load, real_write = lock._project_lock, revisions.load_revisions, project.write_new_file

    @contextmanager
    def spy_lock(project_dir):
        with real_lock(project_dir):
            held.append(True)
            try:
                yield
            finally:
                held.pop()

    def spy_load(project_dir):
        assert held, "load_revisions ran outside the project lock"
        return real_load(project_dir)

    def spy_write(path, text):
        assert held, "write_new_file ran outside the project lock"
        real_write(path, text)

    monkeypatch.setattr(lock, "_project_lock", spy_lock)
    monkeypatch.setattr(revisions, "load_revisions", spy_load)
    monkeypatch.setattr(project, "write_new_file", spy_write)
    assert revision(with_a, "edit").down_revision == A


def test_generated_file_is_published_through_write_new_file(with_a, monkeypatch):
    calls = []
    real = project.write_new_file
    monkeypatch.setattr(project, "write_new_file", lambda path, text: (calls.append(path.name), real(path, text)))
    created = revision(with_a, "edit")
    assert calls == [created.path.name]
    assert b"\r" not in created.path.read_bytes()


def test_cli_existing_target_exits_5(with_a, capsys, monkeypatch):
    monkeypatch.setattr(uuid, "uuid4", ids(B))
    real = project.write_new_file

    def racing(path, text):
        path.write_bytes(b"x")
        real(path, text)

    monkeypatch.setattr(project, "write_new_file", racing)
    code, out, err = run_cli(capsys, with_a, "revision", "-m", "edit")
    assert (code, out) == (5, "")
    assert err.strip() == f"Error: Revision file already exists: {B}_edit.json"


def test_core_facade_still_exports_revision():
    assert core.revision is revision
