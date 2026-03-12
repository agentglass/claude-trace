"""Monkey-patching instrumentation layer for the Anthropic SDK.

Wraps ``anthropic.resources.messages.Messages.create`` (sync) and
``anthropic.resources.messages.AsyncMessages.create`` (async) to inject
OTel spans transparently.

Security:
    - ``_redact_api_keys`` strips ``sk-ant-*`` patterns from error messages.
    - ``capture_content=False`` (default) means no prompt/response text is stored.
    - Sanitize mode suppresses all text attributes.

Idempotency:
    ``_instrument_sync`` / ``_instrument_async`` store the original method under
    a sentinel attribute and skip re-patching on subsequent calls.
"""

from __future__ import annotations

import functools
import re
import time
from typing import TYPE_CHECKING, Any, Callable

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Span, Status, StatusCode

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

    from claude_trace._config import TraceConfig

_TRACER_NAME = "claude-trace"
_SYNC_SENTINEL = "_claude_trace_m3_original_sync"
_ASYNC_SENTINEL = "_claude_trace_m3_original_async"

_orig_sync_create: Callable[..., Any] | None = None
_orig_async_create: Callable[..., Any] | None = None


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _truncate(value: str, max_len: int) -> str:
    """Truncate *value* to *max_len* characters, appending a marker."""
    if len(value) <= max_len:
        return value
    removed = len(value) - max_len
    return value[:max_len] + f"...[truncated {removed} chars]"


def _redact_api_keys(value: str) -> str:
    """Replace ``sk-ant-*`` API key patterns with ``[REDACTED]``."""
    return re.sub(r"sk-ant-[A-Za-z0-9\-_]+", "[REDACTED]", value)


