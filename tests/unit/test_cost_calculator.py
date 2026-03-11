"""
Unit tests for the claude-trace cost calculator.

All expected values are computed independently from the published Anthropic
pricing page (2026-Q1) to catch any pricing table regressions.

Formula reminders:
    cost = tokens * price_per_million / 1_000_000
    cache_write = 1.25x input
    cache_read  = 0.10x input
"""

from __future__ import annotations

import pytest

from claude_trace._cost.calculator import (
    CostBreakdown,
    CostCalculator,
    ModelPricing,
    get_calculator,
    _resolve_pricing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def calc() -> CostCalculator:
    return CostCalculator()


# ---------------------------------------------------------------------------
# Basic calculation accuracy
# ---------------------------------------------------------------------------


class TestCalculationAccuracy:
    """Verify cost values against independently calculated expected results."""

    def test_sonnet4_input_only(self, calc: CostCalculator) -> None:
        # claude-sonnet-4-6: $3.00 per 1M input tokens
        # 1_000_000 tokens → $3.00
        bd = calc.calculate("claude-sonnet-4-6", input_tokens=1_000_000)
        assert abs(bd.input_cost_usd - 3.00) < 1e-9
        assert bd.output_cost_usd == pytest.approx(0.0)
        assert bd.total_usd == pytest.approx(3.00)

    def test_sonnet4_output_only(self, calc: CostCalculator) -> None:
        # claude-sonnet-4-6: $15.00 per 1M output tokens
        bd = calc.calculate("claude-sonnet-4-6", output_tokens=1_000_000)
        assert abs(bd.output_cost_usd - 15.00) < 1e-9
        assert bd.total_usd == pytest.approx(15.00)

    def test_opus4_pricing(self, calc: CostCalculator) -> None:
        # claude-opus-4-5: $15.00 input / $75.00 output per 1M
        bd = calc.calculate(
            "claude-opus-4-5",
            input_tokens=100_000,
            output_tokens=50_000,
        )
        expected_input = 100_000 * 15.00 / 1_000_000  # 1.50
        expected_output = 50_000 * 75.00 / 1_000_000  # 3.75
        assert bd.input_cost_usd == pytest.approx(expected_input, rel=1e-6)
        assert bd.output_cost_usd == pytest.approx(expected_output, rel=1e-6)
        assert bd.total_usd == pytest.approx(expected_input + expected_output, rel=1e-6)

    def test_haiku4_pricing(self, calc: CostCalculator) -> None:
        # claude-haiku-4-5: $0.80 input / $4.00 output per 1M
        bd = calc.calculate(
            "claude-haiku-4-5",
            input_tokens=500_000,
            output_tokens=200_000,
        )
        expected_input = 500_000 * 0.80 / 1_000_000  # 0.40
        expected_output = 200_000 * 4.00 / 1_000_000  # 0.80
        assert bd.input_cost_usd == pytest.approx(expected_input, rel=1e-6)
        assert bd.output_cost_usd == pytest.approx(expected_output, rel=1e-6)

    def test_cache_read_cost(self, calc: CostCalculator) -> None:
        # claude-sonnet-4-6 cache read: $0.30 per 1M
        bd = calc.calculate("claude-sonnet-4-6", cache_read_tokens=1_000_000)
        assert bd.cache_read_cost_usd == pytest.approx(0.30, rel=1e-6)

    def test_cache_creation_cost(self, calc: CostCalculator) -> None:
        # claude-sonnet-4-6 cache write: $3.75 per 1M (1.25x input $3.00)
        bd = calc.calculate("claude-sonnet-4-6", cache_creation_tokens=1_000_000)
        assert bd.cache_creation_cost_usd == pytest.approx(3.75, rel=1e-6)

    def test_full_breakdown_sonnet4(self, calc: CostCalculator) -> None:
        """Test a realistic call with all token types."""
        bd = calc.calculate(
            "claude-sonnet-4-6",
            input_tokens=5_000,
            output_tokens=800,
            cache_read_tokens=10_000,
            cache_creation_tokens=3_000,
        )
        # input:          5_000 * 3.00 / 1M = 0.015000
        # output:           800 * 15.00 / 1M = 0.012000
        # cache_read:    10_000 * 0.30 / 1M  = 0.003000
        # cache_creation: 3_000 * 3.75 / 1M  = 0.011250
        # total:                               0.041250
        assert bd.input_cost_usd == pytest.approx(0.015000, rel=1e-6)
        assert bd.output_cost_usd == pytest.approx(0.012000, rel=1e-6)
        assert bd.cache_read_cost_usd == pytest.approx(0.003000, rel=1e-6)
        assert bd.cache_creation_cost_usd == pytest.approx(0.011250, rel=1e-6)
        assert bd.total_usd == pytest.approx(0.041250, rel=1e-6)

    def test_zero_tokens(self, calc: CostCalculator) -> None:
        bd = calc.calculate("claude-sonnet-4-6")
        assert bd.total_usd == pytest.approx(0.0)
        assert bd.input_cost_usd == 0.0
        assert bd.output_cost_usd == 0.0


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


class TestModelResolution:
    """Verify model string to pricing resolution logic."""

    def test_exact_match(self) -> None:
        pricing = _resolve_pricing("claude-sonnet-4-6-20251101")
        assert pricing.model_id == "claude-sonnet-4-6-20251101"

    def test_prefix_alias_opus(self) -> None:
        pricing = _resolve_pricing("claude-opus-4")
        assert "opus" in pricing.model_id

    def test_prefix_alias_sonnet(self) -> None:
        pricing = _resolve_pricing("claude-sonnet-4")
        assert "sonnet" in pricing.model_id

    def test_prefix_alias_haiku(self) -> None:
        pricing = _resolve_pricing("claude-haiku-4")
        assert "haiku" in pricing.model_id

    def test_dated_variant_exact(self) -> None:
        pricing = _resolve_pricing("claude-3-5-sonnet-20241022")
        assert pricing.model_id == "claude-3-5-sonnet-20241022"
        assert pricing.input_per_million == pytest.approx(3.00)

    def test_unknown_model_falls_back(self) -> None:
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pricing = _resolve_pricing("claude-9-hyperion-future")
            assert len(w) == 1
            assert "unknown model" in str(w[0].message).lower()
        # Fallback is sonnet-tier pricing
        assert pricing.input_per_million == pytest.approx(3.00)

    def test_regex_family_opus(self) -> None:
        pricing = _resolve_pricing("anthropic.claude-opus-weird-variant-1")
        assert pricing.input_per_million == pytest.approx(15.00)

    def test_regex_family_haiku(self) -> None:
        pricing = _resolve_pricing("a-haiku-b-c")
        assert pricing.input_per_million == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# CostBreakdown dataclass
# ---------------------------------------------------------------------------


class TestCostBreakdown:
    """Verify CostBreakdown arithmetic and properties."""

    def _make(self, **kwargs: int | float) -> CostBreakdown:
        defaults: dict[str, int | float] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "input_cost_usd": 0.0,
            "output_cost_usd": 0.0,
            "cache_read_cost_usd": 0.0,
            "cache_creation_cost_usd": 0.0,
        }
        defaults.update(kwargs)
        return CostBreakdown(model="claude-sonnet-4-6", **defaults)  # type: ignore[arg-type]

    def test_total_usd_property(self) -> None:
        bd = self._make(
            input_cost_usd=1.0,
            output_cost_usd=2.0,
            cache_read_cost_usd=0.5,
            cache_creation_cost_usd=0.25,
        )
        assert bd.total_usd == pytest.approx(3.75)

    def test_total_tokens_property(self) -> None:
        bd = self._make(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=200,
            cache_creation_tokens=75,
        )
        assert bd.total_tokens == 425

    def test_addition(self) -> None:
        a = self._make(input_tokens=100, input_cost_usd=0.30)
        b = self._make(input_tokens=200, input_cost_usd=0.60)
        c = a + b
        assert c.input_tokens == 300
        assert c.input_cost_usd == pytest.approx(0.90)

    def test_format_summary_contains_cost(self) -> None:
        bd = self._make(input_tokens=500, output_tokens=200, input_cost_usd=0.0015)
        summary = bd.format_summary()
        assert "$" in summary
        assert "in=500" in summary
        assert "out=200" in summary


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestGetCalculator:
    def test_singleton(self) -> None:
        c1 = get_calculator()
        c2 = get_calculator()
        assert c1 is c2

    def test_list_models_non_empty(self) -> None:
        models = get_calculator().list_models()
        assert len(models) > 5
        assert "claude-sonnet-4-6" in models
        assert "claude-opus-4-5" in models
        assert "claude-haiku-4-5" in models

    def test_get_pricing_returns_model_pricing(self) -> None:
        pricing = get_calculator().get_pricing("claude-opus-4-5")
        assert isinstance(pricing, ModelPricing)
        assert pricing.input_per_million == pytest.approx(15.00)
        assert pricing.output_per_million == pytest.approx(75.00)


# ---------------------------------------------------------------------------
# Cache pricing defaults
# ---------------------------------------------------------------------------


class TestCachePricingDefaults:
    """Verify default cache pricing derivation for models without explicit cache prices."""

    def test_cache_write_default_is_125pct(self) -> None:
        # claude-3-sonnet has no explicit cache pricing
        pricing = _resolve_pricing("claude-3-sonnet-20240229")
        assert pricing.effective_cache_write == pytest.approx(
            pricing.input_per_million * 1.25, rel=1e-6
        )

    def test_cache_read_default_is_10pct(self) -> None:
        pricing = _resolve_pricing("claude-3-sonnet-20240229")
        assert pricing.effective_cache_read == pytest.approx(
            pricing.input_per_million * 0.10, rel=1e-6
        )

    def test_explicit_cache_overrides_default(self) -> None:
        # claude-sonnet-4-6 has explicit cache pricing
        pricing = _resolve_pricing("claude-sonnet-4-6")
        assert pricing.effective_cache_write == pytest.approx(3.75, rel=1e-6)
        assert pricing.effective_cache_read == pytest.approx(0.30, rel=1e-6)
