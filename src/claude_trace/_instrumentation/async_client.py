"""
Async Anthropic client instrumentation.

Monkey-patches ``anthropic.AsyncAnthropic.messages.create`` to inject
claude-trace OTel spans transparently for async usage patterns.

Handles:
    - Non-streaming async responses (``await client.messages.create(...)``)
    - Async streaming (``async for event in await client.messages.create(stream=True)``)
    - Async context manager streaming (``async with client.messages.stream(...) as s:``)
    - Full span hierarchy: session → turn → tool
    - ``contextvars`` propagation across async tasks

Implementation notes:
    - We patch ``AsyncMessages.create`` (the async resource class).
    - For async streaming, we use an ``AsyncGenerator`` wrapper that records
      the first-token timestamp and ends the turn span after the stream closes.
    - Context variables propagate correctly because OTel uses ``contextvars``
      internally and asyncio preserves them per-task.
"""

from __future__ import annotations

import functools
from typing import Any, AsyncIterator, Optional

from claude_trace._spans.session import AgentSession
from claude_trace._spans.tool import ToolInvocation
from claude_trace._spans.turn import AgentTurn
from claude_trace.config import TraceConfig
from claude_trace.context import get_current_session

_PATCHED_ATTR = "_claude_trace_original_async"


def _extract_tool_use_blocks(content: list[Any]) -> list[dict[str, Any]]:
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
    turn_index = session._turn_count if session is not None else 0
    return AgentTurn(
        turn_index=turn_index,
        config=config,
        session=session,
        is_streaming=is_streaming,
    )


class _AsyncTracedStream:
    """Wraps an async streaming response for span recording.

    Implements both:
    - ``async for event in stream:`` (for ``create(stream=True)``)
    - ``async with client.messages.stream(...) as s:`` context manager
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

    # Async context manager protocol
    async def __aenter__(self) -> "_AsyncTracedStream":
        if hasattr(self._raw, "__aenter__"):
            await self._raw.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if hasattr(self._raw, "__aexit__"):
            await self._raw.__aexit__(*args)

    # Async iterator protocol
    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        try:
            async for event in self._raw:
                if not self._first_token_seen:
                    event_type = getattr(event, "type", "")
                    if event_type in ("content_block_delta", "content_block_start"):
                        self._turn.mark_first_token()
                        self._first_token_seen = True
                yield event
        except Exception as exc:
            await self._turn.__aexit__(type(exc), exc, None)
            raise
        else:
            await self._turn.__aexit__(None, None, None)

    async def get_final_message(self) -> Any:
        """Retrieve the final accumulated message and record it on the span."""
        msg = await self._raw.get_final_message()
        self._turn.record_response(msg)
        return msg

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._raw.text_stream

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def _wrap_async_create(original: Any, config: TraceConfig) -> Any:
    """Return a patched async version of ``messages.create``."""

    @functools.wraps(original)
    async def patched_create(*args: Any, **kwargs: Any) -> Any:
        session = get_current_session()
        is_streaming = bool(kwargs.get("stream", False))
        turn = _build_turn(config, session, is_streaming)
        await turn.__aenter__()

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
            result = await original(*args, **kwargs)
        except Exception as exc:
            await turn.__aexit__(type(exc), exc, None)
            raise

        if is_streaming:
            return _AsyncTracedStream(result, turn, config)

        # Non-streaming: record response and create tool spans immediately
        turn.record_response(result)
        _record_async_tool_spans(result, turn, config)
        await turn.__aexit__(None, None, None)
        return result

    return patched_create


def _record_async_tool_spans(response: Any, turn: AgentTurn, config: TraceConfig) -> None:
    """Create instantaneous tool-marker spans for tool_use blocks (non-streaming)."""
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
            pass


def instrument_async(config: TraceConfig) -> bool:
    """Monkey-patch ``anthropic.resources.messages.AsyncMessages.create``.

    Returns ``True`` if patching was applied, ``False`` if already patched.
    """
    try:
        from anthropic.resources.messages import AsyncMessages
    except ImportError:
        return False

    if hasattr(AsyncMessages.create, _PATCHED_ATTR):
        return False

    original = AsyncMessages.create
    patched = _wrap_async_create(original, config)
    setattr(patched, _PATCHED_ATTR, original)
    AsyncMessages.create = patched  # type: ignore[method-assign]
    return True


def uninstrument_async() -> bool:
    """Restore the original ``AsyncMessages.create``.

    Returns ``True`` if uninstrumentation was applied, ``False`` if not patched.
    """
    try:
        from anthropic.resources.messages import AsyncMessages
    except ImportError:
        return False

    patched = AsyncMessages.create
    original = getattr(patched, _PATCHED_ATTR, None)
    if original is None:
        return False

    AsyncMessages.create = original  # type: ignore[method-assign]
    return True
