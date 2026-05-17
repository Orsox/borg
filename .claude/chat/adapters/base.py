"""PlatformAdapter protocol — extensible to Discord, Slack, etc."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class PlatformAdapter(Protocol):
    async def process(self, body: dict, auth_header: str, callback) -> None:
        """Validate auth, parse the incoming message, call callback(turn_context)."""
        ...
