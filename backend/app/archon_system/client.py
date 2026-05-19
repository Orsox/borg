"""HTTP client for the live Archon server."""

from typing import Any

import httpx

from app.config import settings


class ArchonUnavailable(Exception):
    """Raised when the Archon server cannot be reached."""

    def __init__(self, url: str, reason: str = ""):
        self.url = url
        self.reason = reason
        super().__init__(f"Archon unavailable at {url}: {reason}" if reason else f"Archon unavailable at {url}")


class ArchonClient:
    """Async HTTP client for the Archon API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.archon_api_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(5.0, connect=2.0),
        )
        return self

    async def __aexit__(self, *exc_info):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str) -> dict[str, Any] | list[Any]:
        if not self._client:
            raise ArchonUnavailable(self.base_url, "client not initialized")
        try:
            response = await self._client.get(path)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            raise ArchonUnavailable(self.base_url, str(e))
        except httpx.TimeoutException as e:
            raise ArchonUnavailable(self.base_url, f"timeout: {e}")
        except httpx.HTTPStatusError as e:
            raise ArchonUnavailable(self.base_url, f"HTTP {e.response.status_code}")
        except Exception as e:
            raise ArchonUnavailable(self.base_url, str(e))

    async def get_health(self) -> dict[str, Any]:
        data = await self._get("/api/health")
        return data if isinstance(data, dict) else {}

    async def get_runs(self) -> list[Any]:
        data = await self._get("/api/dashboard/runs")
        if isinstance(data, dict):
            return data.get("runs", [])
        if isinstance(data, list):
            return data
        return []

    async def get_codebases(self) -> list[Any]:
        data = await self._get("/api/codebases")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("codebases", [])
        return []

    async def get_workflows(self) -> list[Any]:
        data = await self._get("/api/workflows")
        if isinstance(data, dict):
            return data.get("workflows", [])
        if isinstance(data, list):
            return data
        return []
