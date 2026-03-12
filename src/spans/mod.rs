//! Span lifecycle management for Claude Agent SDK sessions, turns, and tools.
//!
//! The three span types mirror the agent hierarchy:
//!
//! ```text
//! claude.session  (root)
//! └── claude.turn[0]
//!     ├── claude.tool[bash_0]
//!     └── claude.tool[read_file_1]
//! └── claude.turn[1]
//!     └── ...
//! ```
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::spans::{SpanConfig, SessionSpan};
//!
//! let config = SpanConfig::default();
//! let mut session = SessionSpan::new("my-agent-session", &config);
//! session.set_model("claude-sonnet-4-6");
//! session.add_turn_tokens(1000, 500, 200, 50);
//! session.finish_ok();
//! ```

pub mod session;
pub mod tool;
pub mod turn;

pub use session::SessionSpan;
pub use tool::ToolSpan;
pub use turn::TurnSpan;

/// Configuration controlling span data capture behaviour.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::SpanConfig;
///
/// let config = SpanConfig {
///     capture_content: true,
///     max_attribute_length: 256,
///     sanitize: false,
/// };
/// assert_eq!(config.max_attribute_length, 256);
/// ```
#[derive(Debug, Clone)]
pub struct SpanConfig {
    /// When `true`, capture full text content in span attributes.
    /// Default: `false` (only structural metadata is captured).
    pub capture_content: bool,
    /// Maximum length for any string attribute value before truncation.
    /// Default: `512`.
    pub max_attribute_length: usize,
    /// When `true`, omit PII-bearing attributes (e.g. `customer_id`) and set
    /// `claude.session.sanitized = true` on the session span.
    /// Default: `false`.
    pub sanitize: bool,
}

impl Default for SpanConfig {
    /// Create a `SpanConfig` with safe production defaults.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::spans::SpanConfig;
    ///
    /// let config = SpanConfig::default();
    /// assert!(!config.capture_content);
    /// assert_eq!(config.max_attribute_length, 512);
    /// assert!(!config.sanitize);
    /// ```
    fn default() -> Self {
        Self {
            capture_content: false,
            max_attribute_length: 512,
            sanitize: false,
        }
    }
}

/// Truncate a string to `max_len` bytes at a UTF-8 character boundary.
/// Returns the original string if it is already within the limit.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::spans::truncate_attribute;
///
/// let s = truncate_attribute("hello world", 5);
/// assert_eq!(s, "hello");
/// ```
#[must_use]
pub fn truncate_attribute(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        return s.to_owned();
    }
    // Walk back from max_len to find a valid char boundary.
    let mut boundary = max_len;
    while boundary > 0 && !s.is_char_boundary(boundary) {
        boundary -= 1;
    }
    s[..boundary].to_owned()
}
