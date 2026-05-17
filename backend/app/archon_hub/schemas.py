import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    description: Optional[str]
    tags: list[str]
    file_path: str
    raw_content: str
    last_scanned: str
    is_favorite: bool
    created_at: str

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []

    @field_validator("last_scanned", "created_at", mode="before")
    @classmethod
    def format_dt(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class PaginatedAssets(BaseModel):
    items: list[AssetResponse]
    total: int
    page: int
    size: int
    pages: int


class ScanResponse(BaseModel):
    count: int
    scanned_at: str


class CopyResponse(BaseModel):
    source_path: str
    destination_path: str
    copied_at: str


class FavoriteResponse(BaseModel):
    id: int
    is_favorite: bool


class CopyHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    asset_name: str
    source_path: str
    destination_path: str
    copied_at: str

    @field_validator("copied_at", mode="before")
    @classmethod
    def format_dt(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)
