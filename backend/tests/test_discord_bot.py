"""
Pure Unit Tests für Locutus Discord-Bot.

Testing von Command-Parsing und Handler-Logik.
Kein FastAPI-Stack nötig — pure Unit-Tests.
"""

import pytest
from app.discord_bot.handlers import CommandHandler
from app.discord_bot.models import Command, CommandType, Response, TaskEvent, TaskEventType, TaskNotification


class TestCommandParser:
    """Tests für Command-Parsing."""

    def setup_method(self):
        self.handler = CommandHandler()

    def test_prefix_command(self):
        """Test: !chat Hallo wird als Chat-Command geparsed."""
        cmd = self.handler.parse("!chat Hallo", user_id=123, channel_id=456)
        assert cmd is not None
        assert cmd.command_type == CommandType.CHAT
        assert cmd.args == ["Hallo"]
        assert cmd.user_id == 123
        assert cmd.channel_id == 456
        assert not cmd.is_mention

    def test_mention_command(self):
        """Test: @Locutus status wird als Status-Command geparsed."""
        cmd = self.handler.parse("@Locutus status", user_id=123, channel_id=456)
        assert cmd is not None
        assert cmd.command_type == CommandType.STATUS
        assert cmd.is_mention

    def test_no_command(self):
        """Test: Nachricht ohne Prefix/@ wird als None zurückgegeben."""
        cmd = self.handler.parse("Hallo Locutus", user_id=123, channel_id=456)
        assert cmd is None

    def test_unknown_command_becomes_chat(self):
        """Test: Unbekannter Command wird als Chat behandelt."""
        cmd = self.handler.parse("!unknown arg", user_id=123, channel_id=456)
        assert cmd is not None
        assert cmd.command_type == CommandType.CHAT

    def test_help_command(self):
        """Test: !help wird als Help-Command geparsed."""
        cmd = self.handler.parse("!help", user_id=123, channel_id=456)
        assert cmd is not None
        assert cmd.command_type == CommandType.HELP

    def test_search_command(self):
        """Test: !search query wird als Search-Command geparsed."""
        cmd = self.handler.parse("!search test query", user_id=123, channel_id=456)
        assert cmd is not None
        assert cmd.command_type == CommandType.SEARCH
        assert cmd.args == ["test query"]

    def test_case_insensitive_prefix(self):
        """Test: Prefix ist case-insensitive."""
        cmd1 = self.handler.parse("!chat Hallo", user_id=123, channel_id=456)
        cmd2 = self.handler.parse("!CHAT Hallo", user_id=123, channel_id=456)
        assert cmd1 is not None
        assert cmd2 is not None
        assert cmd1.command_type == cmd2.command_type

    def test_create_note_command(self):
        """Test: !note content wird als CreateNote-Command geparsed."""
        cmd = self.handler.parse("!note Test content", user_id=123, channel_id=456)
        assert cmd is not None
        assert cmd.command_type == CommandType.CREATE_NOTE
        assert cmd.args == ["Test content"]

    def test_shortcut_commands(self):
        """Test: Shortcut-Commands (c, s, st, h) werden erkannt."""
        cmd_c = self.handler.parse("!c Hallo", user_id=123, channel_id=456)
        assert cmd_c.command_type == CommandType.CHAT

        cmd_s = self.handler.parse("!s test", user_id=123, channel_id=456)
        assert cmd_s.command_type == CommandType.SEARCH

        cmd_st = self.handler.parse("!st", user_id=123, channel_id=456)
        assert cmd_st.command_type == CommandType.STATUS

        cmd_h = self.handler.parse("!h", user_id=123, channel_id=456)
        assert cmd_h.command_type == CommandType.HELP


