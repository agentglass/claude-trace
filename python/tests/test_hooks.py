"""Tests for the Claude Code hook handler (Milestone 5).

TDD: RED → GREEN → REFACTOR

Tests cover:
  - pre_hook writes a state file with correct fields
  - post_hook reads state, exports span (stubbed), cleans up
  - Session ID isolation: different sessions don't collide
  - Input hashing: same input → same hash, different → different
  - API key redaction in tool inputs
  - Graceful handling of missing state (orphaned post-hook)
  - OTLP export payload structure
  - CLI entry point: pre/post dispatch
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect state files to a temp dir for each test."""
    monkeypatch.setenv("CLAUDE_TRACE_STATE_DIR", str(tmp_path / "hooks-state"))
    # Reload module to pick up new env var
    if "claude_trace._hooks" in sys.modules:
        del sys.modules["claude_trace._hooks"]
    return tmp_path


@pytest.fixture()
def hooks():  # noqa: ANN201
    """Fresh import of _hooks after env var isolation."""
    if "claude_trace._hooks" in sys.modules:
        del sys.modules["claude_trace._hooks"]
    import importlib
    import claude_trace._hooks as m  # noqa: PLC0415
    importlib.reload(m)
    return m


def make_pre_event(
    session_id: str = "sess-abc",
    tool_name: str = "Write",
    tool_input: dict[str, Any] | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": tool_input or {"file_path": "/tmp/test.txt", "content": "hello"},
    }


def make_post_event(
    session_id: str = "sess-abc",
    tool_name: str = "Write",
    tool_response: Any = "success",
) -> dict:
    return {
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_response": tool_response,
    }


# ---------------------------------------------------------------------------
# pre_hook tests
# ---------------------------------------------------------------------------


