"""
Claude Agent SDK Semantic Conventions for OpenTelemetry.

This module defines all span attribute names following the pattern:
    claude.{category}.{name}

These conventions establish a shared vocabulary for observability tooling,
enabling consistent dashboards, alerts, and queries across all claude-trace
instrumented applications.

Attribute categories:
    - session:  Attributes on the top-level agent session span
    - turn:     Attributes on each agentic loop iteration (one LLM call)
    - tool:     Attributes on individual tool invocation spans
    - cost:     Financial cost breakdown attributes (on session and turn spans)

Design principles:
    1. All names are lowercase dot-separated strings (OTel convention)
    2. Each constant has a full docstring explaining legal values and semantics
    3. Enums are provided for attributes with a fixed set of legal values
    4. All classes are frozen dataclasses to prevent mutation

Usage::

    from claude_trace._semconv.claude import SessionAttributes, TurnAttributes

    span.set_attribute(SessionAttributes.SESSION_ID, "sess_abc123")
    span.set_attribute(TurnAttributes.TURN_INDEX, 3)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StopReason(str, Enum):
    """Legal values for ``claude.turn.stop_reason``.

    Maps directly to the ``stop_reason`` field returned by the Anthropic API.
    """

    END_TURN = "end_turn"
    """Model finished generating naturally."""

    MAX_TOKENS = "max_tokens"
    """Response was truncated because the token limit was reached."""

    TOOL_USE = "tool_use"
    """Model emitted one or more tool_use blocks; the agent loop must continue."""

    STOP_SEQUENCE = "stop_sequence"
    """A stop sequence matched before the model finished generating."""

    ERROR = "error"
    """The API returned an error; see ``claude.turn.error_type`` for details."""


class ContentBlockType(str, Enum):
    """Legal values for ``claude.turn.content_block_types`` array attribute."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"
    DOCUMENT = "document"


class ToolStatus(str, Enum):
    """Legal values for ``claude.tool.status``."""

    SUCCESS = "success"
    """Tool executed successfully and returned a result."""

    ERROR = "error"
    """Tool raised an exception or returned an error result."""

    TIMEOUT = "timeout"
    """Tool execution exceeded the configured timeout."""

    CANCELLED = "cancelled"
    """Tool was cancelled (e.g. by the agent stopping mid-loop)."""


class SessionStatus(str, Enum):
    """Legal values for ``claude.session.status``."""

    RUNNING = "running"
    """Session is actively processing."""

    COMPLETED = "completed"
    """Session completed successfully (model reached end_turn)."""

    ERROR = "error"
    """Session terminated due to an error."""

    CANCELLED = "cancelled"
    """Session was cancelled externally."""

    MAX_TURNS_REACHED = "max_turns_reached"
    """Session stopped because max_turns was reached."""


