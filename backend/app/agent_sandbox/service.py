"""Service layer for the agent sandbox — scoped execution of `active` Locutus skills.

Stage 5 of `thoughts/locutus-autonomy-transition-plan.md`: the minimum viable
slice of `thoughts/borg-os-llm-sandbox-hardening-idea.md`, reduced to exactly
what skill *execution* needs — ephemeral worktree -> locked-down container ->
captured output/diff -> teardown. No policy engine yet (Phase 2 of the doc);
a hard-coded deny-list is the only pre-execution check, and only `active`
skills (i.e. ones a human has reviewed and promoted past Stage 4's `draft`)
may run.
"""

import asyncio
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locutus.models import SkillRecord
from app.locutus.service import record_action

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SANDBOX_IMAGE = "borg-agent-sandbox:latest"
SANDBOX_BASE_DIR = Path("/tmp/borg-agent-sandbox")

_OUTPUT_TRUNCATE_LIMIT = 4000


class SkillRecordNotFound(Exception):
    """Raised when execution targets a SkillRecord id that doesn't exist."""


class SkillNotActive(Exception):
    """Raised when execution is attempted on a skill that isn't `status="active"`."""


class SkillExecutionDenied(Exception):
    """Raised when a skill's command matches a hard-coded deny-list rule."""


# Hard-coded deny-list (Phase 1 of the hardening doc — no policy engine yet).
# Mirrors the doc's "Blockieren" list: privilege escalation, mounting,
# piping remote scripts into a shell, and reading host credential dirs.
_DENY_LIST_RULES: list[tuple[str, re.Pattern]] = [
    ("sudo", re.compile(r"(?<![\w-])sudo(?![\w-])")),
    ("mount", re.compile(r"(?<![\w-])(u)?mount(?![\w-])")),
    ("docker host mount", re.compile(r"docker\s+run\b[^\n]*-v\s*/(?::|\s)")),
    ("pipe remote script into shell", re.compile(r"(curl|wget)\b[^\n|]*\|\s*(sh|bash|zsh)\b")),
    ("ssh credential access", re.compile(r"~?/\.ssh\b")),
    ("cloud credential access", re.compile(r"~?/\.(aws|config|gnupg)\b")),
]


def check_deny_list(command: str) -> str | None:
    """Return the name of the first deny-list rule the command violates, or None."""
    for name, pattern in _DENY_LIST_RULES:
        if pattern.search(command):
            return name
    return None


def build_docker_run_argv(
    *,
    container_name: str,
    worktree_path: Path,
    command: list[str],
    image: str = SANDBOX_IMAGE,
) -> list[str]:
    """Construct the locked-down `docker run` invocation for one skill execution.

    Mirrors the example in `thoughts/borg-os-llm-sandbox-hardening-idea.md`: no
    network, all capabilities dropped, read-only root, explicit resource
    limits, and only the ephemeral worktree mounted — never the host
    filesystem, the Docker socket, or secrets.
    """
    return [
        "docker", "run", "--rm",
        "--name", container_name,
        "--cpus=2",
        "--memory=2g",
        "--pids-limit=256",
        "--network=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
        "-v", f"{worktree_path}:/workspace:rw",
        "-w", "/workspace",
        "--user", "1000:1000",
        image,
        *command,
    ]


def _truncate(text: str, limit: int = _OUTPUT_TRUNCATE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more characters]"


