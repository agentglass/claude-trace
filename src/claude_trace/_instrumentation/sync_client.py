"""
Sync Anthropic client instrumentation.

Monkey-patches ``anthropic.Anthropic.messages.create`` to inject
claude-trace OTel spans transparently.

The wrapper handles:
    - Non-streaming responses (``Message`` objects)
    - Streaming responses (``MessageStreamManager`` / ``Stream``)
    - Error propagation and span error recording
    - Tool call extraction from both response types
    - Correct span parent hierarchy via active session context

Implementation notes:
    - We patch at the ``Messages`` resource class level (not the client
      instance) so that all Anthropic client instances are covered.
    - The original method is stored as ``_claude_trace_original`` to allow
      clean uninstrumentation.
    - For streaming, we wrap the returned iterator/context manager so that
      span recording happens after the stream is fully consumed.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Iterator, Optional

import anthropic
from opentelemetry import trace

from claude_trace._spans.session import AgentSession
from claude_trace._spans.tool import ToolInvocation
from claude_trace._spans.turn import AgentTurn
from claude_trace.config import TraceConfig
from claude_trace.context import get_current_session

_PATCHED_ATTR = "_claude_trace_original_sync"


def _extract_tool_use_blocks(content: list[Any]) -> list[dict[str, Any]]:
    """Return a list of tool_use dicts from a message content list."""
    return [
        {
            "id": getattr(b, "id", ""),
            "name": getattr(b, "name", ""),
            "input": getattr(b, "input", {}),
        }
        for b in content
        if getattr(b, "type", "") == "tool_use"
    ]


def _build_turn(
    config: TraceConfig,
    session: Optional[AgentSession],
    is_streaming: bool,
) -> AgentTurn:
    """Create an ``AgentTurn`` with the correct turn index."""
    turn_index = session._turn_count if session is not None else 0
    return AgentTurn(
        turn_index=turn_index,
        config=config,
        session=session,
        is_streaming=is_streaming,
    )


class _TracedStream:
    """Wraps a sync streaming response to record span data on completion.

    Supports both iteration (``for event in stream``) and the
    ``with client.messages.stream(...) as s:`` context manager protocol.
    """

    def __init__(
        self,
        raw_stream: Any,
        turn: AgentTurn,
        config: TraceConfig,
    ) -> None:
        self._raw = raw_stream
        self._turn = turn
        self._config = config
        self._first_token_seen = False

    # Context manager protocol (for stream() API)
    def __enter__(self) -> "_TracedStream":
        if hasattr(self._raw, "__enter__"):
            self._raw.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        if hasattr(self._raw, "__exit__"):
            self._raw.__exit__(*args)

    # Iterator protocol (for create(stream=True) API)
    def __iter__(self) -> Iterator[Any]:
        try:
            for event in self._raw:
                if not self._first_token_seen:
                    event_type = getattr(event, "type", "")
                    if event_type in ("content_block_delta", "content_block_start"):
                        self._turn.mark_first_token()
                        self._first_token_seen = True
                yield event
        except Exception as exc:
            self._turn.__exit__(type(exc), exc, None)
            raise
        else:
            self._turn.__exit__(None, None, None)

    # get_final_message() for stream context manager API
    def get_final_message(self) -> Any:
        msg = self._raw.get_final_message()
        self._turn.record_response(msg)
        return msg

    # text_stream property
    @property
    def text_stream(self) -> Iterator[str]:
        return self._raw.text_stream

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def _wrap_create(original: Any, config: TraceConfig) -> Any:
    """Return a patched version of ``messages.create``."""

    @functools.wraps(original)
    def patched_create(*args: Any, **kwargs: Any) -> Any:
        session = get_current_session()
        is_streaming = bool(kwargs.get("stream", False))
        turn = _build_turn(config, session, is_streaming)
        turn.__enter__()

        # Optionally capture input messages
        if config.capture_inputs:
            messages = kwargs.get("messages", [])
            import json
            try:
                raw = json.dumps(messages, default=str)
                turn.span.set_attribute("claude.turn.input_messages", config.truncate(raw))
            except (TypeError, ValueError):
                pass

        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            turn.__exit__(type(exc), exc, None)
            raise

        if is_streaming:
            # Wrap the stream; the turn ends when iteration completes
            return _TracedStream(result, turn, config)

        # Non-streaming: record response immediately
        turn.record_response(result)

        # Spawn child tool spans (zero-latency, informational)
        _record_tool_spans(result, turn, config)

        turn.__exit__(None, None, None)
        return result

    return patched_create


def _record_tool_spans(response: Any, turn: AgentTurn, config: TraceConfig) -> None:
    """Create tool spans for each tool_use block in the response.

    These spans are created synchronously after the API call; they reflect
    the tool calls the model *requested* rather than the actual execution
    (actual execution timing is captured when your tool functions run).

    Each span is immediately ended so it appears as an instantaneous marker.
    """
    content = getattr(response, "content", []) or []
    tool_blocks = _extract_tool_use_blocks(content)
    is_parallel = len(tool_blocks) > 1

    for idx, block in enumerate(tool_blocks):
        with ToolInvocation(
            tool_name=block.get("name", "unknown"),
            tool_use_id=block.get("id", f"toolu_unknown_{idx}"),
            turn_index=turn.turn_index,
            call_index=idx,
            config=config,
            parent_turn=turn,
            tool_input=block.get("input", {}),
            is_parallel=is_parallel,
        ):
            pass  # Span records the tool_use block; execution timing tracked separately


def instrument_sync(config: TraceConfig) -> bool:
    """Monkey-patch ``anthropic.resources.messages.Messages.create``.

    Returns ``True`` if patching was applied, ``False`` if already patched.
    """
    try:
        from anthropic.resources.messages import Messages
    except ImportError:
        return False

    if hasattr(Messages.create, _PATCHED_ATTR):
        return False  # Already instrumented

    original = Messages.create
    patched = _wrap_create(original, config)
    setattr(patched, _PATCHED_ATTR, original)
    Messages.create = patched  # type: ignore[method-assign]
    return True


def uninstrument_sync() -> bool:
    """Restore the original ``Messages.create``.

    Returns ``True`` if uninstrumentation was applied, ``False`` if not patched.
    """
    try:
        from anthropic.resources.messages import Messages
    except ImportError:
        return False

    patched = Messages.create
    original = getattr(patched, _PATCHED_ATTR, None)
    if original is None:
        return False

    Messages.create = original  # type: ignore[method-assign]
    return True
