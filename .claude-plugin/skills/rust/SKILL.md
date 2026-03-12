# Rust Expert Skill — claude-trace Rust Development Context

<!--
skill:
  name: rust
  description: Deep Rust expert context for all .rs files in claude-trace. Encodes MSRV, clippy pedantic rules, zero-unsafe policy, error handling conventions, PyO3 patterns, and testing requirements.
  auto-invoke:
    - "*.rs"
    - "Cargo.toml"
    - "Cargo.lock"
  triggers:
    - "write rust"
    - "implement"
    - "add a function"
    - "fix clippy"
    - "write a test"
-->

## Critical Context: Always Active for `.rs` Files

This skill is **automatically invoked** whenever you open or edit any `.rs` file. All rules here are **non-negotiable** — they exist because violations cause real problems (unsoundness, PyO3 thread panics, OTel pipeline corruption, semver breaks).

---

## Project Identity

| Property | Value |
|---|---|
| Crate name | `claude_trace` |
| Edition | Rust 2021 |
| MSRV | 1.75.0 |
| Crate types | `["cdylib", "rlib"]` |
| Features | `python` (default), `wasm` |

The dual `cdylib`/`rlib` crate type is required because:
- `cdylib` produces the `.so`/`.pyd` Python extension module loaded by maturin
- `rlib` allows the crate to be used as a normal Rust library dependency

---

## Mandatory Lint Configuration

Every `.rs` file that is not a test must have these at the top:

```rust
#![deny(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]
// Add additional allows HERE, never inline in code unless truly local
```

The file-level allows are documented in `.clippy.toml`. **Do not add inline `#[allow(...)]` attributes** without a comment explaining why:

```rust
// CORRECT: documented inline allow
#[allow(clippy::too_many_arguments)] // This function is a thin FFI shim — callers use a builder
pub fn create_span_raw(/* ... */) {}

// WRONG: unexplained allow
#[allow(clippy::too_many_arguments)]
pub fn create_span_raw(/* ... */) {}
```

### Pedantic Rules That Frequently Trigger (Know These)

| Rule | Why it fires | Correct fix |
|---|---|---|
| `clippy::must_use_candidate` | Returned value is not used | Add `#[must_use]` to the function |
| `clippy::missing_errors_doc` | `pub fn` returns `Result` with no `# Errors` section | Add `# Errors` to doc comment |
| `clippy::missing_panics_doc` | `pub fn` can panic with no `# Panics` section | Add `# Panics` to doc comment |
| `clippy::wildcard_imports` | `use foo::*` | Always name imports explicitly |
| `clippy::items_after_statements` | Variable binding after a non-binding statement | Move all `let` bindings to top of block |
| `clippy::cast_possible_truncation` | `x as u32` where x is u64 | Use `u32::try_from(x)?` or add comment |

---

## Zero Unsafe Policy

**There is no such thing as a casual `unsafe` block in this codebase.**

If you believe you need `unsafe`, go through this checklist first:
1. Can you use a safe alternative? (`std::slice::from_raw_parts` → check if you can use `Vec` instead)
2. Is this truly required for correctness or performance? (Not convenience)
3. Have you read the Rustonomicon chapter relevant to this usage?

If unsafe is genuinely required, **every `unsafe` block** must have this three-line comment directly above it:

```rust
// SAFETY: The pointer `ptr` was obtained from `Box::into_raw` in `Session::new`
//         and has not been aliased since — we are the unique owner.
// INVARIANT: `ptr` must point to a valid, initialized `SessionInner`.
// REVIEWED: <github-username> on YYYY-MM-DD — see PR #NNN for discussion.
unsafe {
    Box::from_raw(ptr)
}
```

PRs with `unsafe` blocks missing any of these three lines **will be rejected** by the rust-reviewer agent.

---

## Error Handling Rules

### Library Code (everything in `src/`)