class TestCommandHandler:
    """Tests für Command-Dispatch."""

    def setup_method(self):
        self.handler = CommandHandler()

    @pytest.mark.asyncio
    async def test_help_response(self):
        """Test: Help-Command gibt Help-Text zurück."""
        cmd = Command(
            content="help",
            user_id=123,
            channel_id=456,
            command_type=CommandType.HELP,
        )
        response = await self.handler.handle(cmd)
        assert response is not None
        assert "Verfügbare Commands" in response.content
        assert not response.is_error

    @pytest.mark.asyncio
    async def test_chat_response(self):
        """Test: Chat-Command gibt Chat-Antwort zurück (ohne Service)."""
        cmd = Command(
            content="test message",
            user_id=123,
            channel_id=456,
            command_type=CommandType.CHAT,
            args=["test message"],
        )
        response = await self.handler.handle(cmd)
        assert response is not None
        assert "Service nicht verfügbar" in response.content
        assert response.is_error

    @pytest.mark.asyncio
    async def test_status_response(self):
        """Test: Status-Command gibt Status-Antwort zurück (ohne Service)."""
        cmd = Command(
            content="status",
            user_id=123,
            channel_id=456,
            command_type=CommandType.STATUS,
        )
        response = await self.handler.handle(cmd)
        assert response is not None
        assert "Service nicht verfügbar" in response.content
        assert response.is_error

    @pytest.mark.asyncio
    async def test_search_response_without_service(self):
        """Test: Search-Handler ohne Service gibt Error zurück."""
        cmd = Command(
            content="test query",
            user_id=123,
            channel_id=456,
            command_type=CommandType.SEARCH,
            args=["test query"],
        )
        response = await self.handler.handle(cmd)
        assert response is not None
        assert "Service nicht verfügbar" in response.content
        assert response.is_error

    @pytest.mark.asyncio
    async def test_error_response(self):
        """Test: Unbekannter Command gibt Error zurück."""
        # Simuliere nicht-registrierten Handler
        response = Response(
            content="Unbekannter Command: unknown",
            is_error=True,
        )
        assert response.is_error
        assert "Unbekannter Command" in response.content


class TestTaskNotification:
    """Tests für Task-Notification-Formatierung."""

    def test_started_notification(self):
        """Test: Task-Start wird korrekt formatiert."""
        event = TaskEvent(
            type=TaskEventType.TASK_STARTED,
            task_id=1,
            task_name="test-task",
            run_id=42,
            timestamp="2026-06-03T16:00:00Z",
        )
        notification = TaskNotification(event=event)
        formatted = notification.format()
        assert "▶" in formatted
        assert "test-task" in formatted
        assert "gestartet" in formatted

    def test_completed_notification(self):
        """Test: Task-Fertig wird korrekt formatiert."""
        event = TaskEvent(
            type=TaskEventType.TASK_COMPLETED,
            task_id=1,
            task_name="test-task",
            run_id=42,
            timestamp="2026-06-03T16:00:00Z",
            duration_ms=5000,
        )
        notification = TaskNotification(event=event)
        formatted = notification.format()
        assert "✓" in formatted
        assert "test-task" in formatted
        assert "fertig" in formatted
        assert "5s" in formatted

    def test_failed_notification(self):
        """Test: Task-Fehler wird korrekt formatiert."""
        event = TaskEvent(
            type=TaskEventType.TASK_FAILED,
            task_id=1,
            task_name="test-task",
            run_id=42,
            timestamp="2026-06-03T16:00:00Z",
            error="Connection timeout",
        )
        notification = TaskNotification(event=event)
        formatted = notification.format()
        assert "✗" in formatted
        assert "test-task" in formatted
        assert "fehlgeschlagen" in formatted
        assert "Connection timeout" in formatted

    def test_failed_notification_no_error(self):
        """Test: Task-Fehler ohne Error-Message."""
        event = TaskEvent(
            type=TaskEventType.TASK_FAILED,
            task_id=1,
            task_name="test-task",
            run_id=42,
            timestamp="2026-06-03T16:00:00Z",
        )
        notification = TaskNotification(event=event)
        formatted = notification.format()
        assert "✗" in formatted
        assert "fehlgeschlagen" in formatted
        assert " — " not in formatted

    def test_completed_notification_no_duration(self):
        """Test: Task-Fertig ohne Duration."""
        event = TaskEvent(
            type=TaskEventType.TASK_COMPLETED,
            task_id=1,
            task_name="test-task",
            run_id=42,
            timestamp="2026-06-03T16:00:00Z",
        )
        notification = TaskNotification(event=event)
        formatted = notification.format()
        assert "✓" in formatted
        assert "?" in formatted


