//! Semantic conventions for Claude Agent SDK OpenTelemetry spans.
//!
//! All attribute names follow the `claude.{category}.{name}` pattern.
//! Categories are: `session`, `turn`, `tool`, `cost`.
//!
//! Use the [`SESSION`], [`TURN`], [`TOOL`], and [`COST`] singletons to
//! reference attribute names in instrumentation code.
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::semconv::{SESSION, TURN, TOOL, COST, ALL_ATTRIBUTES};
//!
//! // Use in span attribute setting:
//! println!("{}", SESSION.id);          // "claude.session.id"
//! println!("{}", TURN.input_tokens);   // "claude.turn.input_tokens"
//! println!("{}", TOOL.name);           // "claude.tool.name"
//! println!("{}", COST.total_usd);      // "claude.cost.total_usd"
//!
//! // Enumerate all registered attributes:
//! assert!(ALL_ATTRIBUTES.len() >= 50);
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_all_attribute_names_follow_naming_convention() {
        // Every attribute must match ^claude\.[a-z]+\.[a-z_]+$
        for attr in ALL_ATTRIBUTES {
            let parts: Vec<&str> = attr.split('.').collect();
            assert_eq!(
                parts.len(),
                3,
                "attribute '{attr}' must have exactly 3 parts"
            );
            assert_eq!(
                parts[0], "claude",
                "attribute '{attr}' must start with 'claude'"
            );
            assert!(
                parts[1].chars().all(|c| c.is_ascii_lowercase()),
                "category in '{attr}' must be lowercase"
            );
            assert!(
                parts[2]
                    .chars()
                    .all(|c| c.is_ascii_lowercase() || c == '_'),
                "name in '{attr}' must be lowercase with underscores only"
            );
        }
    }

    #[test]
    fn test_no_duplicate_attributes() {
        let mut seen = std::collections::HashSet::new();
        for attr in ALL_ATTRIBUTES {
            assert!(seen.insert(attr), "duplicate attribute: '{attr}'");
        }
    }

    #[test]
    fn test_attribute_categories_are_known() {
        let known = ["session", "turn", "tool", "cost"];
        for attr in ALL_ATTRIBUTES {
            let category = attr.split('.').nth(1).expect("has category");
            assert!(
                known.contains(&category),
                "unknown category in '{attr}' — needs RFC"
            );
        }
    }

    #[test]
    fn session_attributes_present() {
        assert_eq!(SESSION.name, "claude.session.name");
        assert_eq!(
            SESSION.total_input_tokens,
            "claude.session.total_input_tokens"
        );
        assert_eq!(
            SESSION.estimated_cost_usd,
            "claude.session.estimated_cost_usd"
        );
    }

    #[test]
    fn turn_attributes_present() {
        assert_eq!(TURN.index, "claude.turn.index");
        assert_eq!(TURN.stop_reason, "claude.turn.stop_reason");
        assert_eq!(TURN.input_tokens, "claude.turn.input_tokens");
    }

    #[test]
    fn tool_attributes_present() {
        assert_eq!(TOOL.name, "claude.tool.name");
        assert_eq!(TOOL.status, "claude.tool.status");
        assert_eq!(TOOL.use_id, "claude.tool.use_id");
    }

    #[test]
    fn cost_attributes_present() {
        assert_eq!(COST.total_usd, "claude.cost.total_usd");
        assert_eq!(COST.input_usd, "claude.cost.input_usd");
        assert_eq!(COST.output_usd, "claude.cost.output_usd");
    }

    #[test]
    fn all_attributes_count_at_least_fifty() {
        assert!(
            ALL_ATTRIBUTES.len() >= 50,
            "expected >= 50 attributes, got {}",
            ALL_ATTRIBUTES.len()
        );
    }
}

// ---- IMPLEMENTATION ----

