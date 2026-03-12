//! Cost calculator implementation.
//!
//! # Example
//!
//! ```rust
//! use _claude_trace_core::cost::CostCalculator;
//!
//! let calc = CostCalculator::new();
//! let bd = calc.calculate("claude-haiku-4-5", 500_000, 250_000, 0, 0)
//!     .expect("known model");
//! assert!(bd.total_usd > 0.0);
//! ```

// ---- TESTS FIRST (TDD) ----
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_known_model_exact_price() {
        let calc = CostCalculator::new();
        // claude-sonnet-4-6: $3/MTok input, $15/MTok output
        let breakdown = calc
            .calculate("claude-sonnet-4-6", 1_000_000, 1_000_000, 0, 0)
            .expect("known model");
        assert!(
            (breakdown.total_usd - 18.0).abs() < 0.001,
            "expected $18.00, got ${}",
            breakdown.total_usd
        );
    }

    #[test]
    fn test_cache_read_discount() {
        let calc = CostCalculator::new();
        // Cache read is ~10% of input price for sonnet-4-6: $0.30/MTok
        let breakdown = calc
            .calculate("claude-sonnet-4-6", 0, 0, 1_000_000, 0)
            .expect("known model");
        assert!(
            (breakdown.cache_read_usd - 0.30).abs() < 0.001,
            "expected $0.30, got ${}",
            breakdown.cache_read_usd
        );
    }

    #[test]
    fn test_cost_breakdown_addition() {
        let a = CostBreakdown {
            input_usd: 1.0,
            output_usd: 2.0,
            cache_read_usd: 0.1,
            cache_write_usd: 0.2,
            total_usd: 3.3,
        };
        let b = CostBreakdown {
            input_usd: 0.5,
            output_usd: 1.0,
            cache_read_usd: 0.05,
            cache_write_usd: 0.1,
            total_usd: 1.65,
        };
        let sum = a + b;
        assert!(
            (sum.total_usd - 4.95).abs() < 0.001,
            "expected $4.95, got ${}",
            sum.total_usd
        );
    }

    #[test]
    fn test_unknown_model_error() {
        let calc = CostCalculator::new();
        assert!(calc.calculate("gpt-totally-fake", 100, 100, 0, 0).is_err());
    }

    #[test]
    fn test_prefix_resolution() {
        // "claude-sonnet-4-6-20251022" should resolve via prefix to sonnet-4-6 pricing
        let calc = CostCalculator::new();
        assert!(calc
            .calculate("claude-sonnet-4-6-20251022", 100, 100, 0, 0)
            .is_ok());
    }

    #[test]
    fn test_haiku_pricing() {
        let calc = CostCalculator::new();
        // claude-haiku-4-5: $0.80/MTok input, $4/MTok output
        let breakdown = calc
            .calculate("claude-haiku-4-5", 1_000_000, 1_000_000, 0, 0)
            .expect("known model");
        assert!(
            (breakdown.total_usd - 4.80).abs() < 0.001,
            "expected $4.80, got ${}",
            breakdown.total_usd
        );
    }

    #[test]
    fn test_opus_pricing() {
        let calc = CostCalculator::new();
        // claude-opus-4-5: $15/MTok input, $75/MTok output
        let breakdown = calc
            .calculate("claude-opus-4-5", 1_000_000, 1_000_000, 0, 0)
            .expect("known model");
        assert!(
            (breakdown.total_usd - 90.0).abs() < 0.001,
            "expected $90.00, got ${}",
            breakdown.total_usd
        );
    }

    #[test]
    fn test_cache_write_premium() {
        let calc = CostCalculator::new();
        // Cache write is 125% of input: sonnet-4-6 = $3.75/MTok
        let breakdown = calc
            .calculate("claude-sonnet-4-6", 0, 0, 0, 1_000_000)
            .expect("known model");
        assert!(
            (breakdown.cache_write_usd - 3.75).abs() < 0.001,
            "expected $3.75, got ${}",
            breakdown.cache_write_usd
        );
    }

    #[test]
    fn test_all_fields_sum_to_total() {
        let calc = CostCalculator::new();
        let bd = calc
            .calculate("claude-sonnet-4-6", 100_000, 50_000, 200_000, 10_000)
            .expect("known model");
        let computed_total = bd.input_usd + bd.output_usd + bd.cache_read_usd + bd.cache_write_usd;
        assert!(
            (computed_total - bd.total_usd).abs() < 1e-9,
            "field sum {computed_total} != total_usd {}",
            bd.total_usd
        );
    }

    #[test]
    fn test_zero_tokens_zero_cost() {
        let calc = CostCalculator::new();
        let bd = calc
            .calculate("claude-haiku-4-5", 0, 0, 0, 0)
            .expect("known model");
        assert_eq!(bd.total_usd, 0.0);
    }

    #[test]
    fn test_claude_3_5_sonnet_exact_match() {
        let calc = CostCalculator::new();
        let bd = calc
            .calculate("claude-3-5-sonnet-20241022", 1_000_000, 1_000_000, 0, 0)
            .expect("known model");
        assert!((bd.total_usd - 18.0).abs() < 0.001);
    }

    #[test]
    fn test_breakdown_add_impl_is_consistent() {
        let calc = CostCalculator::new();
        let a = calc
            .calculate("claude-haiku-4-5", 500_000, 0, 0, 0)
            .expect("known model");
        let b = calc
            .calculate("claude-haiku-4-5", 500_000, 0, 0, 0)
            .expect("known model");
        let combined = a + b;
        let direct = calc
            .calculate("claude-haiku-4-5", 1_000_000, 0, 0, 0)
            .expect("known model");
        assert!(
            (combined.total_usd - direct.total_usd).abs() < 1e-9,
            "combined={} direct={}",
            combined.total_usd,
            direct.total_usd
        );
    }
}

