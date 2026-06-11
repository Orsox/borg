"""APScheduler integration for Task Automation."""

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.task_automation.models import Task, TaskRun

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None

# SSE event queue
sse_queue: asyncio.Queue = asyncio.Queue()


def translate_dreaming_config(time_str: str, frequency: str) -> str:
    """Translates human-friendly config to Cron expression."""
    try:
        hour, minute = time_str.split(":")
        # Remove leading zeros for cron compatibility
        hour_int = int(hour)
        minute_int = int(minute)
        
        freq_map = {
            "hourly": f"{minute_int} * * * *",
            "daily": f"{minute_int} {hour_int} * * *",
            "weekly": f"{minute_int} {hour_int} * * 0",  # Sunday
            "every_6_hours": f"{minute_int} */6 * * *",
            "every_12_hours": f"{minute_int} */12 * * *",
        }
        
        return freq_map.get(frequency, f"{minute_int} {hour_int} * * *")
    except ValueError:
        logger.error(f"Invalid time format: {time_str}. Expected HH:MM.")
        return "* * * * *"


async def init_scheduler() -> None:
    """Initialize the APScheduler and load tasks from DB."""
    global scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    logger.info("APScheduler started")


async def shutdown_scheduler() -> None:
    """Shutdown the APScheduler."""
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


async def register_task(task: Task) -> None:
    """Register a task with the scheduler."""
    if not scheduler or not task.is_enabled or not task.schedule:
        return

    try:
        # Parse cron expression: "minute hour day month weekday"
        parts = task.schedule.split()
        if len(parts) != 5:
            logger.error(f"Invalid cron expression for task {task.id}: {task.schedule}")
            return

        minute, hour, day, month, weekday = parts

        scheduler.add_job(
            _execute_task,
            "cron",
            args=[task.id],
            id=f"task_{task.id}",
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=weekday,
            replace_existing=True,
        )
        logger.info(f"Registered task {task.id} ({task.name}) with schedule {task.schedule}")
    except Exception as e:
        logger.error(f"Failed to register task {task.id}: {e}")


async def remove_task(task_id: int) -> None:
    """Remove a task from the scheduler."""
    if not scheduler:
        return

    job_id = f"task_{task_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Removed task {task_id} from scheduler")
    except Exception as e:
        logger.debug(f"Task {task_id} not found in scheduler: {e}")


async def reschedule_task(task: Task) -> None:
    """Remove and re-add a task to the scheduler."""
    await remove_task(task.id)
    if task.is_enabled and task.schedule:
        await register_task(task)


