"""Pydantic schemas for the Skills module."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    category: Optional[str] = Field(default=None, max_length=128)


class SkillUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    tags: Optional[list[str]] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    category: Optional[str] = Field(default=None, max_length=128)


class SkillResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    archon_workflow_file: str
    model: Optional[str]
    tags: list[str]
    is_active: bool
    category: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillListItem(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    category: Optional[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedSkills(BaseModel):
    items: list[SkillListItem]
    total: int
    page: int
    size: int
    pages: int


class SkillYamlResponse(BaseModel):
    """Response for skill YAML generation."""
    name: str
    yaml_content: str
    file_path: str  # Where the YAML was written
