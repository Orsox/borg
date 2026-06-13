"""HTTP client for a remote BorgOS peer — pulls its sync manifest.

Modeled on archon_system/client.py: a single Unavailable exception and graceful
failure so the UI can report an unreachable peer instead of crashing.
"""

from typing import Any

import httpx


class PeerUnavailable(Exception):
    """Raised when a remote BorgOS peer cannot be reached or refuses the token."""

    def __init__(self, url: str, reason: str = ""):
        self.url = url
        self.reason = reason
        super().__init__(
            f"Peer unavailable at {url}: {reason}" if reason else f"Peer unavailable at {url}"
        )


class PeerClient:
    """Async client for a remote BorgOS `/api/peer/manifest` endpoint."""

    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "PeerClient":
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers=headers,
        )
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_manifest(self) -> list[dict[str, Any]]:
        if not self._client:
            raise PeerUnavailable(self.base_url, "client not initialized")
        try:
            response = await self._client.get("/api/peer/manifest")
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as e:
            raise PeerUnavailable(self.base_url, str(e))
        except httpx.TimeoutException as e:
            raise PeerUnavailable(self.base_url, f"timeout: {e}")
        except httpx.HTTPStatusError as e:
            raise PeerUnavailable(self.base_url, f"HTTP {e.response.status_code}")
        except Exception as e:
            raise PeerUnavailable(self.base_url, str(e))

        if isinstance(data, dict):
            data = data.get("items", [])
        return data if isinstance(data, list) else []