```rust
// CORRECT: use thiserror for all library error types
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SpanError {
    #[error("tracer not initialized — call claude_trace::init() first")]
    TracerNotInitialized,

    #[error("attribute '{name}' value exceeds maximum length {max} (got {actual})")]
    AttributeTooLong { name: String, max: usize, actual: usize },
}

// CORRECT: propagate with ?
pub fn set_attribute(name: &str, value: &str) -> Result<(), SpanError> {
    if value.len() > MAX_ATTR_LEN {
        return Err(SpanError::AttributeTooLong {
            name: name.to_owned(),
            max: MAX_ATTR_LEN,
            actual: value.len(),
        });
    }
    // ...
    Ok(())
}

// WRONG: never use unwrap() in library code
let tracer = global::tracer("claude-trace").unwrap(); // THIS WILL PANIC IN PRODUCTION
```

### `expect()` Usage

`expect()` is allowed **only** when you are asserting an invariant that the program has already guaranteed:

```rust
// CORRECT: the invariant (non-empty vec) was established by the type system
let first = items.first().expect("items is non-empty: enforced by SessionBuilder.add_turn()");

// WRONG: using expect to paper over a Result that should be propagated
let config = serde_json::from_str(&data).expect("config is valid JSON"); // should return Err
```

### Binary Code / Examples

In `main.rs` or `examples/`, you may use `?` with `anyhow` or `color_eyre`. Do not use either in library code.

---

## Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Functions, methods, variables | `snake_case` | `calculate_cost`, `input_tokens` |
| Types (struct, enum, trait) | `PascalCase` | `AgentSession`, `SpanError`, `CostCalculator` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_ATTRIBUTE_LENGTH`, `DEFAULT_MAX_TURNS` |
| Modules | `snake_case` | `mod cost_calculator` |
| Lifetimes | Single lowercase letter or descriptive | `'a`, `'py` (PyO3 convention) |
| Feature flags | `snake_case` | `python`, `wasm` |

### Special Conventions for This Project

- Span type names: prefix with the span kind. `SessionSpan`, `TurnSpan`, `ToolSpan` — not `Span`, `Turn`, `Tool`.
- Config structs: suffix with `Config`. `TracerConfig`, `ExportConfig`.
- Builder types: suffix with `Builder`. `SessionBuilder`.
- Error types: suffix with `Error`. `ClaudeTraceError`, `SpanError`.

---

## Module Structure Rules

Each major concept lives in its own file. The `mod.rs` file re-exports only the public surface:

```
src/
├── lib.rs                  # Crate root: #![deny], pub use re-exports, ClaudeTraceError
├── config/
│   ├── mod.rs              # pub use Config, ExportConfig; (no logic here)
│   └── config.rs           # Config struct and builder
├── spans/
│   ├── mod.rs              # pub use SessionSpan, TurnSpan, ToolSpan;
│   ├── session.rs          # SessionSpan — root span for one agent.run() call
│   ├── turn.rs             # TurnSpan — one LLM API call
│   └── tool.rs             # ToolSpan — one tool invocation
├── semconv/
│   ├── mod.rs              # pub use SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes;
│   └── claude.rs           # All claude.* attribute name constants
└── cost/
    ├── mod.rs              # pub use CostCalculator, CostBreakdown, get_calculator;
    ├── calculator.rs       # CostCalculator implementation
    └── models.rs           # Pricing table: _PRICING_TABLE Vec<ModelPricing>
```

**Visibility rules**:
- `pub`: items that are part of the public API (documented in semver)
- `pub(crate)`: items shared across modules but not part of the public API
- Private (no modifier): items used only within the current module
- **Never** use `pub(super)` — it creates fragile coupling between parent and child modules

---

## PyO3 Patterns (Feature: `python`)

All PyO3 code lives in `src/python_bindings/`. The feature guard ensures it compiles only when `--features python` is set.

### Module Declaration

```rust
// src/python_bindings/mod.rs
use pyo3::prelude::*;

