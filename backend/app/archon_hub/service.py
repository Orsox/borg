import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.archon_hub.models import ArchonAsset, CopyHistory
from app.archon_hub.scanner import scan_directory
from app.config import settings


async def run_scan(db: AsyncSession) -> int:
    """Scan the ARCHON_PATH directory and upsert assets into DB. Returns count of assets."""
    assets = scan_directory(settings.archon_path)

    now = datetime.now(timezone.utc)

    for asset_data in assets:
        file_path = asset_data["file_path"]
        result = await db.execute(select(ArchonAsset).where(ArchonAsset.file_path == file_path))
        existing = result.scalar_one_or_none()

        if existing:
            await db.execute(
                update(ArchonAsset)
                .where(ArchonAsset.file_path == file_path)
                .values(
                    name=asset_data["name"],
                    type=asset_data["type"],
                    description=asset_data["description"],
                    tags=asset_data["tags"],
                    raw_content=asset_data["raw_content"],
                    last_scanned=now,
                )
            )
        else:
            asset = ArchonAsset(
                name=asset_data["name"],
                type=asset_data["type"],
                description=asset_data["description"],
                tags=asset_data["tags"],
                file_path=file_path,
                raw_content=asset_data["raw_content"],
                last_scanned=now,
                is_favorite=False,
            )
            db.add(asset)

    await db.commit()
    return len(assets)


async def list_assets(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    type_filter: str | None = None,
    search: str | None = None,
    tags: str | None = None,
    favorites_only: bool = False,
) -> dict:
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(ArchonAsset)

    if type_filter:
        query = query.where(func.lower(ArchonAsset.type) == type_filter.lower())

    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                ArchonAsset.name.ilike(term),
                ArchonAsset.description.ilike(term),
            )
        )

    if tags:
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                query = query.where(ArchonAsset.tags.contains(f'"{tag}"'))

    if favorites_only:
        query = query.where(ArchonAsset.is_favorite == True)  # noqa: E712

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(query.offset(offset).limit(size).order_by(ArchonAsset.name))
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


async def get_asset(db: AsyncSession, asset_id: int) -> ArchonAsset | None:
    result = await db.execute(select(ArchonAsset).where(ArchonAsset.id == asset_id))
    return result.scalar_one_or_none()


async def copy_asset(db: AsyncSession, asset_id: int) -> dict:
    asset = await get_asset(db, asset_id)
    if not asset:
        return None

    source = Path(asset.file_path)
    dest_dir = Path(settings.archon_path) / "borgos_copies"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name

    shutil.copy2(str(source), str(dest))

    now = datetime.now(timezone.utc)
    history = CopyHistory(
        asset_id=asset.id,
        asset_name=asset.name,
        source_path=str(source),
        destination_path=str(dest),
        copied_at=now,
    )
    db.add(history)
    await db.commit()

    return {
        "source_path": str(source),
        "destination_path": str(dest),
        "copied_at": now.isoformat(),
    }


async def toggle_favorite(db: AsyncSession, asset_id: int) -> dict | None:
    asset = await get_asset(db, asset_id)
    if not asset:
        return None

    asset.is_favorite = not asset.is_favorite
    await db.commit()
    await db.refresh(asset)
    return {"id": asset.id, "is_favorite": asset.is_favorite}


async def get_copy_history(db: AsyncSession) -> list[CopyHistory]:
    result = await db.execute(
        select(CopyHistory).order_by(CopyHistory.copied_at.desc()).limit(50)
    )
    return list(result.scalars().all())
