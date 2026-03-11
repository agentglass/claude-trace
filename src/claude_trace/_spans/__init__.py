"""Span management classes for the claude-trace span hierarchy."""

from claude_trace._spans.session import AgentSession
from claude_trace._spans.tool import ToolInvocation
from claude_trace._spans.turn import AgentTurn

__all__ = ["AgentSession", "AgentTurn", "ToolInvocation"]
