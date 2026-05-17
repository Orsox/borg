"""Service layer for Task Automation."""

import json
import math
from datetime import datetime, timezone

from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.task_automation.models import Task, TaskRun
from app.task_automation.scheduler import (
    register_task,
    remove_task,
    reschedule_task,
    sse_queue,
)


def _tags_to_json(tags: list[str]) -> str:
    return json.dumps(tags)


def _json_to_tags(tags_str: str) -> list[str]:
    try:
        return json.loads(tags_str)
    except (json.JSONDecodeError, TypeError):
        return []


async def create_task(
    db: AsyncSession,
    name: str,
    task_type: str = "shell",
    schedule: str | None = None,
    command: str | None = None,
    archon_workflow_name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    retry_max: int = 0,
    retry_delay: int = 60,
    timeout: int = 300,
) -> Task:
    """Create a new task and register with scheduler."""
    if tags is None:
        tags = []
    
    task = Task(
        name=name,
        task_type=task_type,
        schedule=schedule,
        command=command,
        archon_workflow_name=archon_workflow_name,
        description=description,
        tags=_tags_to_json(tags),
        retry_max=retry_max,
        retry_delay=retry_delay,
        timeout=timeout,
        is_enabled=True,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # Register with scheduler if it has a schedule
    if schedule:
        await register_task(task)
    
    return task


async def get_task(db: AsyncSession, task_id: int) -> Task | None:
    """Get a single task by ID."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    tags: str | None = None,
    status: str | None = None,
) -> dict:
    """List tasks with pagination and filtering."""
    page = max(1, page)
    size = max(1, min(100, size))
    
    query = select(Task)
    
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Task.name.ilike(term),
                Task.description.ilike(term),
            )
        )
    
    if tags and tags.strip():
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                query = query.where(Task.tags.contains(f'"{tag}"'))
    
    if status:
        if status == "enabled":
            query = query.where(Task.is_enabled == True)  # noqa: E712
        elif status == "disabled":
            query = query.where(Task.is_enabled == False)  # noqa: E712
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(Task.created_at.desc())
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


async def update_task(
    db: AsyncSession,
    task_id: int,
    **kwargs,
) -> Task | None:
    """Update a task and reschedule if needed."""
    task = await get_task(db, task_id)
    if not task:
        return None
    
    for key, value in kwargs.items():
        if value is not None and hasattr(task, key):
            setattr(task, key, value)
    
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    
    # Reschedule
    await reschedule_task(task)
    
    return task


async def delete_task(db: AsyncSession, task_id: int) -> bool:
    """Delete a task and remove from scheduler."""
    task = await get_task(db, task_id)
    if not task:
        return False
    
    await remove_task(task_id)
    await db.delete(task)
    await db.commit()
    return True


async def toggle_task(db: AsyncSession, task_id: int) -> dict | None:
    """Toggle task enabled/disabled status."""
    task = await get_task(db, task_id)
    if not task:
        return None
    
    task.is_enabled = not task.is_enabled
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    
    # Reschedule
    await reschedule_task(task)
    
    return {"id": task.id, "is_enabled": task.is_enabled}


async def run_task_now(db: AsyncSession, task_id: int) -> int | None:
    """Manually trigger a task run."""
    task = await get_task(db, task_id)
    if not task:
        return None
    
    # Create run record
    run = TaskRun(task_id=task_id, status="running")
    db.add(run)
    await db.flush()
    await db.refresh(run)
    
    # Notify SSE
    await sse_queue.put({
        "type": "task_run_started",
        "task_id": task_id,
        "task_name": task.name,
        "run_id": run.id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    # Execute in background
    import asyncio
    asyncio.create_task(_execute_task_now(task_id, run.id))
    
    return run.id


async def _execute_task_now(task_id: int, run_id: int) -> None:
    """Execute a task immediately (background task)."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        
        if not task:
            return
        
        result = await db.execute(select(TaskRun).where(TaskRun.id == run_id))
        run = result.scalar_one_or_none()
        
        if not run:
            return
        
        from app.task_automation.scheduler import _run_shell_command, _run_archon_workflow
        
        try:
            start_time = datetime.now(timezone.utc)
            
            if task.task_type == "shell" and task.command:
                exit_code, stdout, stderr = await _run_shell_command(
                    task.command, task.timeout
                )
            elif task.task_type == "archon_workflow" and task.archon_workflow_name:
                exit_code, stdout, stderr = await _run_archon_workflow(
                    task.archon_workflow_name
                )
            else:
                exit_code, stdout, stderr = 1, "", "No command or workflow specified"
            
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            run.finished_at = datetime.now(timezone.utc)
            run.status = "success" if exit_code == 0 else "failed"
            run.exit_code = exit_code
            run.stdout = stdout[:10000]  # Cap output size
            run.stderr = stderr[:10000]
            run.duration_ms = duration_ms
            
            await db.commit()
            
            await sse_queue.put({
                "type": f"task_run_{'completed' if exit_code == 0 else 'failed'}",
                "task_id": task_id,
                "task_name": task.name,
                "run_id": run_id,
                "status": run.status,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Task execution error: {e}")
            run.finished_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.stderr = str(e)
            await db.commit()


async def get_task_runs(
    db: AsyncSession,
    task_id: int,
    page: int = 1,
    size: int = 20,
) -> dict:
    """Get execution history for a task."""
    page = max(1, page)
    size = max(1, min(100, size))
    
    query = select(TaskRun).where(TaskRun.task_id == task_id)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(TaskRun.started_at.desc())
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


async def get_sse_event() -> dict:
    """Get the next SSE event from the queue."""
    return await sse_queue.get()
