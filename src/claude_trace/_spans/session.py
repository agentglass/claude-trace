"""
AgentSession: OTel span lifecycle for a full agent conversation session.

An ``AgentSession`` is a context manager that wraps the root span of the
claude-trace span hierarchy.  All turn and tool spans are created as
descendants of this root span.

Usage (sync)::

    import claude_trace

    with claude_trace.session(customer_id="acme", tags=["prod"]) as sess:
        result = anthropic_client.messages.create(...)  # auto-instrumented
    print(f"Total cost: ${sess.cost.total_usd:.6f}")

Usage (async)::

    async with claude_trace.session(customer_id="acme") as sess:
        result = await async_client.messages.create(...)
"""

from __future__ import annotations

import hashlib
import time
import uuid
from contextvars import Token
from types import TracebackType
from typing import Optional, Sequence

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

from claude_trace._cost.calculator import CostBreakdown, get_calculator
from claude_trace._semconv.claude import SessionStatus
from claude_trace._spans.attributes import COST, SESSION
from claude_trace.config import TraceConfig


class AgentSession:
    """Manages the root OTel span for a single agent session.

    Tracks cumulative token counts and costs across all turns.
    Acts as both a sync and async context manager.

    Attributes:
        session_id: Unique identifier for this session.
        model: Configured Claude model for this session.
        config: The ``TraceConfig`` governing instrumentation behaviour.
        span: The underlying OTel ``Span`` (do not close directly).
        cost: Cumulative ``CostBreakdown`` across all turns (updated live).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        system_prompt: str = "",
        max_turns: int = 10,
        customer_id: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        session_id: Optional[str] = None,
        config: Optional[TraceConfig] = None,
    ) -> None:
        self.session_id: str = session_id or f"sess_{uuid.uuid4().hex[:20]}"
        self.model: str = model
        self.system_prompt: str = system_prompt
        self.max_turns: int = max_turns
        self.customer_id: Optional[str] = customer_id
        self.tags: list[str] = list(tags) if tags else []
        self.config: TraceConfig = config or TraceConfig()

        # Accumulated across turns
        self.cost: CostBreakdown = CostBreakdown(
            model=model,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        self._turn_count: int = 0
        self._tool_names: set[str] = set()
        self._total_tool_calls: int = 0

        self.span: Span = trace.INVALID_SPAN
        self._ctx_token: Optional[Token["AgentSession | None"]] = None
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Context manager protocol (sync)
    # ------------------------------------------------------------------

    def __enter__(self) -> "AgentSession":
        self._start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._finish(exc_type, exc_val)

    # ------------------------------------------------------------------
    # Async context manager protocol
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AgentSession":
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _start(self) -> None:
        """Start the session span and install this session in the context."""
        from claude_trace.context import set_current_session

        self._start_time = time.perf_counter()
        tracer = trace.get_tracer(
            "claude-trace",
            tracer_provider=self.config.tracer_provider,
        )
        span_name = self.config.span_name("session")
        self.span = tracer.start_span(span_name)

        # Set initial attributes
        self.span.set_attribute(SESSION.SESSION_ID, self.session_id)
        self.span.set_attribute(SESSION.MODEL, self.model)
        self.span.set_attribute(SESSION.MAX_TURNS, self.max_turns)
        self.span.set_attribute(SESSION.STATUS, SessionStatus.RUNNING.value)

        if self.system_prompt:
            digest = hashlib.sha256(self.system_prompt.encode()).hexdigest()[:16]
            self.span.set_attribute(SESSION.SYSTEM_PROMPT_HASH, digest)
            self.span.set_attribute(SESSION.SYSTEM_PROMPT_LENGTH, len(self.system_prompt))

        if self.customer_id:
            self.span.set_attribute(SESSION.CUSTOMER_ID, self.customer_id)

        if self.tags:
            self.span.set_attribute(SESSION.TAGS, ",".join(self.tags))

        self._ctx_token = set_current_session(self)

    def _finish(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
    ) -> None:
        """Finalise and end the session span."""
        from claude_trace.context import reset_current_session

        if self._ctx_token is not None:
            reset_current_session(self._ctx_token)
            self._ctx_token = None

        if self.span is trace.INVALID_SPAN:
            return

        # Determine final status
        if exc_type is not None:
            status = SessionStatus.ERROR
            self.span.set_status(StatusCode.ERROR, str(exc_val) if exc_val else "")
            self.span.record_exception(exc_val)  # type: ignore[arg-type]
        else:
            status = SessionStatus.COMPLETED
            self.span.set_status(StatusCode.OK)

        # Write cumulative token/cost attributes
        self.span.set_attribute(SESSION.STATUS, status.value)
        self.span.set_attribute(SESSION.TOTAL_TURNS, self._turn_count)
        self.span.set_attribute(SESSION.TOTAL_INPUT_TOKENS, self.cost.input_tokens)
        self.span.set_attribute(SESSION.TOTAL_OUTPUT_TOKENS, self.cost.output_tokens)
        self.span.set_attribute(SESSION.TOTAL_CACHE_READ_TOKENS, self.cost.cache_read_tokens)
        self.span.set_attribute(
            SESSION.TOTAL_CACHE_CREATION_TOKENS, self.cost.cache_creation_tokens
        )
        self.span.set_attribute(SESSION.TOTAL_COST_USD, f"{self.cost.total_usd:.6f}")

        if self._tool_names:
            self.span.set_attribute(SESSION.TOOL_NAMES, ",".join(sorted(self._tool_names)))
        self.span.set_attribute(SESSION.TOTAL_TOOL_CALLS, self._total_tool_calls)

        # Cost breakdown attributes
        if self.config.record_costs:
            self.span.set_attribute(COST.INPUT_COST_USD, f"{self.cost.input_cost_usd:.6f}")
            self.span.set_attribute(COST.OUTPUT_COST_USD, f"{self.cost.output_cost_usd:.6f}")
            self.span.set_attribute(
                COST.CACHE_READ_COST_USD, f"{self.cost.cache_read_cost_usd:.6f}"
            )
            self.span.set_attribute(
                COST.CACHE_CREATION_COST_USD, f"{self.cost.cache_creation_cost_usd:.6f}"
            )
            self.span.set_attribute(COST.TOTAL_COST_USD, f"{self.cost.total_usd:.6f}")
            self.span.set_attribute(COST.MODEL, self.model)
            self.span.set_attribute(COST.PRICING_TIER, "standard")

        self.span.end()

    # ------------------------------------------------------------------
    # Mutation helpers called by AgentTurn
    # ------------------------------------------------------------------

    def record_turn(self, turn_cost: CostBreakdown, tool_names: Sequence[str]) -> None:
        """Accumulate statistics from a completed turn.

        Called by ``AgentTurn._finish()`` after each API response.
        Thread-safe in asyncio (single-threaded event loop); for
        threaded use add a lock if needed.
        """
        self._turn_count += 1
        self.cost = self.cost + turn_cost
        self._tool_names.update(tool_names)
        self._total_tool_calls += len(tool_names)

        # Update live attributes so span data is visible even if not ended yet
        self.span.set_attribute(SESSION.TOTAL_TURNS, self._turn_count)
        self.span.set_attribute(SESSION.TOTAL_COST_USD, f"{self.cost.total_usd:.6f}")

    def get_span_context(self) -> trace.SpanContext:
        """Return the span context for propagation into child spans."""
        return self.span.get_span_context()

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AgentSession(id={self.session_id!r}, model={self.model!r}, "
            f"turns={self._turn_count}, cost=${self.cost.total_usd:.4f})"
        )
