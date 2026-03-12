//! Tool span — covers a single tool invocation within a turn.
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::spans::{ToolSpan, SpanConfig};
//!
//! let config = SpanConfig::default();
//! let mut tool = ToolSpan::new("bash", "toolu_01ABC", 0, 0, &config);
//! tool.set_input_json(r#"{"cmd":"ls"}"#);
//! tool.set_output_size(128);
//! tool.set_latency_ms(47.3);
//! tool.finish_ok();
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;

    fn default_config() -> SpanConfig {
        SpanConfig::default()
    }

    #[test]
    fn test_new_stores_tool_name() {
        let t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        assert_eq!(t.name(), "bash");
    }

    #[test]
    fn test_new_stores_use_id() {
        let t = ToolSpan::new("read_file", "toolu_XYZ", 1, 2, &default_config());
        assert_eq!(t.use_id(), "toolu_XYZ");
    }

    #[test]
    fn test_new_stores_indices() {
        let t = ToolSpan::new("bash", "toolu_001", 3, 2, &default_config());
        assert_eq!(t.turn_index(), 3);
        assert_eq!(t.call_index(), 2);
    }

    #[test]
    fn test_input_hash_is_sha256_prefix() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        let json = r#"{"command":"ls -la"}"#;
        t.set_input_json(json);
        let hash = t.input_hash().expect("hash must be set after set_input_json");
        // Must be 16 hex chars
        assert_eq!(hash.len(), 16, "hash length: {hash}");
        assert!(
            hash.chars().all(|c| c.is_ascii_hexdigit()),
            "hash must be hex: {hash}"
        );
    }

    #[test]
    fn test_input_hash_deterministic() {
        let json = r#"{"command":"pwd"}"#;
        let mut a = ToolSpan::new("bash", "toolu_a", 0, 0, &default_config());
        let mut b = ToolSpan::new("bash", "toolu_b", 0, 0, &default_config());
        a.set_input_json(json);
        b.set_input_json(json);
        assert_eq!(a.input_hash(), b.input_hash());
    }

    #[test]
    fn test_input_size_bytes_set() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        let json = r#"{"cmd":"echo hi"}"#;
        t.set_input_json(json);
        assert_eq!(t.input_size_bytes(), json.len() as u64);
    }

    #[test]
    fn test_output_size_bytes() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        t.set_output_size(256);
        assert_eq!(t.output_size_bytes(), Some(256));
    }

    #[test]
    fn test_finish_ok_sets_status() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        t.finish_ok();
        assert_eq!(t.status(), ToolStatus::Success);
    }

    #[test]
    fn test_finish_error_sets_status_and_fields() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        t.finish_error("FileNotFoundError", "no such file");
        assert_eq!(t.status(), ToolStatus::Error);
        assert_eq!(t.error_type(), Some("FileNotFoundError"));
        assert_eq!(t.error_message(), Some("no such file"));
    }

    #[test]
    fn test_latency_ms_stored() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        t.set_latency_ms(123.4);
        assert!((t.latency_ms().unwrap_or(0.0) - 123.4).abs() < 1e-9);
    }

    #[test]
    fn test_default_status_is_unset() {
        let t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        assert_eq!(t.status(), ToolStatus::Unset);
    }

    #[test]
    fn test_is_parallel_flag() {
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &default_config());
        assert!(!t.is_parallel());
        t.set_parallel(true);
        assert!(t.is_parallel());
    }

    #[test]
    fn test_string_truncation_for_error_message() {
        let config = SpanConfig {
            max_attribute_length: 8,
            ..SpanConfig::default()
        };
        let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &config);
        t.finish_error("SomeVeryLongErrorType", "A very long error message");
        // truncated to 8 chars
        assert_eq!(t.error_type().map(str::len), Some(8));
        assert_eq!(t.error_message().map(str::len), Some(8));
    }
}

// ---- IMPLEMENTATION ----

use sha2::{Digest, Sha256};

use super::{truncate_attribute, SpanConfig};

/// Status of a tool invocation.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::tool::ToolStatus;
///
/// assert_eq!(ToolStatus::Success, ToolStatus::Success);
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ToolStatus {
    /// Not yet finished.
    Unset,
    /// Tool executed successfully.
    Success,
    /// Tool raised an exception or returned an error.
    Error,
    /// Tool execution timed out.
    Timeout,
    /// Tool was cancelled.
    Cancelled,
}

/// Span covering a single tool invocation.
///
/// Each `tool_use` block in a model response generates one `ToolSpan`.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
///
/// let config = SpanConfig::default();
/// let mut tool = ToolSpan::new("bash", "toolu_01ABC", 0, 0, &config);
/// tool.set_input_json(r#"{"command":"ls"}"#);
/// tool.set_output_size(512);
/// tool.set_latency_ms(42.0);
/// tool.finish_ok();
/// assert_eq!(tool.status(), _claude_trace_core::spans::tool::ToolStatus::Success);
/// ```
#[derive(Debug)]
pub struct ToolSpan {
    name: String,
    use_id: String,
    turn_index: u32,
    call_index: u32,
    input_hash: Option<String>,
    input_size_bytes: u64,
    output_size_bytes: Option<u64>,
    status: ToolStatus,
    error_type: Option<String>,
    error_message: Option<String>,
    latency_ms: Option<f64>,
    is_parallel: bool,
    max_attribute_length: usize,
}

