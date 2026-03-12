//! Structural diff between two agent execution traces.
//!
//! Use [`compare`] to compute a typed [`TraceDiff`] from two [`TraceSnapshot`]s.
//! The result supports assertion-style usage in tests via [`TraceDiff::assert_equivalent`].
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::diff::{compare, TraceSnapshot};
//!
//! let snap = TraceSnapshot {
//!     trace_id: "abc".into(),
//!     tool_calls: vec!["bash".into()],
//!     turn_count: 1,
//!     total_tokens: 500,
//!     stop_reason: "end_turn".into(),
//! };
//! let diff = compare(&snap, &snap);
//! assert!(diff.is_equivalent());
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;

    fn default_snap() -> TraceSnapshot {
        TraceSnapshot {
            trace_id: "test".into(),
            tool_calls: vec![],
            turn_count: 1,
            total_tokens: 500,
            stop_reason: "end_turn".into(),
        }
    }

    #[test]
    fn test_identical_snapshots_are_equivalent() {
        let snap = TraceSnapshot {
            trace_id: "abc".into(),
            tool_calls: vec!["bash".into(), "read_file".into()],
            turn_count: 2,
            total_tokens: 500,
            stop_reason: "end_turn".into(),
        };
        let diff = compare(&snap, &snap);
        assert!(diff.is_equivalent());
    }

    #[test]
    fn test_added_tool_call_detected() {
        let a = TraceSnapshot {
            tool_calls: vec!["bash".into()],
            ..default_snap()
        };
        let b = TraceSnapshot {
            tool_calls: vec!["bash".into(), "read_file".into()],
            ..default_snap()
        };
        let diff = compare(&a, &b);
        assert!(!diff.is_equivalent());
        assert_eq!(diff.added_tool_calls, vec!["read_file".to_string()]);
        assert!(diff.removed_tool_calls.is_empty());
    }

    #[test]
    fn test_removed_tool_call_detected() {
        let a = TraceSnapshot {
            tool_calls: vec!["bash".into(), "web_search".into()],
            ..default_snap()
        };
        let b = TraceSnapshot {
            tool_calls: vec!["bash".into()],
            ..default_snap()
        };
        let diff = compare(&a, &b);
        assert_eq!(diff.removed_tool_calls, vec!["web_search".to_string()]);
    }

    #[test]
    fn test_token_delta_calculated() {
        let a = TraceSnapshot {
            total_tokens: 1000,
            ..default_snap()
        };
        let b = TraceSnapshot {
            total_tokens: 1200,
            ..default_snap()
        };
        let diff = compare(&a, &b);
        assert_eq!(diff.token_delta, 200);
    }

    #[test]
    fn test_token_delta_negative() {
        let a = TraceSnapshot {
            total_tokens: 1200,
            ..default_snap()
        };
        let b = TraceSnapshot {
            total_tokens: 1000,
            ..default_snap()
        };
        let diff = compare(&a, &b);
        assert_eq!(diff.token_delta, -200);
    }

    #[test]
    fn test_summary_format() {
        let a = TraceSnapshot {
            tool_calls: vec!["bash".into()],
            total_tokens: 1000,
            ..default_snap()
        };
        let b = TraceSnapshot {
            tool_calls: vec!["read_file".into()],
            total_tokens: 1100,
            ..default_snap()
        };
        let diff = compare(&a, &b);
        let summary = diff.summary();
        assert!(summary.contains("added"), "summary must mention 'added': {summary}");
        assert!(
            summary.contains("removed"),
            "summary must mention 'removed': {summary}"
        );
        assert!(
            summary.contains("100"),
            "summary must contain token delta 100: {summary}"
        );
    }

    #[test]
    fn test_stop_reason_change_detected() {
        let a = TraceSnapshot {
            stop_reason: "end_turn".into(),
            ..default_snap()
        };
        let b = TraceSnapshot {
            stop_reason: "max_tokens".into(),
            ..default_snap()
        };
        let diff = compare(&a, &b);
        assert!(!diff.is_equivalent());
    }

    #[test]
    fn test_turn_count_change_detected() {
        let a = TraceSnapshot {
            turn_count: 3,
            ..default_snap()
        };
        let b = TraceSnapshot {
            turn_count: 5,
            ..default_snap()
        };
        let diff = compare(&a, &b);
        assert!(!diff.is_equivalent());
    }

    #[test]
    fn test_assert_equivalent_passes_for_identical() {
        let snap = default_snap();
        let diff = compare(&snap, &snap);
        diff.assert_equivalent(); // must not panic
    }

    #[test]
    #[should_panic]
    fn test_assert_equivalent_panics_for_diff() {
        let a = TraceSnapshot {
            tool_calls: vec!["bash".into()],
            ..default_snap()
        };
        let b = TraceSnapshot {
            tool_calls: vec!["read_file".into()],
            ..default_snap()
        };
        let diff = compare(&a, &b);
        diff.assert_equivalent();
    }
}

