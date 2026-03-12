# Backend Skill — Core Rust Library Development

<!--
skill:
  name: backend
  description: Complete context for developing the claude-trace Rust core. Covers span hierarchy, OTel API patterns, semconv attributes, cost model, security rules, and module responsibilities.
  auto-invoke:
    - "src/**/*.rs"
  triggers:
    - "implement span"
    - "add cost"
    - "modify semconv"
    - "OTel"
    - "opentelemetry"
    - "span attributes"
    - "trace"
-->

## What the Backend Is

The backend is the Rust crate at the root of this repository. Its job is to:

1. **Intercept** Anthropic API calls (via a patching/wrapping mechanism activated by the language bindings)
2. **Create OTel spans** with structured attributes describing each session, turn, and tool call
3. **Calculate costs** using the pricing table in `src/cost/models.rs`
4. **Export** spans via the configured OTLP exporter or any OTel-compatible backend

The backend has **no runtime dependencies on Python or JavaScript**. It is a pure Rust library. Language bindings (PyO3, wasm-bindgen) are feature-gated and add thin wrappers.

---

## Span Hierarchy: The Core Model

This is the most important concept in the entire project. Every contributor must understand it.

```
claude.agent.session  ← root span, one per claude.run() or equivalent agent loop
  │
  ├── claude.agent.turn[0]   ← one complete LLM API call (request + full response)
  │     ├── claude.tool.invocation[bash_0]    ← one tool_use block + its result
  │     └── claude.tool.invocation[read_0]   ← another tool_use block in same turn
  │
  ├── claude.agent.turn[1]   ← second turn (after tool results sent back)
  │     └── claude.tool.invocation[bash_1]
  │
  └── claude.agent.turn[2]   ← final turn (stop_reason = end_turn)
        (no tool invocations — model returned text only)
```

### Span Timing Rules

- **Session span**: starts when `claude_trace.session()` context manager is entered; ends when it exits
- **Turn span**: starts when `anthropic.messages.create()` is called; ends when the full response (including all streamed chunks) is received
- **Tool span**: starts when the tool function is called (after the model response is parsed); ends when the tool function returns or raises

### Parent-Child Relationships

OTel parent-child relationships are established via context propagation:

```rust
// The session span context is set as the current context
let session_cx = Context::current_with_span(session_span);

// Turn spans are started within the session context
let turn_span = tracer.start_with_context("claude.agent.turn", &session_cx);
let turn_cx = Context::current_with_span(turn_span);

// Tool spans are started within the turn context
let tool_span = tracer.start_with_context("claude.tool.invocation", &turn_cx);
```

**Never manually set parent span IDs.** Always use OTel context propagation.

---

## Complete Semconv Attribute Reference

These are ALL `claude.*` attributes defined in `src/semconv/claude.rs`. Every attribute here is part of the public semconv contract — do not rename or remove any of them.

### Session Attributes (`claude.session.*`)

| Attribute | Type | Description |
|---|---|---|
| `claude.session.id` | string | Unique session identifier (opaque, typically `sess_` prefix) |
| `claude.session.system_prompt_hash` | string | SHA-256 hex of system prompt (first 16 chars) |
| `claude.session.system_prompt_length` | int | Character length of system prompt |
| `claude.session.model` | string | Model identifier configured for this session |
| `claude.session.max_turns` | int | Configured max_turns limit |
| `claude.session.total_turns` | int | Actual turns executed (set at session end) |
| `claude.session.status` | string | Final status: `running`, `completed`, `error`, `cancelled`, `max_turns_reached` |
| `claude.session.customer_id` | string | Optional customer/tenant for cost attribution |
| `claude.session.tags` | string | Comma-separated user-defined tags |
| `claude.session.total_input_tokens` | int | Cumulative input tokens (set at session end) |
| `claude.session.total_output_tokens` | int | Cumulative output tokens (set at session end) |
| `claude.session.total_cache_read_tokens` | int | Cumulative cache-read tokens |
| `claude.session.total_cache_creation_tokens` | int | Cumulative cache-creation tokens |
| `claude.session.total_cost_usd` | string | Total estimated USD cost (string for OTel compat) |
| `claude.session.tool_names` | string | Comma-separated distinct tool names used |
| `claude.session.total_tool_calls` | int | Total tool invocations across all turns |