class TestLlmConfig:
    """Tests für LlmConfig."""

    def test_default_config(self):
        """Test: Default Config hat erwartete Werte."""
        from app.discord_bot.config import LlmConfig
        
        config = LlmConfig()
        assert config.base_url == "http://localhost:1234/v1"
        assert config.model_id == "mellum2-12b-a2.5b-instruct"
        assert config.context_window == 131072
        assert config.max_tokens == 2048
        assert config.temperature == 0.3


class TestBotConfig:
    """Tests für BotConfig."""

    def test_default_config(self):
        """Test: Default Config ist deaktiviert."""
        from app.discord_bot.config import BotConfig
        
        config = BotConfig()
        assert config.enabled is False
        assert config.token == ""
        assert config.prefix == "!"
        assert config.mention_prefix == "@Locutus"

    def test_validation_missing_token(self):
        """Test: Config ohne Token bei enabled=True gibt Error."""
        from app.discord_bot.config import BotConfig
        
        config = BotConfig(enabled=True, token="")
        errors = config.validate()
        assert len(errors) == 1
        assert "DISCORD_BOT_TOKEN" in errors[0]

    def test_validation_valid(self):
        """Test: Valid Config gibt leere Errors."""
        from app.discord_bot.config import BotConfig
        
        config = BotConfig(enabled=True, token="test-token")
        errors = config.validate()
        assert errors == []


class TestResponse:
    """Tests für Response-Formatierung."""

    def test_success_response_format(self):
        """Test: Erfolgsantwort wird korrekt formatiert."""
        response = Response(content="Test message")
        formatted = response.format()
        assert "[ℹ INFO]" in formatted
        assert "Test message" in formatted

    def test_error_response_format(self):
        """Test: Fehlerantwort wird korrekt formatiert."""
        response = Response(content="Error message", is_error=True)
        formatted = response.format()
        assert "[⚠ ERROR]" in formatted
        assert "Error message" in formatted


