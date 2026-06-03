"""
Locutus Command-Handler.

Parsed Commands werden hier dispatcht. Jeder Handler nimmt einen Command
und gibt eine Response zurück.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from .models import Command, Response, CommandType

if TYPE_CHECKING:
    from .service import DiscordBotService


class CommandHandler:
    """Dispatch und Handler für Locutus Commands."""

    # Regex für Command-Parsing
    # Matches: "!command arg1 arg2" oder "@Locutus command arg1 arg2"
    MENTION_PATTERN = re.compile(r"^@Locutus\s+(.+)", re.IGNORECASE)
    PREFIX_PATTERN = re.compile(r"^!(\s*)(.+)", re.IGNORECASE)

    # Bekannte Commands
    KNOWN_COMMANDS = {"chat", "search", "status", "help", "note", "create"}

    def __init__(self, service: Optional[DiscordBotService] = None) -> None:
        """Initialisiere CommandHandler.
        
        Args:
            service: Optional DiscordBotService für Handler die Service-Methoden aufrufen.
        """
        self._service = service
        self._handlers: dict[CommandType, callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Registriere Default-Handler."""
        self._handlers[CommandType.CHAT] = self._handle_chat
        self._handlers[CommandType.SEARCH] = self._handle_search
        self._handlers[CommandType.STATUS] = self._handle_status
        self._handlers[CommandType.CREATE_NOTE] = self._handle_create_note
        self._handlers[CommandType.HELP] = self._handle_help

    def parse(self, content: str, user_id: int, channel_id: int) -> Optional[Command]:
        """
        Parse eine Discord-Nachricht in einen Command.

        Returns None wenn keine Command-Erkennung (keine @-Erwähnung, kein Prefix).
        """
        is_mention = False

        # Prüfe @-Erwähnung
        mention_match = self.MENTION_PATTERN.match(content)
        if mention_match:
            is_mention = True
            content = mention_match.group(1).strip()
        else:
            # Prüfe Prefix
            prefix_match = self.PREFIX_PATTERN.match(content)
            if prefix_match:
                content = prefix_match.group(2).strip()
            else:
                # Keine Erkennung — ignoriere Nachricht
                return None

        # Extrahiere Command und Args
        parts = content.split(maxsplit=1)
        command_name = parts[0].lower()
        args = [parts[1]] if len(parts) > 1 else []

        # Mappe Command-Name zu CommandType
        command_type = self._map_command(command_name)
        if command_type is None:
            # Unbekannter Command — behandle als Chat
            command_type = CommandType.CHAT
            args = [content]

        return Command(
            content=content,
            user_id=user_id,
            channel_id=channel_id,
            command_type=command_type,
            args=args,
            is_mention=is_mention,
        )

    def _map_command(self, name: str) -> Optional[CommandType]:
        """Mappe Command-Name zu CommandType."""
        mapping = {
            "chat": CommandType.CHAT,
            "c": CommandType.CHAT,
            "search": CommandType.SEARCH,
            "s": CommandType.SEARCH,
            "status": CommandType.STATUS,
            "st": CommandType.STATUS,
            "note": CommandType.CREATE_NOTE,
            "create": CommandType.CREATE_NOTE,
            "help": CommandType.HELP,
            "h": CommandType.HELP,
        }
        return mapping.get(name)

    async def handle(self, command: Command) -> Response:
        """
        Dispatche einen Command zum passenden Handler.

        Raise ValueError wenn Handler nicht registriert.
        """
        if command.command_type not in self._handlers:
            return Response(
                content=f"Unbekannter Command: {command.command_type}",
                is_error=True,
            )

        handler = self._handlers[command.command_type]
        return await handler(command)

    # --- Handler Implementierungen ---

    async def _handle_chat(self, command: Command) -> Response:
        """Chat-Handler: Leitet an LLM weiter (in service.py implementiert)."""
        if self._service:
            message = " ".join(command.args) if command.args else command.content
            return await self._service.chat(message, command.user_id)
        return Response(
            content="Service nicht verfügbar.",
            is_error=True,
        )

    async def _handle_search(self, command: Command) -> Response:
        """Suche-Handler: Durchsucht Notes und Vault (in service.py implementiert)."""
        if self._service:
            query = " ".join(command.args) if command.args else ""
            return await self._service.search(query)
        query = " ".join(command.args) if command.args else ""
        return Response(
            content=f"Service nicht verfügbar. Suche nach: {query}",
            is_error=True,
        )

    async def _handle_status(self, command: Command) -> Response:
        """Status-Handler: Zeigt Archon/Task-Status (in service.py implementiert)."""
        if self._service:
            return await self._service.status()
        return Response(
            content="Service nicht verfügbar.",
            is_error=True,
        )

    async def _handle_create_note(self, command: Command) -> Response:
        """Notiz-Erstellen-Handler: Erstellt Note mit Wiki-Links (in service.py implementiert)."""
        if self._service:
            content = " ".join(command.args) if command.args else ""
            return await self._service.create_note(content)
        content = " ".join(command.args) if command.args else ""
        return Response(
            content=f"Service nicht verfügbar. Notiz-Erstellung: {content}",
            is_error=True,
        )

    async def _handle_help(self, command: Command) -> Response:
        """Help-Handler: Zeigt verfügbare Commands."""
        help_text = """Verfügbare Commands:
  !chat <frage>        — KI-Chat mit Locutus
  !search <query>      — Suche in Notes und Vault
  !status              — Zeige Task/Archon-Status
  !note <inhalt>       — Erstelle Notiz
  !help                — Diese Hilfe

Oder erwähne @Locutus vor deiner Nachricht."""
        return Response(content=help_text)
