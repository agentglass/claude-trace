"""
Structural diff between two agent execution traces.

``compare()`` accepts two ``TraceSnapshot`` objects and returns a typed
``TraceDiff`` dataclass.  The result is designed for use in pytest
assertions and programmatic analysis, not just human reading.

Diffed dimensions:
    - Turn count and stop reasons
    - Tool call sequences (names, order, error rates)
    - Token usage deltas (input, output, cache)
    - Cost deltas
    - Latency profiles
    - Tool name set changes (added/removed tools)
    - Error presence

Usage in tests::

    from claude_trace._diff.trace_diff import TraceSnapshot, compare

    baseline = TraceSnapshot.from_session(baseline_session)
    candidate = TraceSnapshot.from_session(candidate_session)

    diff = compare(baseline, candidate)
    assert diff.is_equivalent(rtol=0.05), diff.summary()

    # Or fine-grained:
    assert diff.tool_names_added == set()
    assert diff.turn_count_delta == 0
    assert diff.cost_delta_usd < 0.01
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


@dataclass
class TurnSnapshot:
    """Snapshot of one turn within a trace."""

    turn_index: int
    model: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    tool_names: list[str]
    tool_use_count: int
    latency_ms: float
    cost_usd: float
    error_type: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TurnSnapshot":
        return cls(
            turn_index=int(d.get("turn_index", 0)),
            model=str(d.get("model", "")),
            stop_reason=str(d.get("stop_reason", "")),
            input_tokens=int(d.get("input_tokens", 0)),
            output_tokens=int(d.get("output_tokens", 0)),
            cache_read_tokens=int(d.get("cache_read_tokens", 0)),
            cache_creation_tokens=int(d.get("cache_creation_tokens", 0)),
            tool_names=list(d.get("tool_names", [])),
            tool_use_count=int(d.get("tool_use_count", 0)),
            latency_ms=float(d.get("latency_ms", 0.0)),
            cost_usd=float(d.get("cost_usd", 0.0)),
            error_type=d.get("error_type"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "tool_names": self.tool_names,
            "tool_use_count": self.tool_use_count,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "error_type": self.error_type,
        }


@dataclass
class TraceSnapshot:
    """A serialisable snapshot of an agent session's observable behaviour.

    Captures everything needed to detect regressions without storing
    the actual content (which may be non-deterministic or contain PII).

    Create from a live session::

        snap = TraceSnapshot.from_session(session)

    Or from a JSON file (for golden-file testing)::

        with open("golden.json") as f:
            snap = TraceSnapshot.from_json(f.read())
    """

    session_id: str
    model: str
    total_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    total_cost_usd: float
    total_tool_calls: int
    distinct_tool_names: list[str]
    final_status: str
    turns: list[TurnSnapshot] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    customer_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_session(cls, session: Any) -> "TraceSnapshot":
        """Build a snapshot from a live or completed ``AgentSession``.

        Args:
            session: A ``claude_trace._spans.session.AgentSession`` instance.
        """
        from claude_trace._spans.session import AgentSession  # avoid circular

        if not isinstance(session, AgentSession):
            raise TypeError(f"Expected AgentSession, got {type(session)}")

        cost = session.cost
        return cls(
            session_id=session.session_id,
            model=session.model,
            total_turns=session._turn_count,
            total_input_tokens=cost.input_tokens,
            total_output_tokens=cost.output_tokens,
            total_cache_read_tokens=cost.cache_read_tokens,
            total_cache_creation_tokens=cost.cache_creation_tokens,
            total_cost_usd=cost.total_usd,
            total_tool_calls=session._total_tool_calls,
            distinct_tool_names=sorted(session._tool_names),
            final_status="completed",
            tags=list(session.tags),
            customer_id=session.customer_id,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TraceSnapshot":
        turns = [TurnSnapshot.from_dict(t) for t in d.get("turns", [])]
        return cls(
            session_id=str(d.get("session_id", "")),
            model=str(d.get("model", "")),
            total_turns=int(d.get("total_turns", 0)),
            total_input_tokens=int(d.get("total_input_tokens", 0)),
            total_output_tokens=int(d.get("total_output_tokens", 0)),
            total_cache_read_tokens=int(d.get("total_cache_read_tokens", 0)),
            total_cache_creation_tokens=int(d.get("total_cache_creation_tokens", 0)),
            total_cost_usd=float(d.get("total_cost_usd", 0.0)),
            total_tool_calls=int(d.get("total_tool_calls", 0)),
            distinct_tool_names=list(d.get("distinct_tool_names", [])),
            final_status=str(d.get("final_status", "")),
            turns=turns,
            tags=list(d.get("tags", [])),
            customer_id=d.get("customer_id"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "TraceSnapshot":
        return cls.from_dict(json.loads(json_str))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model": self.model,
            "total_turns": self.total_turns,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_tool_calls": self.total_tool_calls,
            "distinct_tool_names": self.distinct_tool_names,
            "final_status": self.final_status,
            "turns": [t.to_dict() for t in self.turns],
            "tags": self.tags,
            "customer_id": self.customer_id,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str) -> None:
        """Write this snapshot as a JSON golden file."""
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "TraceSnapshot":
        """Load a snapshot from a JSON golden file."""
        with open(path) as f:
            return cls.from_json(f.read())


@dataclass
class TurnDiff:
    """Diff for a single turn."""

    turn_index: int
    baseline_stop_reason: str
    candidate_stop_reason: str
    input_token_delta: int
    output_token_delta: int
    tool_names_added: list[str]
    tool_names_removed: list[str]
    cost_delta_usd: float
    latency_delta_ms: float
    error_changed: bool  # True if error presence changed

    @property
    def stop_reason_changed(self) -> bool:
        return self.baseline_stop_reason != self.candidate_stop_reason

    @property
    def tool_sequence_changed(self) -> bool:
        return bool(self.tool_names_added or self.tool_names_removed)


@dataclass
class TraceDiff:
    """Structural difference between two agent execution traces.

    All fields use a ``baseline`` / ``candidate`` convention.
    Delta fields are ``candidate - baseline`` (positive = candidate used more).

    Intended for use in automated tests and CI regression checks.
    """

    baseline: TraceSnapshot
    candidate: TraceSnapshot

    # --- Turn-level ---
    turn_count_delta: int
    """candidate.total_turns - baseline.total_turns"""

    turn_diffs: list[TurnDiff]
    """Per-turn diffs for turns that exist in both snapshots."""

    # --- Tool names ---
    tool_names_added: set[str]
    """Tools in candidate but not in baseline."""

    tool_names_removed: set[str]
    """Tools in baseline but not in candidate."""

    tool_call_count_delta: int
    """candidate.total_tool_calls - baseline.total_tool_calls"""

    # --- Tokens ---
    input_token_delta: int
    output_token_delta: int
    cache_read_token_delta: int
    cache_creation_token_delta: int

    # --- Cost ---
    cost_delta_usd: float
    """candidate.total_cost_usd - baseline.total_cost_usd"""

    # --- Status ---
    final_status_changed: bool
    model_changed: bool

    # --- Errors ---
    errors_introduced: int
    """Number of turns that have errors in candidate but not in baseline."""

    errors_resolved: int
    """Number of turns that had errors in baseline but not in candidate."""

    def is_equivalent(self, rtol: float = 0.0, atol_tokens: int = 0) -> bool:
        """Return True if the two traces are functionally equivalent.

        Args:
            rtol: Relative tolerance for cost and token comparisons (e.g. 0.05 = 5%).
            atol_tokens: Absolute token count tolerance.

        Returns:
            True if all structural dimensions are within tolerance.
        """
        if self.turn_count_delta != 0:
            return False
        if self.tool_names_added or self.tool_names_removed:
            return False
        if self.final_status_changed:
            return False
        if self.model_changed:
            return False
        if self.errors_introduced > 0:
            return False

        # Token check with tolerance
        baseline_tokens = (
            self.baseline.total_input_tokens + self.baseline.total_output_tokens
        )
        if baseline_tokens > 0:
            token_rtol = abs(self.input_token_delta + self.output_token_delta) / baseline_tokens
            if token_rtol > rtol and abs(self.input_token_delta) > atol_tokens:
                return False

        # Cost check
        if self.baseline.total_cost_usd > 0:
            cost_rtol = abs(self.cost_delta_usd) / self.baseline.total_cost_usd
            if cost_rtol > rtol and abs(self.cost_delta_usd) > 1e-6:
                return False

        # Stop reason changes in individual turns
        for td in self.turn_diffs:
            if td.stop_reason_changed:
                return False

        return True

    def summary(self) -> str:
        """Return a human-readable multi-line summary of the diff."""
        lines: list[str] = [
            "TraceDiff Summary",
            "=================",
            f"  Baseline session : {self.baseline.session_id}",
            f"  Candidate session: {self.candidate.session_id}",
            "",
            f"  Turns          : {self.baseline.total_turns} → {self.candidate.total_turns}"
            f"  (delta={self.turn_count_delta:+d})",
            f"  Tool calls     : {self.baseline.total_tool_calls} → "
            f"{self.candidate.total_tool_calls} (delta={self.tool_call_count_delta:+d})",
            f"  Input tokens   : {self.baseline.total_input_tokens} → "
            f"{self.candidate.total_input_tokens} (delta={self.input_token_delta:+d})",
            f"  Output tokens  : {self.baseline.total_output_tokens} → "
            f"{self.candidate.total_output_tokens} (delta={self.output_token_delta:+d})",
            f"  Cost USD       : ${self.baseline.total_cost_usd:.6f} → "
            f"${self.candidate.total_cost_usd:.6f} (delta={self.cost_delta_usd:+.6f})",
            "",
        ]
        if self.tool_names_added:
            lines.append(f"  Tools ADDED    : {sorted(self.tool_names_added)}")
        if self.tool_names_removed:
            lines.append(f"  Tools REMOVED  : {sorted(self.tool_names_removed)}")
        if self.errors_introduced:
            lines.append(f"  Errors ADDED   : {self.errors_introduced}")
        if self.errors_resolved:
            lines.append(f"  Errors RESOLVED: {self.errors_resolved}")
        if self.final_status_changed:
            lines.append(
                f"  Status CHANGED : {self.baseline.final_status!r} → "
                f"{self.candidate.final_status!r}"
            )
        for td in self.turn_diffs:
            if td.stop_reason_changed:
                lines.append(
                    f"  Turn {td.turn_index} stop_reason: "
                    f"{td.baseline_stop_reason!r} → {td.candidate_stop_reason!r}"
                )
        return "\n".join(lines)

    def assert_equivalent(
        self,
        rtol: float = 0.0,
        atol_tokens: int = 0,
        msg: Optional[str] = None,
    ) -> None:
        """Assert that the two traces are equivalent, raising ``AssertionError`` if not.

        Designed for direct use in pytest::

            diff = compare(baseline_snap, candidate_snap)
            diff.assert_equivalent(rtol=0.05)
        """
        if not self.is_equivalent(rtol=rtol, atol_tokens=atol_tokens):
            error_msg = msg or self.summary()
            raise AssertionError(error_msg)


def _diff_turn(
    baseline_turns: Sequence[TurnSnapshot],
    candidate_turns: Sequence[TurnSnapshot],
) -> list[TurnDiff]:
    """Produce per-turn diffs for turns that appear in both sequences."""
    diffs: list[TurnDiff] = []
    min_len = min(len(baseline_turns), len(candidate_turns))
    for i in range(min_len):
        bt = baseline_turns[i]
        ct = candidate_turns[i]
        bt_tools = set(bt.tool_names)
        ct_tools = set(ct.tool_names)
        diffs.append(
            TurnDiff(
                turn_index=i,
                baseline_stop_reason=bt.stop_reason,
                candidate_stop_reason=ct.stop_reason,
                input_token_delta=ct.input_tokens - bt.input_tokens,
                output_token_delta=ct.output_tokens - bt.output_tokens,
                tool_names_added=sorted(ct_tools - bt_tools),
                tool_names_removed=sorted(bt_tools - ct_tools),
                cost_delta_usd=ct.cost_usd - bt.cost_usd,
                latency_delta_ms=ct.latency_ms - bt.latency_ms,
                error_changed=(bt.error_type is None) != (ct.error_type is None),
            )
        )
    return diffs


def compare(baseline: TraceSnapshot, candidate: TraceSnapshot) -> TraceDiff:
    """Compute a structural diff between two ``TraceSnapshot`` objects.

    This is the primary public API for trace comparison.  The result is a
    fully-typed ``TraceDiff`` that can be used in assertions, logging, or
    rendered as a human-readable summary.

    Args:
        baseline: The reference trace (e.g. from a golden file or prior run).
        candidate: The trace to compare against the baseline.

    Returns:
        A ``TraceDiff`` instance with all difference dimensions populated.

    Example::

        from claude_trace._diff.trace_diff import compare, TraceSnapshot

        golden = TraceSnapshot.load("tests/golden/my_task.json")
        actual = TraceSnapshot.from_session(session)
        diff = compare(golden, actual)

        if not diff.is_equivalent(rtol=0.05):
            print(diff.summary())
            raise AssertionError("Trace regression detected")
    """
    baseline_tool_set = set(baseline.distinct_tool_names)
    candidate_tool_set = set(candidate.distinct_tool_names)

    # Count errors per snapshot
    def count_errors(turns: list[TurnSnapshot]) -> set[int]:
        return {t.turn_index for t in turns if t.error_type is not None}

    baseline_error_turns = count_errors(baseline.turns)
    candidate_error_turns = count_errors(candidate.turns)

    errors_introduced = len(candidate_error_turns - baseline_error_turns)
    errors_resolved = len(baseline_error_turns - candidate_error_turns)

    return TraceDiff(
        baseline=baseline,
        candidate=candidate,
        turn_count_delta=candidate.total_turns - baseline.total_turns,
        turn_diffs=_diff_turn(baseline.turns, candidate.turns),
        tool_names_added=candidate_tool_set - baseline_tool_set,
        tool_names_removed=baseline_tool_set - candidate_tool_set,
        tool_call_count_delta=candidate.total_tool_calls - baseline.total_tool_calls,
        input_token_delta=candidate.total_input_tokens - baseline.total_input_tokens,
        output_token_delta=candidate.total_output_tokens - baseline.total_output_tokens,
        cache_read_token_delta=(
            candidate.total_cache_read_tokens - baseline.total_cache_read_tokens
        ),
        cache_creation_token_delta=(
            candidate.total_cache_creation_tokens - baseline.total_cache_creation_tokens
        ),
        cost_delta_usd=candidate.total_cost_usd - baseline.total_cost_usd,
        final_status_changed=baseline.final_status != candidate.final_status,
        model_changed=baseline.model != candidate.model,
        errors_introduced=errors_introduced,
        errors_resolved=errors_resolved,
    )
