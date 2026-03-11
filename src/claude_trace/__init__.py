"""
claude-trace: Zero-configuration OpenTelemetry observability for Claude Agent SDK.

claude-trace captures every agent decision as first-class structured OTel spans,
giving you deep visibility into your Claude-powered agents without any manual
instrumentation work.

Span hierarchy::

    claude.session  ← root span; one per claude.run() call
    └── claude.turn[0]  ← one span per LLM API call
        ├── claude.tool[bash_0]   ← tool_use block 0
        └── claude.tool[bash_1]   ← tool_use block 1
    └── claude.turn[1]
        └── claude.tool[web_search_0]
    ...

Quick start::

    import claude_trace
    import anthropic

    # One-line setup: patches both sync and async Anthropic clients
    claude_trace.instrument()

    client = anthropic.Anthropic()

    with claude_trace.session(customer_id="acme", tags=["prod"]) as sess:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello!"}],
        )

    print(f"Session cost: ${sess.cost.total_usd:.4f}")

Public API:
    instrument()     - Activate tracing on the Anthropic SDK
    uninstrument()   - Remove tracing patches
    session()        - Context manager for a full agent session
    compare()        - Structural diff between two trace snapshots
"""

from __future__ import annotations

from typing import Optional, Sequence

from claude_trace._diff.trace_diff import TraceDiff, TraceSnapshot, compare as _compare
from claude_trace._instrumentation import (
    get_active_config,
    instrument as _instrument,
    uninstrument as _uninstrument,
)
from claude_trace._spans.session import AgentSession
from claude_trace.config import TraceConfig

__version__ = "0.1.0"
__all__ = [
    "AgentSession",
    "TraceConfig",
    "TraceSnapshot",
    "TraceDiff",
    "__version__",
    "compare",
    "instrument",
    "session",
    "uninstrument",
]


def instrument(config: Optional[TraceConfig] = None) -> None:
    """Activate claude-trace on the Anthropic SDK.

    Call this once at application startup, before creating any Anthropic
    clients or making any API calls.

    After this call, all ``anthropic.Anthropic.messages.create`` and
    ``anthropic.AsyncAnthropic.messages.create`` calls are automatically
    traced.  Spans are exported via whatever ``TracerProvider`` is registered
    globally (or via ``config.tracer_provider``).

    Args:
        config: Optional ``TraceConfig``.  When ``None``, all settings are
            read from ``CLAUDE_TRACE_*`` environment variables.

    Example::

        import claude_trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))

        from claude_trace.config import TraceConfig
        claude_trace.instrument(config=TraceConfig(tracer_provider=provider))
    """
    _instrument(config)


def uninstrument() -> None:
    """Remove claude-trace instrumentation from the Anthropic SDK.

    Restores the original ``messages.create`` methods. Safe to call even
    if ``instrument()`` was never called.
    """
    _uninstrument()


def session(
    model: str = "claude-sonnet-4-6",
    system_prompt: str = "",
    max_turns: int = 10,
    customer_id: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    session_id: Optional[str] = None,
    config: Optional[TraceConfig] = None,
) -> AgentSession:
    """Factory that returns an ``AgentSession`` context manager.

    Returns an ``AgentSession`` which supports both ``with`` (sync) and
    ``async with`` (async) usage.  All ``messages.create`` calls made within
    the context are automatically linked as children of the session span.

    Args:
        model: Default Claude model for this session.
        system_prompt: System prompt text (stored as hash, never raw).
        max_turns: Maximum agentic loop iterations configured.
        customer_id: Optional customer/tenant ID for cost attribution.
        tags: Optional list of string tags for filtering in OTel backends.
        session_id: Override the auto-generated session ID.
        config: Override the global ``TraceConfig`` for this session only.

    Returns:
        An ``AgentSession`` instance (use as ``with`` or ``async with``).

    Example::

        with claude_trace.session(customer_id="acme", tags=["batch-job"]) as sess:
            response = client.messages.create(...)

        print(f"Turns: {sess._turn_count}")
        print(f"Cost:  ${sess.cost.total_usd:.4f}")

    Async usage::

        async with claude_trace.session(model="claude-opus-4-5") as sess:
            response = await async_client.messages.create(...)
    """
    cfg = config or get_active_config() or TraceConfig()
    return AgentSession(
        model=model,
        system_prompt=system_prompt,
        max_turns=max_turns,
        customer_id=customer_id,
        tags=tags,
        session_id=session_id,
        config=cfg,
    )


def compare(baseline: TraceSnapshot, candidate: TraceSnapshot) -> TraceDiff:
    """Compare two trace snapshots and return a typed diff.

    Suitable for use in pytest assertions and CI regression checks.

    Args:
        baseline: The reference ``TraceSnapshot`` (e.g. loaded from a golden file).
        candidate: The new ``TraceSnapshot`` to compare against.

    Returns:
        A ``TraceDiff`` with all structural differences populated.

    Example::

        golden = TraceSnapshot.load("tests/golden/task_a.json")
        actual = TraceSnapshot.from_session(session)

        diff = claude_trace.compare(golden, actual)
        assert diff.is_equivalent(rtol=0.05), diff.summary()
    """
    return _compare(baseline, candidate)
