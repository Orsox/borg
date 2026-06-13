"""Build the local manifest — the normalized list of syncable items.

Used both by the peer-facing manifest endpoint (what *this* instance offers) and
by the client side when diffing against a remote peer. The same builder on both
ends guarantees symmetric identities and hashing.
"""

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archon_hub.models import ArchonAsset
from app.config import settings
from app.peer_sync.schemas import SyncableItem
from app.skills.models import Skill

# Archon asset types we synchronize (other types, e.g. "unknown", are ignored).
ASSET_KINDS = {"workflow", "skill", "agent"}


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def rel_identity(file_path: str, archon_path: str) -> str | None:
    """POSIX path of `file_path` relative to ARCHON_PATH, or None if outside it.

    Asset file paths are stored absolute (archon_hub/scanner.py); the relative
    path is the cross-machine-stable identity since ARCHON_PATH differs per host.
    """
    try:
        root = Path(archon_path).expanduser().resolve()
        rel = Path(file_path).expanduser().resolve().relative_to(root)
    except (ValueError, OSError):
        return None
    return rel.as_posix()


def _skill_metadata_content(skill: Skill) -> str:
    """Canonical JSON of a Skill's editable metadata.

    We diff the metadata (the source of truth), not the generated YAML, so that
    applying a change can faithfully recreate the skill via skills.service.
    """
    try:
        tags = json.loads(skill.tags) if skill.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []
    return json.dumps(
        {
            "name": skill.name,
            "description": skill.description or "",
            "model": skill.model or "",
            "category": skill.category or "",
            "tags": sorted(tags),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


async def build_local_manifest(db: AsyncSession) -> list[SyncableItem]:
    """Collect all syncable items on this instance."""
    items: list[SyncableItem] = []

    # Archon assets (workflows / skills / agents) scanned from ARCHON_PATH.
    assets = (await db.execute(select(ArchonAsset))).scalars().all()
    for asset in assets:
        kind = (asset.type or "").lower()
        if kind not in ASSET_KINDS:
            continue
        identity = rel_identity(asset.file_path, settings.archon_path)
        if identity is None:
            continue
        items.append(
            SyncableItem(
                kind=kind,
                identity=identity,
                name=asset.name,
                content=asset.raw_content,
                content_hash=content_hash(asset.raw_content),
            )
        )

    # Skill DB module — diff the canonical metadata.
    skills = (await db.execute(select(Skill))).scalars().all()
    for skill in skills:
        content = _skill_metadata_content(skill)
        items.append(
            SyncableItem(
                kind="skill_db",
                identity=skill.name,
                name=skill.name,
                content=content,
                content_hash=content_hash(content),
            )
        )

    return items
