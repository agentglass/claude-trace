//! Session span — the root span covering a full agent session lifecycle.
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::spans::{SessionSpan, SpanConfig};
//!
//! let config = SpanConfig::default();
//! let mut s = SessionSpan::new("my-session", &config);
//! s.set_model("claude-sonnet-4-6");
//! s.add_turn_tokens(1000, 500, 0, 0);
//! s.finish_ok();
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;

    fn default_config() -> SpanConfig {
        SpanConfig::default()
    }

    #[test]
    fn test_new_sets_name() {
        let s = SessionSpan::new("my-agent", &default_config());
        assert_eq!(s.name(), "my-agent");
    }

    #[test]
    fn test_set_model() {
        let mut s = SessionSpan::new("test", &default_config());
        s.set_model("claude-sonnet-4-6");
        assert_eq!(s.model(), Some("claude-sonnet-4-6"));
    }

    #[test]
    fn test_set_customer_id_normal_mode() {
        let mut s = SessionSpan::new("test", &default_config());
        s.set_customer_id("customer_acme");
        assert_eq!(s.customer_id(), Some("customer_acme"));
    }

    #[test]
    fn test_set_customer_id_sanitize_mode() {
        let config = SpanConfig {
            sanitize: true,
            ..SpanConfig::default()
        };
        let mut s = SessionSpan::new("test", &config);
        s.set_customer_id("customer_acme");
        // In sanitize mode the customer_id must be suppressed
        assert_eq!(s.customer_id(), None);
    }

    #[test]
    fn test_sanitize_sets_sanitized_flag() {
        let config = SpanConfig {
            sanitize: true,
            ..SpanConfig::default()
        };
        let s = SessionSpan::new("test", &config);
        assert!(s.is_sanitized());
    }

    #[test]
    fn test_add_turn_tokens_accumulates() {
        let mut s = SessionSpan::new("test", &default_config());
        s.add_turn_tokens(1000, 500, 200, 50);
        s.add_turn_tokens(500, 250, 100, 25);
        let (inp, out, cr, cw) = s.total_tokens();
        assert_eq!(inp, 1500);
        assert_eq!(out, 750);
        assert_eq!(cr, 300);
        assert_eq!(cw, 75);
    }

    #[test]
    fn test_finish_ok_sets_status() {
        let mut s = SessionSpan::new("test", &default_config());
        s.finish_ok();
        assert_eq!(s.status(), SpanStatus::Ok);
    }

    #[test]
    fn test_finish_error_sets_status_and_message() {
        let mut s = SessionSpan::new("test", &default_config());
        s.finish_error("something went wrong");
        assert_eq!(s.status(), SpanStatus::Error);
        assert_eq!(s.error_message(), Some("something went wrong"));
    }

    #[test]
    fn test_string_truncation_applied() {
        let config = SpanConfig {
            max_attribute_length: 10,
            ..SpanConfig::default()
        };
        let long_name = "a".repeat(100);
        let s = SessionSpan::new(&long_name, &config);
        assert_eq!(s.name().len(), 10);
    }

    #[test]
    fn test_turn_count_increments() {
        let mut s = SessionSpan::new("test", &default_config());
        assert_eq!(s.turn_count(), 0);
        s.add_turn_tokens(100, 50, 0, 0);
        s.increment_turn();
        assert_eq!(s.turn_count(), 1);
        s.add_turn_tokens(100, 50, 0, 0);
        s.increment_turn();
        assert_eq!(s.turn_count(), 2);
    }

    #[test]
    fn test_default_status_is_unset() {
        let s = SessionSpan::new("test", &default_config());
        assert_eq!(s.status(), SpanStatus::Unset);
    }
}

// ---- IMPLEMENTATION ----

use super::{truncate_attribute, SpanConfig};

/// Status of a span at finish time.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::session::SpanStatus;
///
/// let s = SpanStatus::Ok;
/// assert_eq!(s, SpanStatus::Ok);
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SpanStatus {
    /// Span has not been finished yet.
    Unset,
    /// Span finished successfully.
    Ok,
    /// Span finished with an error.
    Error,
}

/// Root span covering the full lifecycle of a single agent session.
///
/// Tracks cumulative token counts across all turns and exposes
/// methods to set span attributes following claude-trace semantic conventions.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
///
/// let config = SpanConfig::default();
/// let mut session = SessionSpan::new("summarization-task", &config);
/// session.set_model("claude-sonnet-4-6");
/// session.add_turn_tokens(5000, 1200, 3000, 500);
/// session.finish_ok();
/// assert_eq!(session.status(), _claude_trace_core::spans::session::SpanStatus::Ok);
/// ```
#[derive(Debug)]
pub struct SessionSpan {
    name: String,
    model: Option<String>,
    customer_id: Option<String>,
    total_input_tokens: u64,
    total_output_tokens: u64,
    total_cache_read_tokens: u64,
    total_cache_write_tokens: u64,
    turn_count: u32,
    status: SpanStatus,
    error_message: Option<String>,
    sanitized: bool,
    max_attribute_length: usize,
}

