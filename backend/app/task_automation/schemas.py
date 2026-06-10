"""Pydantic schemas for Task Automation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = Field(default=None)
    task_type: str = Field(default="shell", pattern="^(shell|archon_workflow|heartbeat|skill|dreaming)$")
    schedule: Optional[str] = Field(default=None)  # cron expression
    command: Optional[str] = Field(default=None)
    archon_workflow_name: Optional[str] = Field(default=None)
    archon_workflow_template: Optional[str] = Field(default=None)
    heartbeat_workflow_name: Optional[str] = Field(default=None)
    dreaming_days: int = Field(default=14, ge=1, le=365)
    dreaming_min_actions: int = Field(default=5, ge=1)
    dreaming_persona: Optional[str] = Field(default=None, max_length=64)
    is_enabled: bool = Field(default=True)
    tags: list[str] = Field(default_factory=list)
    retry_max: int = Field(default=0, ge=0, le=10)
    retry_delay: int = Field(default=60, ge=0)
    timeout: int = Field(default=300, ge=1, le=3600)


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None)
    task_type: Optional[str] = Field(default=None, pattern="^(shell|archon_workflow|heartbeat|skill|dreaming)$")
    schedule: Optional[str] = Field(default=None)
    command: Optional[str] = Field(default=None)
    archon_workflow_name: Optional[str] = Field(default=None)
    archon_workflow_template: Optional[str] = Field(default=None)
    heartbeat_workflow_name: Optional[str] = Field(default=None)
    dreaming_days: Optional[int] = Field(default=None, ge=1, le=365)
    dreaming_min_actions: Optional[int] = Field(default=None, ge=1)
    dreaming_persona: Optional[str] = Field(default=None, max_length=64)
    is_enabled: Optional[bool] = Field(default=None)
    tags: Optional[list[str]] = Field(default=None)
    retry_max: Optional[int] = Field(default=None, ge=0, le=10)
    retry_delay: Optional[int] = Field(default=None, ge=0)
    timeout: Optional[int] = Field(default=None, ge=1, le=3600)


class TaskResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    task_type: str
    schedule: Optional[str]
    command: Optional[str]
    archon_workflow_name: Optional[str]
    archon_workflow_template: Optional[str] = None
    heartbeat_workflow_name: Optional[str] = None
    dreaming_days: int
    dreaming_min_actions: int
    dreaming_persona: Optional[str]
    is_enabled: bool
    tags: list[str]
    retry_max: int
    retry_delay: int
    timeout: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListItem(BaseModel):
    id: int
    name: str
    description: Optional[str]
    task_type: str
    schedule: Optional[str]
    is_enabled: bool
    tags: list[str]
    archon_workflow_template: Optional[str] = None
    heartbeat_workflow_name: Optional[str] = None
    dreaming_days: int
    dreaming_min_actions: int
    dreaming_persona: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedTasks(BaseModel):
    items: list[TaskListItem]
    total: int
    page: int
    size: int
    pages: int


class TaskRunResponse(BaseModel):
    id: int
    task_id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    exit_code: Optional[int]
    stdout: Optional[str]
    stderr: Optional[str]
    duration_ms: Optional[int]

    model_config = {"from_attributes": True}


class TaskRunTriggerResponse(BaseModel):
    task_run_id: int
    message: str


class ToggleResponse(BaseModel):
    id: int
    is_enabled: bool
