"""
ToolInvocation: OTel span for a single tool call + result.

A ``ToolInvocation`` span tracks one invocation of a tool function from the
time the function is entered to the time it returns a result (or raises).
It is a child of the current ``AgentTurn`` span.

Tool spans enable per-tool latency analysis, error rate dashboards, and
duplicate-call detection (via input hashing).

Usage (internal — called by the instrumentation layer or user wrapper)::

    with ToolInvocation(
        tool_name="bash",
        tool_use_id="toolu_01...",
        turn_index=2,
        call_index=0,
        config=config,
        parent_turn=current_turn,
    ) as tool:
        result = bash(command="ls -la")
        tool.record_output(result)

Or as a decorator factory::

    @tool_span(name="bash", config=config)
    def bash(command: str) -> str:
        ...
"""

from __future__ import annotations

import hashlib
import json
import time
from types import TracebackType
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from claude_trace._semconv.claude import ToolStatus
from claude_trace._spans.attributes import TOOL
from claude_trace.config import TraceConfig


class ToolInvocation:
    """Manages the OTel span lifecycle for one tool call.

    Attributes:
        tool_name: Name of the tool as registered in the tools list.
        tool_use_id: Anthropic-assigned ID (``toolu_XXXX``).
        turn_index: Parent turn index.
        call_index: Position of this tool call within the turn.
        config: Tracing configuration.
        span: The underlying OTel ``Span``.
        status: Final ``ToolStatus`` (set when span ends).
        latency_ms: Wall-clock duration (set when span ends).
    """

    def __init__(
        self,
        tool_name: str,
        tool_use_id: str,
        turn_index: int,
        call_index: int,
        config: TraceConfig,
        parent_turn: Optional[Any] = None,  # AgentTurn | None
        tool_input: Optional[dict[str, Any]] = None,
        is_parallel: bool = False,
    ) -> None:
        self.tool_name = tool_name
        self.tool_use_id = tool_use_id
        self.turn_index = turn_index
        self.call_index = call_index
        self.config = config
        self.parent_turn = parent_turn
        self.tool_input = tool_input or {}
        self.is_parallel = is_parallel

        self.span: trace.Span = trace.INVALID_SPAN
        self.status: ToolStatus = ToolStatus.SUCCESS
        self.latency_ms: float = 0.0
        self._start_ns: int = 0

    # ------------------------------------------------------------------
    # Context managers (sync and async)
    # ------------------------------------------------------------------

    def __enter__(self) -> "ToolInvocation":
        self._start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._finish(exc_type, exc_val)

    async def __aenter__(self) -> "ToolInvocation":
        self._start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._finish(exc_type, exc_val)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        self._start_ns = time.perf_counter_ns()
        tracer = trace.get_tracer(
            "claude-trace",
            tracer_provider=self.config.tracer_provider,
        )
        span_name = self.config.span_name("tool")

        # Parent context: the turn span if available, else ambient
        if self.parent_turn is not None:
            parent_ctx = self.parent_turn.get_context()
        else:
            from opentelemetry import context as otel_context

            parent_ctx = otel_context.get_current()

        self.span = tracer.start_span(span_name, context=parent_ctx)

        # Core identity attributes
        self.span.set_attribute(TOOL.TOOL_USE_ID, self.tool_use_id)
        self.span.set_attribute(TOOL.TOOL_NAME, self.tool_name)
        self.span.set_attribute(TOOL.TURN_INDEX, self.turn_index)
        self.span.set_attribute(TOOL.CALL_INDEX, self.call_index)
        self.span.set_attribute(TOOL.IS_PARALLEL, self.is_parallel)

        # Input metadata (no PII: hash + size only by default)
        if self.tool_input:
            try:
                serialized = json.dumps(self.tool_input, sort_keys=True, default=str)
                size_bytes = len(serialized.encode())
                digest = hashlib.sha256(serialized.encode()).hexdigest()[:16]
                self.span.set_attribute(TOOL.INPUT_HASH, digest)
                self.span.set_attribute(TOOL.INPUT_SIZE_BYTES, size_bytes)

                # Optionally capture full input
                if self.config.capture_inputs:
                    self.span.set_attribute(
                        "claude.tool.input_json", self.config.truncate(serialized)
                    )
            except (TypeError, ValueError):
                pass

    def _finish(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
    ) -> None:
        if self.span is trace.INVALID_SPAN:
            return

        elapsed_ns = time.perf_counter_ns() - self._start_ns
        self.latency_ms = elapsed_ns / 1_000_000.0
        self.span.set_attribute(TOOL.LATENCY_MS, self.latency_ms)

        if exc_type is not None:
            self.status = ToolStatus.ERROR
            self.span.set_status(StatusCode.ERROR, str(exc_val) if exc_val else "")
            if exc_val is not None:
                self.span.record_exception(exc_val)
            error_name = f"{exc_type.__module__}.{exc_type.__qualname__}"
            self.span.set_attribute(TOOL.ERROR_TYPE, error_name)
            msg = str(exc_val) if exc_val else ""
            self.span.set_attribute(TOOL.ERROR_MESSAGE, self.config.truncate(msg))
        else:
            self.span.set_status(StatusCode.OK)

        self.span.set_attribute(TOOL.STATUS, self.status.value)
        self.span.end()

    # ------------------------------------------------------------------
    # Result recording
    # ------------------------------------------------------------------

    def record_output(self, output: Any) -> None:
        """Record tool output size and optionally the full output text.

        Args:
            output: The return value from the tool function. Will be
                converted to string via ``str()`` if not already a string.
        """
        if self.span is trace.INVALID_SPAN:
            return

        output_str = output if isinstance(output, str) else str(output)
        size_bytes = len(output_str.encode())
        self.span.set_attribute(TOOL.OUTPUT_SIZE_BYTES, size_bytes)

        if self.config.capture_outputs:
            self.span.set_attribute(
                "claude.tool.output_text", self.config.truncate(output_str)
            )

    def mark_timeout(self) -> None:
        """Mark this tool invocation as having timed out.

        Should be called before allowing the context manager to exit so that
        the status is set correctly on the span.
        """
        self.status = ToolStatus.TIMEOUT

    def mark_cancelled(self) -> None:
        """Mark this tool invocation as cancelled."""
        self.status = ToolStatus.CANCELLED