class TestPreHook:
    def test_returns_empty_dict(self, hooks) -> None:
        """pre_hook must return {} to allow the tool call."""
        result = hooks.pre_hook(make_pre_event())
        assert result == {}

    def test_writes_state_file(self, hooks, isolated_state_dir: Path) -> None:
        """pre_hook creates a state file under the state directory."""
        hooks.pre_hook(make_pre_event(session_id="sess-001", tool_name="Write"))
        state_files = list(isolated_state_dir.rglob("*.json"))
        assert len(state_files) == 1

    def test_state_file_permissions(self, hooks, isolated_state_dir: Path) -> None:
        """State file must be owner-read-write only (0o600)."""
        hooks.pre_hook(make_pre_event(session_id="sess-perm"))
        state_files = list(isolated_state_dir.rglob("*.json"))
        assert len(state_files) == 1
        mode = oct(state_files[0].stat().st_mode & 0o777)
        assert mode == oct(0o600), f"Expected 0o600, got {mode}"

    def test_state_contains_required_fields(self, hooks, isolated_state_dir: Path) -> None:
        """State file must contain all fields required by post_hook."""
        hooks.pre_hook(make_pre_event(session_id="sess-fields", tool_name="Bash"))
        state_files = list(isolated_state_dir.rglob("*.json"))
        data = json.loads(state_files[0].read_text())
        assert "trace_id" in data
        assert "span_id" in data
        assert "session_id" in data
        assert "tool_name" in data
        assert "input_hash" in data
        assert "start_ns" in data
        assert "start_epoch_ns" in data

    def test_trace_id_is_128bit_hex(self, hooks, isolated_state_dir: Path) -> None:
        """trace_id must be a 32-char hex string (128-bit W3C)."""
        hooks.pre_hook(make_pre_event())
        data = json.loads(list(isolated_state_dir.rglob("*.json"))[0].read_text())
        assert len(data["trace_id"]) == 32
        assert all(c in "0123456789abcdef" for c in data["trace_id"])

    def test_span_id_is_64bit_hex(self, hooks, isolated_state_dir: Path) -> None:
        """span_id must be a 16-char hex string (64-bit W3C)."""
        hooks.pre_hook(make_pre_event())
        data = json.loads(list(isolated_state_dir.rglob("*.json"))[0].read_text())
        assert len(data["span_id"]) == 16
        assert all(c in "0123456789abcdef" for c in data["span_id"])

    def test_unique_trace_ids_per_call(self, hooks, isolated_state_dir: Path) -> None:
        """Two pre-hook calls must produce distinct trace IDs."""
        hooks.pre_hook(make_pre_event(session_id="s1", tool_name="Write"))
        hooks.pre_hook(make_pre_event(session_id="s2", tool_name="Read"))
        files = sorted(isolated_state_dir.rglob("*.json"))
        ids = {json.loads(f.read_text())["trace_id"] for f in files}
        assert len(ids) == 2

    def test_input_hash_is_deterministic(self, hooks, isolated_state_dir: Path) -> None:
        """Same input → same 16-char hash."""
        input_payload = {"file_path": "/tmp/x.txt", "content": "deterministic"}
        hooks.pre_hook(make_pre_event(session_id="s-det-1", tool_input=input_payload))
        hooks.pre_hook(make_pre_event(session_id="s-det-2", tool_input=input_payload))
        files = sorted(isolated_state_dir.rglob("*.json"))
        hashes = [json.loads(f.read_text())["input_hash"] for f in files]
        assert hashes[0] == hashes[1]

    def test_different_inputs_produce_different_hashes(
        self, hooks, isolated_state_dir: Path
    ) -> None:
        hooks.pre_hook(make_pre_event(session_id="s-h1", tool_input={"x": 1}))
        hooks.pre_hook(make_pre_event(session_id="s-h2", tool_input={"x": 2}))
        files = sorted(isolated_state_dir.rglob("*.json"))
        hashes = [json.loads(f.read_text())["input_hash"] for f in files]
        assert hashes[0] != hashes[1]

    def test_session_isolation(self, hooks, isolated_state_dir: Path) -> None:
        """State files for different sessions are in separate directories."""
        hooks.pre_hook(make_pre_event(session_id="sess-A", tool_name="Write"))
        hooks.pre_hook(make_pre_event(session_id="sess-B", tool_name="Write"))
        dirs = {f.parent for f in isolated_state_dir.rglob("*.json")}
        assert len(dirs) == 2

    def test_redact_skips_input_hash_not_content(
        self, hooks, isolated_state_dir: Path
    ) -> None:
        """Input with API key is hashed (not stored). Hash is deterministic."""
        sensitive_input = {"api_key": "sk-ant-api03-supersecret12345"}
        hooks.pre_hook(make_pre_event(tool_input=sensitive_input))
        data = json.loads(list(isolated_state_dir.rglob("*.json"))[0].read_text())
        # Hash is stored, not the raw input
        assert "sk-ant" not in data["input_hash"]
        assert len(data["input_hash"]) == 16


# ---------------------------------------------------------------------------
# post_hook tests
# ---------------------------------------------------------------------------


