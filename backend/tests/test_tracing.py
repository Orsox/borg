"""Tests for app.shared.tracing — the no-op behavior is the contract.

The whole point of the module is that borg behaves identically without
Langfuse: disabled by default, disabled with missing keys, and the no-op
wrappers never swallow exceptions or require enabled-state branching in
callers.
"""

import pytest

from app.config import settings
from app.shared import tracing


def test_disabled_by_default():
    assert tracing.is_enabled() is False
    assert tracing.get_client() is None


def test_enabled_flag_without_keys_stays_disabled(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    assert tracing.is_enabled() is False
    assert tracing.get_client() is None


def test_noop_span_and_generation_are_usable():
    with tracing.trace_span(
        "test-span", persona="locutus", session_id="run-1", tags=["test"], input="x"
    ) as span:
        assert span.update(output="y") is span

    with tracing.generation("test-gen", model="m", input=[]) as gen:
        gen.update(output="z", usage_details={"input": 1, "output": 2})


def test_noop_does_not_swallow_exceptions():
    with pytest.raises(ValueError):
        with tracing.trace_span("boom"):
            raise ValueError("propagates")

    with pytest.raises(ValueError):
        with tracing.generation("boom"):
            raise ValueError("propagates")


def test_shutdown_is_safe_when_never_initialized():
    tracing.shutdown()
