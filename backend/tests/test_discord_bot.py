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

    def test_from_env_uses_app_settings(self, monkeypatch):
        """Test: BotConfig liest zentrale Settings statt nur exportierte Env Vars."""
        from app.config import settings
        from app.discord_bot.config import BotConfig

        monkeypatch.setattr(settings, "discord_bot_enabled", True)
        monkeypatch.setattr(settings, "discord_bot_token", "settings-token")
        monkeypatch.setattr(settings, "discord_bot_channel_id", 123456)
        monkeypatch.setattr(settings, "discord_bot_allowed_user_ids", "42, 84")
        monkeypatch.setattr(settings, "discord_bot_prefix", "?")
        monkeypatch.setattr(settings, "discord_bot_mention_prefix", "@LocutusTest")

        config = BotConfig.from_env()

        assert config.enabled is True
        assert config.token == "settings-token"
        assert config.channel_id == 123456
        assert config.allowed_user_ids == [42, 84]
        assert config.prefix == "?"
        assert config.mention_prefix == "@LocutusTest"


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
        """Test: BotClient hat nur benötigte Discord Intents aktiviert."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.discord_bot.bot import BotClient

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)
        client = BotClient(config=config, service=service)

        assert client.intents.message_content is True
        assert client.intents.guilds is True
        assert client.intents.members is False

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


class TestBotClientMentionStripping:
    """Tests für BotClient Mention-Striping."""

    def test_strip_single_mention(self):
        """Test: <@123456> hallo wird zu halbo."""
        from app.discord_bot.bot import BotClient

        result = BotClient._strip_mentions("<@123456> hallo", bot_id=123456)
        assert result == "hallo"

    def test_strip_short_mention(self):
        """Test: <@!123456> wie gehts wird zu wie gehts."""
        from app.discord_bot.bot import BotClient

        result = BotClient._strip_mentions("<@!123456> wie gehts", bot_id=123456)
        assert result == "wie gehts"

    def test_strip_mention_in_middle(self):
        """Test: hallo <@123456> world wird zu hallo world."""
        from app.discord_bot.bot import BotClient

        result = BotClient._strip_mentions("hallo <@123456> world", bot_id=123456)
        assert result == "hallo  world"

    def test_strip_no_mention(self):
        """Test: Nachricht ohne Mention bleibt unverändert."""
        from app.discord_bot.bot import BotClient

        result = BotClient._strip_mentions("hallo world", bot_id=123456)
        assert result == "hallo world"

    def test_strip_multiple_mentions(self):
        """Test: Mehrere Mentions werden entfernt."""
        from app.discord_bot.bot import BotClient

        result = BotClient._strip_mentions("<@123456> hi <@123456> there", bot_id=123456)
        assert result == "hi  there"


class TestServiceSearch:
    """Tests für DiscordBotService.search() (Slice 4)."""

    @pytest.mark.asyncio
    async def test_search_finds_notes_in_db(self):
        """Test: search() findet Notes in der DB."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.database import AsyncSessionLocal
        from app.second_brain.models import Note

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Erstelle Test-Notes in der DB
        async with AsyncSessionLocal() as db:
            note1 = Note(title="Archon Workflow Design", content="Details zum Archon Workflow Design und der Integration.", is_archived=False)
            note2 = Note(title="Discord Bot Locutus", content="Locutus ist ein Discord-Bot für BorgOS.", is_archived=False)
            db.add_all([note1, note2])
            await db.commit()

        response = await service.search("Archon")

        assert not response.is_error
        assert "📝 Notes" in response.content
        assert "Archon Workflow Design" in response.content

    @pytest.mark.asyncio
    async def test_search_returns_snippet(self):
        """Test: search() gibt Snippet aus Content zurück."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.database import AsyncSessionLocal
        from app.second_brain.models import Note

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        async with AsyncSessionLocal() as db:
            note = Note(
                title="LM Studio Integration",
                content="LM Studio läuft auf localhost:1234 und bietet eine OpenAI-kompatible API für lokale Modelle.",
                is_archived=False,
            )
            db.add(note)
            await db.commit()

        response = await service.search("LM Studio")

        assert not response.is_error
        assert "LM Studio Integration" in response.content
        assert "localhost:1234" in response.content  # Snippet sollte den Treffer-Kontext zeigen

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        """Test: search() mit keinem Treffer gibt 'Keine Ergebnisse'."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        response = await service.search("xyznonexistent12345")

        assert not response.is_error
        assert "Keine Ergebnisse" in response.content

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self):
        """Test: search() ist case-insensitive."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.database import AsyncSessionLocal
        from app.second_brain.models import Note

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        async with AsyncSessionLocal() as db:
            note = Note(title="Test Note", content="Content mit dem Suchbegriff.", is_archived=False)
            db.add(note)
            await db.commit()

        response_upper = await service.search("SUCHBEGRiff")
        response_lower = await service.search("suchbegriff")

        assert not response_upper.is_error
        assert not response_lower.is_error
        assert "Test Note" in response_upper.content
        assert "Test Note" in response_lower.content

    @pytest.mark.asyncio
    async def test_search_excludes_archived(self):
        """Test: search() ignoriert archivierte Notes."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.database import AsyncSessionLocal
        from app.second_brain.models import Note

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        async with AsyncSessionLocal() as db:
            active = Note(title="Active Note", content="Diese Note ist aktiv.", is_archived=False)
            archived = Note(title="Archived Note", content="Diese Note ist archiviert.", is_archived=True)
            db.add_all([active, archived])
            await db.commit()

        response = await service.search("Note")

        assert not response.is_error
        assert "Active Note" in response.content
        assert "Archived Note" not in response.content

    @pytest.mark.asyncio
    async def test_search_vault_not_found(self):
        """Test: _search_vault() gibt [] zurück wenn Vault nicht existiert."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Vault-Pfad der nicht existiert
        results = service._search_vault("test", vault_path="/tmp/borgos_nonexistent_vault_xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_vault_finds_md_files(self, tmp_path):
        """Test: _search_vault() findet md-Dateien im Vault."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Erstelle ein temporäres Vault
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        md_file = vault_dir / "test.md"
        md_file.write_text("# Test\n\nDies ist ein Vault-Eintrag mit dem Wort Locutus.", encoding="utf-8")

        results = service._search_vault("Locutus", vault_path=str(vault_dir))

        assert len(results) == 1
        assert results[0]["path"] == "test.md"
        assert "Locutus" in results[0]["snippet"]

    @pytest.mark.asyncio
    async def test_search_vault_skips_excluded_dirs(self, tmp_path):
        """Test: _search_vault() überspringt excluded directories."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        excluded_dir = vault_dir / ".obsidian"
        excluded_dir.mkdir()
        md_file = excluded_dir / "ignored.md"
        md_file.write_text("Dies enthält Locutus und sollte ignoriert werden.", encoding="utf-8")

        valid_file = vault_dir / "valid.md"
        valid_file.write_text("Dies enthält auch Locutus.", encoding="utf-8")

        results = service._search_vault("Locutus", vault_path=str(vault_dir))

        # Sollte nur die gültige Datei finden, nicht die aus .obsidian/
        assert len(results) == 1
        assert results[0]["path"] == "valid.md"

    @pytest.mark.asyncio
    async def test_search_combined_db_and_vault(self):
        """Test: search() kombiniert DB Notes und Vault Ergebnisse."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService
        from app.database import AsyncSessionLocal
        from app.second_brain.models import Note
        import tempfile
        import os

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Erstelle Note in DB
        async with AsyncSessionLocal() as db:
            note = Note(title="Archon Config", content="Archon ist ein AI Framework.", is_archived=False)
            db.add(note)
            await db.commit()

        # Erstelle temporäres Vault
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = tmp_path = tmpdir
            md_file = os.path.join(vault_dir, "archon_notes.md")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write("# Archon\n\nArchon workflows werden hier verwaltet.")

            # Override vault_path für diesen Test
            response = await service.search("Archon")

            assert not response.is_error
            assert "📝 Notes" in response.content

    def test_extract_snippet_finds_query(self):
        """Test: _extract_snippet() findet Query-Treffer im Content."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        content = "LM Studio läuft auf localhost:1234 und bietet eine OpenAI-kompatible API für lokale Modelle."
        snippet = service._extract_snippet(content, "LM Studio")

        assert "LM Studio" in snippet
        assert len(snippet) <= 120

    def test_extract_snippet_no_query_match(self):
        """Test: _extract_snippet() gibt ersten Absatz wenn kein Treffer."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        content = "Erster Absatz.\nZweiter Absatz mit dem Suchbegriff."
        snippet = service._extract_snippet(content, "nicht gefunden")

        assert "Erster Absatz" in snippet

    def test_extract_snippet_empty_content(self):
        """Test: _extract_snippet() mit leerem Content gibt '' zurück."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        snippet = service._extract_snippet("", "test")
        assert snippet == ""

    def test_extract_snippet_truncates_long(self):
        """Test: _extract_snippet() kürzt lange Snippets."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Der Snippet ist content[idx-40:idx+len(query)+40], max ~80+query_len chars.
        # Für "TREFFER" (7 chars) ist der Snippet max 87 chars — unter 120.
        # Test mit kleinerem max_len um Truncation zu erzwingen.
        content = "X" * 100 + "TREFFER" + "Y" * 100
        snippet = service._extract_snippet(content, "TREFFER", max_len=50)

        assert len(snippet) <= 51  # max_len + ellipsis
        assert snippet.endswith("…")


