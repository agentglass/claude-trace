//! Turn span — covers one agentic loop iteration (one LLM call).
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::spans::{TurnSpan, SpanConfig};
//!
//! let config = SpanConfig::default();
//! let mut t = TurnSpan::new(0, &config);
//! t.set_model("claude-sonnet-4-6");
//! t.set_tokens(5000, 800, 3000, 500);
//! t.set_stop_reason("end_turn");
//! t.finish_ok();
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;

    fn default_config() -> SpanConfig {
        SpanConfig::default()
    }

    #[test]
    fn test_new_stores_turn_index() {
        let t = TurnSpan::new(3, &default_config());
        assert_eq!(t.index(), 3);
    }

    #[test]
    fn test_set_model() {
        let mut t = TurnSpan::new(0, &default_config());
        t.set_model("claude-haiku-4-5");
        assert_eq!(t.model(), Some("claude-haiku-4-5"));
    }

    #[test]
    fn test_set_tokens() {
        let mut t = TurnSpan::new(0, &default_config());
        t.set_tokens(1000, 500, 200, 50);
        let (inp, out, cr, cw) = t.tokens();
        assert_eq!(inp, 1000);
        assert_eq!(out, 500);
        assert_eq!(cr, 200);
        assert_eq!(cw, 50);
    }

    #[test]
    fn test_set_stop_reason() {
        let mut t = TurnSpan::new(0, &default_config());
        t.set_stop_reason("tool_use");
        assert_eq!(t.stop_reason(), Some("tool_use"));
    }

    #[test]
    fn test_finish_ok_sets_status() {
        let mut t = TurnSpan::new(0, &default_config());
        t.finish_ok();
        assert_eq!(t.status(), TurnStatus::Ok);
    }

    #[test]
    fn test_finish_error_sets_status_and_message() {
        let mut t = TurnSpan::new(0, &default_config());
        t.finish_error("rate_limit", "429 Too Many Requests");
        assert_eq!(t.status(), TurnStatus::Error);
        assert_eq!(t.error_type(), Some("rate_limit"));
        assert_eq!(t.error_message(), Some("429 Too Many Requests"));
    }

    #[test]
    fn test_tool_names_accumulate() {
        let mut t = TurnSpan::new(0, &default_config());
        t.add_tool_name("bash");
        t.add_tool_name("read_file");
        t.add_tool_name("bash"); // duplicate
        assert_eq!(t.tool_use_count(), 3);
        // unique names sorted
        let names = t.unique_tool_names();
        assert_eq!(names, vec!["bash", "read_file"]);
    }

    #[test]
    fn test_string_truncation_applied() {
        let config = SpanConfig {
            max_attribute_length: 5,
            ..SpanConfig::default()
        };
        let mut t = TurnSpan::new(0, &config);
        t.set_stop_reason("end_turn");
        assert_eq!(t.stop_reason(), Some("end_tu"[..5].as_ref()));
    }

    #[test]
    fn test_default_status_is_unset() {
        let t = TurnSpan::new(0, &default_config());
        assert_eq!(t.status(), TurnStatus::Unset);
    }

    #[test]
    fn test_latency_ms() {
        let mut t = TurnSpan::new(0, &default_config());
        t.set_latency_ms(342.7);
        assert!((t.latency_ms().unwrap_or(0.0) - 342.7).abs() < 1e-9);
    }
}

// ---- IMPLEMENTATION ----

use super::{truncate_attribute, SpanConfig};

/// Status of a turn span.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::turn::TurnStatus;
///
/// assert_eq!(TurnStatus::Ok, TurnStatus::Ok);
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TurnStatus {
    /// Not yet finished.
    Unset,
    /// Turn completed successfully.
    Ok,
    /// Turn failed with an API or processing error.
    Error,
}

/// Span covering a single agentic loop iteration.
///
/// A turn represents exactly one call to `anthropic.messages.create()`.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
///
/// let config = SpanConfig::default();
/// let mut t = TurnSpan::new(0, &config);
/// t.set_model("claude-sonnet-4-6");
/// t.set_tokens(5000, 800, 3000, 500);
/// t.set_stop_reason("end_turn");
/// t.finish_ok();
/// assert_eq!(t.status(), _claude_trace_core::spans::turn::TurnStatus::Ok);
/// ```
#[derive(Debug)]
pub struct TurnSpan {
    index: u32,
    model: Option<String>,
    stop_reason: Option<String>,
    input_tokens: u64,
    output_tokens: u64,
    cache_read_tokens: u64,
    cache_write_tokens: u64,
    tool_names_seq: Vec<String>,
    status: TurnStatus,
    error_type: Option<String>,
    error_message: Option<String>,
    latency_ms: Option<f64>,
    max_attribute_length: usize,
}

