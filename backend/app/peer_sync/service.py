"""Service layer for the Peer Sync module.

Flow: register a peer → start_sync (pull remote manifest, static diff, persist a
SyncRun + one SyncItemRecord per non-identical item) → run_comparison (Seven's
comparator analyses the *changed* items) → operator reviews → apply_item writes an
accepted remote version to the local filesystem / skills DB.
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archon_hub import service as archon_hub_service
from app.config import settings
from app.discord_bot.config import LlmConfig
from app.discord_bot.llm import LlmClient, LlmError
from app.peer_sync.client import PeerClient, PeerUnavailable
from app.peer_sync.diff import compute_diff
from app.peer_sync.manifest import ASSET_KINDS, build_local_manifest
from app.peer_sync.models import PeerInstance, SyncItemRecord, SyncRun
from app.peer_sync.schemas import SyncableItem
from app.seven_of_nine import service as seven_service
from app.seven_of_nine.sync_agent import SyncComparatorDrone
from app.skills import service as skills_service

logger = logging.getLogger(__name__)


# --- Peer CRUD ---


async def create_peer(db: AsyncSession, label: str, base_url: str, token: str = "") -> PeerInstance:
    peer = PeerInstance(label=label, base_url=base_url.rstrip("/"), token=token)
    db.add(peer)
    await db.commit()
    await db.refresh(peer)
    return peer


async def list_peers(db: AsyncSession) -> list[PeerInstance]:
    result = await db.execute(select(PeerInstance).order_by(PeerInstance.created_at.desc()))
    return list(result.scalars().all())


async def get_peer(db: AsyncSession, peer_id: int) -> PeerInstance | None:
    result = await db.execute(select(PeerInstance).where(PeerInstance.id == peer_id))
    return result.scalar_one_or_none()


async def delete_peer(db: AsyncSession, peer_id: int) -> bool:
    peer = await get_peer(db, peer_id)
    if not peer:
        return False
    await db.delete(peer)
    await db.commit()
    return True


# --- Sync ---


async def start_sync(db: AsyncSession, peer_id: int) -> SyncRun:
    """Pull the peer's manifest, static-diff against local, persist a SyncRun."""
    peer = await get_peer(db, peer_id)
    if not peer:
        raise ValueError(f"Peer {peer_id} not found")

    async with PeerClient(peer.base_url, peer.token) as client:
        remote_raw = await client.get_manifest()
    remote = [SyncableItem(**r) for r in remote_raw]
    local = await build_local_manifest(db)

    diffs = compute_diff(local, remote)
    counts: dict[str, int] = {"only_remote": 0, "only_local": 0, "changed": 0, "identical": 0}
    for d in diffs:
        counts[d.status] = counts.get(d.status, 0) + 1

    run = SyncRun(peer_id=peer.id, status="diffed", counts_json=json.dumps(counts))
    db.add(run)
    await db.flush()  # assign run.id

    for d in diffs:
        if d.status == "identical":
            continue
        db.add(
            SyncItemRecord(
                run_id=run.id,
                kind=d.kind,
                identity=d.identity,
                name=d.name,
                status=d.status,
                local_hash=d.local_hash,
                remote_hash=d.remote_hash,
                local_content=d.local_content,
                remote_content=d.remote_content,
            )
        )

    peer.last_synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


@asynccontextmanager
async def _seven_chat():
    """Yield a chat_fn backed by Seven's LLM, started/stopped around use.

    Decoupled from the Discord bot lifecycle — built straight from settings so
    sync comparison works even when the bots are disabled.
    """
    client = LlmClient(
        LlmConfig(
            persona="seven",
            base_url=settings.discord_bot_seven_llm_base_url,
            model_id=settings.discord_bot_seven_llm_model_id,
        )
    )
    await client.start()
    try:
        yield client.chat
    finally:
        await client.stop()


async def run_comparison(db: AsyncSession, run_id: int) -> SyncRun:
    """Run Seven's comparator over the changed items of a SyncRun.

    only_remote / only_local items skip the LLM (nothing to compare) and get a
    one-line rationale. A per-item LLM failure is captured in the analysis so the
    run still completes.
    """
    run = await _get_run(db, run_id)
    if not run:
        raise ValueError(f"SyncRun {run_id} not found")

    items = await _run_items(db, run_id)
    changed = [it for it in items if it.status == "changed"]

    if changed:
        async with _seven_chat() as chat_fn:
            drone = SyncComparatorDrone(chat_fn)
            for item in changed:
                try:
                    analysis = await drone.compare(
                        item.kind, item.identity, item.local_content, item.remote_content
                    )
                except LlmError as e:
                    analysis = {"error": f"Vergleich fehlgeschlagen: {e}"}
                item.analysis_json = json.dumps(analysis, ensure_ascii=False)
                await seven_service.record_action(
                    db,
                    action="peer_sync_compare",
                    target=f"{item.kind}:{item.identity}",
                    payload_summary=f"run={run_id}",
                    commit=False,
                )

    for item in items:
        if item.status == "only_remote":
            item.analysis_json = json.dumps(
                {"rationale": "Nur auf Remote vorhanden — Übernahme fügt das Asset lokal hinzu."}
            )
        elif item.status == "only_local":
            item.analysis_json = json.dumps(
                {"rationale": "Nur lokal vorhanden — kein Remote-Pendant zum Übernehmen."}
            )

    run.status = "compared"
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


