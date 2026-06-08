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
import base64
import logging
import re
import shutil
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.locutus.models import SkillRecord
from app.locutus.service import record_action
from app.seven_of_nine.service import record_action as record_seven_action

logger = logging.getLogger(__name__)
agent_logger = logging.getLogger("borg.agent")

REPO_ROOT = Path(__file__).resolve().parents[3]
SANDBOX_IMAGE = "borg-agent-sandbox:latest"
SANDBOX_BASE_DIR = Path("/tmp/borg-agent-sandbox")

# Seven of Nine's "Agent Mode" — `pi` (https://pi.dev) running inside the same
# ephemeral-worktree/locked-down-container shape as skill execution, but on a
# dedicated image (with `pi` baked in) and attached to the `lmstudio` network
# instead of `--network=none`, since `pi` needs to reach an LLM backend. See
# build_pi_docker_run_argv for the exact deviation and Dockerfile.pi for the
# image's lockdown notes.
PI_SANDBOX_IMAGE = "borg-agent-sandbox-pi:latest"
LMSTUDIO_NETWORK = "lmstudio-docker_default"
_PI_RUN_TIMEOUT = 600

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


def _gitlab_remote_url(repo: str) -> str:
    """Build the HTTPS clone URL for one of Seven's own GitLab repos."""
    return f"{settings.seven_gitlab_url}/{settings.seven_gitlab_username}/{repo}.git"


def _gitlab_auth_args() -> list[str]:
    """Per-invocation `git -c` flags — inserted right after `git` in argv.

    Auth header: GitLab's git-http-backend authenticates Personal Access Tokens
    via HTTP Basic auth (`username:token`), NOT `Authorization: Bearer` — that
    style only works against the REST API (confirmed empirically: `Bearer`
    against the smart-HTTP endpoint triggers an interactive credential prompt
    and fails headlessly with "could not read Username"; base64-encoded Basic
    is accepted). Passed via `http.extraHeader` rather than embedded in the
    remote URL (`https://user:token@host/...`), which would leak the PAT into
    `.git/config`, `ps`, and logs — the token exists only in this one argv
    list, which `_run_subprocess` doesn't log.

    sslVerify=false: the omnibus GitLab instance forces HTTPS with a
    self-signed certificate (confirmed empirically — `http://gitlab` answers
    with a TLS redirect). Disabling verification for this one internal,
    Docker-network-only host is the pragmatic trade-off; the alternative
    (importing the self-signed CA into the image's trust store) is more
    moving parts for the same internal-only guarantee.
    """
    basic = base64.b64encode(f"{settings.seven_gitlab_username}:{settings.seven_gitlab_token}".encode()).decode()
    return [
        "-c", f"http.extraHeader=Authorization: Basic {basic}",
        "-c", "http.sslVerify=false",
    ]


async def _clone_seven_repo(run_id: str, repo: str) -> tuple[Path, str]:
    """Clone one of Seven's own GitLab repos into a throwaway directory and check
    out a fresh branch for this run.

    Replaces _create_worktree for Agent Mode: operates entirely on Seven's own
    GitLab remote using her PAT, never touches REPO_ROOT or the local borg
    checkout — sidesteps that bug entirely rather than fixing it.
    """
    SANDBOX_BASE_DIR.mkdir(parents=True, exist_ok=True)
    clone_path = SANDBOX_BASE_DIR / run_id
    branch = f"agent-mode/{run_id}"

    agent_logger.info(f"[clone] Cloning {repo} from {_gitlab_remote_url(repo)}")
    exit_code, clone_stdout, clone_stderr = await _run_subprocess(
        ["git", *_gitlab_auth_args(), "clone", _gitlab_remote_url(repo), str(clone_path)],
    )
    if exit_code != 0:
        agent_logger.error(f"[clone] Failed to clone {repo}: exit_code={exit_code} stderr={clone_stderr.strip()}")
        raise RuntimeError(f"Failed to clone {repo}: {clone_stderr.strip()}")
    agent_logger.info(f"[clone] Clone successful → {clone_path}")

    agent_logger.info(f"[clone] Creating branch {branch}")
    exit_code, _, checkout_stderr = await _run_subprocess(
        ["git", "-C", str(clone_path), "checkout", "-b", branch],
    )
    if exit_code != 0:
        agent_logger.error(f"[clone] Failed to create branch {branch}: exit_code={exit_code} stderr={checkout_stderr.strip()}")
        raise RuntimeError(f"Failed to create branch {branch}: {checkout_stderr.strip()}")
    agent_logger.info(f"[clone] Branch {branch} created")

    return clone_path, branch


async def _cleanup_clone(clone_path: Path) -> None:
    """Remove a throwaway clone.

    Simpler than _remove_worktree: each run is an independent clone of Seven's
    remote, so there's no shared local repo/branch state to clean up afterward.
    """
    shutil.rmtree(clone_path, ignore_errors=True)


