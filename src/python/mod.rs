// src/python/mod.rs — PyO3 bindings for claude-trace.
//
// Exposes CostBreakdown, TraceSnapshot, TraceDiff, TraceConfig, calculate_cost,
// and compare_traces into the `_claude_trace_core` Python extension module.
//
// Feature-gated: only compiled when the `python` feature is enabled.

use pyo3::prelude::*;

use crate::{
    cost::{CostBreakdown, CostCalculator},
    diff::{compare, TraceSnapshot, TraceDiff},
    errors::ClaudeTraceError,
    spans::SpanConfig,
};

// ---------------------------------------------------------------------------
// PyCostBreakdown
// ---------------------------------------------------------------------------

/// Python-exposed cost breakdown from a single API call or session.
#[pyclass(name = "CostBreakdown", frozen)]
#[derive(Clone)]
pub struct PyCostBreakdown {
    inner: CostBreakdown,
}

#[pymethods]
impl PyCostBreakdown {
    /// Input token cost in USD.
    #[getter]
    fn input_usd(&self) -> f64 {
        self.inner.input_usd
    }

    /// Output token cost in USD.
    #[getter]
    fn output_usd(&self) -> f64 {
        self.inner.output_usd
    }

    /// Cache-read token cost in USD.
    #[getter]
    fn cache_read_usd(&self) -> f64 {
        self.inner.cache_read_usd
    }

    /// Cache-write (creation) token cost in USD.
    #[getter]
    fn cache_write_usd(&self) -> f64 {
        self.inner.cache_write_usd
    }

    /// Sum of all cost components in USD.
    #[getter]
    fn total_usd(&self) -> f64 {
        self.inner.total_usd
    }

    fn __repr__(&self) -> String {
        format!(
            "CostBreakdown(total_usd={:.6}, input={:.6}, output={:.6})",
            self.inner.total_usd, self.inner.input_usd, self.inner.output_usd
        )
    }

    fn __add__(&self, other: &PyCostBreakdown) -> PyCostBreakdown {
        PyCostBreakdown {
            inner: self.inner.clone() + other.inner.clone(),
        }
    }
}

// ---------------------------------------------------------------------------
// calculate_cost
// ---------------------------------------------------------------------------

