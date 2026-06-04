"""
Locutus Discord Bot Client.

discord.py Bot-Client der sich mit dem Discord-API verbindet,
Nachrichten empfängt, Commands dispatcht und Antworten sendet.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from .config import BotConfig
from .handlers import CommandHandler
from .models import Command, Response

if TYPE_CHECKING:
    from .service import DiscordBotService

logger = logging.getLogger(__name__)

# Discord hat eine maximale Nachrichtenlänge von 2000 Zeichen.
# Wir schneiden bei Bedarf ab und fügen ein Truncation-Hinweis hinzu.
DISCORD_MAX_LENGTH = 1950


class BotClient(commands.Bot):
    """
    Locutus Discord Bot Client.

    Erbt von discord.ext.commands.Bot und integriert sich nahtlos
    in die BorgOS-Backend-Architektur.
    """

    def __init__(self, config: BotConfig, service: DiscordBotService) -> None:
        """
        Initialisiere BotClient.

        Args:
            config: Locutus Bot-Konfiguration
            service: DiscordBotService für Command-Execution
        """
        intents = discord.Intents.default()
        # Locutus braucht message_content für message-basierte Commands
        # (!status, @Locutus status). Guild-Member-Intents sind dafür nicht nötig
        # und würden im Developer Portal eine zusätzliche privilegierte Freigabe
        # verlangen.
        intents.message_content = True
        intents.guilds = True

        # Command prefix ist das Bot-Prefix (z.B. "!")
        # Wir verwenden auch @-Erwähnungen, die in on_message gehandled werden.
        super().__init__(
            command_prefix=self._prefix_resolver,
            intents=intents,
            help_command=None,  # Wir verwenden unseren eigenen Help-Text
            case_insensitive=True,
        )
        self._config = config
        self._service = service
        self._handler = CommandHandler(service=service)
        self._channel: Optional[discord.TextChannel] = None
        self._ready_event: asyncio.Event = asyncio.Event()

    @staticmethod
    def _prefix_resolver(bot: commands.Bot, message: discord.Message) -> Optional[str]:
        """
        Custom Prefix-Resolver für Bot-Erkennung.

        Gibt das Prefix zurück wenn die Nachricht den Bot erwähnt,
        sonst None (damit Prefix-Commands funktionieren).
        """
        # @-Erwähnung des Bots
        if bot.user and message.content.startswith(f"<@{bot.user.id}>"):
            return bot.config.prefix if hasattr(bot, "config") else "!"
        if bot.user and message.content.startswith(f"<@!{bot.user.id}>"):
            return bot.config.prefix if hasattr(bot, "config") else "!"
        return None

    # Make config accessible to prefix_resolver
    @property
    def config(self) -> BotConfig:
        return self._config

    async def setup_hook(self) -> None:
        """Wird von discord.py nach dem Login aufgerufen."""
        logger.info(f"BotClient setup: connected as {self.user}")

    async def on_ready(self) -> None:
        """Wird aufgerufen wenn der Bot erfolgreich verbunden ist."""
        logger.info(
            f"Locutus online! Benutzer: {self.user} (ID: {self.user.id})"
        )
        logger.info(f"Verbunden mit {len(self.guilds)} Guild(s)")

        # Resolve Channel
        if self._config.channel_id:
            try:
                self._channel = await self.fetch_channel(self._config.channel_id)
                if isinstance(self._channel, discord.TextChannel):
                    logger.info(
                        f"Channel resolved: #{self._channel.name} (ID: {self._channel.id})"
                    )
                else:
                    logger.warning(
                        f"Channel ID {self._config.channel_id} resolved to non-text channel"
                    )
                    self._channel = None
            except discord.NotFound:
                logger.error(f"Channel ID {self._config.channel_id} not found")
                self._channel = None
            except Exception as e:
                logger.error(f"Failed to resolve channel: {e}")
                self._channel = None
        else:
            logger.info("No channel_id configured — listening on all channels")

        self._ready_event.set()

    async def on_message(self, message: discord.Message) -> None:
        """
        Verarbeitet eingehende Nachrichten.

        Filtert eigene Nachrichten, ignoriert Webhooks/Bots,
        und antwortet auf alles — Commands (mit Prefix), Erwähnung oder Chat.
        """
        # Ignoriere eigene Nachrichten und Bots
        if message.author == self.user or message.author.bot:
            return

        # Channel-Filter
        if self._config.channel_id and message.channel.id != self._config.channel_id:
            return

        # Allowed User Filter
        if self._config.allowed_user_ids:
            if message.author.id not in self._config.allowed_user_ids:
                logger.warning(
                    f"Unauthorized user {message.author.id} tried to use Locutus"
                )
                return

        # Prüfe ob Nachricht für Locutus bestimmt ist
        bot_id = self.user.id if self.user else None
        is_command = message.content.strip().startswith(self._config.prefix)
        is_for_bot = bot_id and re.search(
            rf"<@!?{bot_id}>", message.content, re.IGNORECASE
        )

        # Command mit Prefix → Command-Handler (z.B. !status, !search foo)
        if is_command:
            await self._dispatch_command(message, message.content)
            return

        # Erwähnung → Chat mit bereinigtem Text
        if is_for_bot:
            clean = self._strip_mentions(message.content, bot_id)
            if not clean.strip():
                await self._safe_reply(message, "Hey! Schreib mir was, ich höre zu. 😊")
                return
            await self._chat(message, clean.strip())
            return

        # Keine Erwähnung, kein Prefix — Open-Chat-Modus:
        # auf alle Nachrichten im Channel antworten
        if self._config.channel_id is None and not self._config.allowed_user_ids:
            logger.info(f"Open chat: received message from {message.author}: {message.content}")
            await self._chat(message, message.content)

    @staticmethod
    def _strip_mentions(content: str, bot_id: int) -> str:
        """
        Entferne Bot-Mention aus Nachricht.

        Args:
            content: Roh-Text von Discord
            bot_id: ID des Bots

        Returns:
            Text ohne Bot-Mention, gestrippt
        """
        mention_pattern = re.compile(rf"<@!?{bot_id}>", re.IGNORECASE)
        return mention_pattern.sub("", content).strip()

    async def _dispatch_command(self, message: discord.Message, content: str) -> None:
        """
        Parst eine Prefix-Nachricht als Command und dispatcht sie.

        Commands wie !status, !search foo, !help etc.
        """
        try:
            command = self._handler.parse(
                content,
                user_id=message.author.id,
                channel_id=message.channel.id,
            )

            if command is None:
                return

            response = await self._handler.handle(command)
            await self._safe_reply(message, response.content, response.is_error)

        except Exception as e:
            logger.error(f"Error dispatching command: {e}", exc_info=True)
            await self._safe_reply(message, f"Fehler: {str(e)}", is_error=True)

    async def _chat(self, message: discord.Message, text: str) -> None:
        """
        Sende eine natürliche Chat-Nachricht an den LLM und antworte.

        Args:
            message: Ursprüngliche Discord-Nachricht
            text: Bereinigter Chat-Text (ohne Mention)
        """
        try:
            response = await self._service.chat(text, message.author.id)
            await self._safe_reply(message, response.content, response.is_error)
        except Exception as e:
            logger.error(f"Error in chat: {e}", exc_info=True)
            await self._safe_reply(message, "Fehler: Chat nicht verfügbar", is_error=True)


    async def _safe_reply(
        self,
        message_or_channel: discord.Message | discord.abc.Messageable,
        content: str,
        is_error: bool = False,
    ) -> None:
        """
        Sende eine Antwort an Discord mit Truncation-Schutz.

        Discord hat eine maximale Nachrichtenlänge von 2000 Zeichen.
        Wir schneiden bei Bedarf ab.

        Args:
            message_or_channel: Ziel-Nachricht oder Channel
            content: Antwort-Text
            is_error: Ob es eine Fehlermeldung ist
        """
        if not content:
            return

        # Truncate if needed
        if len(content) > DISCORD_MAX_LENGTH:
            content = content[:DISCORD_MAX_LENGTH] + "\n… (gekürzt)"

        prefix = "⚠ ERROR" if is_error else None
        formatted = f"[{prefix}] {content}" if prefix else content

        if len(formatted) > DISCORD_MAX_LENGTH:
            formatted = formatted[:DISCORD_MAX_LENGTH] + "…"

        try:
            if isinstance(message_or_channel, discord.Message):
                await message_or_channel.reply(formatted, mention_author=False)
            else:
                await message_or_channel.send(formatted)
        except discord.HTTPException as e:
            logger.error(f"Failed to send Discord message: {e}")
        except discord.Forbidden:
            logger.error("Locutus hat keine Berechtigung, in diesem Channel zu senden")
        except Exception as e:
            logger.error(f"Unexpected error sending Discord message: {e}")

    async def send_notification(self, content: str) -> None:
        """
        Sende eine Notification an den konfigurierten Channel.

        Wird vom TaskEventListener aufgerufen wenn Tasks starten/fehl schlagen/fertig werden.

        Args:
            content: Notification-Text
        """
        channel = self._channel
        if not channel:
            # Fallback: versuche den ersten Text-Channel der ersten Guild
            if self.guilds:
                guild = self.guilds[0]
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel = ch
                        break
            if not channel:
                logger.warning("No channel available for notification")
                return

        await self._safe_reply(channel, content)

    async def wait_until_ready(self, timeout: float = 30.0) -> None:
        """
        Warte bis der Bot bereit ist.

        Args:
            timeout: Maximale Wartezeit in Sekunden
        """
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Bot ready timeout after {timeout}s")



