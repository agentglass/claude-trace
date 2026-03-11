"""
AgentTurn: OTel span for one complete agentic loop iteration.

A turn corresponds to exactly one call to ``anthropic.messages.create()``.
It begins when the request is sent and ends when the full response is received
(including all streamed chunks).

Turn spans are children of ``AgentSession`` spans.  When no session is active,
the turn span is created as a root span so instrumentation never silently fails.

Usage (internal — called by the instrumentation layer)::

    session = get_current_session()
    with AgentTurn(turn_index=0, session=session, config=config) as turn:
        response = original_create(**kwargs)
        turn.record_response(response)
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any, Optional, Sequence

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, StatusCode

from claude_trace._cost.calculator import CostBreakdown, get_calculator
from claude_trace._semconv.claude import StopReason
from claude_trace._spans.attributes import COST, TURN
from claude_trace.config import TraceConfig


class AgentTurn:
    """Manages the OTel span for a single agentic loop turn (one LLM call).

    Attributes:
        turn_index: Zero-based index within the session.
        config: Tracing configuration.
        span: The underlying OTel ``Span``.
        cost: ``CostBreakdown`` computed from the response usage.
        tool_names: Tool names invoked in this turn (populated after ``record_response``).
    """

    def __init__(
        self,
        turn_index: int,
        config: TraceConfig,
        session: Optional[Any] = None,  # AgentSession | None
        is_streaming: bool = False,
    ) -> None:
        self.turn_index: int = turn_index
        self.config: TraceConfig = config
        self.session = session
        self.is_streaming: bool = is_streaming

        self.span: Span = trace.INVALID_SPAN
        self.cost: CostBreakdown = CostBreakdown(
            model="unknown",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        self.tool_names: list[str] = []
        self._start_ns: int = 0
        self._first_token_ns: Optional[int] = None
        self._model: str = "unknown"

    # ------------------------------------------------------------------
    # Context manager (sync and async)
    # ------------------------------------------------------------------

    def __enter__(self) -> "AgentTurn":
        self._start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._finish(exc_type, exc_val)

    async def __aenter__(self) -> "AgentTurn":
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
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        self._start_ns = time.perf_counter_ns()
        tracer = trace.get_tracer(
            "claude-trace",
            tracer_provider=self.config.tracer_provider,
        )
        span_name = self.config.span_name("turn")

        # Build parent context: either the session span or the ambient context
        if self.session is not None and self.session.span is not trace.INVALID_SPAN:
            parent_ctx = trace.set_span_in_context(self.session.span)
        else:
            parent_ctx = otel_context.get_current()

        self.span = tracer.start_span(span_name, context=parent_ctx)
        self.span.set_attribute(TURN.TURN_INDEX, self.turn_index)
        self.span.set_attribute(TURN.IS_STREAMING, self.is_streaming)

    def _finish(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
    ) -> None:
        if self.span is trace.INVALID_SPAN:
            return

        elapsed_ns = time.perf_counter_ns() - self._start_ns
        elapsed_ms = elapsed_ns / 1_000_000.0
        self.span.set_attribute(TURN.LATENCY_MS, elapsed_ms)

        if self._first_token_ns is not None:
            ttft_ms = (self._first_token_ns - self._start_ns) / 1_000_000.0
            self.span.set_attribute(TURN.TIME_TO_FIRST_TOKEN_MS, ttft_ms)

        if exc_type is not None:
            self.span.set_status(StatusCode.ERROR, str(exc_val) if exc_val else "")
            if exc_val is not None:
                self.span.record_exception(exc_val)
            error_name = f"{exc_type.__module__}.{exc_type.__qualname__}"
            self.span.set_attribute(TURN.ERROR_TYPE, error_name)
            msg = str(exc_val) if exc_val else ""
            self.span.set_attribute(
                TURN.ERROR_MESSAGE, self.config.truncate(msg)
            )
            self.span.set_attribute(TURN.STOP_REASON, StopReason.ERROR.value)
        else:
            self.span.set_status(StatusCode.OK)

        # Write cost attributes
        if self.config.record_costs and self.cost.model != "unknown":
            self.span.set_attribute(COST.INPUT_COST_USD, f"{self.cost.input_cost_usd:.6f}")
            self.span.set_attribute(COST.OUTPUT_COST_USD, f"{self.cost.output_cost_usd:.6f}")
            self.span.set_attribute(
                COST.CACHE_READ_COST_USD, f"{self.cost.cache_read_cost_usd:.6f}"
            )
            self.span.set_attribute(
                COST.CACHE_CREATION_COST_USD, f"{self.cost.cache_creation_cost_usd:.6f}"
            )
            self.span.set_attribute(TURN.COST_USD, f"{self.cost.total_usd:.6f}")
            self.span.set_attribute(COST.MODEL, self.cost.model)

        # Report to parent session
        if self.session is not None:
            self.session.record_turn(self.cost, self.tool_names)

        self.span.end()

    # ------------------------------------------------------------------
    # Response recording
    # ------------------------------------------------------------------

    def record_response(self, response: Any) -> None:
        """Extract and record attributes from an ``anthropic.types.Message``.

        Handles both regular ``Message`` objects and reconstructed messages
        from streamed responses (after collecting all chunks).

        Args:
            response: The ``anthropic.types.Message`` returned by the API.
        """
        if self.span is trace.INVALID_SPAN:
            return

        # Model
        model: str = getattr(response, "model", "unknown")
        self._model = model
        self.span.set_attribute(TURN.MODEL, model)

        # Stop reason
        stop_reason: str = getattr(response, "stop_reason", "") or ""
        self.span.set_attribute(TURN.STOP_REASON, stop_reason)

        # Request ID (from response headers if available)
        if hasattr(response, "_request_id"):
            req_id = str(response._request_id)
            self.span.set_attribute(TURN.REQUEST_ID, req_id)

        # Usage
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens: int = getattr(usage, "input_tokens", 0) or 0
            output_tokens: int = getattr(usage, "output_tokens", 0) or 0
            cache_read: int = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_creation: int = getattr(usage, "cache_creation_input_tokens", 0) or 0

            self.span.set_attribute(TURN.INPUT_TOKENS, input_tokens)
            self.span.set_attribute(TURN.OUTPUT_TOKENS, output_tokens)
            self.span.set_attribute(TURN.CACHE_READ_TOKENS, cache_read)
            self.span.set_attribute(TURN.CACHE_CREATION_TOKENS, cache_creation)

            # Compute cost
            self.cost = get_calculator().calculate(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_creation,
            )

        # Content blocks
        content = getattr(response, "content", []) or []
        block_types: list[str] = []
        tool_use_names: list[str] = []
        text_length = 0

        for block in content:
            btype: str = getattr(block, "type", "unknown")
            block_types.append(btype)
            if btype == "tool_use":
                name: str = getattr(block, "name", "unknown")
                tool_use_names.append(name)
            elif btype == "text":
                text: str = getattr(block, "text", "") or ""
                text_length += len(text)

        self.tool_names = tool_use_names
        self.span.set_attribute(TURN.TOOL_USE_COUNT, len(tool_use_names))
        self.span.set_attribute(TURN.TEXT_CONTENT_LENGTH, text_length)

        if block_types:
            self.span.set_attribute(TURN.CONTENT_BLOCK_TYPES, ",".join(block_types))
        if tool_use_names:
            self.span.set_attribute(TURN.TOOL_NAMES, ",".join(tool_use_names))

        # Optionally capture full output text
        if self.config.capture_outputs and text_length > 0:
            full_text = " ".join(
                getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text"
            )
            self.span.set_attribute("claude.turn.output_text", self.config.truncate(full_text))

    def mark_first_token(self) -> None:
        """Record the timestamp of the first streamed token.

        Call this from the streaming wrapper immediately upon receiving
        the first ``content_block_delta`` event.
        """
        if self._first_token_ns is None:
            self._first_token_ns = time.perf_counter_ns()

    def record_request_id(self, request_id: str) -> None:
        """Record the Anthropic request ID from the response headers."""
        if self.span is not trace.INVALID_SPAN:
            self.span.set_attribute(TURN.REQUEST_ID, request_id)

    def get_context(self) -> otel_context.Context:
        """Return an OTel context with this turn's span active.

        Used when creating child tool spans.
        """
        return trace.set_span_in_context(self.span)
