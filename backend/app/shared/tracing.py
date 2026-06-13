"""Langfuse tracing — no-op safe observability for agent work.

Single integration point for all tracing: persona chats, Agent Mode runs,
skill executions and dreaming cycles wrap their work in `trace_span(...)`,
and the one LLM chokepoint (`discord_bot.llm.LlmClient.chat`) wraps its POST
in `generation(...)`. The SDK is OTel/contextvars-based, so a generation
opened inside a surrounding span automatically becomes its child — dreaming →
gap analysis → LLM call nests without any plumbing.

Hard requirement: the app behaves identically when Langfuse is disabled
(`LANGFUSE_ENABLED=false`, missing keys, or server unreachable). In that case
no langfuse import is ever executed and every context manager yields a shared
no-op object — tests run without Langfuse and never notice.

Linkage convention (what to pass where):
- ``session_id``: borg run_id (``agent-mode-…``, ``dreaming-<id>``,
  ``discord-<user_id>``) — groups related traces into one Langfuse session.
- ``persona``: ``locutus`` / ``seven`` — becomes the Langfuse user_id.
- ``tags``: surface — ``persona-chat``, ``agent-mode``, ``dreaming``,
  ``skill-execution``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any = None
# Latched after a failed client init: Langfuse being down must cost one log
# line, not an exception per request.
_init_failed = False


def is_enabled() -> bool:
    """Tracing is on only when explicitly enabled AND both keys are set."""
    return (
        not _init_failed
        and settings.langfuse_enabled
        and bool(settings.langfuse_public_key)
        and bool(settings.langfuse_secret_key)
    )


def get_client() -> Any:
    """Lazily construct the Langfuse client singleton; None when disabled."""
    global _client, _init_failed
    if not is_enabled():
        return None
    if _client is None:
        try:
            from langfuse import Langfuse

            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            logger.info(f"Langfuse tracing enabled: host={settings.langfuse_host}")
        except Exception:
            logger.exception("Langfuse init failed — tracing disabled for this process")
            _init_failed = True
            return None
    return _client


class _NoopObservation:
    """Stands in for a Langfuse span/generation when tracing is off.

    Accepts any `.update(...)` call and does nothing — callers never branch on
    whether tracing is enabled. Exceptions raised inside the `with` block
    propagate untouched.
    """

    def update(self, **kwargs: Any) -> "_NoopObservation":
        return self


_NOOP = _NoopObservation()


@contextmanager
def trace_span(
    name: str,
    *,
    persona: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    input: Any = None,
) -> Iterator[Any]:
    """Open a root/nested span; yields an object with `.update(output=..., ...)`."""
    client = get_client()
    if client is None:
        yield _NOOP
        return

    from langfuse import propagate_attributes

    with client.start_as_current_observation(
        name=name, as_type="span", input=input, metadata=metadata
    ) as span:
        with propagate_attributes(user_id=persona, session_id=session_id, tags=tags):
            yield span


@contextmanager
def generation(
    name: str,
    *,
    model: str | None = None,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Open an LLM generation; yields an object with `.update(output=..., usage_details=...)`."""
    client = get_client()
    if client is None:
        yield _NOOP
        return

    with client.start_as_current_observation(
        name=name, as_type="generation", model=model, input=input, metadata=metadata
    ) as gen:
        yield gen


def shutdown() -> None:
    """Flush buffered events on app shutdown (no-op when never initialized)."""
    global _client
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:
            logger.warning("Langfuse shutdown/flush failed", exc_info=True)
        _client = None