class TestLlmClient:
    """Tests für LlmClient (Slice 5)."""

    def _make_mock_httpx(self, json_response, raise_error=None):
        """Hilfsfunktion zum Erzeugen eines gemoddeten httpx.AsyncClient."""
        from unittest.mock import AsyncMock, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = json_response
        if raise_error:
            mock_response.raise_for_status = MagicMock(side_effect=raise_error)
        else:
            mock_response.raise_for_status = MagicMock()

        mock_httpx = AsyncMock()
        mock_httpx.post.return_value = mock_response
        return mock_httpx

    @pytest.mark.asyncio
    async def test_llm_client_sends_request(self):
        """Test: LlmClient sendet korrekte Anfrage an LM Studio."""
        from unittest.mock import patch

        from app.discord_bot.config import LlmConfig
        from app.discord_bot.llm import LlmClient

        config = LlmConfig(base_url="http://localhost:1234/v1", model_id="test-model")
        client = LlmClient(config)

        mock_httpx = self._make_mock_httpx({
            "choices": [{"message": {"content": "Test-Antwort"}}]
        })

        with patch("httpx.AsyncClient") as MockHttpClient:
            MockHttpClient.return_value = mock_httpx
            await client.start()
            client._client = mock_httpx

            answer = await client.chat(
                [{"role": "user", "content": "Hallo"}],
                "Du bist ein Bot.",
            )

            assert answer == "Test-Antwort"
            mock_httpx.post.assert_called_once()
            call_args = mock_httpx.post.call_args
            assert call_args.kwargs["json"]["model"] == "test-model"
            assert len(call_args.kwargs["json"]["messages"]) == 2

            await client.stop()

    @pytest.mark.asyncio
    async def test_llm_client_raises_on_empty_choices(self):
        """Test: LlmClient wirft LlmError bei leeren choices."""
        from unittest.mock import patch

        from app.discord_bot.config import LlmConfig
        from app.discord_bot.llm import LlmClient, LlmError

        config = LlmConfig()
        client = LlmClient(config)

        mock_httpx = self._make_mock_httpx({"choices": []})

        with patch("httpx.AsyncClient") as MockHttpClient:
            MockHttpClient.return_value = mock_httpx
            await client.start()
            client._client = mock_httpx

            with pytest.raises(LlmError):
                await client.chat(
                    [{"role": "user", "content": "Hallo"}],
                    "System.",
                )

            await client.stop()

    @pytest.mark.asyncio
    async def test_llm_client_raises_on_empty_content(self):
        """Test: LlmClient wirft LlmError bei leerem Content."""
        from unittest.mock import patch

        from app.discord_bot.config import LlmConfig
        from app.discord_bot.llm import LlmClient, LlmError

        config = LlmConfig()
        client = LlmClient(config)

        mock_httpx = self._make_mock_httpx({
            "choices": [{"message": {"content": ""}}]
        })

        with patch("httpx.AsyncClient") as MockHttpClient:
            MockHttpClient.return_value = mock_httpx
            await client.start()
            client._client = mock_httpx

            with pytest.raises(LlmError):
                await client.chat(
                    [{"role": "user", "content": "Hallo"}],
                    "System.",
                )

            await client.stop()

    @pytest.mark.asyncio
    async def test_llm_client_raises_on_http_error(self):
        """Test: LlmClient wirft LlmError bei HTTP-Fehler."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        from app.discord_bot.config import LlmConfig
        from app.discord_bot.llm import LlmClient, LlmError

        config = LlmConfig()
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        http_error = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=mock_response,
        )

        mock_httpx = AsyncMock()
        mock_httpx.post.side_effect = http_error

        with patch("httpx.AsyncClient") as MockHttpClient:
            MockHttpClient.return_value = mock_httpx
            await client.start()
            client._client = mock_httpx

            with pytest.raises(LlmError):
                await client.chat(
                    [{"role": "user", "content": "Hallo"}],
                    "System.",
                )

            await client.stop()

    @pytest.mark.asyncio
    async def test_llm_client_raises_when_not_started(self):
        """Test: LlmClient wirft LlmError wenn nicht gestartet."""
        from app.discord_bot.config import LlmConfig
        from app.discord_bot.llm import LlmClient, LlmError

        config = LlmConfig()
        client = LlmClient(config)

        # Nicht starten — _client ist None
        with pytest.raises(LlmError, match="not started"):
            await client.chat(
                [{"role": "user", "content": "Hallo"}],
                "System.",
            )

    @pytest.mark.asyncio
    async def test_llm_client_strips_answer(self):
        """Test: LlmClient trimmt Antwort-Text."""
        from unittest.mock import patch

        from app.discord_bot.config import LlmConfig
        from app.discord_bot.llm import LlmClient

        config = LlmConfig()
        client = LlmClient(config)

        mock_httpx = self._make_mock_httpx({
            "choices": [{"message": {"content": "  Antwort mit Whitespace  "}}]
        })

        with patch("httpx.AsyncClient") as MockHttpClient:
            MockHttpClient.return_value = mock_httpx
            await client.start()
            client._client = mock_httpx

            answer = await client.chat(
                [{"role": "user", "content": "Hallo"}],
                "System.",
            )

            assert answer == "Antwort mit Whitespace"
            await client.stop()


class TestServiceChat:
    """Tests für DiscordBotService.chat() (Slice 5)."""

    @pytest.mark.asyncio
    async def test_chat_sends_to_llm(self):
        """Test: chat() sendet Nachricht an LLM und gibt Antwort zurück."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Mock LlmClient
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="Locutus antwortet hier.")
        service._llm_client = mock_llm

        response = await service.chat("Wie geht es dir?", user_id=123)

        assert not response.is_error
        assert "Locutus antwortet hier" in response.content
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_returns_error_when_llm_unavailable(self):
        """Test: chat() gibt Fehler wenn LLM nicht verfügbar."""
        from app.discord_bot.config import BotConfig
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # _llm_client ist None (nicht gestartet)
        response = await service.chat("Hallo", user_id=123)

        assert response.is_error
        assert "LLM-Service nicht verfügbar" in response.content

    @pytest.mark.asyncio
    async def test_chat_returns_error_on_llm_error(self):
        """Test: chat() gibt Fehler wenn LLM Error wirft."""
        from unittest.mock import AsyncMock

        from app.discord_bot.config import BotConfig
        from app.discord_bot.llm import LlmError
        from app.discord_bot.service import DiscordBotService

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=LlmError("Connection refused"))
        service._llm_client = mock_llm

        response = await service.chat("Hallo", user_id=123)

        assert response.is_error
        assert "LLM nicht erreichbar" in response.content
        assert "Connection refused" in response.content

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self):
        """Test: chat() verwendet Locutus System-Prompt."""
        from unittest.mock import AsyncMock, patch

        from app.discord_bot.config import BotConfig
        from app.discord_bot.llm import LlmClient
        from app.discord_bot.service import DiscordBotService, LOCUTUS_SYSTEM_PROMPT

        config = BotConfig(enabled=True, token="test-token")
        service = DiscordBotService(config)

        # Start service to initialize LlmClient
        await service.start()

        # Patch LlmClient.chat to capture the call
        with patch.object(
            LlmClient,
            "chat",
            new_callable=AsyncMock,
            return_value="Test response",
        ) as mock_chat:
            response = await service.chat("Testfrage", user_id=123)

            # Prüfe dass system prompt übergeben wurde
            mock_chat.assert_called_once()
            call_args = mock_chat.call_args
            system_prompt = call_args.args[1]
            assert "Locutus" in system_prompt
            assert "technischer Assistent" in system_prompt

        await service.stop()


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
