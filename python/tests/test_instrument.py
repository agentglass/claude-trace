"""Tests for monkey-patching logic without hitting the real API."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from claude_trace._config import TraceConfig  # type: ignore[import]
from claude_trace._instrument import (  # type: ignore[import]
    _extract_usage,
    _instrument_async,
    _instrument_sync,
    _redact_api_keys,
    _truncate,
    _uninstrument_async,
    _uninstrument_sync,
)


def test_truncate_short_string() -> None:
    assert _truncate("hello", 512) == "hello"


def test_truncate_long_string() -> None:
    s = "x" * 600
    result = _truncate(s, 512)
    assert len(result) < 600
    assert "truncated" in result


def test_truncate_exact_boundary() -> None:
    s = "a" * 512
    assert _truncate(s, 512) == s


def test_truncate_one_over() -> None:
    s = "a" * 513
    result = _truncate(s, 512)
    assert "truncated" in result


def test_redact_api_key() -> None:
    text = "Authorization: Bearer sk-ant-api03-abc123xyz"
    result = _redact_api_keys(text)
    assert "sk-ant" not in result
    assert "[REDACTED]" in result


def test_redact_leaves_non_key_text() -> None:
    text = "Error: invalid request"
    assert _redact_api_keys(text) == text


def test_redact_multiple_keys() -> None:
    text = "key1=sk-ant-foo key2=sk-ant-bar"
    result = _redact_api_keys(text)
    assert "sk-ant-foo" not in result
    assert "sk-ant-bar" not in result
    assert result.count("[REDACTED]") == 2


def test_extract_usage_from_mock_response() -> None:
    mock = MagicMock()
    mock.usage.input_tokens = 100
    mock.usage.output_tokens = 200
    mock.usage.cache_read_input_tokens = 50
    mock.usage.cache_creation_input_tokens = 10
    assert _extract_usage(mock) == (100, 200, 50, 10)


def test_extract_usage_missing_fields() -> None:
    mock = MagicMock()
    mock.usage = None
    assert _extract_usage(mock) == (0, 0, 0, 0)


def test_extract_usage_none_values() -> None:
    mock = MagicMock()
    mock.usage.input_tokens = None
    mock.usage.output_tokens = None
    mock.usage.cache_read_input_tokens = None
    mock.usage.cache_creation_input_tokens = None
    result = _extract_usage(mock)
    assert result == (0, 0, 0, 0)


def test_instrument_uninstrument_cycle() -> None:
    """Verify patching and unpatching doesn't break the SDK import."""
    import anthropic

    original = anthropic.resources.messages.Messages.create
    config = TraceConfig()
    _instrument_sync(config, None)
    assert anthropic.resources.messages.Messages.create is not original
    _uninstrument_sync()
    assert anthropic.resources.messages.Messages.create is original


def test_instrument_idempotent() -> None:
    """Calling instrument twice is safe — second call is a no-op."""
    import anthropic

    config = TraceConfig()
    _instrument_sync(config, None)
    patched_once = anthropic.resources.messages.Messages.create
    _instrument_sync(config, None)
    patched_twice = anthropic.resources.messages.Messages.create
    # The create method should be the same object (idempotent)
    assert patched_once is patched_twice
    _uninstrument_sync()


def test_uninstrument_without_instrument_is_safe() -> None:
    """uninstrument is a no-op if never instrumented."""
    _uninstrument_sync()  # should not raise
    _uninstrument_async()  # should not raise


def test_async_instrument_uninstrument_cycle() -> None:
    """Verify async patching and unpatching."""
    import anthropic

    original = anthropic.resources.messages.AsyncMessages.create
    config = TraceConfig()
    _instrument_async(config, None)
    assert anthropic.resources.messages.AsyncMessages.create is not original
    _uninstrument_async()
    assert anthropic.resources.messages.AsyncMessages.create is original
