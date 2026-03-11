"""
Context variable management for the current claude-trace session.

Uses Python's ``contextvars`` module so that concurrent async tasks each
maintain their own independent session context — no thread-local hacks needed.

The module exposes a simple procedural API::

    from claude_trace.context import get_current_session, set_current_session

    with session_span as sess:
        token = set_current_session(sess)
        try:
            ...  # code that calls anthropic SDK
        finally:
            reset_current_session(token)

The instrumentation layer reads ``get_current_session()`` inside the patched
``messages.create`` wrapper to attach turn spans as children of the session.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from claude_trace._spans.session import AgentSession


# The single ContextVar holding the active AgentSession (or None).
_current_session: ContextVar[Optional["AgentSession"]] = ContextVar(
    "claude_trace_current_session", default=None
)


def get_current_session() -> Optional["AgentSession"]:
    """Return the ``AgentSession`` active in the current context, or ``None``.

    This is safe to call from any thread or async task. Each concurrent
    context (asyncio task, thread pool thread, etc.) has its own value.

    Returns:
        The active ``AgentSession``, or ``None`` if no session is running.
    """
    return _current_session.get()


def set_current_session(session: "AgentSession") -> Token["AgentSession | None"]:
    """Set ``session`` as the active session in the current context.

    Returns a ``Token`` that must be passed to ``reset_current_session()``
    to restore the previous value.  Typically called by ``AgentSession.__enter__``.

    Args:
        session: The ``AgentSession`` to install.

    Returns:
        An opaque ``Token`` for use with ``reset_current_session()``.
    """
    return _current_session.set(session)


def reset_current_session(token: "Token[AgentSession | None]") -> None:
    """Restore the session context to the value it had before ``set_current_session``.

    Typically called in ``AgentSession.__exit__`` / ``__aexit__``.

    Args:
        token: The token returned by the corresponding ``set_current_session`` call.
    """
    _current_session.reset(token)


def clear_current_session() -> None:
    """Set the current session to ``None`` unconditionally.

    Convenience helper for test teardown.  Prefer ``reset_current_session``
    in production code to avoid inadvertently clearing a parent session.
    """
    _current_session.set(None)