@dataclass(frozen=True)
class SessionAttributes:
    """Span attributes for the top-level agent session span.

    The session span covers the full lifecycle of a single call to
    ``claude.run()`` or an equivalent agent loop. It is the root span
    in the claude-trace span hierarchy::

        claude.session  (root)
        └── claude.turn[0]
            ├── claude.tool[bash_0]
            └── claude.tool[bash_1]
        └── claude.turn[1]
            └── ...

    All monetary amounts are in USD.
    """

    SESSION_ID: str = "claude.session.id"
    """Unique identifier for this agent session.

    Format: opaque string (typically prefixed ``sess_``).
    Example: ``"sess_01HV2Y3K8P9Q0R1S2T3U4V5W6X"``
    """

    SYSTEM_PROMPT_HASH: str = "claude.session.system_prompt_hash"
    """SHA-256 hex digest of the system prompt (first 16 chars).

    Enables grouping sessions by system prompt without storing PII.
    Example: ``"a3f2b8c1d4e5f6a7"``
    """

    SYSTEM_PROMPT_LENGTH: str = "claude.session.system_prompt_length"
    """Character length of the system prompt.

    Type: int
    Example: ``4096``
    """

    MODEL: str = "claude.session.model"
    """Model identifier used for this session.

    Example: ``"claude-opus-4-5"``
    """

    MAX_TURNS: str = "claude.session.max_turns"
    """Maximum number of agentic loop turns configured.

    Type: int
    Example: ``10``
    """

    TOTAL_TURNS: str = "claude.session.total_turns"
    """Actual number of agentic loop turns executed.

    Type: int. Set when the session span ends.
    Example: ``4``
    """

    STATUS: str = "claude.session.status"
    """Final status of the session.

    Legal values: see ``SessionStatus`` enum.
    Example: ``"completed"``
    """

    CUSTOMER_ID: str = "claude.session.customer_id"
    """Optional customer/tenant identifier for cost attribution.

    Example: ``"customer_acme_corp"``
    """

    TAGS: str = "claude.session.tags"
    """Comma-separated list of user-defined tags for filtering.

    Example: ``"production,region:us-east-1,feature:summarization"``
    """

    TOTAL_INPUT_TOKENS: str = "claude.session.total_input_tokens"
    """Cumulative input tokens across all turns.

    Type: int. Updated at session end.
    Example: ``12450``
    """

    TOTAL_OUTPUT_TOKENS: str = "claude.session.total_output_tokens"
    """Cumulative output tokens across all turns.

    Type: int. Updated at session end.
    Example: ``3201``
    """

    TOTAL_CACHE_READ_TOKENS: str = "claude.session.total_cache_read_tokens"
    """Cumulative cache-read tokens across all turns.

    Prompt caching re-uses previously computed KV cache. These tokens
    are billed at a discount compared to full input tokens.

    Type: int. Updated at session end.
    Example: ``8900``
    """

    TOTAL_CACHE_CREATION_TOKENS: str = "claude.session.total_cache_creation_tokens"
    """Cumulative cache-creation tokens across all turns.

    Cache creation tokens are billed at a premium on the first request
    that populates the cache.

    Type: int. Updated at session end.
    Example: ``2100``
    """

    TOTAL_COST_USD: str = "claude.session.total_cost_usd"
    """Total estimated USD cost for the session.

    Type: float (stored as string for OTel compatibility).
    Example: ``"0.04523"``
    """

    TOOL_NAMES: str = "claude.session.tool_names"
    """Comma-separated list of distinct tool names invoked during the session.

    Example: ``"bash,read_file,web_search"``
    """

    TOTAL_TOOL_CALLS: str = "claude.session.total_tool_calls"
    """Total number of tool invocations across all turns.

    Type: int. Updated at session end.
    Example: ``7``
    """