class TestPostHook:
    def test_returns_empty_dict(self, hooks) -> None:
        """post_hook must return {} (no-op response)."""
        hooks.pre_hook(make_pre_event())
        with patch.object(hooks, "_export_span"):
            result = hooks.post_hook(make_post_event())
        assert result == {}

    def test_cleans_up_state_file(self, hooks, isolated_state_dir: Path) -> None:
        """post_hook deletes the state file after processing."""
        hooks.pre_hook(make_pre_event(session_id="sess-cleanup"))
        with patch.object(hooks, "_export_span"):
            hooks.post_hook(make_post_event(session_id="sess-cleanup"))
        state_files = list(isolated_state_dir.rglob("*.json"))
        assert len(state_files) == 0

    def test_calls_export_span(self, hooks, isolated_state_dir: Path) -> None:
        """post_hook invokes _export_span exactly once."""
        hooks.pre_hook(make_pre_event(session_id="sess-export"))
        with patch.object(hooks, "_export_span") as mock_export:
            hooks.post_hook(make_post_event(session_id="sess-export"))
        mock_export.assert_called_once()

    def test_export_span_receives_correct_session(
        self, hooks, isolated_state_dir: Path
    ) -> None:
        """Exported span state has the correct session_id."""
        hooks.pre_hook(make_pre_event(session_id="sess-verify"))
        captured: list[Any] = []

        def capture_export(state, *args, **kwargs) -> None:
            captured.append(state)

        with patch.object(hooks, "_export_span", side_effect=capture_export):
            hooks.post_hook(make_post_event(session_id="sess-verify"))

        assert len(captured) == 1
        assert captured[0].session_id == "sess-verify"

    def test_outcome_success(self, hooks, isolated_state_dir: Path) -> None:
        """Outcome is 'success' for a normal tool response."""
        hooks.pre_hook(make_pre_event(session_id="s-ok"))
        captured: list[tuple] = []

        def capture(*args):
            captured.append(args)

        with patch.object(hooks, "_export_span", side_effect=capture):
            hooks.post_hook(make_post_event(session_id="s-ok", tool_response="File written"))

        _, outcome, *_ = captured[0]
        assert outcome == "success"

    def test_outcome_error_from_dict(self, hooks, isolated_state_dir: Path) -> None:
        """Outcome reflects error when tool_response contains error key."""
        hooks.pre_hook(make_pre_event(session_id="s-err"))
        captured: list[tuple] = []

        def capture(*args):
            captured.append(args)

        with patch.object(hooks, "_export_span", side_effect=capture):
            hooks.post_hook(
                make_post_event(
                    session_id="s-err",
                    tool_response={"error": "Permission denied"},
                )
            )

        _, outcome, *_ = captured[0]
        assert "Permission denied" in outcome

    def test_duration_is_positive(self, hooks, isolated_state_dir: Path) -> None:
        """Calculated duration must be >= 0."""
        hooks.pre_hook(make_pre_event(session_id="s-dur"))
        captured: list[tuple] = []

        def capture(state, outcome, duration_ms, *args):
            captured.append(duration_ms)

        with patch.object(hooks, "_export_span", side_effect=capture):
            hooks.post_hook(make_post_event(session_id="s-dur"))

        assert captured[0] >= 0

    def test_missing_state_returns_empty(self, hooks, isolated_state_dir: Path) -> None:
        """post_hook with no matching pre_hook returns {} and does not crash."""
        with patch.object(hooks, "_export_span") as mock_export:
            result = hooks.post_hook(make_post_event(session_id="orphan-session"))
        assert result == {}
        mock_export.assert_not_called()

    def test_output_hash_not_raw_output(self, hooks, isolated_state_dir: Path) -> None:
        """Output content is hashed, never stored verbatim."""
        hooks.pre_hook(make_pre_event(session_id="s-outhash"))
        captured: list[tuple] = []

        def capture(state, outcome, duration_ms, end_ns, output_hash):
            captured.append(output_hash)

        with patch.object(hooks, "_export_span", side_effect=capture):
            hooks.post_hook(
                make_post_event(
                    session_id="s-outhash",
                    tool_response="some long sensitive output text",
                )
            )

        assert len(captured[0]) == 16  # hash[:16]
        assert "sensitive" not in captured[0]


# ---------------------------------------------------------------------------
# OTLP payload structure tests
# ---------------------------------------------------------------------------


