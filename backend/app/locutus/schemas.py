"""Pydantic schemas for Locutus module."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Character Profile ---

class CharacterProfileCreate(BaseModel):
    content: str = Field(..., min_length=1)
    file_path: str = Field(default="~/.locutus/Character.md", max_length=1024)


class CharacterProfileUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1)
    file_path: Optional[str] = Field(default=None, max_length=1024)


class CharacterProfileResponse(BaseModel):
    id: int
    content: str
    file_path: str
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CharacterProfileListItem(BaseModel):
    id: int
    file_path: str
    last_synced_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedCharacterProfiles(BaseModel):
    items: list[CharacterProfileListItem]
    total: int
    page: int
    size: int
    pages: int


# --- Character Memory ---

class CharacterMemoryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(default="")
    category: str = Field(default="general", max_length=64)


class CharacterMemoryUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    content: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None, max_length=64)


class CharacterMemoryResponse(BaseModel):
    id: int
    title: str
    content: str
    category: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CharacterMemoryListItem(BaseModel):
    id: int
    title: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedMemories(BaseModel):
    items: list[CharacterMemoryListItem]
    total: int
    page: int
    size: int
    pages: int


# --- Reasoning Log ---

class ReasoningLogCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    trigger_description: str = Field(..., min_length=1)
    proposed_solution: str = Field(..., min_length=1)
    expected_outcome: str = Field(..., min_length=1)
    trigger_action_id: Optional[int] = Field(default=None)


class ReasoningLogUpdate(BaseModel):
    status: Optional[str] = Field(default=None, max_length=32)
    proposed_solution: Optional[str] = Field(default=None)
    expected_outcome: Optional[str] = Field(default=None)


class ReasoningLogResponse(BaseModel):
    id: int
    title: str
    trigger_description: str
    proposed_solution: str
    expected_outcome: str
    status: str
    trigger_action_id: Optional[int]
    created_skill_path: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReasoningLogListItem(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedReasoningLogs(BaseModel):
    items: list[ReasoningLogListItem]
    total: int
    page: int
    size: int
    pages: int


# --- Evolution Budget ---

class EvolutionBudgetCreate(BaseModel):
    max_skills_per_week: int = Field(default=5, ge=0)
    max_agents_per_week: int = Field(default=5, ge=0)


class EvolutionBudgetUpdate(BaseModel):
    max_skills_per_week: Optional[int] = Field(default=None, ge=0)
    max_agents_per_week: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = Field(default=None)


class EvolutionBudgetResponse(BaseModel):
    id: int
    max_skills_per_week: int
    max_agents_per_week: int
    skills_created: int
    agents_created: int
    week_start: datetime
    is_active: bool
    redundancy_check_enabled: bool
    skills_remaining: int
    agents_remaining: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EvolutionBudgetListItem(BaseModel):
    id: int
    max_skills_per_week: int
    max_agents_per_week: int
    skills_remaining: int
    agents_remaining: int
    is_active: bool
    week_start: datetime

    model_config = {"from_attributes": True}


class PaginatedEvolutionBudgets(BaseModel):
    items: list[EvolutionBudgetListItem]
    total: int
    page: int
    size: int
    pages: int


# --- Skill Record ---

class SkillRecordCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="")


class SkillRecordUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None, max_length=32)


class SkillRecordResponse(BaseModel):
    id: int
    name: str
    description: str
    file_path: str
    status: str
    reasoning_log_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillRecordListItem(BaseModel):
    id: int
    name: str
    description: str
    file_path: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedSkills(BaseModel):
    items: list[SkillRecordResponse]
    total: int
    page: int
    size: int
    pages: int


# --- Evolution / Gap Analysis ---

class GapAnalysisRequest(BaseModel):
    """Trigger manual gap analysis."""

    pass


class SkillGap(BaseModel):
    """An identified skill gap from gap analysis."""

    action_type: str
    failure_count: int
    last_failure: datetime
    suggested_skill_name: str
    suggested_skill_description: str


class GapAnalysisResponse(BaseModel):
    gaps: list[SkillGap]
    analyzed_at: datetime
    total_failures_analyzed: int