def _extract_usage(response: Any) -> tuple[int, int, int, int]:
    """Extract token counts from an Anthropic response.

    Returns:
        Tuple of (input_tokens, output_tokens, cache_read_tokens, cache_write_tokens).
        All values default to 0 when absent or None.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0, 0
    return (
        int(getattr(usage, "input_tokens", None) or 0),
        int(getattr(usage, "output_tokens", None) or 0),
        int(getattr(usage, "cache_read_input_tokens", None) or 0),
        int(getattr(usage, "cache_creation_input_tokens", None) or 0),
    )


# ---------------------------------------------------------------------------
# Span attribute setting
# ---------------------------------------------------------------------------


def _set_turn_attributes(
    span: Span, response: Any, config: "TraceConfig", latency_ms: float
) -> None:
    """Set all ``claude.turn.*`` attributes on *span* from an API response.

    Content (prompts/responses) is only stored when ``config.capture_content``
    is True and ``config.sanitize`` is False.
    """
    model = getattr(response, "model", "unknown") or "unknown"
    stop_reason = getattr(response, "stop_reason", "unknown") or "unknown"
    request_id = getattr(response, "id", None) or ""
    input_tok, output_tok, cache_read, cache_write = _extract_usage(response)

    span.set_attribute("claude.turn.model", _truncate(model, config.max_attribute_length))
    span.set_attribute("claude.turn.stop_reason", stop_reason)
    span.set_attribute("claude.turn.input_tokens", input_tok)
    span.set_attribute("claude.turn.output_tokens", output_tok)
    span.set_attribute("claude.turn.cache_read_tokens", cache_read)
    span.set_attribute("claude.turn.cache_creation_tokens", cache_write)
    span.set_attribute("claude.turn.latency_ms", round(latency_ms, 2))
    if request_id:
        span.set_attribute("claude.turn.request_id", _truncate(request_id, 64))

    # Tool use information (names only, never inputs)
    content = getattr(response, "content", []) or []
    tool_names = [
        b.name
        for b in content
        if getattr(b, "type", None) == "tool_use" and hasattr(b, "name")
    ]
    if tool_names:
        span.set_attribute("claude.turn.tool_names", ",".join(tool_names))
        span.set_attribute("claude.turn.tool_use_count", len(tool_names))


# ---------------------------------------------------------------------------
# Cost recording
# ---------------------------------------------------------------------------


def _record_cost_to_session(
    response: Any,
    sess: Any,
    input_tok: int,
    output_tok: int,
    cache_read: int,
    cache_write: int,
) -> None:
    """Attempt to record cost to the active session. Silently logs on failure."""
    try:
        from claude_trace._claude_trace_core import calculate_cost  # type: ignore[import]

        model = getattr(response, "model", "unknown") or "unknown"
        cost = calculate_cost(model, input_tok, output_tok, cache_read, cache_write)
        sess._record_turn(input_tok, output_tok, cache_read, cache_write, cost.total_usd)
    except Exception as exc:  # noqa: BLE001 — log but don't crash the caller
        import warnings

        warnings.warn(
            f"claude-trace: cost calculation failed: {exc}",
            stacklevel=4,
        )
        sess._record_turn(input_tok, output_tok, cache_read, cache_write, 0.0)


# ---------------------------------------------------------------------------
# Sync wrapper factory
# ---------------------------------------------------------------------------


def _make_sync_wrapper(
    original: Callable[..., Any], config: "TraceConfig"
) -> Callable[..., Any]:
    """Build a synchronous wrapper that records OTel spans around *original*."""

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from claude_trace._session import current_session

        tracer = otel_trace.get_tracer(_TRACER_NAME)
        sess = current_session()
        context = (
            otel_trace.set_span_in_context(sess._span)  # type: ignore[arg-type]
            if sess and sess._span
            else None
        )

        with tracer.start_as_current_span("claude.agent.turn", context=context) as span:
            start = time.monotonic()
            try:
                response = original(*args, **kwargs)
                latency_ms = (time.monotonic() - start) * 1000
                _set_turn_attributes(span, response, config, latency_ms)
                span.set_status(Status(StatusCode.OK))

                if sess:
                    input_tok, output_tok, cache_read, cache_write = _extract_usage(response)
                    _record_cost_to_session(
                        response, sess, input_tok, output_tok, cache_read, cache_write
                    )
                return response
            except Exception as exc:
                latency_ms = (time.monotonic() - start) * 1000
                span.set_attribute("claude.turn.latency_ms", round(latency_ms, 2))
                span.set_attribute("claude.turn.error_type", type(exc).__name__)
                msg = _truncate(
                    _redact_api_keys(str(exc)), config.max_attribute_length
                )
                span.set_attribute("claude.turn.error_message", msg)
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise

    return wrapper


# ---------------------------------------------------------------------------
# Public instrument / uninstrument (sync)
# ---------------------------------------------------------------------------


def _instrument_sync(
    config: "TraceConfig", tracer_provider: "TracerProvider | None"
) -> None:
    """Monkey-patch ``anthropic.resources.messages.Messages.create``."""
    global _orig_sync_create
    try:
        import anthropic

        create_fn = anthropic.resources.messages.Messages.create
        if hasattr(create_fn, _SYNC_SENTINEL):
            return  # Already instrumented — idempotent

        _orig_sync_create = create_fn
        patched = _make_sync_wrapper(_orig_sync_create, config)
        setattr(patched, _SYNC_SENTINEL, _orig_sync_create)
        anthropic.resources.messages.Messages.create = patched  # type: ignore[method-assign]
    except ImportError:
        pass


def _uninstrument_sync() -> None:
    """Restore the original ``Messages.create``."""
    global _orig_sync_create
    if _orig_sync_create is None:
        return
    try:
        import anthropic

        anthropic.resources.messages.Messages.create = _orig_sync_create  # type: ignore[method-assign]
        _orig_sync_create = None
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Public instrument / uninstrument (async)
# ---------------------------------------------------------------------------


def _instrument_async(
    config: "TraceConfig", tracer_provider: "TracerProvider | None"
) -> None:
    """Monkey-patch ``anthropic.resources.messages.AsyncMessages.create``."""
    global _orig_async_create
    try:
        import anthropic

        create_fn = anthropic.resources.messages.AsyncMessages.create
        if hasattr(create_fn, _ASYNC_SENTINEL):
            return  # Already instrumented — idempotent

        original = create_fn
        _orig_async_create = original

        @functools.wraps(original)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            from claude_trace._session import current_session

            tracer = otel_trace.get_tracer(_TRACER_NAME)
            sess = current_session()
            context = (
                otel_trace.set_span_in_context(sess._span)  # type: ignore[arg-type]
                if sess and sess._span
                else None
            )

            with tracer.start_as_current_span("claude.agent.turn", context=context) as span:
                start = time.monotonic()
                try:
                    response = await original(*args, **kwargs)
                    latency_ms = (time.monotonic() - start) * 1000
                    _set_turn_attributes(span, response, config, latency_ms)
                    span.set_status(Status(StatusCode.OK))
                    if sess:
                        input_tok, output_tok, cache_read, cache_write = _extract_usage(
                            response
                        )
                        _record_cost_to_session(
                            response, sess, input_tok, output_tok, cache_read, cache_write
                        )
                    return response
                except Exception as exc:
                    latency_ms = (time.monotonic() - start) * 1000
                    span.set_attribute("claude.turn.latency_ms", round(latency_ms, 2))
                    span.set_attribute("claude.turn.error_type", type(exc).__name__)
                    msg = _truncate(
                        _redact_api_keys(str(exc)), config.max_attribute_length
                    )
                    span.set_attribute("claude.turn.error_message", msg)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    raise

        setattr(async_wrapper, _ASYNC_SENTINEL, original)
        anthropic.resources.messages.AsyncMessages.create = async_wrapper  # type: ignore[method-assign]
    except ImportError:
        pass


def _uninstrument_async() -> None:
    """Restore the original ``AsyncMessages.create``."""
    global _orig_async_create
    if _orig_async_create is None:
        return
    try:
        import anthropic

        anthropic.resources.messages.AsyncMessages.create = _orig_async_create  # type: ignore[method-assign]
        _orig_async_create = None
    except ImportError:
        pass