async def _execute_task(task_id: int) -> None:
    """Execute a task and record the run."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            logger.error(f"Task {task_id} not found")
            return

        # Create run record — committed sofort: Dreaming-Tasks öffnen eine
        # eigene Session auf derselben SQLite-Datei; eine hier offen gehaltene
        # Schreibtransaktion würde deren INSERTs blockieren (Single-Writer →
        # Self-Deadlock, "database is locked" bis zum busy_timeout).
        run = TaskRun(task_id=task_id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        # Notify SSE
        if task.task_type == "heartbeat":
            await sse_queue.put({
                "type": "heartbeat_turn_started",
                "task_id": task_id,
                "task_name": task.name,
                "run_id": run.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            await sse_queue.put({
                "type": "task_run_started",
                "task_id": task_id,
                "task_name": task.name,
                "run_id": run.id,
                "persona": task.dreaming_persona,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

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
            elif task.task_type == "heartbeat" and task.heartbeat_workflow_name:
                exit_code, stdout, stderr = await _run_heartbeat_workflow(
                    task.heartbeat_workflow_name
                )
            elif task.task_type == "skill" and task.archon_workflow_template:
                exit_code, stdout, stderr = await _run_skill_workflow(
                    task.archon_workflow_template, task.id
                )
            elif task.task_type == "dreaming":
                exit_code, stdout, stderr = await _run_dreaming_task(
                    task.dreaming_days, task.dreaming_min_actions, task.dreaming_persona
                )
            else:
                exit_code, stdout, stderr = 1, "", "No command or workflow specified"

            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            run.finished_at = datetime.now(timezone.utc)
            run.status = "success" if exit_code == 0 else "failed"
            run.exit_code = exit_code
            run.stdout = stdout
            run.stderr = stderr
            run.duration_ms = duration_ms

            await db.commit()

            # Notify SSE
            if task.task_type == "heartbeat":
                await sse_queue.put({
                    "type": "heartbeat_turn_completed",
                    "task_id": task_id,
                    "task_name": task.name,
                    "run_id": run.id,
                    "status": run.status,
                    "duration_ms": duration_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                await sse_queue.put({
                    "type": f"task_run_{'completed' if exit_code == 0 else 'failed'}",
                    "task_id": task_id,
                    "task_name": task.name,
                    "run_id": run.id,
                    "status": run.status,
                    "duration_ms": duration_ms,
                    "persona": task.dreaming_persona,
                    "error": (stderr or stdout)[:300] if exit_code != 0 else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        except Exception as e:
            logger.error(f"Task execution error for task {task_id}: {e}")
            run.finished_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.stderr = str(e)
            await db.commit()

            await sse_queue.put({
                "type": "task_run_failed",
                "task_id": task_id,
                "task_name": task.name,
                "run_id": run.id,
                "persona": task.dreaming_persona,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })


async def _run_shell_command(command: str, timeout: int = 300) -> tuple[int, str, str]:
    """Execute a shell command and return (exit_code, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"Task timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


async def _run_archon_workflow(workflow_name: str) -> tuple[int, str, str]:
    """Trigger an Archon workflow by name."""
    cmd = f"archon workflow run {workflow_name} --no-worktree 'Triggered by BorgOS scheduler'"
    return await _run_shell_command(cmd, timeout=600)


async def _run_heartbeat_workflow(workflow_name: str) -> tuple[int, str, str]:
    """Trigger a heartbeat Archon workflow (persistent worktree, full context)."""
    cmd = f"archon workflow run {workflow_name} --no-worktree 'Heartbeat turn by BorgOS'"
    return await _run_shell_command(cmd, timeout=600)


async def _run_skill_workflow(template_name: str, skill_task_id: int) -> tuple[int, str, str]:
    """Execute a skill workflow, recording result as ActionMemory."""
    cmd = f"archon workflow run {template_name} --no-worktree 'Skill execution for task {skill_task_id}'"
    return await _run_shell_command(cmd, timeout=600)


async def _run_dreaming_task(
    days: int = 14,
    min_actions: int = 5,
    persona: str | None = None,
) -> tuple[int, str, str]:
    """Run the dreaming consolidation cycle with retry on SQLite lock."""
    import asyncio as _asyncio

    max_retries = 3
    for attempt in range(max_retries):
        try:
            from app.dreaming.service import run_dreaming_cycle
            async with AsyncSessionLocal() as db:
                result = await run_dreaming_cycle(
                    db, days=days, min_actions=min_actions, persona=persona
                )
            return 0, json.dumps(result), ""
        except Exception as e:
            err_str = str(e)
            # Retry on "database is locked" with exponential backoff
            if "database is locked" in err_str and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    f"Dreaming task database locked (attempt {attempt+1}/{max_retries}), "
                    f"retrying in {wait}s"
                )
                await _asyncio.sleep(wait)
            else:
                logger.exception("Dreaming task failed")
                return 1, "", err_str
    # Should not reach here, but just in case
    return 1, "", "Dreaming task failed after retries"


async def reload_all_tasks() -> None:
    """Reload all enabled tasks from the database into the scheduler."""
    if not scheduler:
        return

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(Task).where(Task.is_enabled == True))  # noqa: E712
        tasks = list(result.scalars().all())

        for task in tasks:
            if task.schedule:
                await register_task(task)

    logger.info(f"Reloaded {len(tasks)} tasks into scheduler")
