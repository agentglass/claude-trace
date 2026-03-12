"""Type stubs for claude_trace public API."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from claude_trace._config import TraceConfig as TraceConfig
from claude_trace._session import AgentSession as AgentSession
from opentelemetry.sdk.trace import TracerProvider

# Re-exported from Rust extension
class CostBreakdown:
    input_usd: float
    output_usd: float
    cache_read_usd: float
    cache_write_usd: float
    total_usd: float
    def __add__(self, other: CostBreakdown) -> CostBreakdown: ...
    def __repr__(self) -> str: ...

class TraceSnapshot:
    trace_id: str
    tool_calls: list[str]
    turn_count: int
    total_tokens: int
    stop_reason: str
    def __init__(
        self,
        trace_id: str,
        tool_calls: list[str],
        turn_count: int,
        total_tokens: int,
        stop_reason: str,
    ) -> None: ...
    def __repr__(self) -> str: ...

class TraceDiff:
    added_tool_calls: list[str]
    removed_tool_calls: list[str]
    token_delta: int
    turn_delta: int
    def is_equivalent(self) -> bool: ...
    def summary(self) -> str: ...
    def assert_equivalent(self) -> None: ...
    def __repr__(self) -> str: ...

def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> CostBreakdown: ...

__version__: str

def instrument(
    *,
    config: TraceConfig | None = None,
    tracer_provider: TracerProvider | None = None,
) -> None: ...

def uninstrument() -> None: ...

def session(
    name: str,
    *,
    customer_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    config: TraceConfig | None = None,
) -> AbstractContextManager[AgentSession]: ...

def compare(snapshot_a: TraceSnapshot, snapshot_b: TraceSnapshot) -> TraceDiff: ...