def tool_span(
    name: str,
    config: Optional[TraceConfig] = None,
    turn_index: int = 0,
    call_index: int = 0,
) -> Any:
    """Decorator factory that wraps a tool function with a ``ToolInvocation`` span.

    This is a convenience wrapper for manual tool instrumentation outside of
    the automatic monkey-patching.

    Usage::

        cfg = TraceConfig()

        @tool_span(name="bash", config=cfg)
        def bash(command: str) -> str:
            import subprocess
            return subprocess.check_output(command, shell=True, text=True)

    Args:
        name: Tool name to record on the span.
        config: ``TraceConfig`` to use (defaults to ``TraceConfig()``).
        turn_index: Turn index hint (default 0).
        call_index: Call index hint (default 0).
    """
    import functools

    cfg = config or TraceConfig()

    def decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tool_use_id = f"toolu_manual_{name}_{time.perf_counter_ns()}"
            with ToolInvocation(
                tool_name=name,
                tool_use_id=tool_use_id,
                turn_index=turn_index,
                call_index=call_index,
                config=cfg,
                tool_input={"args": args, "kwargs": kwargs},
            ) as inv:
                result = fn(*args, **kwargs)
                inv.record_output(result)
                return result

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tool_use_id = f"toolu_manual_{name}_{time.perf_counter_ns()}"
            async with ToolInvocation(
                tool_name=name,
                tool_use_id=tool_use_id,
                turn_index=turn_index,
                call_index=call_index,
                config=cfg,
                tool_input={"args": args, "kwargs": kwargs},
            ) as inv:
                result = await fn(*args, **kwargs)
                inv.record_output(result)
                return result

        import asyncio

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator
