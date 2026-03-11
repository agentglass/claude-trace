"""
Typed span attribute name constants.

This module re-exports the frozen dataclass instances from ``_semconv.claude``
as module-level singletons, providing a convenient import path for internal use::

    from claude_trace._spans.attributes import SESSION, TURN, TOOL, COST

    span.set_attribute(SESSION.SESSION_ID, "sess_abc")
    span.set_attribute(TURN.TURN_INDEX, 0)
    span.set_attribute(TOOL.TOOL_NAME, "bash")
    span.set_attribute(COST.TOTAL_COST_USD, "0.01234")
"""

from __future__ import annotations

from claude_trace._semconv.claude import (
    CostAttributes,
    SessionAttributes,
    ToolAttributes,
    TurnAttributes,
)

# Singleton instances — frozen dataclasses, safe to share
SESSION: SessionAttributes = SessionAttributes()
TURN: TurnAttributes = TurnAttributes()
TOOL: ToolAttributes = ToolAttributes()
COST: CostAttributes = CostAttributes()

__all__ = ["COST", "SESSION", "TOOL", "TURN"]
