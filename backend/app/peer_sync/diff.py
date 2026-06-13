"""Static diff — pure function, no I/O, trivially unit-testable.

Indexes the local and remote manifests by (kind, identity) and classifies every
key as only_remote / only_local / changed / identical.
"""

from app.peer_sync.schemas import DiffItem, SyncableItem


def compute_diff(
    local: list[SyncableItem], remote: list[SyncableItem]
) -> list[DiffItem]:
    """Compare two manifests and return one DiffItem per (kind, identity) key.

    `identical` items are included so callers can report totals; the service
    persists only the non-identical ones.
    """
    local_by_key = {(it.kind, it.identity): it for it in local}
    remote_by_key = {(it.kind, it.identity): it for it in remote}

    diffs: list[DiffItem] = []
    for key in sorted(set(local_by_key) | set(remote_by_key)):
        kind, identity = key
        loc = local_by_key.get(key)
        rem = remote_by_key.get(key)

        if loc and rem:
            status = "identical" if loc.content_hash == rem.content_hash else "changed"
        elif rem:
            status = "only_remote"
        else:
            status = "only_local"

        diffs.append(
            DiffItem(
                kind=kind,
                identity=identity,
                name=(rem or loc).name,
                status=status,
                local_hash=loc.content_hash if loc else None,
                remote_hash=rem.content_hash if rem else None,
                local_content=loc.content if loc else None,
                remote_content=rem.content if rem else None,
            )
        )
    return diffs