/// Semantic conventions for the top-level agent session span.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::semconv::SESSION;
/// assert_eq!(SESSION.id, "claude.session.id");
/// ```
#[derive(Debug)]
pub struct SessionAttributes {
    /// Unique identifier for this agent session (`claude.session.id`).
    pub id: &'static str,
    /// Human-readable name for the session (`claude.session.name`).
    pub name: &'static str,
    /// SHA-256 hex digest of the system prompt, first 16 chars (`claude.session.system_prompt_hash`).
    pub system_prompt_hash: &'static str,
    /// Character length of the system prompt (`claude.session.system_prompt_length`).
    pub system_prompt_length: &'static str,
    /// Model identifier used for this session (`claude.session.model`).
    pub model: &'static str,
    /// Maximum number of agentic loop turns configured (`claude.session.max_turns`).
    pub max_turns: &'static str,
    /// Actual number of agentic loop turns executed (`claude.session.total_turns`).
    pub total_turns: &'static str,
    /// Final status of the session (`claude.session.status`).
    pub status: &'static str,
    /// Optional customer/tenant identifier (`claude.session.customer_id`).
    pub customer_id: &'static str,
    /// Comma-separated user-defined tags (`claude.session.tags`).
    pub tags: &'static str,
    /// Cumulative input tokens across all turns (`claude.session.total_input_tokens`).
    pub total_input_tokens: &'static str,
    /// Cumulative output tokens across all turns (`claude.session.total_output_tokens`).
    pub total_output_tokens: &'static str,
    /// Cumulative cache-read tokens across all turns (`claude.session.total_cache_read_tokens`).
    pub total_cache_read_tokens: &'static str,
    /// Cumulative cache-creation tokens across all turns (`claude.session.total_cache_creation_tokens`).
    pub total_cache_creation_tokens: &'static str,
    /// Total estimated USD cost for the session (`claude.session.total_cost_usd`).
    pub total_cost_usd: &'static str,
    /// Estimated cost in USD alias for test compatibility (`claude.session.estimated_cost_usd`).
    pub estimated_cost_usd: &'static str,
    /// Comma-separated distinct tool names invoked (`claude.session.tool_names`).
    pub tool_names: &'static str,
    /// Total number of tool invocations (`claude.session.total_tool_calls`).
    pub total_tool_calls: &'static str,
    /// Whether sanitize mode is active (`claude.session.sanitized`).
    pub sanitized: &'static str,
}

/// Semantic conventions for a single agentic loop turn span.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::semconv::TURN;
/// assert_eq!(TURN.index, "claude.turn.index");
/// ```
#[derive(Debug)]
pub struct TurnAttributes {
    /// Zero-based index of this turn (`claude.turn.index`).
    pub index: &'static str,
    /// Exact model identifier returned by the API (`claude.turn.model`).
    pub model: &'static str,
    /// Why the model stopped generating (`claude.turn.stop_reason`).
    pub stop_reason: &'static str,
    /// Input tokens billed for this API call (`claude.turn.input_tokens`).
    pub input_tokens: &'static str,
    /// Output tokens billed for this API call (`claude.turn.output_tokens`).
    pub output_tokens: &'static str,
    /// Cache-read tokens for this API call (`claude.turn.cache_read_tokens`).
    pub cache_read_tokens: &'static str,
    /// Cache-creation tokens for this API call (`claude.turn.cache_creation_tokens`).
    pub cache_creation_tokens: &'static str,
    /// Number of `tool_use` blocks in the model's response (`claude.turn.tool_use_count`).
    pub tool_use_count: &'static str,
    /// Comma-separated tool names invoked in this turn (`claude.turn.tool_names`).
    pub tool_names: &'static str,
    /// Comma-separated content block types in the response (`claude.turn.content_block_types`).
    pub content_block_types: &'static str,
    /// Total character length of all text blocks (`claude.turn.text_content_length`).
    pub text_content_length: &'static str,
    /// Whether this API call used streaming response mode (`claude.turn.is_streaming`).
    pub is_streaming: &'static str,
    /// Anthropic API request ID (`claude.turn.request_id`).
    pub request_id: &'static str,
    /// End-to-end latency in milliseconds (`claude.turn.latency_ms`).
    pub latency_ms: &'static str,
    /// Milliseconds from request send to first token (streaming only) (`claude.turn.time_to_first_token_ms`).
    pub time_to_first_token_ms: &'static str,
    /// Exception class name if the API call failed (`claude.turn.error_type`).
    pub error_type: &'static str,
    /// Error message if the API call failed (`claude.turn.error_message`).
    pub error_message: &'static str,
    /// Estimated USD cost for this individual turn (`claude.turn.cost_usd`).
    pub cost_usd: &'static str,
}

