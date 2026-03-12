"""AgentSession: context manager tracking a complete agent conversation.

Records cumulative token counts and cost, and creates an OTel root span
that all turn spans will be attached to as children.

Usage::

    with claude_trace.session("billing-agent", customer_id="acme") as sess:
        response = client.messages.create(...)
    print(f"Cost: ${sess.total_cost_usd:.4f}")
"""

from __future__ import annotations

import contextvars
import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Span, Status, StatusCode

if TYPE_CHECKING:
    from claude_trace._config import TraceConfig

_TRACER_NAME = "claude-trace"

_SESSION_CONTEXT_VAR: contextvars.ContextVar["AgentSession | None"] = contextvars.ContextVar(
    "claude_trace_session", default=None
)


class AgentSession:
    """Tracks a complete agent conversation as an OTel root span.

    All API calls made within this context manager are attributed to this
    session, enabling per-session cost tracking, trace grouping, and metadata.
    """

    def __init__(
        self,
        name: str,
        customer_id: str | None,
        tags: list[str],
        metadata: dict[str, Any],
        config: "TraceConfig",
    ) -> None:
        self.name = name
        self.customer_id = customer_id
        self.tags = tags
        self.metadata = metadata
        self.config = config
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cache_read_tokens: int = 0
        self.total_cache_write_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.turn_count: int = 0
        self._span: Span | None = None
        self._token: contextvars.Token["AgentSession | None"] | None = None
        self._start_time: float = 0.0

    def __enter__(self) -> "AgentSession":
        tracer = otel_trace.get_tracer(_TRACER_NAME)
        self._span = tracer.start_span("claude.agent.session")
        self._span.set_attribute("claude.session.name", self.name)
        if self.customer_id and not self.config.sanitize:
            self._span.set_attribute("claude.session.customer_id", self.customer_id)
        if self.tags:
            self._span.set_attribute("claude.session.tags", ",".join(self.tags))
        for k, v in self.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                self._span.set_attribute(f"claude.session.{k}", v)
        self._token = _SESSION_CONTEXT_VAR.set(self)
        self._start_time = time.monotonic()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span is None:
            return
        self._span.set_attribute("claude.session.total_input_tokens", self.total_input_tokens)
        self._span.set_attribute("claude.session.total_output_tokens", self.total_output_tokens)
        self._span.set_attribute(
            "claude.session.total_cache_read_tokens", self.total_cache_read_tokens
        )
        self._span.set_attribute("claude.session.turn_count", self.turn_count)
        self._span.set_attribute(
            "claude.session.estimated_cost_usd", f"{self.total_cost_usd:.6f}"
        )
        if exc_type is not None:
            self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
        else:
            self._span.set_status(Status(StatusCode.OK))
        self._span.end()
        if self._token is not None:
            _SESSION_CONTEXT_VAR.reset(self._token)

    def _record_turn(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read: int,
        cache_write: int,
        cost_usd: float,
    ) -> None:
        """Called by the instrumentation layer after each API call."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read
        self.total_cache_write_tokens += cache_write
        self.total_cost_usd += cost_usd
        self.turn_count += 1


def current_session() -> "AgentSession | None":
    """Return the active AgentSession from context, or None."""
    return _SESSION_CONTEXT_VAR.get()