### Turn Attributes (`claude.turn.*`)

| Attribute | Type | Description |
|---|---|---|
| `claude.turn.index` | int | Zero-based turn index within session |
| `claude.turn.model` | string | Exact model ID from API response |
| `claude.turn.stop_reason` | string | `end_turn`, `max_tokens`, `tool_use`, `stop_sequence`, `error` |
| `claude.turn.input_tokens` | int | Input tokens billed for this call |
| `claude.turn.output_tokens` | int | Output tokens billed |
| `claude.turn.cache_read_tokens` | int | Cache-read tokens (discounted) |
| `claude.turn.cache_creation_tokens` | int | Cache-creation tokens (premium) |
| `claude.turn.tool_use_count` | int | Number of tool_use blocks in response |
| `claude.turn.tool_names` | string | Comma-separated tool names in this turn |
| `claude.turn.content_block_types` | string | Comma-separated block types: `text`, `tool_use`, etc. |
| `claude.turn.text_content_length` | int | Total char length of text blocks |
| `claude.turn.is_streaming` | bool | Whether streaming was used |
| `claude.turn.request_id` | string | Anthropic API request ID (`x-request-id` header) |
| `claude.turn.latency_ms` | float | End-to-end latency in milliseconds |
| `claude.turn.time_to_first_token_ms` | float | TTFT for streaming (streaming only) |
| `claude.turn.error_type` | string | Exception class name on error |
| `claude.turn.error_message` | string | Truncated error message (max 500 chars) |
| `claude.turn.cost_usd` | string | Estimated cost for this turn |

### Tool Attributes (`claude.tool.*`)

| Attribute | Type | Description |
|---|---|---|
| `claude.tool.use_id` | string | Anthropic tool_use block ID (`toolu_` prefix) |
| `claude.tool.name` | string | Tool name as defined in tools parameter |
| `claude.tool.turn_index` | int | Parent turn's index (for flat-tree filtering) |
| `claude.tool.call_index` | int | Zero-based index within the turn |
| `claude.tool.input_hash` | string | SHA-256 hex of JSON input (first 16 chars) |
| `claude.tool.input_size_bytes` | int | Byte length of JSON input |
| `claude.tool.output_size_bytes` | int | Byte length of tool output string |
| `claude.tool.status` | string | `success`, `error`, `timeout`, `cancelled` |
| `claude.tool.error_type` | string | Exception class name on error |
| `claude.tool.error_message` | string | Truncated error message (max 500 chars) |
| `claude.tool.latency_ms` | float | Wall-clock milliseconds for the tool call |
| `claude.tool.is_parallel` | bool | True if called in parallel with other tools |

### Cost Attributes (`claude.cost.*`)

| Attribute | Type | Description |
|---|---|---|
| `claude.cost.input_usd` | string | Cost for standard input tokens |
| `claude.cost.output_usd` | string | Cost for output tokens |
| `claude.cost.cache_read_usd` | string | Cost for cache-read tokens |
| `claude.cost.cache_creation_usd` | string | Cost for cache-creation tokens |
| `claude.cost.total_usd` | string | Sum of all cost components |
| `claude.cost.model` | string | Model used for pricing lookup |
| `claude.cost.pricing_tier` | string | `standard`, `volume_1`, `volume_2` |

---

## Cost Calculator: Complete Pricing Table (2026-Q1)

The `src/cost/models.rs` file contains this pricing table. All prices are USD per million tokens:

| Model ID | Input/M | Output/M | Cache Write/M | Cache Read/M |
|---|---|---|---|---|
| `claude-opus-4-5` | $15.00 | $75.00 | $18.75 | $1.50 |
| `claude-opus-4-0` | $15.00 | $75.00 | $18.75 | $1.50 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-sonnet-4-6-20251101` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-sonnet-4-5` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-sonnet-4-5-20250514` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-haiku-4-5` | $0.80 | $4.00 | $1.00 | $0.08 |
| `claude-haiku-4-5-20250514` | $0.80 | $4.00 | $1.00 | $0.08 |
| `claude-3-5-sonnet-20241022` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-3-5-sonnet-20240620` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-3-5-haiku-20241022` | $0.80 | $4.00 | $1.00 | $0.08 |
| `claude-3-opus-20240229` | $15.00 | $75.00 | $18.75 | $1.50 |
| `claude-3-sonnet-20240229` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-3-haiku-20240307` | $0.25 | $1.25 | $0.31 | $0.025 |
| `claude-2.1` | $8.00 | $24.00 | $10.00 | $0.80 |
| `claude-2.0` | $8.00 | $24.00 | $10.00 | $0.80 |
| `unknown` (fallback) | $3.00 | $15.00 | $3.75 | $0.30 |

**To add a new model**: Add an entry to `_PRICING_TABLE` in `src/cost/models.rs`, write a test in `#[cfg(test)] mod tests` asserting the correct price for 1M tokens, and update the pricing table in `site/src/content/docs/internals/cost-model.mdx`.