/// Python module entry point — called by the interpreter when importing `claude_trace._claude_trace`
#[pymodule(gil_used = false)]  // REQUIRED: we never hold GIL across async operations
pub fn _claude_trace(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PySessionSpan>()?;
    m.add_class::<PyCostBreakdown>()?;
    m.add_function(wrap_pyfunction!(py_calculate_cost, m)?)?;
    Ok(())
}
```

### Exposing Rust Structs as Python Classes

```rust
#[pyclass(name = "SessionSpan", frozen)]  // `frozen` prevents mutation from Python
#[derive(Debug, Clone)]
pub struct PySessionSpan {
    inner: Arc<SessionSpan>,  // Arc for shared ownership with Python
}

#[pymethods]
impl PySessionSpan {
    /// Create a new session span.
    ///
    /// Args:
    ///     session_id: Unique identifier for this session.
    ///     model: Claude model identifier (e.g. "claude-sonnet-4-6").
    #[new]
    pub fn new(session_id: String, model: String) -> PyResult<Self> {
        let inner = SessionSpan::new(session_id, model)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(Self { inner: Arc::new(inner) })
    }

    /// Human-readable representation shown in repr().
    pub fn __repr__(&self) -> String {
        format!("SessionSpan(id='{}', model='{}')", self.inner.session_id, self.inner.model)
    }

    /// String shown in str().
    pub fn __str__(&self) -> String {
        self.__repr__()
    }

    // Properties use #[getter] — never expose fields directly
    #[getter]
    pub fn session_id(&self) -> &str {
        &self.inner.session_id
    }
}
```

### GIL Rules

```rust
// CORRECT: release GIL for any blocking I/O or CPU-bound work
pub fn export_spans(&self, py: Python<'_>) -> PyResult<()> {
    py.allow_threads(|| {
        self.inner.flush_blocking()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    })
}

// WRONG: blocking while holding the GIL prevents other Python threads from running
pub fn export_spans(&self) -> PyResult<()> {
    self.inner.flush_blocking()?;  // This blocks the GIL!
    Ok(())
}
```

### Error Conversion

```rust
// In src/python_bindings/errors.rs
impl From<ClaudeTraceError> for PyErr {
    fn from(err: ClaudeTraceError) -> Self {
        match err {
            ClaudeTraceError::UnknownModel(m) =>
                PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("Unknown model '{}' — see claude_trace.list_models()", m)
                ),
            ClaudeTraceError::OtelError(msg) =>
                PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(msg),
            ClaudeTraceError::AttributeTooLong { attribute, max, actual } =>
                PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("Attribute '{}' too long: {} > {}", attribute, actual, max)
                ),
            ClaudeTraceError::InvalidConfig(msg) =>
                PyErr::new::<pyo3::exceptions::PyValueError, _>(msg),
        }
    }
}
```

### Thread Safety Requirement

**All types exposed to Python via `#[pyclass]` MUST be `Send + Sync`.**

The Python GIL does not protect Rust objects. If a Python object is passed between threads (e.g., with `asyncio` or `threading`), the Rust type must be safe to send and share across threads.

Use `Arc<Mutex<T>>` for interior mutability, or make the struct `frozen` if it is truly immutable.

---

## Testing Requirements

### Coverage Gate: 85% minimum

CI enforces this. When you add a public function, you **must** add at least one test.

### Test Location

```rust
// Tests live at the BOTTOM of the same file as the code being tested.
// This is Rust convention and enables testing private internals.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_span_new_sets_session_id() {
        let span = SessionSpan::new("test-session-id", "claude-sonnet-4-6").unwrap();
        assert_eq!(span.session_id(), "test-session-id");
    }

    #[test]
    fn test_session_span_new_rejects_empty_session_id() {
        let result = SessionSpan::new("", "claude-sonnet-4-6");
        assert!(matches!(result, Err(ClaudeTraceError::InvalidConfig(_))));
    }
}
```

### Test Naming

Tests are named after **behaviors**, not implementations:

```rust
// CORRECT: describes what the system does
#[test] fn test_cost_calculator_uses_cache_read_discount_rate() { }
#[test] fn test_session_span_accumulates_tokens_across_turns() { }
#[test] fn test_attribute_truncation_preserves_utf8_boundaries() { }

// WRONG: describes what code does internally
#[test] fn test_calculator() { }
#[test] fn test_set_attribute() { }
```

