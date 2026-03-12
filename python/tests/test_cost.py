"""Tests for CostBreakdown and calculate_cost (Rust core via PyO3)."""
from __future__ import annotations

import pytest

from claude_trace._claude_trace_core import CostBreakdown, calculate_cost  # type: ignore[import]


def test_sonnet_pricing() -> None:
    cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000, 0, 0)
    assert abs(cost.total_usd - 18.0) < 0.001


def test_haiku_pricing() -> None:
    cost = calculate_cost("claude-haiku-4-5", 1_000_000, 1_000_000, 0, 0)
    assert abs(cost.total_usd - 4.80) < 0.001


def test_cache_read_discount() -> None:
    cost = calculate_cost("claude-sonnet-4-6", 0, 0, 1_000_000, 0)
    assert abs(cost.cache_read_usd - 0.30) < 0.001


def test_cost_breakdown_addition() -> None:
    a = calculate_cost("claude-sonnet-4-6", 100_000, 100_000, 0, 0)
    b = calculate_cost("claude-sonnet-4-6", 100_000, 100_000, 0, 0)
    total = a + b
    assert abs(total.total_usd - (a.total_usd + b.total_usd)) < 0.0001


def test_unknown_model_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_cost("gpt-fake-model", 100, 100, 0, 0)


def test_prefix_resolution() -> None:
    # Dated model ID should resolve via prefix
    cost = calculate_cost("claude-sonnet-4-6-20251022", 1_000_000, 0, 0, 0)
    assert cost.input_usd > 0


def test_breakdown_repr() -> None:
    cost = calculate_cost("claude-sonnet-4-6", 1_000, 500, 0, 0)
    r = repr(cost)
    assert "CostBreakdown" in r
    assert "total_usd" in r


def test_breakdown_input_output_fields() -> None:
    cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 0, 0, 0)
    assert abs(cost.input_usd - 3.0) < 0.001
    assert cost.output_usd == 0.0
    assert cost.cache_read_usd == 0.0
    assert cost.cache_write_usd == 0.0


def test_cache_write_premium() -> None:
    # Cache write for sonnet = $3.75/MTok (1.25x input)
    cost = calculate_cost("claude-sonnet-4-6", 0, 0, 0, 1_000_000)
    assert abs(cost.cache_write_usd - 3.75) < 0.001


def test_zero_tokens_zero_cost() -> None:
    cost = calculate_cost("claude-haiku-4-5", 0, 0, 0, 0)
    assert cost.total_usd == 0.0