**Model ID matching**: The calculator uses fuzzy prefix matching. `"claude-sonnet-4-6"` matches `"claude-sonnet-4-6-20251101"` because one is a prefix of the other. The most specific match wins. Implement this with a `starts_with` sort by model_id length descending.

---

## OTel Span API: Correct Patterns

### Initialization

```rust
// src/export/otlp.rs — initialize the global tracer provider
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{runtime, trace as sdktrace};

pub fn init_tracer(config: &ExportConfig) -> Result<sdktrace::Tracer, ClaudeTraceError> {
    let exporter = opentelemetry_otlp::new_exporter()
        .tonic()
        .with_endpoint(&config.otlp_endpoint)
        .build_span_exporter()
        .map_err(|e| ClaudeTraceError::OtelError(e.to_string()))?;

    let provider = sdktrace::TracerProvider::builder()
        .with_batch_exporter(exporter, runtime::Tokio)
        .with_resource(opentelemetry_sdk::Resource::new(vec![
            KeyValue::new("service.name", "claude-trace"),
            KeyValue::new("service.version", env!("CARGO_PKG_VERSION")),
        ]))
        .build();

    Ok(provider.tracer("claude-trace"))
}
```

### Creating Spans

```rust
// Use opentelemetry API crate (not SDK) in library code
use opentelemetry::{global, trace::{Span, SpanKind, Tracer}};
use opentelemetry::KeyValue;

pub fn start_session_span(session_id: &str, model: &str, config: &Config) -> impl Span {
    let tracer = global::tracer("claude-trace");
    let mut span = tracer
        .span_builder("claude.agent.session")
        .with_kind(SpanKind::Internal)
        .start(&tracer);

    // Always set from semconv constants — never inline the string
    span.set_attribute(KeyValue::new(
        crate::semconv::claude::SESSION_ID,
        session_id.to_owned(),
    ));
    span.set_attribute(KeyValue::new(
        crate::semconv::claude::SESSION_MODEL,
        model.to_owned(),
    ));

    span
}
```

### Setting Status

```rust
use opentelemetry::trace::Status;

// Success
span.set_status(Status::Ok);

// Error with description
span.set_status(Status::Error { description: Cow::Owned(err.to_string()) });
```

---

## Security Rules: Non-Negotiable

These rules exist because claude-trace instruments LLM calls that may process sensitive user data.

### Rule 1: Never Capture Content by Default

The `capture_content` config flag defaults to `false`. **All** code that sets `claude.turn.input_text` or `claude.turn.output_text` MUST be gated:

```rust
// src/spans/turn.rs
pub fn set_content_attributes(
    span: &mut impl Span,
    input: &str,
    output: &str,
    config: &Config,
) {
    if config.capture_content {
        span.set_attribute(KeyValue::new(
            "claude.turn.input_text",
            truncate_attribute(input, config),
        ));
        span.set_attribute(KeyValue::new(
            "claude.turn.output_text",
            truncate_attribute(output, config),
        ));
    }
    // When capture_content = false: no content attributes are set.
    // Token counts and costs are always recorded.
}
```

### Rule 2: Never Log Authorization Headers

When recording HTTP metadata (e.g., for debugging), explicitly skip auth headers:

```rust
const REDACTED_HEADERS: &[&str] = &["authorization", "x-api-key", "cookie"];

pub fn sanitize_header(name: &str, value: &str) -> Option<String> {
    if REDACTED_HEADERS.contains(&name.to_lowercase().as_str()) {
        return None; // Do not record at all
    }
    Some(truncate_attribute(value, MAX_HEADER_LENGTH))
}
```