impl ToolSpan {
    /// Create a new `ToolSpan`.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    ///
    /// let t = ToolSpan::new("bash", "toolu_001", 1, 0, &SpanConfig::default());
    /// assert_eq!(t.name(), "bash");
    /// ```
    #[must_use]
    pub fn new(name: &str, use_id: &str, turn_index: u32, call_index: u32, config: &SpanConfig) -> Self {
        Self {
            name: truncate_attribute(name, config.max_attribute_length),
            use_id: truncate_attribute(use_id, config.max_attribute_length),
            turn_index,
            call_index,
            input_hash: None,
            input_size_bytes: 0,
            output_size_bytes: None,
            status: ToolStatus::Unset,
            error_type: None,
            error_message: None,
            latency_ms: None,
            is_parallel: false,
            max_attribute_length: config.max_attribute_length,
        }
    }

    /// Set the JSON-serialized tool input.
    ///
    /// This computes `input_size_bytes` and sets `input_hash` as the
    /// first 16 hex chars of the SHA-256 digest of the raw JSON string.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.set_input_json(r#"{"cmd":"pwd"}"#);
    /// assert!(t.input_hash().is_some());
    /// ```
    pub fn set_input_json(&mut self, json: &str) {
        self.input_size_bytes = json.len() as u64;
        let digest = Sha256::digest(json.as_bytes());
        let full_hex = hex::encode(digest);
        // Take first 16 hex chars (8 bytes)
        self.input_hash = Some(full_hex[..16].to_owned());
    }

    /// Set the byte length of the tool output.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.set_output_size(1024);
    /// assert_eq!(t.output_size_bytes(), Some(1024));
    /// ```
    pub fn set_output_size(&mut self, bytes: u64) {
        self.output_size_bytes = Some(bytes);
    }

    /// Set the wall-clock latency for this tool invocation.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.set_latency_ms(50.5);
    /// assert!(t.latency_ms().is_some());
    /// ```
    pub fn set_latency_ms(&mut self, ms: f64) {
        self.latency_ms = Some(ms);
    }

    /// Set whether this tool was invoked in parallel with others in the same turn.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.set_parallel(true);
    /// assert!(t.is_parallel());
    /// ```
    pub fn set_parallel(&mut self, parallel: bool) {
        self.is_parallel = parallel;
    }

    /// Mark the tool as successfully completed.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    /// use _claude_trace_core::spans::tool::ToolStatus;
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.finish_ok();
    /// assert_eq!(t.status(), ToolStatus::Success);
    /// ```
    pub fn finish_ok(&mut self) {
        self.status = ToolStatus::Success;
    }

    /// Mark the tool as failed with error type and message.
    ///
    /// Both strings are truncated to `max_attribute_length`.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    /// use _claude_trace_core::spans::tool::ToolStatus;
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.finish_error("IOError", "permission denied");
    /// assert_eq!(t.status(), ToolStatus::Error);
    /// ```
    pub fn finish_error(&mut self, error_type: &str, error_message: &str) {
        self.status = ToolStatus::Error;
        self.error_type = Some(truncate_attribute(error_type, self.max_attribute_length));
        self.error_message = Some(truncate_attribute(error_message, self.max_attribute_length));
    }

    /// Mark the tool as timed out.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::{ToolSpan, SpanConfig};
    /// use _claude_trace_core::spans::tool::ToolStatus;
    ///
    /// let mut t = ToolSpan::new("bash", "toolu_001", 0, 0, &SpanConfig::default());
    /// t.finish_timeout();
    /// assert_eq!(t.status(), ToolStatus::Timeout);
    /// ```
    pub fn finish_timeout(&mut self) {
        self.status = ToolStatus::Timeout;
    }

    // ---- Accessors ----

    /// Returns the tool name.
    #[must_use]
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Returns the Anthropic-assigned `tool_use` block ID.
    #[must_use]
    pub fn use_id(&self) -> &str {
        &self.use_id
    }

    /// Returns the turn index this tool call belongs to.
    #[must_use]
    pub fn turn_index(&self) -> u32 {
        self.turn_index
    }

    /// Returns the zero-based call index within the turn.
    #[must_use]
    pub fn call_index(&self) -> u32 {
        self.call_index
    }

    /// Returns the input hash (first 16 hex chars of SHA-256), if set.
    #[must_use]
    pub fn input_hash(&self) -> Option<&str> {
        self.input_hash.as_deref()
    }

    /// Returns the byte length of the JSON-serialized input.
    #[must_use]
    pub fn input_size_bytes(&self) -> u64 {
        self.input_size_bytes
    }

    /// Returns the byte length of the output, if set.
    #[must_use]
    pub fn output_size_bytes(&self) -> Option<u64> {
        self.output_size_bytes
    }

    /// Returns the current tool status.
    #[must_use]
    pub fn status(&self) -> ToolStatus {
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

    /// Returns `true` if this tool was invoked in parallel with others.
    #[must_use]
    pub fn is_parallel(&self) -> bool {
        self.is_parallel
    }
}