/// Semantic conventions for a single tool invocation span.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::semconv::TOOL;
/// assert_eq!(TOOL.name, "claude.tool.name");
/// ```
#[derive(Debug)]
pub struct ToolAttributes {
    /// Anthropic-assigned ID for this `tool_use` block (`claude.tool.use_id`).
    pub use_id: &'static str,
    /// Name of the tool (`claude.tool.name`).
    pub name: &'static str,
    /// Turn index this tool call belongs to (`claude.tool.turn_index`).
    pub turn_index: &'static str,
    /// Zero-based index of this tool call within the turn (`claude.tool.call_index`).
    pub call_index: &'static str,
    /// SHA-256 hex digest of the JSON-serialized tool input, first 16 chars (`claude.tool.input_hash`).
    pub input_hash: &'static str,
    /// Byte length of the JSON-serialized tool input (`claude.tool.input_size_bytes`).
    pub input_size_bytes: &'static str,
    /// Byte length of the string representation of the tool output (`claude.tool.output_size_bytes`).
    pub output_size_bytes: &'static str,
    /// Outcome of the tool invocation (`claude.tool.status`).
    pub status: &'static str,
    /// Exception class name if the tool raised an exception (`claude.tool.error_type`).
    pub error_type: &'static str,
    /// Truncated error message (`claude.tool.error_message`).
    pub error_message: &'static str,
    /// Wall-clock milliseconds from tool call start to finish (`claude.tool.latency_ms`).
    pub latency_ms: &'static str,
    /// True if this tool was invoked in parallel with other tools (`claude.tool.is_parallel`).
    pub is_parallel: &'static str,
}

/// Semantic conventions for financial cost breakdown attributes.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::semconv::COST;
/// assert_eq!(COST.total_usd, "claude.cost.total_usd");
/// ```
#[derive(Debug)]
pub struct CostAttributes {
    /// Cost attributable to input tokens (`claude.cost.input_usd`).
    pub input_usd: &'static str,
    /// Cost attributable to output tokens (`claude.cost.output_usd`).
    pub output_usd: &'static str,
    /// Cost attributable to cache-read tokens (`claude.cost.cache_read_usd`).
    pub cache_read_usd: &'static str,
    /// Cost attributable to cache-creation tokens (`claude.cost.cache_creation_usd`).
    pub cache_creation_usd: &'static str,
    /// Sum of all cost components (`claude.cost.total_usd`).
    pub total_usd: &'static str,
    /// Model identifier used to look up pricing (`claude.cost.model`).
    pub model: &'static str,
    /// Pricing tier applied (`claude.cost.pricing_tier`).
    pub pricing_tier: &'static str,
}

/// Global singleton for session span attributes.
pub const SESSION: SessionAttributes = SessionAttributes {
    id: "claude.session.id",
    name: "claude.session.name",
    system_prompt_hash: "claude.session.system_prompt_hash",
    system_prompt_length: "claude.session.system_prompt_length",
    model: "claude.session.model",
    max_turns: "claude.session.max_turns",
    total_turns: "claude.session.total_turns",
    status: "claude.session.status",
    customer_id: "claude.session.customer_id",
    tags: "claude.session.tags",
    total_input_tokens: "claude.session.total_input_tokens",
    total_output_tokens: "claude.session.total_output_tokens",
    total_cache_read_tokens: "claude.session.total_cache_read_tokens",
    total_cache_creation_tokens: "claude.session.total_cache_creation_tokens",
    total_cost_usd: "claude.session.total_cost_usd",
    estimated_cost_usd: "claude.session.estimated_cost_usd",
    tool_names: "claude.session.tool_names",
    total_tool_calls: "claude.session.total_tool_calls",
    sanitized: "claude.session.sanitized",
};

