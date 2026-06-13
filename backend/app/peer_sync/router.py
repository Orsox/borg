"""Client-side API for the Peer Sync module — peer management, diff, compare, apply.

JWT-guarded like the other BorgOS routers (the operator is logged in here).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_session
from app.peer_sync import service
from app.peer_sync.client import PeerUnavailable
from app.peer_sync.schemas import DecisionRequest, PeerCreate, PeerResponse

router = APIRouter(prefix="/api/peer-sync", tags=["peer-sync"])


@router.get("/peers", response_model=list[PeerResponse])
async def list_peers(db: AsyncSession = Depends(get_session), _user=Depends(get_current_user)):
    peers = await service.list_peers(db)
    return [PeerResponse.from_model(p) for p in peers]


@router.post("/peers", response_model=PeerResponse, status_code=201)
async def create_peer(
    body: PeerCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    peer = await service.create_peer(db, label=body.label, base_url=body.base_url, token=body.token)
    return PeerResponse.from_model(peer)


@router.delete("/peers/{peer_id}")
async def delete_peer(
    peer_id: int, db: AsyncSession = Depends(get_session), _user=Depends(get_current_user)
):
    ok = await service.delete_peer(db, peer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Peer not found")
    return {"ok": True}


@router.post("/peers/{peer_id}/sync")
async def start_sync(
    peer_id: int, db: AsyncSession = Depends(get_session), _user=Depends(get_current_user)
):
    """Pull the peer's manifest and compute the static diff."""
    try:
        run = await service.start_sync(db, peer_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PeerUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e))
    return await service.get_run_detail(db, run.id)


@router.post("/runs/{run_id}/compare")
async def run_comparison(
    run_id: int, db: AsyncSession = Depends(get_session), _user=Depends(get_current_user)
):
    """Run Seven's comparator over the changed items."""
    try:
        run = await service.run_comparison(db, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await service.get_run_detail(db, run.id)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int, db: AsyncSession = Depends(get_session), _user=Depends(get_current_user)
):
    detail = await service.get_run_detail(db, run_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return detail


@router.post("/items/{item_id}/decision")
async def set_decision(
    item_id: int,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    item = await service.set_decision(db, item_id, body.decision)
    if not item:
        raise HTTPException(status_code=404, detail="Sync item not found")
    return {"ok": True, "id": item.id, "decision": item.decision}


@router.post("/items/{item_id}/apply")
async def apply_item(
    item_id: int, db: AsyncSession = Depends(get_session), _user=Depends(get_current_user)
):
    """Write the accepted remote version to the local instance."""
    try:
        item = await service.apply_item(db, item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": item.id, "decision": item.decision}