class TestOtlpPayload:
    def test_payload_has_resource_spans(self, hooks, isolated_state_dir: Path) -> None:
        from claude_trace._hooks import HookState, _build_otlp_payload  # noqa: PLC0415

        state = HookState(
            trace_id="a" * 32,
            span_id="b" * 16,
            session_id="s1",
            tool_name="Write",
            input_hash="deadbeef01234567",
            start_ns=1000,
            start_epoch_ns=1_000_000_000,
        )
        payload = _build_otlp_payload(state, "success", 42.5, 1_001_000_000, "hash0123")
        assert "resourceSpans" in payload
        scope_spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(scope_spans) == 1

    def test_span_name_is_tool_invocation(
        self, hooks, isolated_state_dir: Path
    ) -> None:
        from claude_trace._hooks import HookState, _build_otlp_payload  # noqa: PLC0415

        state = HookState(
            trace_id="c" * 32,
            span_id="d" * 16,
            session_id="s2",
            tool_name="Bash",
            input_hash="0" * 16,
            start_ns=0,
            start_epoch_ns=0,
        )
        payload = _build_otlp_payload(state, "success", 10.0, 1000, "")
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "claude.tool.invocation"

    def test_status_ok_for_success(self, hooks, isolated_state_dir: Path) -> None:
        from claude_trace._hooks import HookState, _build_otlp_payload  # noqa: PLC0415

        state = HookState(
            trace_id="e" * 32,
            span_id="f" * 16,
            session_id="s3",
            tool_name="Read",
            input_hash="0" * 16,
            start_ns=0,
            start_epoch_ns=0,
        )
        payload = _build_otlp_payload(state, "success", 5.0, 5000, "")
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["status"]["code"] == 1  # OK

    def test_status_error_for_failure(self, hooks, isolated_state_dir: Path) -> None:
        from claude_trace._hooks import HookState, _build_otlp_payload  # noqa: PLC0415

        state = HookState(
            trace_id="g" * 32,
            span_id="h" * 16,
            session_id="s4",
            tool_name="Bash",
            input_hash="0" * 16,
            start_ns=0,
            start_epoch_ns=0,
        )
        payload = _build_otlp_payload(state, "Permission denied", 5.0, 5000, "")
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["status"]["code"] == 2  # ERROR

    def test_service_name_attribute(self, hooks, isolated_state_dir: Path) -> None:
        from claude_trace._hooks import HookState, _build_otlp_payload  # noqa: PLC0415

        state = HookState(
            trace_id="i" * 32,
            span_id="j" * 16,
            session_id="s5",
            tool_name="Write",
            input_hash="0" * 16,
            start_ns=0,
            start_epoch_ns=0,
        )
        payload = _build_otlp_payload(state, "success", 1.0, 1000, "")
        resource_attrs = {
            a["key"]: a["value"]
            for a in payload["resourceSpans"][0]["resource"]["attributes"]
        }
        assert "service.name" in resource_attrs
        assert resource_attrs["service.name"]["stringValue"] == "claude-code"


# ---------------------------------------------------------------------------
# CLI entry point tests
# ---------------------------------------------------------------------------


class TestHooksCli:
    def test_pre_mode_returns_json(
        self, hooks, isolated_state_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from claude_trace._hooks_cli import main  # noqa: PLC0415

        event = json.dumps(make_pre_event())
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = event
            with patch.object(hooks, "_export_span"):
                rc = main(["pre"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert json.loads(out) == {}

    def test_post_mode_returns_json(
        self, hooks, isolated_state_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from claude_trace._hooks_cli import main  # noqa: PLC0415

        # Create state first
        hooks.pre_hook(make_pre_event())

        event = json.dumps(make_post_event())
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = event
            with patch.object(hooks, "_export_span"):
                rc = main(["post"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert json.loads(out) == {}

    def test_invalid_mode_returns_1(
        self, isolated_state_dir: Path
    ) -> None:
        from claude_trace._hooks_cli import main  # noqa: PLC0415

        rc = main(["unknown"])
        assert rc == 1

    def test_invalid_json_stdin_does_not_crash(
        self, isolated_state_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Malformed stdin must never crash — Claude Code hooks must not block."""
        from claude_trace._hooks_cli import main  # noqa: PLC0415

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = "not valid json {"
            rc = main(["pre"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert json.loads(out) == {}
