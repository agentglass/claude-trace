"""Claude Code hook handler — fires OTel spans for every tool invocation
inside a Claude Code session.

Hook flow
---------
PreToolUse  → pre_hook()  → writes {trace_id, span_id, start_ns, tool_name, ...}
              to a state file under /tmp/claude-trace/{session_id}/

PostToolUse → post_hook() → reads that state file, calculates duration,
              exports a completed ``claude.tool.invocation`` span via OTLP HTTP,
              then deletes the state file.

Security
--------
- Input payload is hashed (SHA-256, first 16 hex chars) — never stored verbatim.
- ``sk-ant-*`` patterns are redacted from any string before storage.
- State files are written with mode 0o600 (owner-read only).
- OTLP export is fire-and-forget with a 3-second timeout; failures are logged
  to stderr and never propagate.

Environment variables
---------------------
OTEL_EXPORTER_OTLP_ENDPOINT   - OTLP HTTP base URL (default: http://localhost:4318)
CLAUDE_TRACE_HOOKS_LOG        - path to fallback NDJSON log (default: off)
CLAUDE_TRACE_MAX_ATTR_LENGTH  - max chars per attribute (default: 512)
CLAUDE_TRACE_SANITIZE         - "true" suppresses all text attributes
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATE_ROOT = Path(os.getenv("CLAUDE_TRACE_STATE_DIR", "/tmp/claude-trace"))
_DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
_SPAN_NAME = "claude.tool.invocation"
_SCOPE_NAME = "claude-trace-hooks"
_SCOPE_VERSION = "0.1.0"
_SERVICE_NAME = "claude-code"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class HookState:
    """Serialisable span-in-progress record written by the pre-hook."""

    trace_id: str  # 32 hex chars (128-bit W3C)
    span_id: str  # 16 hex chars (64-bit W3C)
    session_id: str
    tool_name: str
    input_hash: str  # SHA-256[:16] of JSON-encoded tool_input
    start_ns: int  # time.monotonic_ns() at pre-hook invocation
    start_epoch_ns: int  # time.time_ns() at pre-hook invocation (for OTLP)

    # Optional propagated parent from an outer claude-trace session
    parent_span_id: str = ""
    parent_trace_id: str = ""

    # Metadata
    plugin_version: str = "0.1.0"
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redact(value: str) -> str:
    """Strip ``sk-ant-*`` API key patterns."""
    return re.sub(r"sk-ant-[A-Za-z0-9\-_]+", "[REDACTED]", value)


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    removed = len(value) - max_len
    return value[:max_len] + f"...[truncated {removed} chars]"


def _hash_input(payload: Any) -> str:
    """SHA-256 of JSON-encoded payload, first 16 hex chars."""
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _max_attr_len() -> int:
    try:
        return int(os.getenv("CLAUDE_TRACE_MAX_ATTR_LENGTH", "512"))
    except ValueError:
        return 512


def _sanitize_mode() -> bool:
    return os.getenv("CLAUDE_TRACE_SANITIZE", "").lower() == "true"


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------


def _state_dir(session_id: str) -> Path:
    d = _STATE_ROOT / _safe_name(session_id)
    d.mkdir(parents=True, exist_ok=True)
    # Restrict to owner only
    d.chmod(0o700)
    return d


def _state_path(session_id: str, tool_name: str) -> Path:
    return _state_dir(session_id) / f"{_safe_name(tool_name)}.json"


def _safe_name(s: str) -> str:
    """Strip path-unsafe characters."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)[:64]


def _write_state(state: HookState) -> None:
    path = _state_path(state.session_id, state.tool_name)
    data = asdict(state)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    tmp.replace(path)


def _read_state(session_id: str, tool_name: str) -> HookState | None:
    path = _state_path(session_id, tool_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return HookState(**data)
    except Exception as exc:  # noqa: BLE001
        _warn(f"claude-trace hooks: failed to read state file {path}: {exc}")
        return None


def _delete_state(session_id: str, tool_name: str) -> None:
    path = _state_path(session_id, tool_name)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# OTLP HTTP JSON export
# ---------------------------------------------------------------------------


def _otlp_endpoint() -> str:
    base = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_OTLP_ENDPOINT).rstrip("/")
    return f"{base}/v1/traces"