// ---- IMPLEMENTATION ----

/// A lightweight snapshot of an agent trace for comparison purposes.
///
/// Contains only the structural dimensions needed for regression detection,
/// without storing potentially sensitive content.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::diff::TraceSnapshot;
///
/// let snap = TraceSnapshot {
///     trace_id: "sess_001".into(),
///     tool_calls: vec!["bash".into(), "read_file".into()],
///     turn_count: 2,
///     total_tokens: 1000,
///     stop_reason: "end_turn".into(),
/// };
/// assert_eq!(snap.turn_count, 2);
/// ```
#[derive(Debug, Clone)]
pub struct TraceSnapshot {
    /// Unique identifier for this trace.
    pub trace_id: String,
    /// Ordered list of tool names called during the trace.
    pub tool_calls: Vec<String>,
    /// Number of agentic loop turns executed.
    pub turn_count: u32,
    /// Total tokens consumed (input + output) across all turns.
    pub total_tokens: u64,
    /// Final stop reason from the last turn.
    pub stop_reason: String,
}

/// Structural difference between two [`TraceSnapshot`]s.
///
/// Produced by [`compare`]. All delta fields use `candidate - baseline`
/// convention (positive = candidate used more).
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::diff::{compare, TraceSnapshot};
///
/// let a = TraceSnapshot { trace_id: "a".into(), tool_calls: vec![], turn_count: 1, total_tokens: 100, stop_reason: "end_turn".into() };
/// let b = TraceSnapshot { trace_id: "b".into(), tool_calls: vec![], turn_count: 1, total_tokens: 150, stop_reason: "end_turn".into() };
/// let diff = compare(&a, &b);
/// assert_eq!(diff.token_delta, 50);
/// ```
#[derive(Debug)]
pub struct TraceDiff {
    /// Tool names present in candidate but not in baseline.
    pub added_tool_calls: Vec<String>,
    /// Tool names present in baseline but not in candidate.
    pub removed_tool_calls: Vec<String>,
    /// `candidate.total_tokens - baseline.total_tokens`.
    pub token_delta: i64,
    /// `candidate.turn_count - baseline.turn_count` (as i64).
    pub turn_count_delta: i64,
    /// `true` if the stop reason changed between snapshots.
    pub stop_reason_changed: bool,
    // Keep references to snapshots for richer summary output.
    baseline_stop_reason: String,
    candidate_stop_reason: String,
    baseline_turn_count: u32,
    candidate_turn_count: u32,
}

impl TraceDiff {
    /// Returns `true` when both snapshots are structurally equivalent:
    /// same tool calls (as sets), same token count, same turn count, same stop reason.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::diff::{compare, TraceSnapshot};
    ///
    /// let snap = TraceSnapshot { trace_id: "x".into(), tool_calls: vec![], turn_count: 1, total_tokens: 100, stop_reason: "end_turn".into() };
    /// assert!(compare(&snap, &snap).is_equivalent());
    /// ```
    #[must_use]
    pub fn is_equivalent(&self) -> bool {
        self.added_tool_calls.is_empty()
            && self.removed_tool_calls.is_empty()
            && self.token_delta == 0
            && self.turn_count_delta == 0
            && !self.stop_reason_changed
    }