impl SessionSpan {
    /// Create a new `SessionSpan` with the given name and configuration.
    ///
    /// The `name` is truncated to `config.max_attribute_length` if needed.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    ///
    /// let s = SessionSpan::new("my-session", &SpanConfig::default());
    /// assert_eq!(s.name(), "my-session");
    /// ```
    #[must_use]
    pub fn new(name: &str, config: &SpanConfig) -> Self {
        Self {
            name: truncate_attribute(name, config.max_attribute_length),
            model: None,
            customer_id: None,
            total_input_tokens: 0,
            total_output_tokens: 0,
            total_cache_read_tokens: 0,
            total_cache_write_tokens: 0,
            turn_count: 0,
            status: SpanStatus::Unset,
            error_message: None,
            sanitized: config.sanitize,
            max_attribute_length: config.max_attribute_length,
        }
    }

    /// Set the model identifier for this session.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    ///
    /// let mut s = SessionSpan::new("t", &SpanConfig::default());
    /// s.set_model("claude-sonnet-4-6");
    /// assert_eq!(s.model(), Some("claude-sonnet-4-6"));
    /// ```
    pub fn set_model(&mut self, model: &str) {
        self.model = Some(truncate_attribute(model, self.max_attribute_length));
    }

    /// Set the customer identifier.
    ///
    /// In sanitize mode this is silently dropped (no-op).
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    ///
    /// let mut s = SessionSpan::new("t", &SpanConfig::default());
    /// s.set_customer_id("acme");
    /// assert_eq!(s.customer_id(), Some("acme"));
    /// ```
    pub fn set_customer_id(&mut self, id: &str) {
        if !self.sanitized {
            self.customer_id = Some(truncate_attribute(id, self.max_attribute_length));
        }
    }

    /// Accumulate token counts from one turn into the session totals.
    ///
    /// Call this once per completed turn to keep running session totals.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    ///
    /// let mut s = SessionSpan::new("t", &SpanConfig::default());
    /// s.add_turn_tokens(1000, 500, 200, 50);
    /// let (inp, out, cr, cw) = s.total_tokens();
    /// assert_eq!(inp, 1000);
    /// ```
    pub fn add_turn_tokens(
        &mut self,
        input: u64,
        output: u64,
        cache_read: u64,
        cache_write: u64,
    ) {
        self.total_input_tokens += input;
        self.total_output_tokens += output;
        self.total_cache_read_tokens += cache_read;
        self.total_cache_write_tokens += cache_write;
    }

    /// Increment the internal turn counter.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    ///
    /// let mut s = SessionSpan::new("t", &SpanConfig::default());
    /// s.increment_turn();
    /// assert_eq!(s.turn_count(), 1);
    /// ```
    pub fn increment_turn(&mut self) {
        self.turn_count += 1;
    }

    /// Mark the span as successfully completed.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    /// use _claude_trace_core::spans::session::SpanStatus;
    ///
    /// let mut s = SessionSpan::new("t", &SpanConfig::default());
    /// s.finish_ok();
    /// assert_eq!(s.status(), SpanStatus::Ok);
    /// ```
    pub fn finish_ok(&mut self) {
        self.status = SpanStatus::Ok;
    }

    /// Mark the span as failed with the given error message.
    ///
    /// The message is truncated to `max_attribute_length`.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{SessionSpan, SpanConfig};
    /// use _claude_trace_core::spans::session::SpanStatus;
    ///
    /// let mut s = SessionSpan::new("t", &SpanConfig::default());
    /// s.finish_error("boom");
    /// assert_eq!(s.status(), SpanStatus::Error);
    /// ```
    pub fn finish_error(&mut self, msg: &str) {
        self.status = SpanStatus::Error;
        self.error_message = Some(truncate_attribute(msg, self.max_attribute_length));
    }

    // ---- Accessors (used in tests and by export layer) ----

    /// Returns the session name.
    #[must_use]
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Returns the model identifier, if set.
    #[must_use]
    pub fn model(&self) -> Option<&str> {
        self.model.as_deref()
    }

    /// Returns the customer identifier, if set and not suppressed by sanitize mode.
    #[must_use]
    pub fn customer_id(&self) -> Option<&str> {
        self.customer_id.as_deref()
    }

    /// Returns cumulative token counts: `(input, output, cache_read, cache_write)`.
    #[must_use]
    pub fn total_tokens(&self) -> (u64, u64, u64, u64) {
        (
            self.total_input_tokens,
            self.total_output_tokens,
            self.total_cache_read_tokens,
            self.total_cache_write_tokens,
        )
    }

    /// Returns the number of turns completed.
    #[must_use]
    pub fn turn_count(&self) -> u32 {
        self.turn_count
    }

    /// Returns the current span status.
    #[must_use]
    pub fn status(&self) -> SpanStatus {
        self.status.clone()
    }

    /// Returns the error message, if set.
    #[must_use]
    pub fn error_message(&self) -> Option<&str> {
        self.error_message.as_deref()
    }

    /// Returns `true` when sanitize mode is active.
    #[must_use]
    pub fn is_sanitized(&self) -> bool {
        self.sanitized
    }
}