impl TurnSpan {
    /// Create a new `TurnSpan` for the given zero-based turn index.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    ///
    /// let t = TurnSpan::new(2, &SpanConfig::default());
    /// assert_eq!(t.index(), 2);
    /// ```
    #[must_use]
    pub fn new(index: u32, config: &SpanConfig) -> Self {
        Self {
            index,
            model: None,
            stop_reason: None,
            input_tokens: 0,
            output_tokens: 0,
            cache_read_tokens: 0,
            cache_write_tokens: 0,
            tool_names_seq: Vec::new(),
            status: TurnStatus::Unset,
            error_type: None,
            error_message: None,
            latency_ms: None,
            max_attribute_length: config.max_attribute_length,
        }
    }

    /// Set the model identifier for this turn.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.set_model("claude-haiku-4-5");
    /// assert_eq!(t.model(), Some("claude-haiku-4-5"));
    /// ```
    pub fn set_model(&mut self, model: &str) {
        self.model = Some(truncate_attribute(model, self.max_attribute_length));
    }

    /// Set the token counts for this turn.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.set_tokens(1000, 500, 200, 50);
    /// let (inp, ..) = t.tokens();
    /// assert_eq!(inp, 1000);
    /// ```
    pub fn set_tokens(
        &mut self,
        input: u64,
        output: u64,
        cache_read: u64,
        cache_write: u64,
    ) {
        self.input_tokens = input;
        self.output_tokens = output;
        self.cache_read_tokens = cache_read;
        self.cache_write_tokens = cache_write;
    }

    /// Set the stop reason for this turn.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.set_stop_reason("tool_use");
    /// assert_eq!(t.stop_reason(), Some("tool_use"));
    /// ```
    pub fn set_stop_reason(&mut self, reason: &str) {
        self.stop_reason = Some(truncate_attribute(reason, self.max_attribute_length));
    }

    /// Record a tool invocation in this turn.
    ///
    /// Multiple calls are accumulated; duplicates are kept for ordering purposes.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.add_tool_name("bash");
    /// assert_eq!(t.tool_use_count(), 1);
    /// ```
    pub fn add_tool_name(&mut self, name: &str) {
        self.tool_names_seq
            .push(truncate_attribute(name, self.max_attribute_length));
    }

    /// Set end-to-end latency in milliseconds.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.set_latency_ms(250.0);
    /// assert!(t.latency_ms().is_some());
    /// ```
    pub fn set_latency_ms(&mut self, ms: f64) {
        self.latency_ms = Some(ms);
    }

    /// Mark the turn as successfully completed.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    /// use _claude_trace_core::spans::turn::TurnStatus;
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.finish_ok();
    /// assert_eq!(t.status(), TurnStatus::Ok);
    /// ```
    pub fn finish_ok(&mut self) {
        self.status = TurnStatus::Ok;
    }

    /// Mark the turn as failed.
    ///
    /// Both `error_type` and `error_message` are truncated.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{TurnSpan, SpanConfig};
    /// use _claude_trace_core::spans::turn::TurnStatus;
    ///
    /// let mut t = TurnSpan::new(0, &SpanConfig::default());
    /// t.finish_error("RateLimitError", "429");
    /// assert_eq!(t.status(), TurnStatus::Error);
    /// ```
    pub fn finish_error(&mut self, error_type: &str, error_message: &str) {
        self.status = TurnStatus::Error;
        self.error_type = Some(truncate_attribute(error_type, self.max_attribute_length));
        self.error_message = Some(truncate_attribute(error_message, self.max_attribute_length));
    }

    // ---- Accessors ----

    /// Returns the zero-based turn index.
    #[must_use]
    pub fn index(&self) -> u32 {
        self.index
    }

    /// Returns the model identifier, if set.
    #[must_use]
    pub fn model(&self) -> Option<&str> {
        self.model.as_deref()
    }

    /// Returns the stop reason, if set.
    #[must_use]
    pub fn stop_reason(&self) -> Option<&str> {
        self.stop_reason.as_deref()
    }

    /// Returns token counts: `(input, output, cache_read, cache_write)`.
    #[must_use]
    pub fn tokens(&self) -> (u64, u64, u64, u64) {
        (
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
        )
    }

    /// Returns the total number of tool invocations in this turn.
    #[must_use]
    pub fn tool_use_count(&self) -> usize {
        self.tool_names_seq.len()
    }

    /// Returns a sorted, deduplicated list of unique tool names invoked.
    #[must_use]
    pub fn unique_tool_names(&self) -> Vec<&str> {
        let mut names: Vec<&str> = self.tool_names_seq.iter().map(String::as_str).collect();
        names.sort_unstable();
        names.dedup();
        names
    }

    /// Returns the current span status.
    #[must_use]
    pub fn status(&self) -> TurnStatus {
        self.status.clone()
    }

    /// Returns the error type, if set.
    #[must_use]
    pub fn error_type(&self) -> Option<&str> {
        self.error_type.as_deref()
    }

    /// Returns the error message, if set.
    #[must_use]
    pub fn error_message(&self) -> Option<&str> {
        self.error_message.as_deref()
    }

    /// Returns the latency in milliseconds, if set.
    #[must_use]
    pub fn latency_ms(&self) -> Option<f64> {
        self.latency_ms
    }
}
