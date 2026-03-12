//! Token cost calculation for Anthropic Claude models.
//!
//! Use [`CostCalculator`] to compute per-call and session-aggregate costs.
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::cost::CostCalculator;
//!
//! let calc = CostCalculator::new();
//! let bd = calc.calculate("claude-sonnet-4-6", 1_000, 500, 0, 0).expect("known model");
//! println!("Total: ${:.6}", bd.total_usd);
//! ```

mod calculator;

pub use calculator::{CostBreakdown, CostCalculator, ModelPricing};
