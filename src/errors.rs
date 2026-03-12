//! Error types for `claude-trace`.
//!
//! All errors are defined using [`thiserror`] for consistent display
//! formatting and source-chain propagation.
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::errors::ClaudeTraceError;
//!
//! let e = ClaudeTraceError::UnknownModel { model: "gpt-4".into() };
//! assert!(e.to_string().contains("gpt-4"));
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    #[test]
    fn test_display_formatting_invalid_attribute() {
        let e = ClaudeTraceError::InvalidAttributeName {
            name: "bad.attr".into(),
        };
        let s = e.to_string();
        assert!(s.contains("bad.attr"), "display must contain the name: {s}");
        assert!(
            s.contains("claude."),
            "display must mention expected pattern: {s}"
        );
    }

    #[test]
    fn test_display_formatting_semconv_breaking_change() {
        let e = ClaudeTraceError::SemconvBreakingChange {
            name: "claude.session.model".into(),
        };
        let s = e.to_string();
        assert!(s.contains("claude.session.model"), "display must contain name: {s}");
        assert!(s.contains("additive"), "display must mention additive: {s}");
    }

    #[test]
    fn test_display_formatting_unknown_model() {
        let e = ClaudeTraceError::UnknownModel {
            model: "gpt-totally-fake".into(),
        };
        let s = e.to_string();
        assert!(s.contains("gpt-totally-fake"), "display must contain model: {s}");
    }

    #[test]
    fn test_display_formatting_cost_overflow() {
        let e = ClaudeTraceError::CostOverflow {
            model: "claude-opus-4".into(),
        };
        let s = e.to_string();
        assert!(s.contains("claude-opus-4"), "display must contain model: {s}");
        assert!(s.contains("overflow"), "display must mention overflow: {s}");
    }

    #[test]
    fn test_display_formatting_trace_not_found() {
        let e = ClaudeTraceError::TraceNotFound {
            trace_id: "trace-abc-123".into(),
        };
        let s = e.to_string();
        assert!(s.contains("trace-abc-123"), "display must contain trace_id: {s}");
    }

    #[test]
    fn test_error_source_chain_serialization() {
        let json_err: Result<serde_json::Value, _> = serde_json::from_str("{invalid json}");
        let raw_err = json_err.expect_err("must fail");
        let wrapped = ClaudeTraceError::Serialization(raw_err);
        // source chain is preserved via #[from]
        assert!(
            wrapped.source().is_some(),
            "serialization error must have a source"
        );
    }

    #[test]
    fn test_all_variants_are_debug() {
        let variants: Vec<Box<dyn std::fmt::Debug>> = vec![
            Box::new(ClaudeTraceError::InvalidAttributeName { name: "x".into() }),
            Box::new(ClaudeTraceError::SemconvBreakingChange { name: "x".into() }),
            Box::new(ClaudeTraceError::UnknownModel { model: "x".into() }),
            Box::new(ClaudeTraceError::CostOverflow { model: "x".into() }),
            Box::new(ClaudeTraceError::TraceNotFound { trace_id: "x".into() }),
        ];
        for v in variants {
            let dbg = format!("{v:?}");
            assert!(!dbg.is_empty());
        }
    }
}

// ---- IMPLEMENTATION ----

use thiserror::Error;

/// All errors that can be produced by `claude-trace` core.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::errors::ClaudeTraceError;
///
/// let e = ClaudeTraceError::UnknownModel { model: "gpt-x".into() };
/// assert!(e.to_string().contains("gpt-x"));
/// ```
#[derive(Error, Debug)]
pub enum ClaudeTraceError {
    /// An attribute name does not follow the `claude.{category}.{name}` convention.
    #[error("invalid attribute name '{name}': must match claude.{{category}}.{{name}}")]
    InvalidAttributeName { name: String },

    /// A semconv change removes an attribute that previously existed (breaking change).
    #[error("semconv change is not additive: attribute '{name}' was removed")]
    SemconvBreakingChange { name: String },

    /// The given model identifier was not found in the pricing table.
    #[error("model '{model}' not found in pricing table")]
    UnknownModel { model: String },

    /// A cost calculation produced a numeric overflow for the given model.
    #[error("cost calculation overflow for model '{model}'")]
    CostOverflow { model: String },

    /// A trace with the given ID could not be found.
    #[error("trace not found: '{trace_id}'")]
    TraceNotFound { trace_id: String },

    /// A JSON serialization or deserialization error.
    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}