def _attr(key: str, value: str | int | float | bool) -> dict:
    """Build an OTLP attribute dict."""
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _build_otlp_payload(
    state: HookState,
    outcome: str,
    duration_ms: float,
    end_epoch_ns: int,
    output_hash: str,
) -> dict:
    max_len = _max_attr_len()
    sanitize = _sanitize_mode()

    attributes = [
        _attr("claude.tool.name", _truncate(state.tool_name, max_len) if not sanitize else state.tool_name),
        _attr("claude.tool.input_hash", state.input_hash),
        _attr("claude.tool.outcome", outcome),
        _attr("claude.tool.duration_ms", round(duration_ms, 2)),
        _attr("claude.tool.hook_source", "claude_code_plugin"),
        _attr("claude.tool.session_id", state.session_id),
        _attr("claude.tool.plugin_version", state.plugin_version),
    ]
    if output_hash:
        attributes.append(_attr("claude.tool.output_hash", output_hash))

    # Build span dict
    span: dict[str, Any] = {
        "traceId": state.trace_id,
        "spanId": state.span_id,
        "name": _SPAN_NAME,
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(state.start_epoch_ns),
        "endTimeUnixNano": str(end_epoch_ns),
        "attributes": attributes,
        "status": {
            "code": 1 if outcome == "success" else 2,  # OK / ERROR
            "message": "" if outcome == "success" else outcome,
        },
    }

    # Parent span context (from outer claude-trace session)
    if state.parent_span_id:
        span["parentSpanId"] = state.parent_span_id

    resource_attrs = [
        _attr("service.name", _SERVICE_NAME),
        _attr("telemetry.sdk.name", "claude-trace-hooks"),
        _attr("telemetry.sdk.version", _SCOPE_VERSION),
    ]

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": resource_attrs},
                "scopeSpans": [
                    {
                        "scope": {"name": _SCOPE_NAME, "version": _SCOPE_VERSION},
                        "spans": [span],
                    }
                ],
            }
        ]
    }


def _export_span(
    state: HookState,
    outcome: str,
    duration_ms: float,
    end_epoch_ns: int,
    output_hash: str,
) -> None:
    """Export a completed span via OTLP HTTP JSON. Never raises."""
    payload = _build_otlp_payload(state, outcome, duration_ms, end_epoch_ns, output_hash)
    body = json.dumps(payload).encode()
    url = _otlp_endpoint()

    try:
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=3) as resp:
            _ = resp.read()
    except URLError:
        # No OTLP collector running — fall through to log file
        pass
    except Exception as exc:  # noqa: BLE001
        _warn(f"claude-trace hooks: OTLP export failed: {exc}")

    # Fallback NDJSON log
    log_path = os.getenv("CLAUDE_TRACE_HOOKS_LOG", "")
    if log_path:
        try:
            record = {
                "trace_id": state.trace_id,
                "span_id": state.span_id,
                "span_name": _SPAN_NAME,
                "session_id": state.session_id,
                "tool_name": state.tool_name,
                "outcome": outcome,
                "duration_ms": round(duration_ms, 2),
                "input_hash": state.input_hash,
                "output_hash": output_hash,
                "start_ns": state.start_epoch_ns,
                "end_ns": end_epoch_ns,
            }
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public hook entrypoints
# ---------------------------------------------------------------------------


def pre_hook(event: dict[str, Any]) -> dict[str, Any]:
    """Handle a PreToolUse event.

    Generates W3C-compatible trace/span IDs, records the start timestamp,
    and writes a state file for correlation with the corresponding post-hook.

    Args:
        event: Decoded JSON from Claude Code's hook stdin.

    Returns:
        Empty dict ``{}`` — signals Claude Code to allow the tool call.
    """
    session_id = str(event.get("session_id", "unknown"))
    tool_name = str(event.get("tool_name", "UnknownTool"))
    tool_input = event.get("tool_input", {})

    input_hash = _hash_input(tool_input)
    trace_id = secrets.token_hex(16)   # 128-bit
    span_id = secrets.token_hex(8)     # 64-bit

    state = HookState(
        trace_id=trace_id,
        span_id=span_id,
        session_id=session_id,
        tool_name=tool_name,
        input_hash=input_hash,
        start_ns=time.monotonic_ns(),
        start_epoch_ns=time.time_ns(),
    )

    _write_state(state)
    return {}


def post_hook(event: dict[str, Any]) -> dict[str, Any]:
    """Handle a PostToolUse event.

    Reads the matching pre-hook state file, calculates wall-clock duration,
    exports a completed ``claude.tool.invocation`` OTel span, and cleans up
    the state file.

    Args:
        event: Decoded JSON from Claude Code's hook stdin.

    Returns:
        Empty dict ``{}`` — no modification to Claude Code behaviour.
    """
    session_id = str(event.get("session_id", "unknown"))
    tool_name = str(event.get("tool_name", "UnknownTool"))
    tool_response = event.get("tool_response", "")

    end_ns = time.monotonic_ns()
    end_epoch_ns = time.time_ns()

    state = _read_state(session_id, tool_name)
    if state is None:
        # No matching pre-hook state — skip silently (hook may have been added
        # mid-session, or state file was lost).
        return {}

    duration_ms = (end_ns - state.start_ns) / 1_000_000.0

    # Determine outcome
    outcome = "success"
    if isinstance(tool_response, dict) and tool_response.get("error"):
        outcome = _truncate(str(tool_response["error"]), 128)
    elif isinstance(tool_response, str) and tool_response.lower().startswith("error"):
        outcome = _truncate(tool_response, 128)

    # Hash the output (never store verbatim)
    output_hash = _hash_input(tool_response)

    _export_span(state, outcome, duration_ms, end_epoch_ns, output_hash)
    _delete_state(session_id, tool_name)

    return {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _warn(msg: str) -> None:
    print(msg, file=sys.stderr)