// ---- IMPLEMENTATION ----

use crate::errors::ClaudeTraceError;
use std::ops::Add;

/// Pricing for a specific Claude model variant.
///
/// All prices are in USD per million tokens.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::cost::ModelPricing;
///
/// let p = ModelPricing {
///     input_per_mtok: 3.0,
///     output_per_mtok: 15.0,
///     cache_read_per_mtok: 0.30,
///     cache_write_per_mtok: 3.75,
/// };
/// assert_eq!(p.input_per_mtok, 3.0);
/// ```
#[derive(Debug, Clone, PartialEq)]
pub struct ModelPricing {
    /// Standard input token price per 1 million tokens (USD).
    pub input_per_mtok: f64,
    /// Output token price per 1 million tokens (USD).
    pub output_per_mtok: f64,
    /// Cache read price per 1 million tokens (USD).
    pub cache_read_per_mtok: f64,
    /// Cache write (creation) price per 1 million tokens (USD).
    pub cache_write_per_mtok: f64,
}

impl ModelPricing {
    /// Create pricing with cache prices derived from input price:
    /// `cache_read` = 10% of input, `cache_write` = 125% of input.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::ModelPricing;
    ///
    /// let p = ModelPricing::standard(3.0, 15.0);
    /// assert!((p.cache_read_per_mtok - 0.30).abs() < 1e-9);
    /// assert!((p.cache_write_per_mtok - 3.75).abs() < 1e-9);
    /// ```
    #[must_use]
    pub fn standard(input_per_mtok: f64, output_per_mtok: f64) -> Self {
        Self {
            cache_read_per_mtok: input_per_mtok * 0.10,
            cache_write_per_mtok: input_per_mtok * 1.25,
            input_per_mtok,
            output_per_mtok,
        }
    }

    /// Create pricing with explicit cache prices.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::ModelPricing;
    ///
    /// let p = ModelPricing::explicit(3.0, 15.0, 0.30, 3.75);
    /// assert_eq!(p.cache_read_per_mtok, 0.30);
    /// ```
    #[must_use]
    pub fn explicit(
        input_per_mtok: f64,
        output_per_mtok: f64,
        cache_read_per_mtok: f64,
        cache_write_per_mtok: f64,
    ) -> Self {
        Self {
            input_per_mtok,
            output_per_mtok,
            cache_read_per_mtok,
            cache_write_per_mtok,
        }
    }
}

/// Detailed cost breakdown for a single API call.
///
/// All monetary values are in USD. The `total_usd` field is the sum of
/// all components.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::cost::{CostBreakdown, CostCalculator};
///
/// let calc = CostCalculator::new();
/// let bd = calc.calculate("claude-sonnet-4-6", 1000, 500, 0, 0).expect("ok");
/// assert!(bd.total_usd > 0.0);
/// ```
#[derive(Debug, Clone, PartialEq)]
pub struct CostBreakdown {
    /// Cost for standard input tokens (USD).
    pub input_usd: f64,
    /// Cost for output tokens (USD).
    pub output_usd: f64,
    /// Cost for cache-read tokens (USD).
    pub cache_read_usd: f64,
    /// Cost for cache-write (creation) tokens (USD).
    pub cache_write_usd: f64,
    /// Sum of all components (USD).
    pub total_usd: f64,
}

impl Add for CostBreakdown {
    type Output = Self;

