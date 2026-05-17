"""Microsoft Teams adapter using the Bot Framework SDK.

Setup (one-time, requires IT admin):
  1. Azure Portal → Bot Services → Create a Bot
  2. Note the Microsoft App ID and generate an App Password (Certificates & secrets)
  3. Set the messaging endpoint: https://<your-vps>/webhook/teams
  4. Add the bot to your Teams tenant and install it for your user
  5. Set TEAMS_BOT_APP_ID and TEAMS_BOT_APP_PASSWORD in borg/.env

The botbuilder SDK handles JWT validation automatically via process_activity().
"""
import os

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity, ActivityTypes


class TeamsAdapter:
    """Wraps BotFrameworkAdapter for use in FastAPI."""

    def __init__(
        self,
        app_id: str | None = None,
        app_password: str | None = None,
    ):
        self._app_id = app_id or os.environ.get("TEAMS_BOT_APP_ID", "")
        self._app_password = app_password or os.environ.get("TEAMS_BOT_APP_PASSWORD", "")

        settings = BotFrameworkAdapterSettings(self._app_id, self._app_password)
        self._adapter = BotFrameworkAdapter(settings)
        self._adapter.on_turn_error = TeamsAdapter._on_error

    @staticmethod
    async def _on_error(context: TurnContext, error: Exception):
        print(f"[TeamsAdapter] Error during turn: {error}")
        try:
            await context.send_activity(
                Activity(type=ActivityTypes.message, text="Something went wrong. Try again.")
            )
        except Exception:
            pass

    async def process(self, body: dict, auth_header: str, callback) -> None:
        """Deserialize activity, validate JWT, invoke callback(TurnContext)."""
        activity = Activity.deserialize(body)
        await self._adapter.process_activity(activity, auth_header, callback)

    @staticmethod
    async def reply(context: TurnContext, text: str) -> None:
        """Send a plain-text reply in the current turn."""
        reply = Activity(type=ActivityTypes.message, text=text)
        await context.send_activity(reply)

    @staticmethod
    def is_message(context: TurnContext) -> bool:
        return context.activity.type == ActivityTypes.message

    @staticmethod
    def get_text(context: TurnContext) -> str:
        return (context.activity.text or "").strip()

    @staticmethod
    def get_conversation_id(context: TurnContext) -> str:
        return context.activity.conversation.id

    @property
    def is_configured(self) -> bool:
        return bool(self._app_id and self._app_password)