async def _commit_and_push(clone_path: Path, branch: str, run_id: str, task_description: str) -> tuple[bool, str]:
    """Commit the run's changes and push them to a throwaway branch.

    Review-first, just moved up a level: only ever pushes a fresh
    `agent-mode/{run_id}` branch, never `main`/`master` — pushing a branch is
    the new "diff", reviewed and merged by hand via the returned compare URL.
    Returns (pushed, compare_url) on success or (False, error message) on
    failure at any of the three git steps.
    """
    agent_logger.info(f"[commit] git add -A")
    exit_code, _, add_stderr = await _run_subprocess(["git", "-C", str(clone_path), "add", "-A"])
    if exit_code != 0:
        agent_logger.error(f"[commit] git add failed: exit_code={exit_code} stderr={add_stderr.strip()}")
        return False, f"git add failed: {add_stderr.strip()}"

    commit_message = f"Agent Mode {run_id}: {task_description[:72]}"
    agent_logger.info(f"[commit] git commit -m \"{commit_message}\"")
    exit_code, _, commit_stderr = await _run_subprocess([
        "git", "-C", str(clone_path),
        "-c", "user.name=Seven of Nine",
        "-c", "user.email=seven-of-nine@borgos.local",
        "commit", "-m", commit_message,
    ])
    if exit_code != 0:
        agent_logger.error(f"[commit] git commit failed: exit_code={exit_code} stderr={commit_stderr.strip()}")
        return False, f"git commit failed: {commit_stderr.strip()}"
    agent_logger.info(f"[commit] Commit successful")

    agent_logger.info(f"[push] git push -u origin {branch}")
    exit_code, _, push_stderr = await _run_subprocess([
        "git", *_gitlab_auth_args(), "-C", str(clone_path), "push", "-u", "origin", branch,
    ])
    if exit_code != 0:
        agent_logger.error(f"[push] git push failed: exit_code={exit_code} stderr={push_stderr.strip()}")
        return False, f"git push failed: {push_stderr.strip()}"
    agent_logger.info(f"[push] Push successful → {branch}")

    compare_url = (
        f"{settings.seven_gitlab_url}/{settings.seven_gitlab_username}/"
        f"{settings.seven_gitlab_workspace_repo}/-/compare/main...{branch}"
    )
    return True, compare_url


async def create_gitlab_repo(name: str, description: str = "") -> dict:
    """Create a new project under Seven's own GitLab namespace.

    Mirrors ArchonClient's authenticated-httpx-call shape (archon_system/client.py).
    Triggered only via the `[GITLAB_REPO: <name>]` directive — "the model
    decides, the code holds the fixed contract" — never from free-form input.
    Returns the GitLab project dict (incl. `web_url`, `http_url_to_repo`).
    """
    url = f"{settings.seven_gitlab_url}/api/v4/projects"
    headers = {"PRIVATE-TOKEN": settings.seven_gitlab_token}
    payload: dict = {"name": name, "visibility": "private"}
    if description:
        payload["description"] = description

    # verify=False: same self-signed-certificate trade-off as _gitlab_auth_args'
    # http.sslVerify=false — internal, Docker-network-only host.
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), verify=False) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


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


def build_pi_docker_run_argv(
    *,
    container_name: str,
    worktree_path: Path,
    task: str,
    llm_base_url: str,
    model_id: str,
    image: str = PI_SANDBOX_IMAGE,
) -> list[str]:
    """Construct the `docker run` invocation for one Seven of Nine Agent Mode run.

    Same lockdown as build_docker_run_argv (cap-drop, read-only, resource
    limits, --user 1000:1000, worktree-only mount) with two deliberate
    deviations from `--network=none`/a stock `$HOME`:

    1. Attached to the `lmstudio` bridge network instead of `--network=none`,
       because `pi` has to reach an LLM backend to do anything. That network
       reaches only the LM Studio hosts — no internet, no other containers,
       no host filesystem. See Dockerfile.pi for the rationale.
    2. `HOME` is redirected to the `/tmp` tmpfs. `pi` persists session state
       under `$HOME/.pi/agent/sessions/<workspace>/` — but Dockerfile.pi's
       `useradd --create-home sandbox` puts `$HOME` at `/home/sandbox`, which
       lives on the `--read-only` root filesystem. Without this override `pi`
       crashes immediately trying to create that directory (confirmed
       empirically: "directory ... did not exist" under
       `/home/sandbox/.pi/agent/sessions/...`) — an environment-init failure
       no task description can work around, since it happens before `pi` does
       anything task-related. `/tmp` is the one writable path already mounted
       (`--tmpfs`), so pointing `$HOME` there needs no extra mount.
    """
    return [
        "docker", "run", "--rm",
        "--name", container_name,
        "--network", LMSTUDIO_NETWORK,
        "--cpus=2",
        "--memory=2g",
        "--pids-limit=256",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
        "-v", f"{worktree_path}:/workspace:rw",
        "-w", "/workspace",
        "--user", "1000:1000",
        "-e", "HOME=/tmp/pi-home",
        # LM Studio speaks OpenAI-compatible API — configure pi to use it as
        # the "openai" provider. OPENAI_BASE_URL points to the LM Studio
        # endpoint; OPENAI_API_KEY can be any non-empty string since LM Studio
        # does not require authentication (it accepts any bearer token).
        "-e", f"OPENAI_BASE_URL={llm_base_url}",
        "-e", "OPENAI_API_KEY=not-needed-lm-studio-no-auth",
        image,
        "pi", "run", "--provider", "openai", "--model", model_id, task,
    ]


