//! Zero-configuration OpenTelemetry observability for Claude Agent SDK.
//!
//! This crate provides the core Rust implementation for claude-trace:
//! semantic conventions, cost calculation, trace diffing, and span lifecycle
//! management for Claude Agent SDK sessions, turns, and tool calls.
//!
//! # Feature Flags
//!
//! - `python` — Enables `PyO3` bindings for use as a Python extension module.
//!
//! # Quick Start
//!
//! ```rust
//! use _claude_trace_core::cost::CostCalculator;
//! use _claude_trace_core::semconv::SESSION;
//!
//! let calc = CostCalculator::new();
//! let bd = calc.calculate("claude-sonnet-4-6", 1000, 500, 0, 0).expect("known model");
//! println!("Total: ${:.6}", bd.total_usd);
//! println!("Session id attr: {}", SESSION.id);
//! ```
#![deny(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]

pub mod cost;
pub mod diff;
pub mod errors;

#[cfg(feature = "otel")]
pub mod semconv;

#[cfg(feature = "otel")]
pub mod spans;

#[cfg(feature = "python")]
pub mod python;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule(gil_used = false)]
fn _claude_trace_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    python::register(m)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
