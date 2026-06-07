"""Schemas for the agent sandbox module."""

from pydantic import BaseModel, Field


class SkillExecutionRequest(BaseModel):
    command: list[str] = Field(..., min_length=1, description="Argv to run inside the sandbox container")


class SkillExecutionResponse(BaseModel):
    skill_id: int
    run_id: str
    exit_code: int
    stdout: str
    stderr: str
    diff: str
    worktree_path: str