### Rule 3: Scan for API Key Patterns

The `sanitize_string` function scans for and redacts API key patterns before they can appear in span attributes:

```rust
/// Redact Anthropic API keys from arbitrary strings.
///
/// Replaces any substring matching `sk-ant-[a-zA-Z0-9_-]{20,}` with `[REDACTED]`.
pub fn redact_api_keys(s: &str) -> String {
    // Pattern: sk-ant- followed by 20+ word chars
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| {
        regex::Regex::new(r"sk-ant-[a-zA-Z0-9_\-]{20,}").expect("valid regex")
    });
    re.replace_all(s, "[REDACTED]").into_owned()
}
```

### Rule 4: Always Truncate String Attributes

The `truncate_attribute` function must be called on ALL string values before setting span attributes:

```rust
// src/config/mod.rs
pub fn truncate_attribute(value: &str, config: &Config) -> String {
    let max = config.max_attribute_length; // default: 512
    if value.len() <= max {
        return value.to_owned();
    }
    // Truncate at UTF-8 character boundary to avoid invalid strings
    let truncated = &value[..value.char_indices()
        .take_while(|(i, _)| *i < max)
        .last()
        .map(|(i, c)| i + c.len_utf8())
        .unwrap_or(0)];
    format!("{}…", truncated)
}
```

---

## Config Struct

```rust
// src/config/mod.rs
#[derive(Debug, Clone)]
pub struct Config {
    /// Whether to include prompt/response text in span attributes.
    /// DEFAULT: false — do not capture PII by default.
    pub capture_content: bool,

    /// Maximum character length for string span attributes.
    /// Values longer than this are truncated with an ellipsis.
    /// DEFAULT: 512
    pub max_attribute_length: usize,

    /// OTLP export endpoint (gRPC).
    /// DEFAULT: "http://localhost:4317"
    pub otlp_endpoint: String,

    /// Whether to fail loudly on unknown model IDs.
    /// DEFAULT: false — use fallback pricing with a warning
    pub strict_model_pricing: bool,

    /// Service name for OTel resource attributes.
    /// DEFAULT: "claude-trace"
    pub service_name: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            capture_content: false,   // SECURITY: opt-in only
            max_attribute_length: 512,
            otlp_endpoint: "http://localhost:4317".to_owned(),
            strict_model_pricing: false,
            service_name: "claude-trace".to_owned(),
        }
    }
}
```

---

## Module Responsibilities Quick Reference

| Module | File(s) | Responsibility |
|---|---|---|
| `spans::session` | `src/spans/session.rs` | Session span lifecycle, cumulative token accumulation |
| `spans::turn` | `src/spans/turn.rs` | Turn span creation, token recording, content gating |
| `spans::tool` | `src/spans/tool.rs` | Tool span creation, input/output hashing, status recording |
| `semconv::claude` | `src/semconv/claude.rs` | All `claude.*` attribute name constants (frozen dataclasses) |
| `cost::calculator` | `src/cost/calculator.rs` | `CostCalculator::calculate()`, model lookup, `CostBreakdown` |
| `cost::models` | `src/cost/models.rs` | `_PRICING_TABLE: Vec<ModelPricing>` — authoritative pricing data |
| `config` | `src/config/mod.rs` | `Config` struct, `truncate_attribute`, `redact_api_keys` |
| `export::otlp` | `src/export/otlp.rs` | OTLP exporter initialization, resource attributes |

---

## Adding a New Span Attribute: Complete Checklist

1. Add the constant to the appropriate `*Attributes` struct in `src/semconv/claude.rs`
2. Add a doc comment explaining type, legal values, and example
3. Add attribute setting code in the appropriate span file (`session.rs`, `turn.rs`, `tool.rs`)
4. If it's a string attribute, ensure it goes through `truncate_attribute`
5. Add a test in the span file's `#[cfg(test)] mod tests` verifying the attribute is set
6. Update the semconv table in `site/src/content/docs/reference/semconv.mdx`
7. Run `python scripts/check_semconv_compat.py` — new attributes always pass, but verify
8. Commit message: `feat(semconv): add claude.<category>.<name> attribute`