    /// Return a human-readable multi-line summary of the diff.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::diff::{compare, TraceSnapshot};
    ///
    /// let a = TraceSnapshot { trace_id: "a".into(), tool_calls: vec!["bash".into()], turn_count: 1, total_tokens: 100, stop_reason: "end_turn".into() };
    /// let b = TraceSnapshot { trace_id: "b".into(), tool_calls: vec![], turn_count: 1, total_tokens: 100, stop_reason: "end_turn".into() };
    /// let s = compare(&a, &b).summary();
    /// assert!(s.contains("removed"));
    /// ```
    #[must_use]
    pub fn summary(&self) -> String {
        let mut lines = vec![
            "TraceDiff Summary".to_owned(),
            "=================".to_owned(),
            format!(
                "  Turns        : {} → {} (delta={:+})",
                self.baseline_turn_count, self.candidate_turn_count, self.turn_count_delta
            ),
            format!("  Token delta  : {:+}", self.token_delta),
        ];

        if !self.added_tool_calls.is_empty() {
            lines.push(format!(
                "  Tools added  : {}",
                self.added_tool_calls.join(", ")
            ));
        }
        if !self.removed_tool_calls.is_empty() {
            lines.push(format!(
                "  Tools removed: {}",
                self.removed_tool_calls.join(", ")
            ));
        }
        if self.stop_reason_changed {
            lines.push(format!(
                "  Stop reason  : {:?} → {:?}",
                self.baseline_stop_reason, self.candidate_stop_reason
            ));
        }
        lines.join("\n")
    }

    /// Assert that the two traces are equivalent, panicking with a diff summary if not.
    ///
    /// Designed for direct use in tests.
    ///
    /// # Panics
    ///
    /// Panics when `!self.is_equivalent()`, printing the diff summary.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::diff::{compare, TraceSnapshot};
    ///
    /// let snap = TraceSnapshot { trace_id: "x".into(), tool_calls: vec![], turn_count: 1, total_tokens: 100, stop_reason: "end_turn".into() };
    /// compare(&snap, &snap).assert_equivalent(); // passes
    /// ```
    pub fn assert_equivalent(&self) {
        assert!(self.is_equivalent(), "{}", self.summary());
    }
}

/// Compute a structural diff between two [`TraceSnapshot`] objects.
///
/// This is the primary public API for trace comparison.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::diff::{compare, TraceSnapshot};
///
/// let baseline = TraceSnapshot {
///     trace_id: "base".into(),
///     tool_calls: vec!["bash".into()],
///     turn_count: 2,
///     total_tokens: 1000,
///     stop_reason: "end_turn".into(),
/// };
/// let candidate = TraceSnapshot {
///     trace_id: "cand".into(),
///     tool_calls: vec!["bash".into(), "read_file".into()],
///     turn_count: 2,
///     total_tokens: 1200,
///     stop_reason: "end_turn".into(),
/// };
/// let diff = compare(&baseline, &candidate);
/// assert_eq!(diff.added_tool_calls, vec!["read_file".to_string()]);
/// assert_eq!(diff.token_delta, 200);
/// ```
#[must_use]
pub fn compare(baseline: &TraceSnapshot, candidate: &TraceSnapshot) -> TraceDiff {
    use std::collections::HashSet;

    let base_tools: HashSet<&str> = baseline.tool_calls.iter().map(String::as_str).collect();
    let cand_tools: HashSet<&str> = candidate.tool_calls.iter().map(String::as_str).collect();

    let mut added: Vec<String> = cand_tools
        .difference(&base_tools)
        .map(|s| (*s).to_owned())
        .collect();
    added.sort();

    let mut removed: Vec<String> = base_tools
        .difference(&cand_tools)
        .map(|s| (*s).to_owned())
        .collect();
    removed.sort();

    // total_tokens is u64; we accept wrapping is impossible in practice (token counts < 2^63).
    // Use saturating conversion to avoid undefined behaviour.
    #[allow(clippy::cast_possible_wrap)]
    let token_delta = candidate.total_tokens as i64 - baseline.total_tokens as i64;
    let turn_count_delta = i64::from(candidate.turn_count) - i64::from(baseline.turn_count);
    let stop_reason_changed = baseline.stop_reason != candidate.stop_reason;

    TraceDiff {
        added_tool_calls: added,
        removed_tool_calls: removed,
        token_delta,
        turn_count_delta,
        stop_reason_changed,
        baseline_stop_reason: baseline.stop_reason.clone(),
        candidate_stop_reason: candidate.stop_reason.clone(),
        baseline_turn_count: baseline.turn_count,
        candidate_turn_count: candidate.turn_count,
    }
}
