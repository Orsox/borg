"""Schemas for the Peer Sync module."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# The four syncable scopes. Assets carry a POSIX rel-path identity under
# ARCHON_PATH; skill_db carries the normalized skill name.
SyncKind = Literal["workflow", "skill", "agent", "skill_db"]

# Static-diff classification of a single (kind, identity) key.
DiffStatus = Literal["only_remote", "only_local", "changed", "identical"]


class SyncableItem(BaseModel):
    """Normalized, transport-friendly shape unifying all four scopes.

    The peer manifest endpoint returns a list of these; the local manifest is
    built in the same shape so diff/compare/apply are written once.
    """

    kind: SyncKind
    identity: str
    name: str
    content: str
    content_hash: str


class DiffItem(BaseModel):
    """Result of comparing one (kind, identity) across local and remote."""

    kind: SyncKind
    identity: str
    name: str
    status: DiffStatus
    local_hash: Optional[str] = None
    remote_hash: Optional[str] = None
    local_content: Optional[str] = None
    remote_content: Optional[str] = None


# --- Peer management ---


class PeerCreate(BaseModel):
    label: str
    base_url: str
    token: str = ""


class PeerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    base_url: str
    is_active: bool
    last_synced_at: Optional[str] = None
    created_at: str

    @classmethod
    def from_model(cls, peer) -> "PeerResponse":
        return cls(
            id=peer.id,
            label=peer.label,
            base_url=peer.base_url,
            is_active=peer.is_active,
            last_synced_at=peer.last_synced_at.isoformat() if peer.last_synced_at else None,
            created_at=peer.created_at.isoformat(),
        )


# --- Sync run / review ---


class SyncItemResponse(BaseModel):
    id: int
    kind: str
    identity: str
    name: str
    status: str
    local_hash: Optional[str] = None
    remote_hash: Optional[str] = None
    local_content: Optional[str] = None
    remote_content: Optional[str] = None
    analysis: Optional[dict] = None
    decision: str


class SyncRunResponse(BaseModel):
    id: int
    peer_id: int
    status: str
    counts: dict
    started_at: str
    finished_at: Optional[str] = None
    items: list[SyncItemResponse] = []


class DecisionRequest(BaseModel):
    decision: Literal["accept", "reject"]
