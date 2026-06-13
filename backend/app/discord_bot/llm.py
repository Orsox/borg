"""
Locutus LLM-Integration.

Schnittstelle zu LM Studio für KI-gestützten Chat.
Nutzt OpenAI-kompatible API von LM Studio.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.shared import tracing

from .config import LlmConfig

logger = logging.getLogger(__name__)


def _usage_details(usage: dict[str, Any] | None) -> dict[str, int]:
    """Map LM Studios OpenAI-Format-`usage` auf Langfuse usage_details."""
    if not usage:
        return {}
    details = {}
    if isinstance(usage.get("prompt_tokens"), int):
        details["input"] = usage["prompt_tokens"]
    if isinstance(usage.get("completion_tokens"), int):
        details["output"] = usage["completion_tokens"]
    if isinstance(usage.get("total_tokens"), int):
        details["total"] = usage["total_tokens"]
    return details


class LlmClient:
    """
    LM Studio Client für KI-Chat.

    Nutzt die OpenAI-kompatible API von LM Studio
    (http://localhost:1234/v1/chat/completions).
    """

    def __init__(self, config: LlmConfig) -> None:
        """Initialisiere LlmClient mit Config."""
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialisiere HTTP-Client."""
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        logger.info(f"LlmClient initialized: model={self._config.model_id}")

    async def stop(self) -> None:
        """Schließe HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("LlmClient stopped")

    async def chat(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        """
        Sende Chat-Nachricht an LM Studio.

        Args:
            messages: Liste von {"role": str, "content": str} Dicts
            system_prompt: System-Prompt für Locutus-Persönlichkeit

        Returns:
            Antwort-Text vom Modell

        Raises:
            LlmError: Wenn LM Studio nicht erreichbar oder Antwort fehlerhaft
        """
        if not self._client:
            raise LlmError("LlmClient not started")

        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]
        with tracing.generation(
            "llm-chat",
            model=self._config.model_id,
            input=full_messages,
            metadata={"persona": self._config.persona, "base_url": self._config.base_url},
        ) as gen:
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json={
                        "model": self._config.model_id,
                        "messages": full_messages,
                        "temperature": self._config.temperature,
                        "max_tokens": self._config.max_tokens,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Extrahiere Antwort aus OpenAI-kompatiblen Response
                choices = data.get("choices", [])
                if not choices:
                    raise LlmError("LM Studio returned empty choices")

                assistant_message = choices[0].get("message", {})
                content = assistant_message.get("content", "")

                if not content:
                    raise LlmError("LM Studio returned empty content")

                gen.update(output=content, usage_details=_usage_details(data.get("usage")))
                return content.strip()

            except httpx.HTTPStatusError as e:
                logger.error(f"LM Studio HTTP error: {e.response.status_code} {e.response.text}")
                gen.update(level="ERROR", status_message=f"HTTP {e.response.status_code}")
                raise LlmError(f"LM Studio HTTP error: {e.response.status_code}")
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                logger.error(f"LM Studio timeout: {e}")
                gen.update(level="ERROR", status_message="timeout")
                raise LlmError("LM Studio timeout after 30s")
            except LlmError as e:
                gen.update(level="ERROR", status_message=str(e))
                raise
            except Exception as e:
                logger.error(f"LM Studio error: {e}")
                gen.update(level="ERROR", status_message=str(e))
                raise LlmError(f"LM Studio error: {e}")


class LlmError(Exception):
    """Fehler in der LLM-Integration."""

    pass
