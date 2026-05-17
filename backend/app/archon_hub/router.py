from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.archon_hub import service
from app.archon_hub.schemas import (
    AssetResponse,
    CopyHistoryItem,
    CopyResponse,
    FavoriteResponse,
    PaginatedAssets,
    ScanResponse,
)
from app.auth.router import get_current_user
from app.database import get_session

router = APIRouter(prefix="/api/archon", tags=["archon_hub"])


@router.post("/scan", response_model=ScanResponse)
async def scan_assets(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    try:
        count = await service.run_scan(db)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from datetime import datetime, timezone
    return ScanResponse(count=count, scanned_at=datetime.now(timezone.utc).isoformat())


@router.get("/assets", response_model=PaginatedAssets)
async def list_assets(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    favorites: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_assets(
        db,
        page=page,
        size=size,
        type_filter=type,
        search=search,
        tags=tags,
        favorites_only=favorites,
    )
    return PaginatedAssets(
        items=[AssetResponse.model_validate(item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    asset = await service.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return AssetResponse.model_validate(asset)


@router.post("/assets/{asset_id}/copy", response_model=CopyResponse)
async def copy_asset(
    asset_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.copy_asset(db, asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return CopyResponse(**result)


@router.post("/assets/{asset_id}/favorite", response_model=FavoriteResponse)
async def toggle_favorite(
    asset_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.toggle_favorite(db, asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return FavoriteResponse(**result)


@router.get("/copy-history", response_model=list[CopyHistoryItem])
async def get_copy_history(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    history = await service.get_copy_history(db)
    return [CopyHistoryItem.model_validate(h) for h in history]