### Snapshot Tests with `insta`

Use `insta` for testing complex outputs (span attributes, JSON serialization, error messages):

```rust
#[test]
fn test_cost_breakdown_format_summary_matches_snapshot() {
    let breakdown = CostBreakdown {
        model: "claude-sonnet-4-6".to_owned(),
        input_tokens: 1000,
        output_tokens: 500,
        cache_read_tokens: 2000,
        cache_creation_tokens: 800,
        // ... costs
    };
    insta::assert_snapshot!(breakdown.format_summary());
}
```

Run `cargo insta review` to approve new snapshots. Committed snapshots live in `tests/snapshots/`.

---

## Documentation Requirements

Every `pub` item needs a `///` doc comment with:

1. One-line summary (imperative mood: "Calculate the cost breakdown...")
2. Extended description if non-obvious
3. `# Arguments` section (if > 2 params)
4. `# Returns` section (if non-obvious)
5. `# Errors` section (if returns `Result`)
6. `# Panics` section (if can panic — should be extremely rare)
7. `# Examples` section with a runnable example

```rust
/// Calculate the cost breakdown for a single Anthropic API call.
///
/// Looks up the model in the internal pricing table. If the model is not found,
/// falls back to the `unknown` pricing entry (sonnet-4 rates) and logs a warning.
///
/// # Arguments
///
/// * `model` - Claude model identifier (e.g. `"claude-sonnet-4-6"`)
/// * `input_tokens` - Standard input tokens (not cache tokens)
/// * `output_tokens` - Generated output tokens
/// * `cache_read_tokens` - Tokens served from prompt cache (billed at 10% of input rate)
/// * `cache_creation_tokens` - Tokens written to prompt cache (billed at 125% of input rate)
///
/// # Errors
///
/// Returns [`ClaudeTraceError::UnknownModel`] if the model has no pricing entry AND
/// `config.strict_model_pricing = true` (default: false).
///
/// # Examples
///
/// ```rust
/// use claude_trace::cost::get_calculator;
///
/// let calc = get_calculator();
/// let breakdown = calc.calculate("claude-sonnet-4-6", 1000, 500, 0, 0)?;
/// assert!(breakdown.total_usd > 0.0);
/// # Ok::<(), claude_trace::ClaudeTraceError>(())
/// ```
pub fn calculate(
    &self,
    model: &str,
    input_tokens: u64,
    output_tokens: u64,
    cache_read_tokens: u64,
    cache_creation_tokens: u64,
) -> Result<CostBreakdown, ClaudeTraceError> {
    // ...
}
```

---

## OTel API Usage Patterns

Use the `opentelemetry` crate API, not the SDK directly in library code. The SDK is only used in `src/export/`.

```rust
use opentelemetry::{
    global,
    trace::{Span, SpanKind, Status, Tracer},
    KeyValue,
};

// Span naming: always "claude.<kind>.<operation>"
let tracer = global::tracer("claude-trace");
let mut span = tracer
    .span_builder("claude.agent.session")
    .with_kind(SpanKind::Internal)
    .start(&tracer);

// Attribute names from semconv constants — never inline strings
span.set_attribute(KeyValue::new(
    crate::semconv::claude::SessionAttributes::SESSION_ID,
    session_id.to_owned(),
));

// End with explicit status
span.set_status(Status::Ok);
span.end();
```

### Never Capture Content Without Config Check

```rust
// CORRECT: gate on capture_content
if self.config.capture_content {
    span.set_attribute(KeyValue::new("claude.turn.input_text", truncate(input, self.config.max_attribute_length)));
}

// WRONG: always sets content — potential PII leak
span.set_attribute(KeyValue::new("claude.turn.input_text", input));
```

### Always Truncate String Attributes

```rust
// CORRECT: all string attributes go through truncation
use crate::config::truncate_attribute;
span.set_attribute(KeyValue::new(attr_name, truncate_attribute(value, &self.config)));

// WRONG: raw value without truncation
span.set_attribute(KeyValue::new(attr_name, value));
```
