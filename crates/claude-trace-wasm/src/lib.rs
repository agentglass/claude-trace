#![deny(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]

use wasm_bindgen::prelude::*;
// The dependency "claude-trace" has lib name "_claude_trace_core".
// Rust resolves extern crate references by lib name, so we use that directly.
use _claude_trace_core::{
    cost::CostCalculator,
    diff::compare,
};

#[cfg(feature = "console_error_panic_hook")]
pub use console_error_panic_hook::set_once as set_panic_hook;

/// Initialize the WASM module. Call this once before using any other API.
#[wasm_bindgen(start)]
pub fn init() {
    #[cfg(feature = "console_error_panic_hook")]
    console_error_panic_hook::set_once();
}

/// Configuration for claude-trace instrumentation.
#[wasm_bindgen]
pub struct TraceConfig {
    pub capture_content: bool,
    pub max_attribute_length: usize,
    pub sanitize: bool,
}

#[wasm_bindgen]
impl TraceConfig {
    /// Create config with safe defaults. captureContent=false protects PII.
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        Self {
            capture_content: false,
            max_attribute_length: 512,
            sanitize: false,
        }
    }

    #[wasm_bindgen(js_name = withCaptureContent)]
    pub fn with_capture_content(mut self, value: bool) -> Self {
        self.capture_content = value;
        self
    }

    #[wasm_bindgen(js_name = withSanitize)]
    pub fn with_sanitize(mut self, value: bool) -> Self {
        self.sanitize = value;
        self
    }

    #[wasm_bindgen(js_name = withMaxAttributeLength)]
    pub fn with_max_attribute_length(mut self, value: usize) -> Self {
        self.max_attribute_length = value;
        self
    }
}

impl Default for TraceConfig {
    fn default() -> Self {
        Self::new()
    }
}

/// Cost breakdown for a Claude API call.
#[wasm_bindgen]
pub struct CostBreakdown {
    pub input_usd: f64,
    pub output_usd: f64,
    pub cache_read_usd: f64,
    pub cache_write_usd: f64,
    pub total_usd: f64,
}

#[wasm_bindgen]
impl CostBreakdown {
    #[wasm_bindgen(getter, js_name = totalUsd)]
    pub fn total_usd_getter(&self) -> f64 {
        self.total_usd
    }

    #[wasm_bindgen(js_name = toString)]
    pub fn to_string_js(&self) -> String {
        format!("CostBreakdown(total=${:.6})", self.total_usd)
    }
}

/// Calculate USD cost for a Claude API call.
///
/// Throws if the model is not recognized.
#[wasm_bindgen(js_name = calculateCost)]
pub fn calculate_cost(
    model: &str,
    input_tokens: u32,
    output_tokens: u32,
    cache_read_tokens: u32,
    cache_write_tokens: u32,
) -> Result<CostBreakdown, JsError> {
    let calc = CostCalculator::new();
    calc.calculate(
        model,
        u64::from(input_tokens),
        u64::from(output_tokens),
        u64::from(cache_read_tokens),
        u64::from(cache_write_tokens),
    )
    .map(|b| CostBreakdown {
        input_usd: b.input_usd,
        output_usd: b.output_usd,
        cache_read_usd: b.cache_read_usd,
        cache_write_usd: b.cache_write_usd,
        total_usd: b.total_usd,
    })
    .map_err(|e| JsError::new(&e.to_string()))
}

/// Snapshot of an agent trace for structural diffing.
#[wasm_bindgen]
pub struct TraceSnapshot {
    inner: _claude_trace_core::diff::TraceSnapshot,
}

#[wasm_bindgen]
impl TraceSnapshot {
    #[wasm_bindgen(constructor)]
    pub fn new(
        trace_id: String,
        tool_calls: Vec<String>,
        turn_count: u32,
        total_tokens: u32,
        stop_reason: String,
    ) -> Self {
        Self {
            inner: _claude_trace_core::diff::TraceSnapshot {
                trace_id,
                tool_calls,
                turn_count,
                total_tokens: u64::from(total_tokens),
                stop_reason,
            },
        }
    }
}

/// Diff result between two agent traces.
#[wasm_bindgen]
pub struct TraceDiff {
    inner: _claude_trace_core::diff::TraceDiff,
}

#[wasm_bindgen]
impl TraceDiff {
    #[wasm_bindgen(getter, js_name = addedToolCalls)]
    pub fn added_tool_calls(&self) -> Vec<String> {
        self.inner.added_tool_calls.clone()
    }

    #[wasm_bindgen(getter, js_name = removedToolCalls)]
    pub fn removed_tool_calls(&self) -> Vec<String> {
        self.inner.removed_tool_calls.clone()
    }

    #[wasm_bindgen(getter, js_name = tokenDelta)]
    pub fn token_delta(&self) -> i64 {
        self.inner.token_delta
    }

    #[wasm_bindgen(getter, js_name = turnDelta)]
    pub fn turn_delta(&self) -> i64 {
        self.inner.turn_count_delta
    }

    #[wasm_bindgen(js_name = isEquivalent)]
    pub fn is_equivalent(&self) -> bool {
        self.inner.is_equivalent()
    }

    pub fn summary(&self) -> String {
        self.inner.summary()
    }

    /// Assert the two traces are equivalent. Throws if not.
    #[wasm_bindgen(js_name = assertEquivalent)]
    pub fn assert_equivalent(&self) -> Result<(), JsError> {
        if self.inner.is_equivalent() {
            Ok(())
        } else {
            Err(JsError::new(&self.inner.summary()))
        }
    }
}

/// Compare two trace snapshots.
#[wasm_bindgen(js_name = compareTraces)]
pub fn compare_traces(a: &TraceSnapshot, b: &TraceSnapshot) -> TraceDiff {
    TraceDiff {
        inner: compare(&a.inner, &b.inner),
    }
}