@dataclass(frozen=True)
class TurnAttributes:
    """Span attributes for a single agentic loop turn.

    A turn spans exactly one call to ``anthropic.messages.create()``.
    It begins when the request is sent and ends when the full response
    (including streamed chunks) has been received.

    Turn spans are children of the session span.
    """

    TURN_INDEX: str = "claude.turn.index"
    """Zero-based index of this turn within the session.

    Type: int
    Example: ``0``  (first turn), ``3`` (fourth turn)
    """

    MODEL: str = "claude.turn.model"
    """Exact model identifier returned by the API for this turn.

    May differ from the session-level model if model routing is used.
    Example: ``"claude-sonnet-4-6-20251101"``
    """

    STOP_REASON: str = "claude.turn.stop_reason"
    """Why the model stopped generating.

    Legal values: see ``StopReason`` enum.
    Example: ``"tool_use"``
    """

    INPUT_TOKENS: str = "claude.turn.input_tokens"
    """Input tokens billed for this API call.

    Type: int
    Example: ``5230``
    """

    OUTPUT_TOKENS: str = "claude.turn.output_tokens"
    """Output tokens billed for this API call.

    Type: int
    Example: ``842``
    """

    CACHE_READ_TOKENS: str = "claude.turn.cache_read_tokens"
    """Cache-read tokens for this API call.

    Type: int
    Example: ``3100``
    """

    CACHE_CREATION_TOKENS: str = "claude.turn.cache_creation_tokens"
    """Cache-creation tokens for this API call.

    Type: int
    Example: ``2100``
    """

    TOOL_USE_COUNT: str = "claude.turn.tool_use_count"
    """Number of tool_use blocks in the model's response.

    Type: int. 0 means stop_reason is ``end_turn`` or ``max_tokens``.
    Example: ``2``
    """

    TOOL_NAMES: str = "claude.turn.tool_names"
    """Comma-separated tool names invoked in this turn.

    Example: ``"bash,read_file"``
    """

    CONTENT_BLOCK_TYPES: str = "claude.turn.content_block_types"
    """Comma-separated content block types in the response.

    Example: ``"text,tool_use"``
    """

    TEXT_CONTENT_LENGTH: str = "claude.turn.text_content_length"
    """Total character length of all text blocks in the response.

    Useful for detecting unexpectedly verbose or truncated responses.
    Type: int
    Example: ``1024``
    """

    IS_STREAMING: str = "claude.turn.is_streaming"
    """Whether this API call used the streaming response mode.

    Type: bool
    Example: ``True``
    """

    REQUEST_ID: str = "claude.turn.request_id"
    """Anthropic API request ID from the ``x-request-id`` response header.

    Enables correlation with Anthropic support tickets.
    Example: ``"req_01HV2Y3K8P9Q0R1S2T3U4V5W6X"``
    """

    LATENCY_MS: str = "claude.turn.latency_ms"
    """End-to-end latency in milliseconds for this API call.

    For streaming, this is the time from request send to last chunk.
    Type: float
    Example: ``2341.7``
    """

    TIME_TO_FIRST_TOKEN_MS: str = "claude.turn.time_to_first_token_ms"
    """Milliseconds from request send to first token received (streaming only).

    Type: float. Only present when ``is_streaming`` is True.
    Example: ``312.4``
    """

    ERROR_TYPE: str = "claude.turn.error_type"
    """Exception class name if the API call failed.

    Example: ``"anthropic.RateLimitError"``
    """

    ERROR_MESSAGE: str = "claude.turn.error_message"
    """Error message if the API call failed (truncated to 500 chars).

    Example: ``"Rate limit exceeded: 429 Too Many Requests"``
    """

    COST_USD: str = "claude.turn.cost_usd"
    """Estimated USD cost for this individual turn.

    Type: float (stored as string for OTel compatibility).
    Example: ``"0.01234"``
    """


