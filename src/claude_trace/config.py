"""
TraceConfig: Configuration for claude-trace instrumentation.

All fields support environment variable overrides via CLAUDE_TRACE_* prefixed
variables, enabling zero-code configuration in containerised deployments.

Environment variables:
    CLAUDE_TRACE_ENABLED            - "true"/"false" (default: "true")
    CLAUDE_TRACE_SERVICE_NAME       - OTel service.name (default: "claude-agent")
    CLAUDE_TRACE_CAPTURE_INPUTS     - "true"/"false" (default: "false")
    CLAUDE_TRACE_CAPTURE_OUTPUTS    - "true"/"false" (default: "false")
    CLAUDE_TRACE_MAX_ATTRIBUTE_LEN  - int (default: 1024)
    CLAUDE_TRACE_RECORD_COSTS       - "true"/"false" (default: "true")
    CLAUDE_TRACE_TRACER_PROVIDER    - ignored (set programmatically only)

Usage::

    # Zero-config: reads from environment and uses global TracerProvider
    config = TraceConfig()

    # Fully explicit:
    config = TraceConfig(
        service_name="my-agent",
        capture_inputs=True,
        capture_outputs=True,
        record_costs=True,
        max_attribute_length=2048,
    )

    claude_trace.instrument(config=config)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from opentelemetry.sdk.trace import TracerProvider


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable. Accepts 'true'/'1'/'yes' as True."""
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to ``default``."""
    val = os.environ.get(name, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    """Read a string environment variable, falling back to ``default``."""
    return os.environ.get(name, default).strip() or default


@dataclass
class TraceConfig:
    """Full configuration for claude-trace instrumentation.

    Attributes:
        enabled: Master switch. When False, instrumentation is a no-op.
            Env: CLAUDE_TRACE_ENABLED

        service_name: OTel ``service.name`` resource attribute added to all spans.
            Env: CLAUDE_TRACE_SERVICE_NAME

        capture_inputs: When True, store the full message list (user messages,
            tool results) as span attributes. WARNING: may capture PII.
            Env: CLAUDE_TRACE_CAPTURE_INPUTS

        capture_outputs: When True, store the full model response text as a
            span attribute. WARNING: may capture PII.
            Env: CLAUDE_TRACE_CAPTURE_OUTPUTS

        record_costs: When True, compute token cost estimates and attach them
            as ``claude.cost.*`` attributes to session and turn spans.
            Env: CLAUDE_TRACE_RECORD_COSTS

        max_attribute_length: Maximum character length for string span attributes.
            Values longer than this are truncated with a ``...`` suffix.
            Env: CLAUDE_TRACE_MAX_ATTRIBUTE_LEN

        tracer_provider: The OTel TracerProvider to use. When None (default),
            the globally-registered provider is used. Can only be set
            programmatically (not via environment variable).

        session_id_header: HTTP header name to read a session ID from in web
            frameworks. When set, claude-trace will try to pull the session ID
            from the current OTel baggage under this key.
            Env: CLAUDE_TRACE_SESSION_ID_HEADER

        span_name_prefix: Prefix for all span names. Defaults to "claude".
            Changing this allows multiple independent instrumented libraries
            to coexist without span name collisions.
            Env: CLAUDE_TRACE_SPAN_NAME_PREFIX

        propagate_baggage: When True, propagate W3C TraceContext + Baggage from
            the current context into each API call's attributes.
            Env: CLAUDE_TRACE_PROPAGATE_BAGGAGE
    """

    enabled: bool = field(
        default_factory=lambda: _env_bool("CLAUDE_TRACE_ENABLED", default=True)
    )

    service_name: str = field(
        default_factory=lambda: _env_str("CLAUDE_TRACE_SERVICE_NAME", default="claude-agent")
    )

    capture_inputs: bool = field(
        default_factory=lambda: _env_bool("CLAUDE_TRACE_CAPTURE_INPUTS", default=False)
    )

    capture_outputs: bool = field(
        default_factory=lambda: _env_bool("CLAUDE_TRACE_CAPTURE_OUTPUTS", default=False)
    )

    record_costs: bool = field(
        default_factory=lambda: _env_bool("CLAUDE_TRACE_RECORD_COSTS", default=True)
    )

    max_attribute_length: int = field(
        default_factory=lambda: _env_int("CLAUDE_TRACE_MAX_ATTRIBUTE_LEN", default=1024)
    )

    tracer_provider: Optional[TracerProvider] = field(default=None, repr=False)

    session_id_header: str = field(
        default_factory=lambda: _env_str(
            "CLAUDE_TRACE_SESSION_ID_HEADER", default="x-claude-session-id"
        )
    )

    span_name_prefix: str = field(
        default_factory=lambda: _env_str("CLAUDE_TRACE_SPAN_NAME_PREFIX", default="claude")
    )

    propagate_baggage: bool = field(
        default_factory=lambda: _env_bool("CLAUDE_TRACE_PROPAGATE_BAGGAGE", default=True)
    )

    def truncate(self, value: str) -> str:
        """Truncate ``value`` to ``max_attribute_length``, adding ``...`` suffix."""
        if len(value) <= self.max_attribute_length:
            return value
        return value[: self.max_attribute_length - 3] + "..."

    def span_name(self, suffix: str) -> str:
        """Build a full span name by joining prefix and suffix.

        Example::

            config.span_name("session")  # -> "claude.session"
            config.span_name("turn")     # -> "claude.turn"
        """
        return f"{self.span_name_prefix}.{suffix}"

    @classmethod
    def from_env(cls) -> "TraceConfig":
        """Construct a TraceConfig reading all values from environment variables.

        This is equivalent to ``TraceConfig()`` (the default constructor already
        reads from environment), but is provided as an explicit factory method
        for clarity in application code.
        """
        return cls()

    def replace(self, **kwargs: object) -> "TraceConfig":
        """Return a copy of this config with the given fields replaced.

        Usage::

            base = TraceConfig()
            debug_cfg = base.replace(capture_inputs=True, capture_outputs=True)
        """
        import dataclasses

        return dataclasses.replace(self, **kwargs)  # type: ignore[arg-type]
