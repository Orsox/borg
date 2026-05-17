"""API router for Task Automation module."""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.task_automation import service
from app.task_automation.schemas import (
    PaginatedTasks,
    TaskCreate,
    TaskListItem,
    TaskResponse,
    TaskRunResponse,
    TaskRunTriggerResponse,
    TaskUpdate,
    ToggleResponse,
)
from app.auth.router import get_current_user
from app.database import get_session

router = APIRouter(prefix="/api/tasks", tags=["task_automation"])


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    task = await service.create_task(
        db,
        name=body.name,
        task_type=body.task_type,
        schedule=body.schedule,
        command=body.command,
        archon_workflow_name=body.archon_workflow_name,
        description=body.description,
        tags=body.tags,
        retry_max=body.retry_max,
        retry_delay=body.retry_delay,
        timeout=body.timeout,
    )
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        task_type=task.task_type,
        schedule=task.schedule,
        command=task.command,
        archon_workflow_name=task.archon_workflow_name,
        is_enabled=task.is_enabled,
        tags=json.loads(task.tags) if task.tags else [],
        retry_max=task.retry_max,
        retry_delay=task.retry_delay,
        timeout=task.timeout,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("", response_model=PaginatedTasks)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_tasks(
        db,
        page=page,
        size=size,
        search=search,
        tags=tags,
        status=status,
    )
    return PaginatedTasks(
        items=[
            TaskListItem(
                id=t.id,
                name=t.name,
                description=t.description,
                task_type=t.task_type,
                schedule=t.schedule,
                is_enabled=t.is_enabled,
                tags=json.loads(t.tags) if t.tags else [],
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    task = await service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        task_type=task.task_type,
        schedule=task.schedule,
        command=task.command,
        archon_workflow_name=task.archon_workflow_name,
        is_enabled=task.is_enabled,
        tags=json.loads(task.tags) if task.tags else [],
        retry_max=task.retry_max,
        retry_delay=task.retry_delay,
        timeout=task.timeout,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    task = await service.update_task(db, task_id, **body.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        task_type=task.task_type,
        schedule=task.schedule,
        command=task.command,
        archon_workflow_name=task.archon_workflow_name,
        is_enabled=task.is_enabled,
        tags=json.loads(task.tags) if task.tags else [],
        retry_max=task.retry_max,
        retry_delay=task.retry_delay,
        timeout=task.timeout,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    deleted = await service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"message": "Task deleted"}


@router.post("/{task_id}/toggle", response_model=ToggleResponse)
async def toggle_task(
    task_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.toggle_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return ToggleResponse(**result)


@router.post("/{task_id}/run", response_model=TaskRunTriggerResponse)
async def run_task_now(
    task_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    run_id = await service.run_task_now(db, task_id)
    if run_id is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskRunTriggerResponse(task_run_id=run_id, message="Task triggered")


@router.get("/{task_id}/runs", response_model=PaginatedTasks)
async def get_task_runs(
    task_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    task = await service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    result = await service.get_task_runs(db, task_id, page=page, size=size)
    
    return {
        "items": [
            TaskRunResponse(
                id=r.id,
                task_id=r.task_id,
                started_at=r.started_at,
                finished_at=r.finished_at,
                status=r.status,
                exit_code=r.exit_code,
                stdout=r.stdout,
                stderr=r.stderr,
                duration_ms=r.duration_ms,
            )
            for r in result["items"]
        ],
        "total": result["total"],
        "page": result["page"],
        "size": result["size"],
        "pages": result["pages"],
    }


@router.get("/stream")
async def sse_stream(
    _user=Depends(get_current_user),
):
    """Server-Sent Events endpoint for real-time task notifications."""
    async def event_generator():
        from app.task_automation.scheduler import sse_queue
        while True:
            try:
                event = await sse_queue.get()
                yield f"data: {json.dumps(event)}\n\n"
            except Exception:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Stream disconnected'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