# --- Review + apply ---


async def set_decision(db: AsyncSession, item_id: int, decision: str) -> SyncItemRecord | None:
    item = await _get_item(db, item_id)
    if not item:
        return None
    item.decision = "accepted" if decision == "accept" else "rejected"
    await db.commit()
    await db.refresh(item)
    return item


async def apply_item(db: AsyncSession, item_id: int) -> SyncItemRecord:
    """Write an accepted item's remote version to the local instance.

    This is the one mutating step — gated behind the per-item accept click. For
    assets we write the file under ARCHON_PATH and re-scan; for skill_db we
    create/update the Skill via skills.service from its canonical metadata.
    """
    item = await _get_item(db, item_id)
    if not item:
        raise ValueError(f"Sync item {item_id} not found")
    if item.status == "only_local":
        raise ValueError("only_local items have no remote version to apply")
    if not item.remote_content:
        raise ValueError("item has no remote content to apply")

    if item.kind in ASSET_KINDS:
        await _apply_asset(db, item)
    elif item.kind == "skill_db":
        await _apply_skill_db(db, item)
    else:
        raise ValueError(f"Unsupported sync kind: {item.kind}")

    item.decision = "applied"
    await seven_service.record_action(
        db,
        action="peer_sync_apply",
        target=f"{item.kind}:{item.identity}",
        payload_summary=item.name,
        commit=False,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def _apply_asset(db: AsyncSession, item: SyncItemRecord) -> None:
    root = Path(settings.archon_path).expanduser().resolve()
    target = (root / item.identity).resolve()
    # Guard against path traversal in the (untrusted) remote identity.
    if root not in target.parents and target != root:
        raise ValueError(f"identity escapes ARCHON_PATH: {item.identity}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(item.remote_content, encoding="utf-8")
    # Refresh the DB so the new/updated asset is reflected immediately.
    await archon_hub_service.run_scan(db)


async def _apply_skill_db(db: AsyncSession, item: SyncItemRecord) -> None:
    meta = json.loads(item.remote_content)
    name = meta.get("name") or item.identity
    description = meta.get("description") or None
    model = meta.get("model") or None
    category = meta.get("category") or None
    tags = meta.get("tags") or []

    existing = await skills_service.get_skill_by_name(db, name)
    if existing:
        await skills_service.update_skill(
            db, existing.id, description=description, model=model, category=category, tags=tags
        )
    else:
        await skills_service.create_skill(
            db, name=name, description=description, model=model, category=category, tags=tags
        )


# --- Internal query helpers ---


async def _get_run(db: AsyncSession, run_id: int) -> SyncRun | None:
    return (await db.execute(select(SyncRun).where(SyncRun.id == run_id))).scalar_one_or_none()


async def _run_items(db: AsyncSession, run_id: int) -> list[SyncItemRecord]:
    result = await db.execute(
        select(SyncItemRecord)
        .where(SyncItemRecord.run_id == run_id)
        .order_by(SyncItemRecord.kind, SyncItemRecord.identity)
    )
    return list(result.scalars().all())


async def _get_item(db: AsyncSession, item_id: int) -> SyncItemRecord | None:
    return (
        await db.execute(select(SyncItemRecord).where(SyncItemRecord.id == item_id))
    ).scalar_one_or_none()


def serialize_run(run: SyncRun, items: list[SyncItemRecord]) -> dict:
    """Shape a SyncRun + its items for the API/UI."""
    return {
        "id": run.id,
        "peer_id": run.peer_id,
        "status": run.status,
        "counts": json.loads(run.counts_json) if run.counts_json else {},
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "items": [
            {
                "id": it.id,
                "kind": it.kind,
                "identity": it.identity,
                "name": it.name,
                "status": it.status,
                "local_hash": it.local_hash,
                "remote_hash": it.remote_hash,
                "local_content": it.local_content,
                "remote_content": it.remote_content,
                "analysis": json.loads(it.analysis_json) if it.analysis_json else None,
                "decision": it.decision,
            }
            for it in items
        ],
    }


async def get_run_detail(db: AsyncSession, run_id: int) -> dict | None:
    run = await _get_run(db, run_id)
    if not run:
        return None
    items = await _run_items(db, run_id)
    return serialize_run(run, items)