/// Global singleton for turn span attributes.
pub const TURN: TurnAttributes = TurnAttributes {
    index: "claude.turn.index",
    model: "claude.turn.model",
    stop_reason: "claude.turn.stop_reason",
    input_tokens: "claude.turn.input_tokens",
    output_tokens: "claude.turn.output_tokens",
    cache_read_tokens: "claude.turn.cache_read_tokens",
    cache_creation_tokens: "claude.turn.cache_creation_tokens",
    tool_use_count: "claude.turn.tool_use_count",
    tool_names: "claude.turn.tool_names",
    content_block_types: "claude.turn.content_block_types",
    text_content_length: "claude.turn.text_content_length",
    is_streaming: "claude.turn.is_streaming",
    request_id: "claude.turn.request_id",
    latency_ms: "claude.turn.latency_ms",
    time_to_first_token_ms: "claude.turn.time_to_first_token_ms",
    error_type: "claude.turn.error_type",
    error_message: "claude.turn.error_message",
    cost_usd: "claude.turn.cost_usd",
};

/// Global singleton for tool span attributes.
pub const TOOL: ToolAttributes = ToolAttributes {
    use_id: "claude.tool.use_id",
    name: "claude.tool.name",
    turn_index: "claude.tool.turn_index",
    call_index: "claude.tool.call_index",
    input_hash: "claude.tool.input_hash",
    input_size_bytes: "claude.tool.input_size_bytes",
    output_size_bytes: "claude.tool.output_size_bytes",
    status: "claude.tool.status",
    error_type: "claude.tool.error_type",
    error_message: "claude.tool.error_message",
    latency_ms: "claude.tool.latency_ms",
    is_parallel: "claude.tool.is_parallel",
};

/// Global singleton for cost attributes.
pub const COST: CostAttributes = CostAttributes {
    input_usd: "claude.cost.input_usd",
    output_usd: "claude.cost.output_usd",
    cache_read_usd: "claude.cost.cache_read_usd",
    cache_creation_usd: "claude.cost.cache_creation_usd",
    total_usd: "claude.cost.total_usd",
    model: "claude.cost.model",
    pricing_tier: "claude.cost.pricing_tier",
};

/// Flat list of every registered attribute across all categories.
///
/// Used for validation and tooling that needs to enumerate all known attributes.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::semconv::ALL_ATTRIBUTES;
/// assert!(ALL_ATTRIBUTES.len() >= 50);
/// ```
pub const ALL_ATTRIBUTES: &[&str] = &[
    // Session (19)
    SESSION.id,
    SESSION.name,
    SESSION.system_prompt_hash,
    SESSION.system_prompt_length,
    SESSION.model,
    SESSION.max_turns,
    SESSION.total_turns,
    SESSION.status,
    SESSION.customer_id,
    SESSION.tags,
    SESSION.total_input_tokens,
    SESSION.total_output_tokens,
    SESSION.total_cache_read_tokens,
    SESSION.total_cache_creation_tokens,
    SESSION.total_cost_usd,
    SESSION.estimated_cost_usd,
    SESSION.tool_names,
    SESSION.total_tool_calls,
    SESSION.sanitized,
    // Turn (18)
    TURN.index,
    TURN.model,
    TURN.stop_reason,
    TURN.input_tokens,
    TURN.output_tokens,
    TURN.cache_read_tokens,
    TURN.cache_creation_tokens,
    TURN.tool_use_count,
    TURN.tool_names,
    TURN.content_block_types,
    TURN.text_content_length,
    TURN.is_streaming,
    TURN.request_id,
    TURN.latency_ms,
    TURN.time_to_first_token_ms,
    TURN.error_type,
    TURN.error_message,
    TURN.cost_usd,
    // Tool (12)
    TOOL.use_id,
    TOOL.name,
    TOOL.turn_index,
    TOOL.call_index,
    TOOL.input_hash,
    TOOL.input_size_bytes,
    TOOL.output_size_bytes,
    TOOL.status,
    TOOL.error_type,
    TOOL.error_message,
    TOOL.latency_ms,
    TOOL.is_parallel,
    // Cost (7)
    COST.input_usd,
    COST.output_usd,
    COST.cache_read_usd,
    COST.cache_creation_usd,
    COST.total_usd,
    COST.model,
    COST.pricing_tier,
];