/// Calculate the USD cost for a model call.
///
/// Args:
///     model: Claude model identifier string.
///     input_tokens: Standard (non-cached) input token count.
///     output_tokens: Output token count.
///     cache_read_tokens: Tokens served from prompt cache (default 0).
///     cache_write_tokens: Tokens that populate the cache (default 0).
///
/// Returns:
///     CostBreakdown with per-component and total USD costs.
///
/// Raises:
///     ValueError: When the model is not found in the pricing table.
#[pyfunction]
#[pyo3(signature = (model, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0))]
fn calculate_cost(
    model: &str,
    input_tokens: u64,
    output_tokens: u64,
    cache_read_tokens: u64,
    cache_write_tokens: u64,
) -> PyResult<PyCostBreakdown> {
    let calc = CostCalculator::new();
    calc.calculate(
        model,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
    )
    .map(|inner| PyCostBreakdown { inner })
    .map_err(|e: ClaudeTraceError| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

// ---------------------------------------------------------------------------
// PyTraceSnapshot
// ---------------------------------------------------------------------------

/// Snapshot of an agent trace for diffing.
#[pyclass(name = "TraceSnapshot")]
#[derive(Clone)]
pub struct PyTraceSnapshot {
    inner: TraceSnapshot,
}

#[pymethods]
impl PyTraceSnapshot {
    #[new]
    #[pyo3(signature = (trace_id, tool_calls, turn_count, total_tokens, stop_reason))]
    fn new(
        trace_id: String,
        tool_calls: Vec<String>,
        turn_count: u32,
        total_tokens: u64,
        stop_reason: String,
    ) -> Self {
        Self {
            inner: TraceSnapshot {
                trace_id,
                tool_calls,
                turn_count,
                total_tokens,
                stop_reason,
            },
        }
    }

    /// Unique trace identifier.
    #[getter]
    fn trace_id(&self) -> &str {
        &self.inner.trace_id
    }

    /// Ordered list of tool names called during the trace.
    #[getter]
    fn tool_calls(&self) -> Vec<String> {
        self.inner.tool_calls.clone()
    }

    /// Number of agentic loop turns executed.
    #[getter]
    fn turn_count(&self) -> u32 {
        self.inner.turn_count
    }

    /// Total tokens consumed across all turns.
    #[getter]
    fn total_tokens(&self) -> u64 {
        self.inner.total_tokens
    }

    /// Final stop reason from the last turn.
    #[getter]
    fn stop_reason(&self) -> &str {
        &self.inner.stop_reason
    }

    fn __repr__(&self) -> String {
        format!(
            "TraceSnapshot(trace_id='{}', turns={}, tokens={})",
            self.inner.trace_id, self.inner.turn_count, self.inner.total_tokens
        )
    }
}

// ---------------------------------------------------------------------------
// PyTraceDiff
// ---------------------------------------------------------------------------

/// Structural diff between two agent traces.
#[pyclass(name = "TraceDiff", frozen)]
pub struct PyTraceDiff {
    inner: TraceDiff,
}

#[pymethods]
impl PyTraceDiff {
    /// Tool names present in candidate but not in baseline.
    #[getter]
    fn added_tool_calls(&self) -> Vec<String> {
        self.inner.added_tool_calls.clone()
    }

    /// Tool names present in baseline but not in candidate.
    #[getter]
    fn removed_tool_calls(&self) -> Vec<String> {
        self.inner.removed_tool_calls.clone()
    }

    /// candidate.total_tokens - baseline.total_tokens.
    #[getter]
    fn token_delta(&self) -> i64 {
        self.inner.token_delta
    }

    /// candidate.turn_count - baseline.turn_count.
    #[getter]
    fn turn_delta(&self) -> i64 {
        self.inner.turn_count_delta
    }

    /// Return True when both snapshots are structurally equivalent.
    fn is_equivalent(&self) -> bool {
        self.inner.is_equivalent()
    }

    /// Human-readable summary of the diff.
    fn summary(&self) -> String {
        self.inner.summary()
    }

    /// Assert equivalence, raising AssertionError with diff summary if not equal.
    ///
    /// Raises:
    ///     AssertionError: When the two traces are not equivalent.
    fn assert_equivalent(&self) -> PyResult<()> {
        if self.inner.is_equivalent() {
            Ok(())
        } else {
            Err(pyo3::exceptions::PyAssertionError::new_err(
                self.inner.summary(),
            ))
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "TraceDiff(equivalent={}, token_delta={})",
            self.inner.is_equivalent(),
            self.inner.token_delta
        )
    }
}

// ---------------------------------------------------------------------------
// compare_traces
// ---------------------------------------------------------------------------

/// Compare two trace snapshots and return a structured diff.
///
/// Args:
///     a: Baseline TraceSnapshot.
///     b: Candidate TraceSnapshot.
///
/// Returns:
///     TraceDiff with typed fields.
#[pyfunction]
fn compare_traces(a: &PyTraceSnapshot, b: &PyTraceSnapshot) -> PyTraceDiff {
    PyTraceDiff {
        inner: compare(&a.inner, &b.inner),
    }
}

// ---------------------------------------------------------------------------
// PyTraceConfig
// ---------------------------------------------------------------------------

/// Span configuration controlling what data is captured.
#[pyclass(name = "TraceConfig")]
#[derive(Clone)]
pub struct PyTraceConfig {
    /// Inner Rust SpanConfig.
    pub inner: SpanConfig,
}

#[pymethods]
impl PyTraceConfig {
    #[new]
    #[pyo3(signature = (capture_content=false, max_attribute_length=512, sanitize=false))]
    fn new(capture_content: bool, max_attribute_length: usize, sanitize: bool) -> Self {
        Self {
            inner: SpanConfig {
                capture_content,
                max_attribute_length,
                sanitize,
            },
        }
    }

    /// Whether raw prompt/response text is captured.
    #[getter]
    fn capture_content(&self) -> bool {
        self.inner.capture_content
    }

    /// Maximum characters for any string span attribute.
    #[getter]
    fn max_attribute_length(&self) -> usize {
        self.inner.max_attribute_length
    }

    /// Whether PII-bearing attributes are stripped.
    #[getter]
    fn sanitize(&self) -> bool {
        self.inner.sanitize
    }

    fn __repr__(&self) -> String {
        format!(
            "TraceConfig(capture_content={}, max_attribute_length={}, sanitize={})",
            self.inner.capture_content, self.inner.max_attribute_length, self.inner.sanitize
        )
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register all Python-exposed types and functions into the module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyCostBreakdown>()?;
    m.add_class::<PyTraceSnapshot>()?;
    m.add_class::<PyTraceDiff>()?;
    m.add_class::<PyTraceConfig>()?;
    m.add_function(wrap_pyfunction!(calculate_cost, m)?)?;
    m.add_function(wrap_pyfunction!(compare_traces, m)?)?;
    Ok(())
}