class TestBotClientInitialization:
    """Tests für BotClient-Initialisierung."""

    def test_client_creates_with_config_and_service(self):
        """Test: BotClient lässt sich mit Config und Service instanziieren."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        assert client is not None
        assert client._config == config
        assert client._service == service

    def test_bot_has_message_intents(self):
        """Test: BotClient hat message_content Intent aktiviert."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        assert client.intents.message_content is True
        assert client.intents.guilds is True
        assert client.intents.members is True

    def test_bot_has_no_help_command(self):
        """Test: BotClient verwendet keinen discord.py Help-Command."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        assert client.help_command is None


class TestCommandHandlerWithService:
    """Tests für Command-Dispatch mit Service-Referenz (Slice 2)."""

    @pytest.mark.asyncio
    async def test_chat_without_service(self):
        """Test: Chat-Handler ohne Service gibt Error zurück."""
        from app.discord_bot.handlers import CommandHandler
        from app.discord_bot.models import Command, CommandType

        handler = CommandHandler(service=None)
        cmd = Command(
            content="test message",
            user_id=123,
            channel_id=456,
            command_type=CommandType.CHAT,
            args=["test message"],
        )
        response = await handler.handle(cmd)
        assert response.is_error
        assert "Service nicht verfügbar" in response.content


class TestTaskEventListener:
    """Tests für TaskEventListener."""

    @pytest.mark.asyncio
    async def test_listener_starts_and_stops(self):
        """Test: TaskEventListener lässt sich starten und stoppen."""
        from app.discord_bot.listener import TaskEventListener

        callback_called = False

        async def mock_callback(content: str) -> None:
            nonlocal callback_called
            callback_called = True

        listener = TaskEventListener(mock_callback)
        await listener.start()
        await listener.stop()

        # Listener sollte nach Stop nicht mehr laufen
        assert not listener._running

    @pytest.mark.asyncio
    async def test_listener_processes_started_event(self):
        """Test: TaskEventListener verarbeitet TASK_STARTED Event."""
        from app.discord_bot.listener import TaskEventListener
        from app.discord_bot.models import TaskEventType

        received = []

        async def mock_callback(content: str) -> None:
            received.append(content)

        listener = TaskEventListener(mock_callback)
        await listener.start()

        event = {
            "type": TaskEventType.TASK_STARTED.value,
            "task_id": 1,
            "task_name": "test-task",
            "run_id": 42,
            "timestamp": "2026-06-03T16:00:00Z",
        }
        await listener._process_event(event)

        assert len(received) == 1
        assert "test-task" in received[0]
        assert "gestartet" in received[0]

        await listener.stop()

    @pytest.mark.asyncio
    async def test_listener_processes_completed_event(self):
        """Test: TaskEventListener verarbeitet TASK_COMPLETED Event."""
        from app.discord_bot.listener import TaskEventListener
        from app.discord_bot.models import TaskEventType

        received = []

        async def mock_callback(content: str) -> None:
            received.append(content)

        listener = TaskEventListener(mock_callback)
        await listener.start()

        event = {
            "type": TaskEventType.TASK_COMPLETED.value,
            "task_id": 1,
            "task_name": "test-task",
            "run_id": 42,
            "timestamp": "2026-06-03T16:00:00Z",
            "duration_ms": 5000,
        }
        await listener._process_event(event)

        assert len(received) == 1
        assert "fertig" in received[0]

        await listener.stop()

    @pytest.mark.asyncio
    async def test_listener_processes_failed_event(self):
        """Test: TaskEventListener verarbeitet TASK_FAILED Event."""
        from app.discord_bot.listener import TaskEventListener
        from app.discord_bot.models import TaskEventType

        received = []

        async def mock_callback(content: str) -> None:
            received.append(content)

        listener = TaskEventListener(mock_callback)
        await listener.start()

        event = {
            "type": TaskEventType.TASK_FAILED.value,
            "task_id": 1,
            "task_name": "test-task",
            "run_id": 42,
            "timestamp": "2026-06-03T16:00:00Z",
            "error": "Connection timeout",
        }
        await listener._process_event(event)

        assert len(received) == 1
        assert "fehlgeschlagen" in received[0]
        assert "Connection timeout" in received[0]

        await listener.stop()

    @pytest.mark.asyncio
    async def test_listener_ignores_unknown_event_type(self):
        """Test: TaskEventListener ignoriert unbekannte Event-Typen."""
        from app.discord_bot.listener import TaskEventListener

        received = []

        async def mock_callback(content: str) -> None:
            received.append(content)

        listener = TaskEventListener(mock_callback)
        await listener.start()

        event = {
            "type": "unknown_event_type",
            "task_id": 1,
            "task_name": "test-task",
            "run_id": 42,
            "timestamp": "2026-06-03T16:00:00Z",
        }
        await listener._process_event(event)

        assert len(received) == 0

        await listener.stop()


class TestNotificationCallbackFlow:
    """Tests für den Notification-Callback-Flow (SSE → Listener → Discord)."""

    @pytest.mark.asyncio
    async def test_notification_callback_receives_formatted_message(self):
        """Test: Notification-Callback empfängt formatierte Nachricht."""
        from app.discord_bot.listener import TaskEventListener
        from app.discord_bot.models import TaskEventType

        received_contents = []

        async def mock_callback(content: str) -> None:
            received_contents.append(content)

        listener = TaskEventListener(mock_callback)
        await listener.start()

        # Simuliere ein Task-Fehler-Event wie es vom Scheduler kommt
        event = {
            "type": TaskEventType.TASK_FAILED.value,
            "task_id": 5,
            "task_name": "borg-queen",
            "run_id": 359,
            "timestamp": "2026-06-03T17:00:00Z",
            "error": "Model resolution failed",
        }
        await listener._process_event(event)

        assert len(received_contents) == 1
        notification = received_contents[0]
        assert "borg-queen" in notification
        assert "fehlgeschlagen" in notification
        assert "359" in notification
        assert "Model resolution failed" in notification

        await listener.stop()


class TestBotClientPrefixResolver:
    """Tests für BotClient Prefix-Resolver."""

    def test_prefix_resolver_returns_prefix_on_short_mention(self):
        """Test: Prefix-Resolver erkennt <@!ID> Format."""
        from unittest.mock import PropertyMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        class MockMessage:
            content = "<@!123456> hello"

        # Mock client.user (read-only property from discord.py)
        mock_user = type("MockUser", (), {"id": 123456})()

        with patch.object(type(client), "user", new_callable=PropertyMock, return_value=mock_user):
            client._ready_event.set()
            result = BotClient._prefix_resolver(client, MockMessage())
            assert result == "!"

    def test_prefix_resolver_returns_prefix_on_long_mention(self):
        """Test: Prefix-Resolver erkennt <@ID> Format."""
        from unittest.mock import PropertyMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        class MockMessage:
            content = "<@123456> hello"

        mock_user = type("MockUser", (), {"id": 123456})()

        with patch.object(type(client), "user", new_callable=PropertyMock, return_value=mock_user):
            result = BotClient._prefix_resolver(client, MockMessage())
            assert result == "!"

    def test_prefix_resolver_returns_none_for_other_user(self):
        """Test: Prefix-Resolver gibt None zurück für andere User."""
        from unittest.mock import PropertyMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        class MockMessage:
            content = "<@!999999> hello"

        mock_user = type("MockUser", (), {"id": 123456})()

        with patch.object(type(client), "user", new_callable=PropertyMock, return_value=mock_user):
            result = BotClient._prefix_resolver(client, MockMessage())
            assert result is None


class TestServiceStatus:
    """Tests für DiscordBotService.status() (Slice 3)."""

    @pytest.mark.asyncio
    async def test_status_returns_task_count(self):
        """Test: status() gibt Anzahl der aktiven Tasks zurück."""
        from unittest.mock import AsyncMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.task_automation.models import Task

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Erstelle einen Test-Task in der DB (autouse setup_db Fixture)
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            task = Task(name="test-task", task_type="shell", command="echo hi", is_enabled=True)
            db.add(task)
            await db.commit()
            await db.refresh(task)

        # Mock sync_and_get_health at the source module
        mock_health = AsyncMock(return_value={"online": True, "cached": False})
        with patch("app.archon_system.service.sync_and_get_health", mock_health):
            response = await service.status()

        assert not response.is_error
        assert "Status:" in response.content
        assert "Tasks aktiv: 1" in response.content
        assert "Archon: online" in response.content

    @pytest.mark.asyncio
    async def test_status_shows_archon_online(self):
        """Test: status() zeigt Archon: online wenn Archon erreichbar."""
        from unittest.mock import AsyncMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        with patch(
            "app.archon_system.service.sync_and_get_health",
            new_callable=AsyncMock,
            return_value={"online": True, "cached": False},
        ):
            response = await service.status()

        assert "Archon: online" in response.content

    @pytest.mark.asyncio
    async def test_status_shows_archon_offline(self):
        """Test: status() zeigt Archon: offline wenn Archon nicht erreichbar."""
        from unittest.mock import AsyncMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        with patch(
            "app.archon_system.service.sync_and_get_health",
            new_callable=AsyncMock,
            return_value={"online": False, "cached": True},
        ):
            response = await service.status()

        assert "Archon: offline" in response.content

    @pytest.mark.asyncio
    async def test_status_shows_archon_on_health_error(self):
        """Test: status() zeigt Archon: offline bei Health-Exception."""
        from unittest.mock import AsyncMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        with patch(
            "app.archon_system.service.sync_and_get_health",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            response = await service.status()

        assert "Archon: offline" in response.content

    @pytest.mark.asyncio
    async def test_status_empty_db(self):
        """Test: status() funktioniert mit leerer DB."""
        from unittest.mock import AsyncMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        with patch(
            "app.archon_system.service.sync_and_get_health",
            new_callable=AsyncMock,
            return_value={"online": True, "cached": False},
        ):
            response = await service.status()

        assert not response.is_error
        assert "Status:" in response.content
        assert "Tasks aktiv: 0" in response.content
        assert "Runs aktiv: 0" in response.content
        assert "Archon: online" in response.content
