"""Tests for TraceConfig — env-var reading and defaults."""
from __future__ import annotations

import pytest

from claude_trace._config import TraceConfig  # type: ignore[import]


def test_defaults() -> None:
    cfg = TraceConfig()
    assert cfg.capture_content is False
    assert cfg.max_attribute_length == 512
    assert cfg.sanitize is False


def test_from_env_sanitize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_TRACE_SANITIZE", "true")
    cfg = TraceConfig.from_env()
    assert cfg.sanitize is True


def test_from_env_sanitize_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_TRACE_SANITIZE", "false")
    cfg = TraceConfig.from_env()
    assert cfg.sanitize is False


def test_from_env_capture_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_TRACE_CAPTURE_CONTENT", "true")
    cfg = TraceConfig.from_env()
    assert cfg.capture_content is True


def test_from_env_max_length(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_TRACE_MAX_ATTR_LENGTH", "1024")
    cfg = TraceConfig.from_env()
    assert cfg.max_attribute_length == 1024


def test_from_env_defaults_when_no_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_TRACE_CAPTURE_CONTENT", raising=False)
    monkeypatch.delenv("CLAUDE_TRACE_MAX_ATTR_LENGTH", raising=False)
    monkeypatch.delenv("CLAUDE_TRACE_SANITIZE", raising=False)
    cfg = TraceConfig.from_env()
    assert cfg.capture_content is False
    assert cfg.max_attribute_length == 512
    assert cfg.sanitize is False


def test_explicit_constructor() -> None:
    cfg = TraceConfig(capture_content=True, max_attribute_length=256, sanitize=True)
    assert cfg.capture_content is True
    assert cfg.max_attribute_length == 256
    assert cfg.sanitize is True
