"""
Locutus — Discord-Bot-Modul für BorgOS.

In-process Discord-Bot der auf Discord-Nachrichten hört,
Task-Notifications push-t und KI-Chat über LM Studio ermöglicht.
"""

from .config import BotConfig
from .service import DiscordBotService
from .listener import TaskEventListener
from .bot import BotClient

__all__ = [
    "BotConfig",
    "DiscordBotService",
    "TaskEventListener",
    "BotClient",
]
