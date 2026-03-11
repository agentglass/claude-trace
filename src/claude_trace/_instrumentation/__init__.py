"""
Instrumentation entry points for claude-trace.

This module provides ``instrument()`` and ``uninstrument()`` functions that
patch the Anthropic SDK at import time.  Both sync and async clients are
patched in a single call.

Idempotency:
    Calling ``instrument()`` multiple times is safe — subsequent calls are
    no-ops if the SDK is already patched.  Similarly, ``uninstrument()``
    is safe to call even if the SDK was never instrumented.

Thread safety:
    ``instrument()`` and ``uninstrument()`` are not designed for concurrent
    invocation.  Call them once at application startup/shutdown.

Usage::

    import claude_trace

    # Zero-config (reads CLAUDE_TRACE_* env vars, uses global TracerProvider)
    claude_trace.instrument()

    # Explicit config
    from claude_trace.config import TraceConfig
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider()
    claude_trace.instrument(config=TraceConfig(tracer_provider=provider))
"""

from __future__ import annotations

from typing import Optional

from claude_trace._instrumentation.async_client import instrument_async, uninstrument_async
from claude_trace._instrumentation.sync_client import instrument_sync, uninstrument_sync
from claude_trace.config import TraceConfig

_active_config: Optional[TraceConfig] = None


def instrument(config: Optional[TraceConfig] = None) -> None:
    """Activate claude-trace instrumentation on the Anthropic SDK.

    After calling this function, every ``anthropic.Anthropic.messages.create``
    and ``anthropic.AsyncAnthropic.messages.create`` call will automatically:

    1. Look up the active ``AgentSession`` from the current context.
    2. Create a ``claude.turn`` span as a child of the session span.
    3. Create ``claude.tool`` child spans for each tool_use block.
    4. Record token counts, costs, latency, and stop reason on all spans.

    Args:
        config: Optional ``TraceConfig``. When ``None``, a default config is
            created which reads all settings from ``CLAUDE_TRACE_*`` env vars
            and uses the globally-registered OTel ``TracerProvider``.
    """
    global _active_config

    cfg = config or TraceConfig()
    if not cfg.enabled:
        return

    _active_config = cfg
    sync_ok = instrument_sync(cfg)
    async_ok = instrument_async(cfg)

    if not sync_ok and not async_ok:
        import warnings

        warnings.warn(
            "claude-trace: anthropic SDK not found or already instrumented. "
            "No patching applied.",
            stacklevel=2,
        )


def uninstrument() -> None:
    """Remove claude-trace instrumentation from the Anthropic SDK.

    Restores the original ``messages.create`` methods on both sync and
    async Anthropic clients.  Safe to call even if never instrumented.
    """
    global _active_config

    uninstrument_sync()
    uninstrument_async()
    _active_config = None


def get_active_config() -> Optional[TraceConfig]:
    """Return the ``TraceConfig`` that was passed to ``instrument()``, or ``None``."""
    return _active_config


__all__ = ["get_active_config", "instrument", "uninstrument"]
