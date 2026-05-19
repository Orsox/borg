"""Pydantic v2 response schemas for archon_system endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ArchonConcurrency(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active: int = 0
    queued_total: int = 0
    max_concurrent: int = 10


class ArchonSystemHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    online: bool = False
    archon_url: str = ""
    version: Optional[str] = None
    adapter: Optional[str] = None
    is_docker: bool = False
    active_platforms: list[str] = []
    running_workflows: int = 0
    concurrency: Optional[ArchonConcurrency] = None
    checked_at: Optional[str] = None
    cached: bool = False


class ArchonRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: str = ""
    workflow_name: str = ""
    status: str = "unknown"
    user_message: Optional[str] = None
    started_at: Optional[str] = None
    last_activity_at: Optional[str] = None
    completed_at: Optional[str] = None
    codebase_name: Optional[str] = None
    working_path: Optional[str] = None


class ArchonRunsResponse(BaseModel):
    items: list[ArchonRunItem] = []
    total: int = 0


class ArchonCodebaseItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: str = ""
    name: str = ""
    repository_url: Optional[str] = None
    default_branch: Optional[str] = None
    ai_assistant_type: Optional[str] = None


class ArchonCodebasesResponse(BaseModel):
    items: list[ArchonCodebaseItem] = []
    total: int = 0


class ArchonWorkflowItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    name: str = ""
    description: Optional[str] = None
    provider: Optional[str] = None
    source: str = "unknown"


class ArchonWorkflowsResponse(BaseModel):
    items: list[ArchonWorkflowItem] = []
    total: int = 0


class SyncResponse(BaseModel):
    synced_at: str
    health_updated: bool
    runs_count: int
    codebases_count: int
    workflows_count: int