    /// Add two cost breakdowns together, summing all components.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::CostBreakdown;
    ///
    /// let a = CostBreakdown { input_usd: 1.0, output_usd: 2.0, cache_read_usd: 0.0, cache_write_usd: 0.0, total_usd: 3.0 };
    /// let b = CostBreakdown { input_usd: 0.5, output_usd: 1.0, cache_read_usd: 0.0, cache_write_usd: 0.0, total_usd: 1.5 };
    /// let sum = a + b;
    /// assert!((sum.total_usd - 4.5).abs() < 1e-9);
    /// ```
    fn add(self, rhs: Self) -> Self::Output {
        let input_usd = self.input_usd + rhs.input_usd;
        let output_usd = self.output_usd + rhs.output_usd;
        let cache_read_usd = self.cache_read_usd + rhs.cache_read_usd;
        let cache_write_usd = self.cache_write_usd + rhs.cache_write_usd;
        let total_usd = input_usd + output_usd + cache_read_usd + cache_write_usd;
        Self {
            input_usd,
            output_usd,
            cache_read_usd,
            cache_write_usd,
            total_usd,
        }
    }
}

/// Convert a token count to `f64` for multiplication.
///
/// Token counts are always below 2^53 in real usage so no precision is lost.
#[allow(clippy::cast_precision_loss)]
fn tokens_to_f64(t: u64) -> f64 {
    t as f64
}

/// `MTok` denominator constant (1 000 000).
const M: f64 = 1_000_000.0;

/// Named pricing entry: model prefix + pricing data.
struct PricingEntry {
    /// Model ID or prefix to match against.
    id: &'static str,
    pricing: ModelPricing,
}

/// Build Claude 4 and Claude 3.5 family pricing entries.
fn build_claude4_and_35_entries() -> Vec<PricingEntry> {
    let opus = ModelPricing::explicit(15.00, 75.00, 1.50, 18.75);
    let sonnet4 = ModelPricing::explicit(3.00, 15.00, 0.30, 3.75);
    let haiku4 = ModelPricing::explicit(0.80, 4.00, 0.08, 1.00);
    vec![
        // Claude 4 Opus family
        PricingEntry { id: "claude-opus-4-5",           pricing: opus.clone() },
        PricingEntry { id: "claude-opus-4-0",           pricing: opus.clone() },
        PricingEntry { id: "claude-opus-4",             pricing: opus },
        // Claude 4 Sonnet family
        PricingEntry { id: "claude-sonnet-4-6-20251101", pricing: sonnet4.clone() },
        PricingEntry { id: "claude-sonnet-4-6",          pricing: sonnet4.clone() },
        PricingEntry { id: "claude-sonnet-4-5-20250514", pricing: sonnet4.clone() },
        PricingEntry { id: "claude-sonnet-4-5",          pricing: sonnet4.clone() },
        PricingEntry { id: "claude-sonnet-4",            pricing: sonnet4.clone() },
        // Claude 4 Haiku family
        PricingEntry { id: "claude-haiku-4-5-20250514",  pricing: haiku4.clone() },
        PricingEntry { id: "claude-haiku-4-5",           pricing: haiku4.clone() },
        PricingEntry { id: "claude-haiku-4",             pricing: haiku4.clone() },
        // Claude 3.5 Sonnet
        PricingEntry { id: "claude-3-5-sonnet-20241022", pricing: sonnet4.clone() },
        PricingEntry { id: "claude-3-5-sonnet-20240620", pricing: sonnet4.clone() },
        PricingEntry { id: "claude-3-5-sonnet",          pricing: sonnet4 },
        // Claude 3.5 Haiku
        PricingEntry { id: "claude-3-5-haiku-20241022",  pricing: haiku4.clone() },
        PricingEntry { id: "claude-3-5-haiku",           pricing: haiku4 },
    ]
}

/// Build Claude 3 and legacy pricing entries.
fn build_claude3_and_legacy_entries() -> Vec<PricingEntry> {
    let opus3 = ModelPricing::explicit(15.00, 75.00, 1.50, 18.75);
    let sonnet3 = ModelPricing::standard(3.00, 15.00);
    let haiku3 = ModelPricing::explicit(0.25, 1.25, 0.03, 0.30);
    let claude2 = ModelPricing::standard(8.00, 24.00);
    vec![
        // Claude 3 Opus
        PricingEntry { id: "claude-3-opus-20240229", pricing: opus3.clone() },
        PricingEntry { id: "claude-3-opus",          pricing: opus3 },
        // Claude 3 Sonnet
        PricingEntry { id: "claude-3-sonnet-20240229", pricing: sonnet3.clone() },
        PricingEntry { id: "claude-3-sonnet",          pricing: sonnet3 },
        // Claude 3 Haiku
        PricingEntry { id: "claude-3-haiku-20240307", pricing: haiku3.clone() },
        PricingEntry { id: "claude-3-haiku",          pricing: haiku3 },
        // Claude 2 (legacy)
        PricingEntry { id: "claude-2.1", pricing: claude2.clone() },
        PricingEntry { id: "claude-2.0", pricing: claude2.clone() },
        PricingEntry { id: "claude-2",   pricing: claude2 },
    ]
}

