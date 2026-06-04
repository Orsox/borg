"""API router for the Skills module."""

import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_session
from app.skills import service
from app.skills.schemas import (
    PaginatedSkills,
    SkillCreate,
    SkillListItem,
    SkillResponse,
    SkillUpdate,
    SkillYamlResponse,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    # Check for duplicate name
    existing = await service.get_skill_by_name(db, body.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{body.name}' already exists",
        )

    skill = await service.create_skill(
        db,
        name=body.name,
        description=body.description,
        model=body.model,
        tags=body.tags,
        category=body.category,
    )
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        archon_workflow_file=skill.archon_workflow_file,
        model=skill.model,
        tags=json.loads(skill.tags) if skill.tags else [],
        is_active=skill.is_active,
        category=skill.category,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.get("", response_model=PaginatedSkills)
async def list_skills(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_skills(
        db,
        page=page,
        size=size,
        search=search,
        category=category,
        active_only=active_only,
    )
    return PaginatedSkills(
        items=[
            SkillListItem(
                id=s.id,
                name=s.name,
                description=s.description,
                is_active=s.is_active,
                category=s.category,
                tags=json.loads(s.tags) if s.tags else [],
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    skill = await service.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        archon_workflow_file=skill.archon_workflow_file,
        model=skill.model,
        tags=json.loads(skill.tags) if skill.tags else [],
        is_active=skill.is_active,
        category=skill.category,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: int,
    body: SkillUpdate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    skill = await service.update_skill(db, skill_id, **body.model_dump(exclude_unset=True))
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        archon_workflow_file=skill.archon_workflow_file,
        model=skill.model,
        tags=json.loads(skill.tags) if skill.tags else [],
        is_active=skill.is_active,
        category=skill.category,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    deleted = await service.delete_skill(db, skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"message": "Skill deleted"}


@router.post("/{skill_id}/regenerate-yaml", response_model=SkillYamlResponse)
async def regenerate_skill_yaml(
    skill_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.regenerate_skill_yaml(db, skill_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return SkillYamlResponse(**result)


@router.get("/{skill_id}/yaml", response_model=SkillYamlResponse)
async def get_skill_yaml(
    skill_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Return the raw YAML content for a skill."""
    skill = await service.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    workflow_path = Path(skill.archon_workflow_file)
    if workflow_path.exists():
        return SkillYamlResponse(
            name=skill.name,
            yaml_content=workflow_path.read_text(encoding="utf-8"),
            file_path=skill.archon_workflow_file,
        )

    # Regenerate if file doesn't exist
    result = await service.regenerate_skill_yaml(db, skill_id)
    if result:
        return SkillYamlResponse(**result)

    raise HTTPException(status_code=500, detail="Cannot generate YAML")