async def run_agent_mode_task(
    db: AsyncSession,
    task_description: str,
    llm_base_url: str,
    model_id: str,
    run_id: str | None = None,
) -> dict:
    """Run one Seven of Nine Agent Mode task: `pi` working an ephemeral worktree
    inside a locked-down sandbox container.

    Mirrors execute_skill's shape (deny-list -> worktree -> container -> capture
    diff -> audit -> teardown), but the "skill" here is the user's free-text task
    description handed to `pi` rather than a pre-approved SkillRecord — so the
    deny-list is the only pre-execution gate, and the result is purely
    informational: the diff is reported back, never auto-applied (see plan
    "review-first, no auto-apply"). Every attempt produces exactly one
    DroneAuditEntry with action="agent_mode_run".
    """
    run_id = run_id or f"agent-mode-{uuid.uuid4().hex[:8]}"

    violation = check_deny_list(task_description)
    if violation:
        await record_seven_action(
            db,
            action="agent_mode_run",
            target=run_id,
            payload_summary=f"denied — matched deny-list rule '{violation}': {_truncate(task_description, 500)}",
            result="denied",
            run_id=run_id,
        )
        raise SkillExecutionDenied(f"Task violates deny-list rule '{violation}'")

    agent_logger.info(f"[run] Starting agent run {run_id}")
    agent_logger.info(f"[run] task={_truncate(task_description, 500)}")
    agent_logger.info(f"[run] llm_base_url={llm_base_url}")
    agent_logger.info(f"[run] model={model_id}")

    clone_path, branch = await _clone_seven_repo(run_id, settings.seven_gitlab_workspace_repo)
    try:
        agent_logger.info(f"[run] Clone ready at {clone_path}, branch {branch}")

        container_name = f"borg-agent-run-{run_id}"
        argv = build_pi_docker_run_argv(
            container_name=container_name,
            worktree_path=clone_path,
            task=task_description,
            llm_base_url=llm_base_url,
            model_id=model_id,
        )
        agent_logger.info(f"[run] Docker command: {' '.join(argv[:10])}...")
        agent_logger.info(f"[run] Waiting up to {_PI_RUN_TIMEOUT}s for container output")
        exit_code, stdout, stderr = await _run_subprocess(argv, timeout=_PI_RUN_TIMEOUT)

        if exit_code != 0:
            agent_logger.error(f"[run] Container exited with code {exit_code}")
            agent_logger.error(f"[run] stderr (first 1000 chars): {_truncate(stderr, 1000)}")
            agent_logger.error(f"[run] stdout (first 1000 chars): {_truncate(stdout, 1000)}")
        else:
            agent_logger.info(f"[run] Container exited successfully (code 0)")

        diff = await _capture_diff(clone_path)
        if diff.strip():
            agent_logger.info(f"[run] Diff produced: {len(diff)} bytes")
        else:
            agent_logger.info(f"[run] No diff produced (no changes)")

        pushed = False
        compare_url: str | None = None
        if exit_code != 0:
            push_note = "skipped — run failed"
            agent_logger.info(f"[push] Skipped — run failed")
        elif not diff.strip():
            push_note = "skipped — no changes"
            agent_logger.info(f"[push] Skipped — no changes")
        else:
            agent_logger.info(f"[push] Attempting commit and push")
            pushed, push_result = await _commit_and_push(clone_path, branch, run_id, task_description)
            if pushed:
                compare_url = push_result
                push_note = f"pushed branch {branch} — compare: {compare_url}"
                agent_logger.info(f"[push] Success — compare: {compare_url}")
            else:
                push_note = f"push failed: {push_result}"
                agent_logger.error(f"[push] Failed: {push_result}")

        outcome = "ok" if exit_code == 0 else "error"
        summary = (
            f"task={_truncate(task_description, 500)}\n"
            f"exit_code={exit_code}\n"
            f"clone={clone_path}\n"
            f"branch={branch}\n"
            f"push={push_note}\n"
            f"--- stdout ---\n{_truncate(stdout)}\n"
            f"--- stderr ---\n{_truncate(stderr)}\n"
            f"--- diff ---\n{_truncate(diff)}"
        )
        await record_seven_action(
            db,
            action="agent_mode_run",
            target=run_id,
            payload_summary=_truncate(summary),
            result=outcome,
            run_id=run_id,
        )

        return {
            "run_id": run_id,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "diff": diff,
            "worktree_path": str(clone_path),
            "branch": branch,
            "pushed": pushed,
            "compare_url": compare_url,
        }
    finally:
        await _cleanup_clone(clone_path)
