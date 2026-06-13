"""HTTP client for the Langfuse public API.

Mirrors ArchonClient's authenticated-httpx-call shape (archon_system/client.py):
async context manager, one exception type for every flavor of "not reachable",
defensive response mapping. The secret key never leaves the backend — the
frontend talks to /api/observability, which proxies to Langfuse server-side.
"""

from typing import Any

import httpx

from app.config import settings


class LangfuseUnavailable(Exception):
    """Raised when the Langfuse server cannot be reached or rejects the request."""

    def __init__(self, url: str, reason: str = ""):
        self.url = url
        self.reason = reason
        super().__init__(
            f"Langfuse unavailable at {url}: {reason}" if reason else f"Langfuse unavailable at {url}"
        )


def is_configured() -> bool:
    """Frontend integration needs keys; it works regardless of langfuse_enabled
    (read access to existing traces is useful even while ingestion is off)."""
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


class LangfuseApiClient:
    """Async client for the Langfuse public API (HTTP Basic: public/secret key)."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.langfuse_host).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=(settings.langfuse_public_key, settings.langfuse_secret_key),
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
        return self

    async def __aexit__(self, *exc_info):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._client:
            raise LangfuseUnavailable(self.base_url, "client not initialized")
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        except httpx.ConnectError as e:
            raise LangfuseUnavailable(self.base_url, str(e))
        except httpx.TimeoutException as e:
            raise LangfuseUnavailable(self.base_url, f"timeout: {e}")
        except httpx.HTTPStatusError as e:
            raise LangfuseUnavailable(self.base_url, f"HTTP {e.response.status_code}")
        except Exception as e:
            raise LangfuseUnavailable(self.base_url, str(e))

    async def get_health(self) -> dict[str, Any]:
        """Unauthenticated server health — used for the status endpoint."""
        return await self._get("/api/public/health")

    async def list_traces(
        self,
        page: int = 1,
        limit: int = 25,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "orderBy": "timestamp.DESC",
        }
        if user_id:
            params["userId"] = user_id
        if session_id:
            params["sessionId"] = session_id
        if tags:
            params["tags"] = tags
        return await self._get("/api/public/traces", params=params)

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        return await self._get(f"/api/public/traces/{trace_id}")
