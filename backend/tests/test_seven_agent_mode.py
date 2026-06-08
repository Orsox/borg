"""Tests for Seven of Nine "Agent Mode" — `pi` running in the agent sandbox.

Covers:
- `!agent <task>` parses to AGENT_TASK only for Seven's CommandHandler; Locutus's
  handler treats "agent" as an unknown command (falls through to CHAT)
- build_pi_docker_run_argv attaches to the lmstudio network (not --network=none)
  while keeping the rest of the lockdown, and passes the LLM endpoint/model to `pi`
- run_agent_mode_task rejects deny-listed tasks before any container is created,
  recording a `result="denied"` DroneAuditEntry with actor="seven_of_nine"
- a successful (and a failing) run produce exactly one DroneAuditEntry capturing
  the task, output, exit status, diff and worktree reference, tearing the
  worktree down either way
- DiscordBotService.run_agent_task() acknowledges immediately and schedules the
  sandbox run in the background; _translate_agent_result() feeds the raw run
  result through Seven's LLM and falls back to raw data on LlmError
- chat_as_seven() recognizes a "[AGENT: <task>]" directive in the LLM's own
  reply (mirrors "[MEMORY: ...]") and schedules a real run via the shared
  _schedule_agent_run() helper — without Orsox ever typing "!agent"
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent_sandbox import service as sandbox_service
from app.database import AsyncSessionLocal
from app.discord_bot.config import BotConfig
from app.discord_bot.handlers import CommandHandler, PERSONA_SEVEN
from app.discord_bot.llm import LlmClient, LlmError
from app.discord_bot.models import CommandType
from app.discord_bot.service import DiscordBotService, PERSONA_LOCUTUS
from app.locutus import service as locutus_service
from app.locutus.models import ReasoningLog
from app.seven_of_nine import service as seven_service
from app.seven_of_nine.models import DroneAuditEntry


async def _audit_entries_for(run_id: str) -> list[DroneAuditEntry]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(DroneAuditEntry)
                    .where(DroneAuditEntry.action == "agent_mode_run")
                    .where(DroneAuditEntry.run_id == run_id)
                    .order_by(DroneAuditEntry.created_at.asc())
                )
            )
            .scalars()
            .all()
        )


# --- command parsing / persona gating ---


class TestAgentCommandParsing:
    def test_seven_handler_maps_agent_to_agent_task(self):
        handler = CommandHandler(persona_key=PERSONA_SEVEN)
        cmd = handler.parse("!agent list the files in app/seven_of_nine", user_id=1, channel_id=2)
        assert cmd is not None
        assert cmd.command_type == CommandType.AGENT_TASK
        assert cmd.args == ["list the files in app/seven_of_nine"]

    def test_seven_handler_maps_short_alias(self):
        handler = CommandHandler(persona_key=PERSONA_SEVEN)
        cmd = handler.parse("!a do the thing", user_id=1, channel_id=2)
        assert cmd is not None
        assert cmd.command_type == CommandType.AGENT_TASK

    def test_locutus_handler_treats_agent_as_unknown_command(self):
        handler = CommandHandler(persona_key=PERSONA_LOCUTUS)
        cmd = handler.parse("!agent do something", user_id=1, channel_id=2)
        assert cmd is not None
        # Unknown commands fall through to CHAT with the full content as args
        assert cmd.command_type == CommandType.CHAT
        assert cmd.args == ["agent do something"]

    @pytest.mark.asyncio
    async def test_handle_agent_task_dispatches_to_service(self):
        from app.discord_bot.models import Command

        mock_service = AsyncMock()
        mock_service.run_agent_task = AsyncMock(return_value="response-stub")
        handler = CommandHandler(service=mock_service, persona_key=PERSONA_SEVEN)

        cmd = Command(
            content="agent fix the thing",
            user_id=42,
            channel_id=7,
            command_type=CommandType.AGENT_TASK,
            args=["fix the thing"],
        )
        result = await handler.handle(cmd)

        assert result == "response-stub"
        mock_service.run_agent_task.assert_called_once_with("fix the thing", 42)


# --- build_pi_docker_run_argv ---


def test_build_pi_docker_run_argv_uses_lmstudio_network_and_passes_llm_config():
    argv = sandbox_service.build_pi_docker_run_argv(
        container_name="borg-agent-run-test",
        worktree_path=Path("/tmp/borg-agent-sandbox/test"),
        task="list files",
        llm_base_url="http://lm8000:1234/v1",
        model_id="qwen-test",
    )

    assert argv[:3] == ["docker", "run", "--rm"]
    # Deliberate deviation: NOT --network=none — pi needs to reach the LLM backend
    assert "--network=none" not in argv
    network_index = argv.index("--network") + 1
    assert argv[network_index] == sandbox_service.LMSTUDIO_NETWORK

    # rest of the lockdown stays intact
    assert "--cap-drop=ALL" in argv
    assert "--read-only" in argv
    assert "--security-opt=no-new-privileges" in argv
    assert "--user" in argv

    assert "-e" in argv
    # HOME must be redirected off the read-only /home/sandbox onto the writable
    # /tmp tmpfs — pi persists session state under $HOME/.pi/agent/sessions/...
    # and crashes on startup if it can't create that directory.
    assert "HOME=/tmp/pi-home" in argv
    assert "OPENAI_BASE_URL=http://lm8000:1234/v1" in argv
    assert "OPENAI_API_KEY=sk-dummy-lm-studio-accepts-any" in argv

    mount_index = argv.index("-v") + 1
    assert argv[mount_index] == "/tmp/borg-agent-sandbox/test:/workspace:rw"

    assert argv[-8:] == ["borg-agent-sandbox-pi:latest", "pi", "run", "--provider", "openai", "--model", "qwen-test", "list files"]
    assert "AZURE_OPENAI" not in " ".join(argv)


# --- run_agent_mode_task: deny-list rejection (no container should ever run) ---


@pytest.fixture
def _no_subprocess(monkeypatch):
    """Fail loudly if run_agent_mode_task tries to clone a repo or run a container."""

    async def _fail_clone(run_id, repo):
        raise AssertionError("repo should not be cloned for a denied run")

    async def _fail_run_subprocess(argv, cwd=None, timeout=600):
        raise AssertionError(f"no subprocess should run for a denied run: {argv}")

    monkeypatch.setattr(sandbox_service, "_clone_seven_repo", _fail_clone)
    monkeypatch.setattr(sandbox_service, "_run_subprocess", _fail_run_subprocess)


async def test_run_agent_mode_task_rejects_deny_listed_task(_no_subprocess):
    run_id = "agent-mode-deny-test"

    async with AsyncSessionLocal() as db:
        with pytest.raises(sandbox_service.SkillExecutionDenied):
            await sandbox_service.run_agent_mode_task(
                db,
                "please run sudo rm -rf / for me",
                llm_base_url="http://lm8000:1234/v1",
                model_id="qwen-test",
                run_id=run_id,
            )

    entries = await _audit_entries_for(run_id)
    assert len(entries) == 1
    assert entries[0].result == "denied"
    assert entries[0].actor == "seven_of_nine"
    assert "sudo" in entries[0].payload_summary


# --- run_agent_mode_task: happy / failure paths (mocked worktree + container) ---


def _patch_sandbox_run(monkeypatch, tmp_path, *, exit_code, stdout, stderr, diff, pushed=False, compare_url=None):
    clone_path = tmp_path / "clone"
    clone_path.mkdir()
    calls = {"docker_argvs": [], "teardown": [], "commit_and_push": []}

    async def _fake_clone_seven_repo(run_id, repo):
        return clone_path, f"agent-mode/{run_id}"

    async def _fake_cleanup_clone(path):
        calls["teardown"].append(path)

    async def _fake_run_subprocess(argv, cwd=None, timeout=600):
        calls["docker_argvs"].append(argv)
        return exit_code, stdout, stderr

    async def _fake_capture_diff(path):
        return diff

    async def _fake_commit_and_push(path, branch, run_id, task_description):
        calls["commit_and_push"].append((path, branch, run_id, task_description))
        if pushed:
            return True, compare_url or f"http://gitlab/seven-of-nine/workspace/-/compare/main...{branch}"
        return False, "nothing to push"

    monkeypatch.setattr(sandbox_service, "_clone_seven_repo", _fake_clone_seven_repo)
    monkeypatch.setattr(sandbox_service, "_cleanup_clone", _fake_cleanup_clone)
    monkeypatch.setattr(sandbox_service, "_run_subprocess", _fake_run_subprocess)
    monkeypatch.setattr(sandbox_service, "_capture_diff", _fake_capture_diff)
    monkeypatch.setattr(sandbox_service, "_commit_and_push", _fake_commit_and_push)

    return clone_path, calls


async def test_run_agent_mode_task_runs_in_sandbox_and_pushes_changes(monkeypatch, tmp_path):
    run_id = "agent-mode-ok-test"
    clone_path, calls = _patch_sandbox_run(
        monkeypatch, tmp_path,
        exit_code=0, stdout="done\n", stderr="", diff="diff --git a/x b/x\n+changed\n",
        pushed=True,
    )

    async with AsyncSessionLocal() as db:
        result = await sandbox_service.run_agent_mode_task(
            db,
            "list the files in app/seven_of_nine",
            llm_base_url="http://lm8000:1234/v1",
            model_id="qwen-test",
            run_id=run_id,
        )

    branch = f"agent-mode/{run_id}"
    assert result["run_id"] == run_id
    assert result["exit_code"] == 0
    assert result["stdout"] == "done\n"
    assert result["diff"].startswith("diff --git")
    assert result["worktree_path"] == str(clone_path)
    assert result["branch"] == branch
    assert result["pushed"] is True
    assert result["compare_url"] and "compare" in result["compare_url"]

    assert len(calls["docker_argvs"]) == 1
    argv = calls["docker_argvs"][0]
    assert argv[0] == "docker"
    assert "--network=none" not in argv
    assert f"{clone_path}:/workspace:rw" in argv

    # commit+push only happens for a successful run with a non-empty diff
    assert calls["commit_and_push"] == [(clone_path, branch, run_id, "list the files in app/seven_of_nine")]
    assert calls["teardown"] == [clone_path]

    entries = await _audit_entries_for(run_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.result == "ok"
    assert entry.actor == "seven_of_nine"
    assert "list the files in app/seven_of_nine" in entry.payload_summary
    assert "exit_code=0" in entry.payload_summary
    assert "done" in entry.payload_summary
    assert "diff --git" in entry.payload_summary
    assert f"branch={branch}" in entry.payload_summary
    assert "pushed branch" in entry.payload_summary


async def test_run_agent_mode_task_skips_push_when_diff_is_empty(monkeypatch, tmp_path):
    run_id = "agent-mode-nodiff-test"
    clone_path, calls = _patch_sandbox_run(
        monkeypatch, tmp_path, exit_code=0, stdout="nothing to do\n", stderr="", diff="", pushed=True,
    )

    async with AsyncSessionLocal() as db:
        result = await sandbox_service.run_agent_mode_task(
            db,
            "look around",
            llm_base_url="http://lm8000:1234/v1",
            model_id="qwen-test",
            run_id=run_id,
        )

    assert result["exit_code"] == 0
    assert result["pushed"] is False
    assert result["compare_url"] is None
    assert calls["commit_and_push"] == [], "no changes to commit — _commit_and_push must not be called"

    entries = await _audit_entries_for(run_id)
    assert len(entries) == 1
    assert "push=skipped — no changes" in entries[0].payload_summary


async def test_run_agent_mode_task_tears_down_and_records_failure(monkeypatch, tmp_path):
    run_id = "agent-mode-fail-test"
    clone_path, calls = _patch_sandbox_run(
        monkeypatch, tmp_path, exit_code=1, stdout="", stderr="boom\n", diff="", pushed=True,
    )

    async with AsyncSessionLocal() as db:
        result = await sandbox_service.run_agent_mode_task(
            db,
            "break something",
            llm_base_url="http://lm8000:1234/v1",
            model_id="qwen-test",
            run_id=run_id,
        )

    assert result["exit_code"] == 1
    assert result["pushed"] is False
    assert result["compare_url"] is None
    assert calls["commit_and_push"] == [], "a failed run must never be committed/pushed"
    assert calls["teardown"], "clone must be torn down even when the run fails"

    entries = await _audit_entries_for(run_id)
    assert len(entries) == 1
    assert entries[0].result == "error"
    assert "exit_code=1" in entries[0].payload_summary
    assert "boom" in entries[0].payload_summary
    assert "push=skipped — run failed" in entries[0].payload_summary


# --- DiscordBotService.run_agent_task: acknowledge + background execution ---


class TestRunAgentTask:
    def _make_service(self):
        config = BotConfig(enabled=True, token="test-token")
        return DiscordBotService(config)

    @pytest.mark.asyncio
    async def test_returns_error_when_llm_unavailable(self):
        service = self._make_service()
        # _seven_llm_client is None (not started)
        response = await service.run_agent_task("do something", user_id=123)

        assert response.is_error
        assert "LLM-Service (Seven of Nine) nicht verfügbar" in response.content

    @pytest.mark.asyncio
    async def test_rejects_empty_task(self):
        service = self._make_service()
        service._seven_llm_client = AsyncMock()

        response = await service.run_agent_task("   ", user_id=123)

        assert response.is_error
        assert "unzureichend spezifiziert" in response.content

    @pytest.mark.asyncio
    async def test_acknowledges_immediately_and_schedules_background_run(self):
        service = self._make_service()
        service._seven_llm_client = AsyncMock()

        scheduled = []

        def fake_create_task(coro, name=None):
            scheduled.append((coro, name))
            coro.close()  # never actually run it — just prove it was scheduled
            return AsyncMock()

        import app.discord_bot.service as service_module

        with patch.object(service_module.asyncio, "create_task", side_effect=fake_create_task):
            response = await service.run_agent_task("list files in app/", user_id=123)

        assert not response.is_error
        assert "Auftrag angenommen" in response.content
        assert "agent-mode-" in response.content
        assert len(scheduled) == 1
        assert scheduled[0][1].startswith("seven-agent-task-")


# --- DiscordBotService.chat_as_seven: natural-language "[AGENT: ...]" directive ---


class TestAgentDirectiveInChat:
    """Seven kann Agent Mode direkt aus dem Gespräch heraus auslösen — ohne dass
    Orsox `!agent <auftrag>` tippen muss. Erkennt sie (im LLM, nicht per Regex
    gegen die freie User-Eingabe) einen konkreten Auftragswunsch, markiert sie
    ihre Antwort mit '[AGENT: <auftrag>]' (siehe SEVEN_SYSTEM_PROMPT); der Code
    parst nur dieses feste Format, plant den Lauf real ein (_schedule_agent_run,
    geteilt mit run_agent_task) und liefert Orsox nur ihre natürliche Bestätigung
    — die Marker-Zeile bleibt unsichtbar. Spiegelt exakt das etablierte
    [MEMORY: ...]-Verhalten."""

    def _make_service(self):
        config = BotConfig(enabled=True, token="test-token")
        return DiscordBotService(config)

    @pytest.mark.asyncio
    async def test_chat_schedules_agent_run_when_llm_emits_directive(self):
        service = self._make_service()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=(
                "[AGENT: Liste die Dateien im Verzeichnis app/seven_of_nine auf]\n"
                "Verstanden, ich initiiere die Analyse — Ergebnis folgt."
            )
        )
        service._seven_llm_client = mock_llm

        # _schedule_agent_run (asyncio.create_task + run_id) ist bereits durch
        # TestRunAgentTask abgedeckt — hier interessiert nur, DASS chat_as_seven
        # sie mit dem extrahierten Auftrag aufruft, nicht WIE sie einplant.
        with patch.object(
            DiscordBotService, "_schedule_agent_run", return_value="agent-mode-directive-test"
        ) as mock_schedule:
            response = await service.chat_as_seven(
                "Sieben, schau bitte nach, welche Dateien im seven_of_nine Verzeichnis liegen", user_id=123
            )

        assert not response.is_error
        assert response.content == "Verstanden, ich initiiere die Analyse — Ergebnis folgt."
        assert "[AGENT:" not in response.content
        mock_schedule.assert_called_once_with(
            "Liste die Dateien im Verzeichnis app/seven_of_nine auf", 123
        )

    @pytest.mark.asyncio
    async def test_chat_does_not_schedule_when_llm_omits_directive(self):
        service = self._make_service()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="Was würdest du tun, wenn ich das wollte? Beschreib mir den Auftrag genauer.")
        service._seven_llm_client = mock_llm

        with patch.object(DiscordBotService, "_schedule_agent_run") as mock_schedule:
            response = await service.chat_as_seven("Könntest du grundsätzlich Code schreiben?", user_id=123)

        assert not response.is_error
        assert "[AGENT:" not in response.content
        mock_schedule.assert_not_called()


# --- DiscordBotService._translate_agent_result: relay through Seven's LLM ---


class TestTranslateAgentResult:
    def _make_service(self):
        config = BotConfig(enabled=True, token="test-token")
        return DiscordBotService(config)

    def _result(self, **overrides):
        base = {
            "run_id": "agent-mode-translate-test",
            "exit_code": 0,
            "stdout": "all good\n",
            "stderr": "",
            "diff": "diff --git a/x b/x\n+changed\n",
            "worktree_path": "/tmp/borg-agent-sandbox/agent-mode-translate-test",
            "branch": "agent-mode/agent-mode-translate-test",
            "pushed": False,
            "compare_url": None,
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_translates_raw_result_via_seven_llm(self):
        service = self._make_service()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="Auftrag erledigt — Diff liegt zur Sichtung bereit.")
        service._seven_llm_client = mock_llm

        summary = await service._translate_agent_result("list files", self._result())

        assert summary == "Auftrag erledigt — Diff liegt zur Sichtung bereit."
        mock_llm.chat.assert_called_once()
        messages, system_prompt = mock_llm.chat.call_args.args[:2]
        assert "list files" in messages[0]["content"]
        assert "agent-mode-translate-test" in messages[0]["content"]
        assert "diff --git" in messages[0]["content"]
        assert "pi`-Coding-Agent" in system_prompt or "pi-Coding-Agent" in system_prompt

    @pytest.mark.asyncio
    async def test_includes_push_outcome_in_raw_summary(self):
        service = self._make_service()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="Auftrag erledigt — Branch zur Sichtung gepusht.")
        service._seven_llm_client = mock_llm

        result = self._result(
            branch="agent-mode/push-test",
            pushed=True,
            compare_url="http://gitlab/seven-of-nine/workspace/-/compare/main...agent-mode/push-test",
        )
        await service._translate_agent_result("list files", result)

        messages, _ = mock_llm.chat.call_args.args[:2]
        raw = messages[0]["content"]
        assert "agent-mode/push-test" in raw
        assert "compare/main...agent-mode/push-test" in raw

    @pytest.mark.asyncio
    async def test_includes_no_push_note_when_nothing_was_pushed(self):
        service = self._make_service()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="Auftrag erledigt — keine Änderungen.")
        service._seven_llm_client = mock_llm

        result = self._result(pushed=False, compare_url=None)
        await service._translate_agent_result("look around", result)

        messages, _ = mock_llm.chat.call_args.args[:2]
        raw = messages[0]["content"]
        assert "nichts zu pushen" in raw

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_data_on_llm_error(self):
        service = self._make_service()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=LlmError("Connection refused"))
        service._seven_llm_client = mock_llm

        summary = await service._translate_agent_result("list files", self._result(exit_code=1))

        assert "Übersetzung fehlgeschlagen" in summary
        assert "agent-mode-translate-test" in summary
        assert "exit_code=1" in summary


# --- DiscordBotService._execute_agent_task: end-to-end orchestration (mocked sandbox) ---


class TestExecuteAgentTask:
    def _make_service(self):
        config = BotConfig(enabled=True, token="test-token")
        return DiscordBotService(config)

    @pytest.mark.asyncio
    async def test_delivers_translated_result_via_seven_notifier(self):
        service = self._make_service()
        service._seven_llm_client = AsyncMock()

        fake_result = {
            "run_id": "agent-mode-exec-test",
            "exit_code": 0,
            "stdout": "ok\n",
            "stderr": "",
            "diff": "",
            "worktree_path": "/tmp/x",
        }

        notified = []

        async def fake_notifier(content):
            notified.append(content)

        service.set_seven_notifier(fake_notifier)

        with patch.object(
            __import__("app.agent_sandbox.service", fromlist=["service"]),
            "run_agent_mode_task",
            new=AsyncMock(return_value=fake_result),
        ), patch.object(
            DiscordBotService, "_translate_agent_result", new=AsyncMock(return_value="Übersetzte Antwort")
        ):
            await service._execute_agent_task("agent-mode-exec-test", "do the thing", user_id=123)

        assert notified == ["Übersetzte Antwort"]

    @pytest.mark.asyncio
    async def test_reports_denial_via_seven_notifier(self):
        service = self._make_service()
        service._seven_llm_client = AsyncMock()

        notified = []

        async def fake_notifier(content):
            notified.append(content)

        service.set_seven_notifier(fake_notifier)

        with patch.object(
            __import__("app.agent_sandbox.service", fromlist=["service"]),
            "run_agent_mode_task",
            new=AsyncMock(side_effect=sandbox_service.SkillExecutionDenied("matched deny-list rule 'sudo'")),
        ):
            await service._execute_agent_task("agent-mode-denied-test", "sudo do the thing", user_id=123)

        assert len(notified) == 1
        assert "abgelehnt" in notified[0]
        assert "agent-mode-denied-test" in notified[0]


# --- DiscordBotService.chat_as_seven: development-activity digest in system prompt ---


class TestDevelopmentDigest:
    @pytest.mark.asyncio
    async def test_chat_as_seven_includes_development_digest_in_system_prompt(self):
        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        await service.start()

        async with AsyncSessionLocal() as db:
            await seven_service.record_action(
                db,
                action="agent_mode_run",
                target="agent-mode-digest-test",
                payload_summary="task=list files\nexit_code=0\n--- stdout ---\nfile listing...",
                result="ok",
                run_id="agent-mode-digest-test",
            )
            await locutus_service.record_action(
                db,
                action="skill_execution",
                target="42",
                payload_summary="command=pytest -v\nexit_code=0\n--- stdout ---\nall good",
                result="ok",
                run_id="skill-exec-digest-test",
            )
            db.add(
                ReasoningLog(
                    title="Neuer Heartbeat-Skill",
                    trigger_description="Wiederkehrender Archon-Timeout",
                    proposed_solution="Einen Skill bauen, der den Heartbeat-Workflow neu triggert",
                    expected_outcome="Weniger manuelle Eingriffe bei Timeouts",
                    status="draft",
                )
            )
            await db.commit()

        with patch.object(
            LlmClient, "chat", new_callable=AsyncMock, return_value="Test response"
        ) as mock_chat:
            response = await service.chat_as_seven("Was macht Locutus gerade?", user_id=123)

            assert not response.is_error
            mock_chat.assert_called_once()
            system_prompt = mock_chat.call_args.args[1]
            assert "Deine letzten Agent-Mode-Läufe" in system_prompt
            assert "agent-mode-digest-test" in system_prompt or "list files" in system_prompt
            assert "Locutus' letzte Sandbox-Skill-Läufe" in system_prompt
            assert "pytest -v" in system_prompt
            assert "Locutus' offene Vorschläge" in system_prompt
            assert "Neuer Heartbeat-Skill" in system_prompt

        await service.stop()

    @pytest.mark.asyncio
    async def test_chat_as_seven_omits_digest_section_when_no_activity(self):
        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        await service.start()

        with patch.object(
            LlmClient, "chat", new_callable=AsyncMock, return_value="Test response"
        ) as mock_chat:
            response = await service.chat_as_seven("Hallo Seven", user_id=123)

            assert not response.is_error
            system_prompt = mock_chat.call_args.args[1]
            assert "Aktueller Stand der Entwicklung" not in system_prompt

        await service.stop()


# --- agent_sandbox_service.create_gitlab_repo / _gitlab_auth_args / _gitlab_remote_url ---


class TestCreateGitlabRepo:
    def test_gitlab_remote_url_uses_username_and_repo(self, monkeypatch):
        monkeypatch.setattr(sandbox_service.settings, "seven_gitlab_url", "http://gitlab")
        monkeypatch.setattr(sandbox_service.settings, "seven_gitlab_username", "seven-of-nine")

        assert sandbox_service._gitlab_remote_url("workspace") == "http://gitlab/seven-of-nine/workspace.git"

    def test_gitlab_auth_args_carry_basic_auth_token_only_in_argv(self, monkeypatch):
        import base64

        monkeypatch.setattr(sandbox_service.settings, "seven_gitlab_username", "seven-of-nine")
        monkeypatch.setattr(sandbox_service.settings, "seven_gitlab_token", "s3cr3t-pat")

        args = sandbox_service._gitlab_auth_args()

        # GitLab's git-http-backend authenticates PATs via HTTP Basic
        # (username:token) — Bearer only works against the REST API
        # (verified empirically: Bearer triggers an interactive credential
        # prompt and fails headlessly against the smart-HTTP endpoint).
        expected_basic = base64.b64encode(b"seven-of-nine:s3cr3t-pat").decode()
        assert "-c" in args
        assert f"http.extraHeader=Authorization: Basic {expected_basic}" in args
        # self-signed cert on the internal omnibus instance — verified empirically
        assert "http.sslVerify=false" in args
        # the raw token must appear ONLY base64-encoded inside this argv —
        # never in cleartext, never embedded in a URL
        assert "s3cr3t-pat" not in args
        assert "s3cr3t-pat" not in sandbox_service._gitlab_remote_url("workspace")

    @pytest.mark.asyncio
    async def test_create_gitlab_repo_posts_to_projects_api_with_pat_header(self, monkeypatch):
        monkeypatch.setattr(sandbox_service.settings, "seven_gitlab_url", "http://gitlab")
        monkeypatch.setattr(sandbox_service.settings, "seven_gitlab_token", "s3cr3t-pat")

        captured = {}

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"name": "hello-world", "web_url": "http://gitlab/seven-of-nine/hello-world"}

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                captured["client_kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc_info):
                pass

            async def post(self, url, headers=None, json=None):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                return _FakeResponse()

        monkeypatch.setattr(sandbox_service.httpx, "AsyncClient", _FakeAsyncClient)

        project = await sandbox_service.create_gitlab_repo("hello-world")

        assert project["web_url"] == "http://gitlab/seven-of-nine/hello-world"
        assert captured["url"] == "http://gitlab/api/v4/projects"
        assert captured["headers"] == {"PRIVATE-TOKEN": "s3cr3t-pat"}
        assert captured["json"]["name"] == "hello-world"
        assert captured["json"]["visibility"] == "private"
        # self-signed cert on the internal omnibus instance — verified empirically
        assert captured["client_kwargs"]["verify"] is False


# --- DiscordBotService.chat_as_seven: natural-language "[GITLAB_REPO: ...]" directive ---


class TestGitlabRepoDirective:
    """Spiegelt TestAgentDirectiveInChat für [GITLAB_REPO: <name>]: erkennt Seven
    in der Konversation, dass Orsox ein neues Projekt unter ihrem eigenen
    GitLab-Konto angelegt haben will, markiert ihre Antwort mit
    '[GITLAB_REPO: <name>]' (siehe SEVEN_SYSTEM_PROMPT). Der Code parst nur
    dieses feste Format und ruft create_gitlab_repo direkt auf — anders als
    [AGENT: ...] kein Hintergrund-Lauf, sondern ein einzelner, schneller
    API-Call, daher direkte Antwort statt Notification."""

    def _make_service(self):
        config = BotConfig(enabled=True, token="test-token")
        return DiscordBotService(config)

    async def _gitlab_repo_create_entries(self) -> list[DroneAuditEntry]:
        async with AsyncSessionLocal() as db:
            return list(
                (
                    await db.execute(
                        select(DroneAuditEntry).where(DroneAuditEntry.action == "gitlab_repo_create")
                    )
                )
                .scalars()
                .all()
            )

    @pytest.mark.asyncio
    async def test_chat_creates_repo_when_llm_emits_directive(self):
        service = self._make_service()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=(
                "[GITLAB_REPO: hello-world]\n"
                "Verstanden, ich lege das Repository an."
            )
        )
        service._seven_llm_client = mock_llm

        with patch.object(
            sandbox_service,
            "create_gitlab_repo",
            new=AsyncMock(return_value={"web_url": "http://gitlab/seven-of-nine/hello-world"}),
        ) as mock_create:
            response = await service.chat_as_seven(
                "Sieben, leg bitte ein neues Projekt namens hello-world an", user_id=123
            )

        assert not response.is_error
        assert response.content == "Verstanden, ich lege das Repository an."
        assert "[GITLAB_REPO:" not in response.content
        mock_create.assert_called_once_with("hello-world")

        entries = await self._gitlab_repo_create_entries()
        assert len(entries) == 1
        assert entries[0].target == "hello-world"
        assert entries[0].result == "ok"
        assert "hello-world" in entries[0].payload_summary

    @pytest.mark.asyncio
    async def test_chat_does_not_create_repo_when_llm_omits_directive(self):
        service = self._make_service()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value="Was würdest du tun, wenn ich grundsätzlich ein neues Projekt bräuchte?"
        )
        service._seven_llm_client = mock_llm

        with patch.object(sandbox_service, "create_gitlab_repo", new=AsyncMock()) as mock_create:
            response = await service.chat_as_seven("Könntest du grundsätzlich Repos anlegen?", user_id=123)

        assert not response.is_error
        assert "[GITLAB_REPO:" not in response.content
        mock_create.assert_not_called()
        assert await self._gitlab_repo_create_entries() == []

    @pytest.mark.asyncio
    async def test_chat_reports_error_and_records_audit_when_repo_creation_fails(self):
        service = self._make_service()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value="[GITLAB_REPO: borked]\nVerstanden, ich lege das Repository an."
        )
        service._seven_llm_client = mock_llm

        with patch.object(
            sandbox_service, "create_gitlab_repo", new=AsyncMock(side_effect=RuntimeError("HTTP 422 Unprocessable"))
        ):
            response = await service.chat_as_seven("Leg bitte ein Projekt namens borked an", user_id=123)

        assert response.is_error
        assert "borked" in response.content

        entries = await self._gitlab_repo_create_entries()
        assert len(entries) == 1
        assert entries[0].target == "borked"
        assert entries[0].result == "error"
        assert "HTTP 422" in entries[0].payload_summary