/// Build the complete static pricing table (2026 Q1 Anthropic prices).
fn build_pricing_table() -> Vec<PricingEntry> {
    let mut table = build_claude4_and_35_entries();
    table.extend(build_claude3_and_legacy_entries());
    table
}

/// Thread-safe cost calculator for Claude API calls.
///
/// Constructed with [`CostCalculator::new`]. The internal pricing table is
/// immutable after construction so this type is `Send + Sync`.
///
/// # Example
///
/// ```rust
/// use _claude_trace_core::cost::CostCalculator;
///
/// let calc = CostCalculator::new();
/// let bd = calc.calculate("claude-sonnet-4-6", 1000, 500, 0, 0)
///     .expect("known model");
/// println!("Total: ${:.6}", bd.total_usd);
/// ```
pub struct CostCalculator {
    table: Vec<PricingEntry>,
}

impl CostCalculator {
    /// Create a new `CostCalculator` with the built-in 2026 Q1 pricing table.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::CostCalculator;
    ///
    /// let calc = CostCalculator::new();
    /// assert!(calc.calculate("claude-sonnet-4-6", 0, 0, 0, 0).is_ok());
    /// ```
    #[must_use]
    pub fn new() -> Self {
        Self {
            table: build_pricing_table(),
        }
    }

    /// Resolve a model string to its `ModelPricing`.
    ///
    /// Resolution order:
    /// 1. Exact match.
    /// 2. Prefix match (longest prefix that matches wins).
    /// 3. Error — `ClaudeTraceError::UnknownModel`.
    ///
    /// # Errors
    ///
    /// Returns [`ClaudeTraceError::UnknownModel`] when no match is found.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::CostCalculator;
    ///
    /// let calc = CostCalculator::new();
    /// let p = calc.resolve("claude-sonnet-4-6-20251022").expect("prefix match");
    /// assert!((p.input_per_mtok - 3.0).abs() < 1e-9);
    /// ```
    pub fn resolve(&self, model: &str) -> Result<ModelPricing, ClaudeTraceError> {
        // 1. Exact match
        if let Some(entry) = self.table.iter().find(|e| e.id == model) {
            return Ok(entry.pricing.clone());
        }

        // 2. Prefix match — longest prefix wins
        let best = self
            .table
            .iter()
            .filter(|e| model.starts_with(e.id))
            .max_by_key(|e| e.id.len());

        best.map(|e| e.pricing.clone())
            .ok_or_else(|| ClaudeTraceError::UnknownModel {
                model: model.to_owned(),
            })
    }

    /// Calculate a full cost breakdown for one API call.
    ///
    /// # Errors
    ///
    /// Returns [`ClaudeTraceError::UnknownModel`] when the model is not
    /// found in the pricing table (no exact or prefix match).
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::CostCalculator;
    ///
    /// let calc = CostCalculator::new();
    /// let bd = calc.calculate("claude-haiku-4-5", 1_000_000, 1_000_000, 0, 0)
    ///     .expect("known model");
    /// assert!((bd.total_usd - 4.80).abs() < 0.001);
    /// ```
    pub fn calculate(
        &self,
        model: &str,
        input_tokens: u64,
        output_tokens: u64,
        cache_read_tokens: u64,
        cache_write_tokens: u64,
    ) -> Result<CostBreakdown, ClaudeTraceError> {
        let pricing = self.resolve(model)?;
        let input_usd = tokens_to_f64(input_tokens) * pricing.input_per_mtok / M;
        let output_usd = tokens_to_f64(output_tokens) * pricing.output_per_mtok / M;
        let cache_read_usd = tokens_to_f64(cache_read_tokens) * pricing.cache_read_per_mtok / M;
        let cache_write_usd = tokens_to_f64(cache_write_tokens) * pricing.cache_write_per_mtok / M;
        let total_usd = input_usd + output_usd + cache_read_usd + cache_write_usd;

        Ok(CostBreakdown {
            input_usd,
            output_usd,
            cache_read_usd,
            cache_write_usd,
            total_usd,
        })
    }

    /// List all model IDs with known exact pricing.
    ///
    /// # Example
    ///
    /// ```rust
    /// use _claude_trace_core::cost::CostCalculator;
    ///
    /// let calc = CostCalculator::new();
    /// let models = calc.list_models();
    /// assert!(models.contains(&"claude-sonnet-4-6"));
    /// ```
    #[must_use]
    pub fn list_models(&self) -> Vec<&str> {
        self.table.iter().map(|e| e.id).collect()
    }
}

impl Default for CostCalculator {
    fn default() -> Self {
        Self::new()
    }
}
