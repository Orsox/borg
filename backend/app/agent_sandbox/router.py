"""API router for the agent sandbox — scoped execution of `active` Locutus skills."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_sandbox import service
from app.agent_sandbox.schemas import SkillExecutionRequest, SkillExecutionResponse
from app.auth.router import get_current_user
from app.database import get_session

router = APIRouter(prefix="/api/agent-sandbox", tags=["agent-sandbox"])


@router.post("/skills/{skill_id}/execute", response_model=SkillExecutionResponse)
async def execute_skill(
    skill_id: int,
    body: SkillExecutionRequest,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Run an `active` skill inside a locked-down, ephemeral sandbox container.

    The only entry point for skill *execution* — Stage 4 never auto-promotes a
    drafted skill to `active`, so this always requires a prior, separate human
    review/promotion of the target `SkillRecord`.
    """
    try:
        result = await service.execute_skill(db, skill_id, command=body.command)
    except service.SkillRecordNotFound:
        raise HTTPException(status_code=404, detail="Skill record not found")
    except service.SkillNotActive as e:
        raise HTTPException(status_code=409, detail=str(e))
    except service.SkillExecutionDenied as e:
        raise HTTPException(status_code=403, detail=str(e))

    return SkillExecutionResponse(**result)