@dataclass(frozen=True)
class ToolAttributes:
    """Span attributes for a single tool invocation.

    Each tool_use block in a model response generates a child span
    under the turn span. The span begins when the tool function is
    called and ends when it returns (or raises).

    Tool spans are children of turn spans.
    """

    TOOL_USE_ID: str = "claude.tool.use_id"
    """Anthropic-assigned ID for this specific tool_use block.

    Format: ``toolu_XXXX``. Correlates with the tool_result sent back.
    Example: ``"toolu_01A2B3C4D5E6F7G8H9I0J1K2"``
    """

    TOOL_NAME: str = "claude.tool.name"
    """Name of the tool as defined in the tools parameter.

    Example: ``"bash"``
    """

    TURN_INDEX: str = "claude.tool.turn_index"
    """Turn index this tool call belongs to.

    Duplicates the parent turn's index for easier filtering in backends
    that flatten span trees.
    Type: int
    Example: ``2``
    """

    CALL_INDEX: str = "claude.tool.call_index"
    """Zero-based index of this tool call within the turn.

    When a model emits multiple tool_use blocks in one response,
    this distinguishes them.
    Type: int
    Example: ``1``
    """

    INPUT_HASH: str = "claude.tool.input_hash"
    """SHA-256 hex digest of the JSON-serialized tool input (first 16 chars).

    Enables detecting duplicate calls without storing potentially
    sensitive input data.
    Example: ``"b7e3f2a1c8d9e0f1"``
    """

    INPUT_SIZE_BYTES: str = "claude.tool.input_size_bytes"
    """Byte length of the JSON-serialized tool input.

    Type: int
    Example: ``256``
    """

    OUTPUT_SIZE_BYTES: str = "claude.tool.output_size_bytes"
    """Byte length of the string representation of the tool output.

    Type: int. Set when the tool call completes.
    Example: ``1024``
    """

    STATUS: str = "claude.tool.status"
    """Outcome of the tool invocation.

    Legal values: see ``ToolStatus`` enum.
    Example: ``"success"``
    """

    ERROR_TYPE: str = "claude.tool.error_type"
    """Exception class name if the tool raised an exception.

    Only present when ``status`` is ``"error"``.
    Example: ``"FileNotFoundError"``
    """

    ERROR_MESSAGE: str = "claude.tool.error_message"
    """Truncated error message (max 500 chars).

    Only present when ``status`` is ``"error"``.
    Example: ``"No such file or directory: '/tmp/missing.txt'"``
    """

    LATENCY_MS: str = "claude.tool.latency_ms"
    """Wall-clock milliseconds from tool call start to finish.

    Type: float
    Example: ``47.3``
    """

    IS_PARALLEL: str = "claude.tool.is_parallel"
    """True if this tool was invoked in parallel with other tools in the same turn.

    Type: bool. True when turn's tool_use_count > 1.
    Example: ``True``
    """


@dataclass(frozen=True)
class CostAttributes:
    """Financial cost breakdown attributes.

    These attributes appear on both session and turn spans to enable
    cost analysis at both the granular (per-turn) and aggregate
    (per-session) level.

    All monetary values are in USD. They are stored as strings to
    avoid floating-point precision loss in OTel backends that coerce
    float attributes to 64-bit IEEE 754 doubles.

    Pricing source: Anthropic pricing page (verified 2025-Q4).
    """

    INPUT_COST_USD: str = "claude.cost.input_usd"
    """Cost attributable to input tokens at the standard rate.

    Formula: ``input_tokens * model_input_price_per_million / 1_000_000``
    Example: ``"0.01500"``
    """

    OUTPUT_COST_USD: str = "claude.cost.output_usd"
    """Cost attributable to output tokens.

    Formula: ``output_tokens * model_output_price_per_million / 1_000_000``
    Example: ``"0.07500"``
    """

    CACHE_READ_COST_USD: str = "claude.cost.cache_read_usd"
    """Cost attributable to cache-read tokens (discounted rate).

    Cache reads are billed at ~10% of the standard input token price.
    Formula: ``cache_read_tokens * model_cache_read_price_per_million / 1_000_000``
    Example: ``"0.00150"``
    """

    CACHE_CREATION_COST_USD: str = "claude.cost.cache_creation_usd"
    """Cost attributable to cache-creation tokens (premium rate).

    Cache creation is billed at ~125% of the standard input token price.
    Formula: ``cache_creation_tokens * model_cache_write_price_per_million / 1_000_000``
    Example: ``"0.01875"``
    """

    TOTAL_COST_USD: str = "claude.cost.total_usd"
    """Sum of all cost components for this span.

    Formula: ``input_cost + output_cost + cache_read_cost + cache_creation_cost``
    Example: ``"0.11025"``
    """

    MODEL: str = "claude.cost.model"
    """Model identifier used to look up pricing.

    Stored here so cost records remain self-contained even if the
    session/turn model attribute is missing.
    Example: ``"claude-opus-4-5"``
    """

    PRICING_TIER: str = "claude.cost.pricing_tier"
    """Pricing tier applied (for future volume discount support).

    Current legal values: ``"standard"``, ``"volume_1"``, ``"volume_2"``
    Example: ``"standard"``
    """
