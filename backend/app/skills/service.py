"""Service layer for the Skills module."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.models import Skill
from app.skills.yaml_generator import generate_skill_yaml

# Path to Archon workflows directory (same as archon_hub scanner)
_DEFAULT_ARCHON_WORKFLOWS = Path(__file__).resolve().parents[3] / ".archon" / "workflows"


def _tags_to_json(tags: list[str]) -> str:
    return json.dumps(tags)


async def create_skill(
    db: AsyncSession,
    name: str,
    description: str | None = None,
    model: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
) -> Skill:
    """Create a new skill. Generates the Archon workflow YAML file."""
    if tags is None:
        tags = []

    # Generate YAML first (before any DB write) so a failure leaves no partial state
    yaml_content = generate_skill_yaml(
        name=name,
        description=description or "",
        model=model or "lm-studio/qwen/qwen3.6-35b-a3b-mtp",
        category=category or "general",
        tags=tags or [],
    )
    workflow_path = _DEFAULT_ARCHON_WORKFLOWS / f"{name}.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(yaml_content, encoding="utf-8")

    skill = Skill(
        name=name,
        description=description,
        model=model,
        tags=_tags_to_json(tags),
        category=category,
        is_active=True,
        archon_workflow_file=str(workflow_path),
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)

    # Notify SSE
    from app.task_automation.scheduler import sse_queue
    await sse_queue.put({
        "type": "skill_created",
        "skill_id": skill.id,
        "skill_name": skill.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return skill


async def get_skill(db: AsyncSession, skill_id: int) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    return result.scalar_one_or_none()


async def get_skill_by_name(db: AsyncSession, name: str) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.name == name))
    return result.scalar_one_or_none()


async def list_skills(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    category: str | None = None,
    active_only: bool = True,
) -> dict:
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(Skill)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Skill.name.ilike(term),
                Skill.description.ilike(term),
            )
        )

    if category and category.strip():
        query = query.where(Skill.category == category)

    if active_only:
        query = query.where(Skill.is_active == True)  # noqa: E712

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(Skill.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


async def update_skill(
    db: AsyncSession,
    skill_id: int,
    **kwargs,
) -> Skill | None:
    skill = await get_skill(db, skill_id)
    if not skill:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(skill, key):
            # Serialize list values to JSON for Text columns (tags)
            if key == "tags" and isinstance(value, list):
                value = json.dumps(value)
            setattr(skill, key, value)

    skill.updated_at = datetime.now(timezone.utc)

    # If name changed, regenerate workflow YAML with new name
    if "name" in kwargs and kwargs["name"]:
        yaml_content = _generate_workflow_yaml(skill)
        workflow_path = _DEFAULT_ARCHON_WORKFLOWS / f"{skill.name}.yaml"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(yaml_content, encoding="utf-8")
        skill.archon_workflow_file = str(workflow_path)

    await db.commit()
    await db.refresh(skill)

    # Notify SSE
    from app.task_automation.scheduler import sse_queue
    await sse_queue.put({
        "type": "skill_updated",
        "skill_id": skill.id,
        "skill_name": skill.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return skill


async def delete_skill(db: AsyncSession, skill_id: int) -> bool:
    skill = await get_skill(db, skill_id)
    if not skill:
        return False

    # Remove the workflow YAML file
    if skill.archon_workflow_file:
        workflow_path = Path(skill.archon_workflow_file)
        if workflow_path.exists():
            workflow_path.unlink()

    await db.delete(skill)
    await db.commit()

    # Notify SSE
    from app.task_automation.scheduler import sse_queue
    await sse_queue.put({
        "type": "skill_deleted",
        "skill_id": skill_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return True


async def regenerate_skill_yaml(db: AsyncSession, skill_id: int) -> dict | None:
    """Regenerate the Archon workflow YAML for a skill."""
    skill = await get_skill(db, skill_id)
    if not skill:
        return None

    yaml_content = _generate_workflow_yaml(skill)
    workflow_path = _DEFAULT_ARCHON_WORKFLOWS / f"{skill.name}.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(yaml_content, encoding="utf-8")
    skill.archon_workflow_file = str(workflow_path)
    await db.commit()

    # Notify SSE
    from app.task_automation.scheduler import sse_queue
    await sse_queue.put({
        "type": "skill_yaml_regenerated",
        "skill_id": skill.id,
        "skill_name": skill.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "name": skill.name,
        "yaml_content": yaml_content,
        "file_path": str(workflow_path),
    }


def _generate_workflow_yaml(skill: Skill) -> str:
    """Generate an Archon workflow YAML from a skill definition.

    Follows the pattern from borg-nanoprobe.yaml: multi-node workflow
    with model routing, artifact directories, and context management.
    """
    from app.skills.yaml_generator import generate_skill_yaml
    return generate_skill_yaml(
        name=skill.name,
        description=skill.description or "",
        model=skill.model or "lm-studio/qwen/qwen3.6-35b-a3b-mtp",
        category=skill.category or "general",
        tags=json.loads(skill.tags) if skill.tags else [],
    )