async def _run_subprocess(argv: list[str], cwd: Path | None = None, timeout: int = 600) -> tuple[int, str, str]:
    """Run a subprocess to completion and capture (exit_code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return -1, "", f"Command timed out after {timeout}s"
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _create_worktree(run_id: str) -> tuple[Path, str]:
    """Create an ephemeral git worktree on its own throwaway branch."""
    SANDBOX_BASE_DIR.mkdir(parents=True, exist_ok=True)
    worktree_path = SANDBOX_BASE_DIR / run_id
    branch = f"agent-sandbox/{run_id}"

    exit_code, _, stderr = await _run_subprocess(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"],
        cwd=REPO_ROOT,
    )
    if exit_code != 0:
        raise RuntimeError(f"Failed to create sandbox worktree: {stderr.strip()}")
    return worktree_path, branch


async def _remove_worktree(worktree_path: Path, branch: str) -> None:
    """Tear down the ephemeral worktree and its throwaway branch."""
    exit_code, _, stderr = await _run_subprocess(
        ["git", "worktree", "remove", "--force", str(worktree_path)], cwd=REPO_ROOT
    )
    if exit_code != 0:
        logger.warning(f"Failed to remove sandbox worktree {worktree_path}: {stderr.strip()}")
    exit_code, _, stderr = await _run_subprocess(["git", "branch", "-D", branch], cwd=REPO_ROOT)
    if exit_code != 0:
        logger.warning(f"Failed to remove sandbox branch {branch}: {stderr.strip()}")


async def _capture_diff(worktree_path: Path) -> str:
    """Capture the diff produced by the skill run inside its worktree."""
    _, stdout, _ = await _run_subprocess(["git", "diff", "HEAD"], cwd=worktree_path)
    return stdout


async def execute_skill(
    db: AsyncSession,
    skill_id: int,
    command: list[str],
    run_id: str | None = None,
) -> dict:
    """Execute an `active` skill inside a locked-down, ephemeral sandbox.

    The sole entry point for skill *execution* — Stage 4 drafts skills as
    `status="draft"` and never auto-promotes them, so reaching here always
    requires a prior, separate human review/promotion of the `SkillRecord`.
    Every attempt — denied, rejected, or completed — produces exactly one
    `LocutusAuditEntry` with `action="skill_execution"`.
    """
    run_id = run_id or f"skill-exec-{skill_id}-{uuid.uuid4().hex[:8]}"
    command_str = " ".join(command)

    result = await db.execute(select(SkillRecord).where(SkillRecord.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise SkillRecordNotFound(f"SkillRecord {skill_id} not found")

    if skill.status != "active":
        await record_action(
            db,
            action="skill_execution",
            target=str(skill.id),
            payload_summary=f"rejected — skill status is '{skill.status}', not 'active': {_truncate(command_str, 500)}",
            result="denied",
            run_id=run_id,
        )
        raise SkillNotActive(
            f"SkillRecord {skill_id} is '{skill.status}' — only 'active' skills can be executed"
        )

    violation = check_deny_list(command_str)
    if violation:
        await record_action(
            db,
            action="skill_execution",
            target=str(skill.id),
            payload_summary=f"denied — matched deny-list rule '{violation}': {_truncate(command_str, 500)}",
            result="denied",
            run_id=run_id,
        )
        raise SkillExecutionDenied(f"Command violates deny-list rule '{violation}'")

    worktree_path, branch = await _create_worktree(run_id)
    try:
        container_name = f"borg-agent-run-{run_id}"
        argv = build_docker_run_argv(container_name=container_name, worktree_path=worktree_path, command=command)
        exit_code, stdout, stderr = await _run_subprocess(argv, timeout=600)
        diff = await _capture_diff(worktree_path)

        outcome = "ok" if exit_code == 0 else "error"
        summary = (
            f"command={command_str}\n"
            f"exit_code={exit_code}\n"
            f"worktree={worktree_path}\n"
            f"--- stdout ---\n{_truncate(stdout)}\n"
            f"--- stderr ---\n{_truncate(stderr)}"
        )
        await record_action(
            db,
            action="skill_execution",
            target=str(skill.id),
            payload_summary=_truncate(summary),
            result=outcome,
            run_id=run_id,
        )

        return {
            "skill_id": skill.id,
            "run_id": run_id,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "diff": diff,
            "worktree_path": str(worktree_path),
        }
    finally:
        await _remove_worktree(worktree_path, branch)
