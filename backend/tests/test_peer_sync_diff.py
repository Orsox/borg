"""Unit tests for the pure static-diff function."""

from app.peer_sync.diff import compute_diff
from app.peer_sync.schemas import SyncableItem


def _item(kind, identity, content):
    from app.peer_sync.manifest import content_hash

    return SyncableItem(
        kind=kind, identity=identity, name=identity, content=content, content_hash=content_hash(content)
    )


def _status_map(diffs):
    return {(d.kind, d.identity): d.status for d in diffs}


def test_compute_diff_classifies_all_statuses_across_kinds():
    local = [
        _item("workflow", "workflows/a.yaml", "A"),       # identical
        _item("skill", "skills/b.yaml", "B-local"),        # changed
        _item("agent", "agents/c.yaml", "C"),              # only_local
        _item("skill_db", "my-skill", "{}"),               # changed
    ]
    remote = [
        _item("workflow", "workflows/a.yaml", "A"),        # identical
        _item("skill", "skills/b.yaml", "B-remote"),       # changed
        _item("agent", "agents/d.yaml", "D"),              # only_remote
        _item("skill_db", "my-skill", '{"x":1}'),          # changed
    ]

    status = _status_map(compute_diff(local, remote))

    assert status[("workflow", "workflows/a.yaml")] == "identical"
    assert status[("skill", "skills/b.yaml")] == "changed"
    assert status[("agent", "agents/c.yaml")] == "only_local"
    assert status[("agent", "agents/d.yaml")] == "only_remote"
    assert status[("skill_db", "my-skill")] == "changed"


def test_compute_diff_same_identity_different_kind_is_independent():
    # A workflow and an agent that share an identity string must not collide.
    local = [_item("workflow", "shared", "X")]
    remote = [_item("agent", "shared", "Y")]
    status = _status_map(compute_diff(local, remote))
    assert status[("workflow", "shared")] == "only_local"
    assert status[("agent", "shared")] == "only_remote"


def test_compute_diff_carries_content_for_changed():
    local = [_item("skill", "s", "old")]
    remote = [_item("skill", "s", "new")]
    diff = compute_diff(local, remote)[0]
    assert diff.status == "changed"
    assert diff.local_content == "old"
    assert diff.remote_content == "new"
