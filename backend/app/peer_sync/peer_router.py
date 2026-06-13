"""Peer-facing endpoint — what *this* instance offers to a connecting BorgOS.

The only endpoint that exposes asset content cross-machine. Read-only and gated by
a dedicated bearer token (PEER_SYNC_TOKEN), NOT the JWT user session — the calling
instance has no user here. Empty token ⇒ this instance refuses to act as a peer.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.peer_sync.manifest import build_local_manifest

router = APIRouter(prefix="/api/peer", tags=["peer"])


async def require_peer_token(authorization: str | None = Header(default=None)) -> None:
    """Validate the bearer PEER_SYNC_TOKEN. 403 unless configured and matching."""
    expected = settings.peer_sync_token
    if not expected:
        raise HTTPException(status_code=403, detail="Peer sync is disabled (PEER_SYNC_TOKEN unset)")
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid peer token")


@router.get("/manifest")
async def get_manifest(
    db: AsyncSession = Depends(get_session),
    _auth: None = Depends(require_peer_token),
):
    """Normalized list of this instance's syncable items."""
    items = await build_local_manifest(db)
    return {"items": [item.model_dump() for item in items]}
