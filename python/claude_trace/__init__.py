"""
claude-trace: Zero-configuration OpenTelemetry observability for Claude Agent SDK.

Usage::

    import claude_trace
    claude_trace.instrument()   # one line, done

    # Optional: named sessions with metadata
    with claude_trace.session("billing-agent", customer_id="acme") as sess:
        response = client.messages.create(...)
        print(f"Cost: ${sess.total_cost_usd:.4f}")

Public API:
    instrument()    - Activate tracing on the Anthropic SDK.
    uninstrument()  - Remove tracing patches (useful in tests).
    session()       - Context manager for a named agent session.
    compare()       - Structural diff between two trace snapshots.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry.sdk.trace import TracerProvider

from claude_trace._config import TraceConfig
from claude_trace._instrument import (
    _instrument_async,
    _instrument_sync,
    _uninstrument_async,
    _uninstrument_sync,
)
from claude_trace._session import AgentSession
from claude_trace._claude_trace_core import (  # type: ignore[import]
    CostBreakdown,
    TraceDiff,
    TraceSnapshot,
    calculate_cost,
    compare_traces,
)

__version__ = "0.1.0"
__all__ = [
    "AgentSession",
    "CostBreakdown",
    "TraceConfig",
    "TraceDiff",
    "TraceSnapshot",
    "__version__",
    "calculate_cost",
    "compare",
    "instrument",
    "session",
    "uninstrument",
]

_instrumented = False


def instrument(
    *,
    config: TraceConfig | None = None,
    tracer_provider: TracerProvider | None = None,
) -> None:
    """Auto-instrument the Anthropic SDK. Call once at application startup.

    Patches ``anthropic.Anthropic`` and ``anthropic.AsyncAnthropic`` in-place.
    All existing code is traced without any modifications.

    Args:
        config: Trace configuration. Reads ``CLAUDE_TRACE_*`` env vars by default.
        tracer_provider: OTel TracerProvider. Uses global provider if not set.

    Example::

        import claude_trace
        import anthropic

        claude_trace.instrument()
        client = anthropic.Anthropic()
        # All client.messages.create() calls are now traced
    """
    global _instrumented
    if _instrumented:
        return
    cfg = config or TraceConfig.from_env()
    _instrument_sync(cfg, tracer_provider)
    _instrument_async(cfg, tracer_provider)
    _instrumented = True


def uninstrument() -> None:
    """Remove all patches. Useful in tests.

    Example::

        claude_trace.uninstrument()
    """
    global _instrumented
    _uninstrument_sync()
    _uninstrument_async()
    _instrumented = False


@contextmanager
def session(
    name: str,
    *,
    customer_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    config: TraceConfig | None = None,
) -> Generator[AgentSession, None, None]:
    """Group all Claude API calls into a named agent session.

    All API calls within this context manager are attributed to this session,
    enabling per-session cost tracking, trace grouping, and metadata.

    Args:
        name: Human-readable name for this agent session.
        customer_id: Optional tenant ID for multi-tenant cost attribution.
        tags: Optional list of tags for filtering traces.
        metadata: Optional dict of additional span attributes.
        config: Override trace config for this session only.

    Yields:
        AgentSession with .total_cost_usd, .total_input_tokens, etc.

    Example::

        with claude_trace.session("billing-agent", customer_id="acme") as sess:
            response = client.messages.create(...)
        print(f"Session cost: ${sess.total_cost_usd:.4f}")
    """
    cfg = config or TraceConfig.from_env()
    sess = AgentSession(
        name=name,
        customer_id=customer_id,
        tags=tags or [],
        metadata=metadata or {},
        config=cfg,
    )
    with sess:
        yield sess


def compare(snapshot_a: TraceSnapshot, snapshot_b: TraceSnapshot) -> TraceDiff:
    """Compare two trace snapshots and return a structured diff.

    Useful for regression testing: run the same input before and after a
    prompt change, then assert the traces are equivalent.

    Args:
        snapshot_a: The baseline trace.
        snapshot_b: The new trace to compare against baseline.

    Returns:
        TraceDiff with typed fields: added_tool_calls, removed_tool_calls,
        token_delta, turn_delta. Call .assert_equivalent() in tests.

    Example::

        before = claude_trace.TraceSnapshot(...)
        after = claude_trace.TraceSnapshot(...)
        diff = claude_trace.compare(before, after)
        diff.assert_equivalent()   # raises AssertionError if different
    """
    return compare_traces(snapshot_a, snapshot_b)
