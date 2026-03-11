"""
Token cost calculator for Anthropic Claude models.

Pricing data is sourced from the official Anthropic pricing page.
All prices are in USD per million tokens.

Pricing last updated: 2026-Q1

Model families supported:
    - claude-opus-4      (claude-opus-4-5, claude-opus-4-0)
    - claude-sonnet-4    (claude-sonnet-4-6, claude-sonnet-4-5)
    - claude-haiku-4     (claude-haiku-4-5)
    - claude-3-5-sonnet  (claude-3-5-sonnet-20241022, claude-3-5-sonnet-20240620)
    - claude-3-5-haiku   (claude-3-5-haiku-20241022)
    - claude-3-opus      (claude-3-opus-20240229)
    - claude-3-sonnet    (claude-3-sonnet-20240229)
    - claude-3-haiku     (claude-3-haiku-20240307)

Prompt caching pricing:
    - Cache creation: billed at 125% of input token price
    - Cache read:     billed at 10% of input token price

Usage::

    calc = get_calculator()
    breakdown = calc.calculate(
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=2000,
        cache_creation_tokens=800,
    )
    print(f"Total cost: ${breakdown.total_usd:.6f}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class ModelPricing:
    """Pricing for a specific Claude model variant.

    All prices are in USD per million tokens.
    Cache pricing is derived from input_per_million unless overridden.
    """

    model_id: str
    """Canonical model identifier (e.g. ``"claude-sonnet-4-6-20251101"``)."""

    input_per_million: float
    """Standard input token price per 1M tokens (USD)."""

    output_per_million: float
    """Output token price per 1M tokens (USD)."""

    cache_write_per_million: Optional[float] = None
    """Cache creation price per 1M tokens. Defaults to 1.25x input price."""

    cache_read_per_million: Optional[float] = None
    """Cache read price per 1M tokens. Defaults to 0.10x input price."""

    @property
    def effective_cache_write(self) -> float:
        """Effective cache-write price, defaulting to 1.25x input."""
        return self.cache_write_per_million or self.input_per_million * 1.25

    @property
    def effective_cache_read(self) -> float:
        """Effective cache-read price, defaulting to 0.10x input."""
        return self.cache_read_per_million or self.input_per_million * 0.10


@dataclass(frozen=True)
class CostBreakdown:
    """Detailed cost breakdown for a single API call.

    All monetary values are in USD.
    """

    model: str
    """Model identifier used for pricing lookup."""

    input_tokens: int
    """Number of standard input tokens."""

    output_tokens: int
    """Number of output tokens."""

    cache_read_tokens: int
    """Number of cache-read tokens (billed at discount)."""

    cache_creation_tokens: int
    """Number of cache-creation tokens (billed at premium)."""

    input_cost_usd: float = field(default=0.0)
    """Cost for standard input tokens."""

    output_cost_usd: float = field(default=0.0)
    """Cost for output tokens."""

    cache_read_cost_usd: float = field(default=0.0)
    """Cost for cache-read tokens."""

    cache_creation_cost_usd: float = field(default=0.0)
    """Cost for cache-creation tokens."""

    @property
    def total_usd(self) -> float:
        """Sum of all cost components."""
        return (
            self.input_cost_usd
            + self.output_cost_usd
            + self.cache_read_cost_usd
            + self.cache_creation_cost_usd
        )

    @property
    def total_tokens(self) -> int:
        """Total tokens across all categories."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def __add__(self, other: "CostBreakdown") -> "CostBreakdown":
        """Combine two cost breakdowns (for cumulative session totals)."""
        return CostBreakdown(
            model=self.model,  # Keep first model; session uses session-level model
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            input_cost_usd=self.input_cost_usd + other.input_cost_usd,
            output_cost_usd=self.output_cost_usd + other.output_cost_usd,
            cache_read_cost_usd=self.cache_read_cost_usd + other.cache_read_cost_usd,
            cache_creation_cost_usd=self.cache_creation_cost_usd + other.cache_creation_cost_usd,
        )

    def format_summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"${self.total_usd:.6f} "
            f"(in={self.input_tokens}, out={self.output_tokens}, "
            f"cache_r={self.cache_read_tokens}, cache_w={self.cache_creation_tokens})"
        )


# ---------------------------------------------------------------------------
# Pricing table — USD per million tokens (as of 2026-Q1)
# ---------------------------------------------------------------------------

_PRICING_TABLE: list[ModelPricing] = [
    # Claude 4 Opus family
    ModelPricing(
        model_id="claude-opus-4-5",
        input_per_million=15.00,
        output_per_million=75.00,
        cache_write_per_million=18.75,
        cache_read_per_million=1.50,
    ),
    ModelPricing(
        model_id="claude-opus-4-0",
        input_per_million=15.00,
        output_per_million=75.00,
        cache_write_per_million=18.75,
        cache_read_per_million=1.50,
    ),
    # Claude 4 Sonnet family
    ModelPricing(
        model_id="claude-sonnet-4-6",
        input_per_million=3.00,
        output_per_million=15.00,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    ModelPricing(
        model_id="claude-sonnet-4-6-20251101",
        input_per_million=3.00,
        output_per_million=15.00,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    ModelPricing(
        model_id="claude-sonnet-4-5",
        input_per_million=3.00,
        output_per_million=15.00,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    ModelPricing(
        model_id="claude-sonnet-4-5-20250514",
        input_per_million=3.00,
        output_per_million=15.00,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    # Claude 4 Haiku family
    ModelPricing(
        model_id="claude-haiku-4-5",
        input_per_million=0.80,
        output_per_million=4.00,
        cache_write_per_million=1.00,
        cache_read_per_million=0.08,
    ),
    ModelPricing(
        model_id="claude-haiku-4-5-20250514",
        input_per_million=0.80,
        output_per_million=4.00,
        cache_write_per_million=1.00,
        cache_read_per_million=0.08,
    ),
    # Claude 3.5 Sonnet family
    ModelPricing(
        model_id="claude-3-5-sonnet-20241022",
        input_per_million=3.00,
        output_per_million=15.00,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    ModelPricing(
        model_id="claude-3-5-sonnet-20240620",
        input_per_million=3.00,
        output_per_million=15.00,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    # Claude 3.5 Haiku
    ModelPricing(
        model_id="claude-3-5-haiku-20241022",
        input_per_million=0.80,
        output_per_million=4.00,
        cache_write_per_million=1.00,
        cache_read_per_million=0.08,
    ),
    # Claude 3 Opus
    ModelPricing(
        model_id="claude-3-opus-20240229",
        input_per_million=15.00,
        output_per_million=75.00,
        cache_write_per_million=18.75,
        cache_read_per_million=1.50,
    ),
    # Claude 3 Sonnet
    ModelPricing(
        model_id="claude-3-sonnet-20240229",
        input_per_million=3.00,
        output_per_million=15.00,
    ),
    # Claude 3 Haiku
    ModelPricing(
        model_id="claude-3-haiku-20240307",
        input_per_million=0.25,
        output_per_million=1.25,
        cache_write_per_million=0.30,
        cache_read_per_million=0.03,
    ),
    # Claude 2 (legacy)
    ModelPricing(
        model_id="claude-2.1",
        input_per_million=8.00,
        output_per_million=24.00,
    ),
    ModelPricing(
        model_id="claude-2.0",
        input_per_million=8.00,
        output_per_million=24.00,
    ),
]

# Index by model_id for O(1) lookup
_PRICING_INDEX: dict[str, ModelPricing] = {p.model_id: p for p in _PRICING_TABLE}

# Alias prefixes for fuzzy matching (e.g. "claude-sonnet-4-6" → exact entry)
_PREFIX_ALIASES: dict[str, str] = {
    "claude-opus-4": "claude-opus-4-5",
    "claude-sonnet-4": "claude-sonnet-4-6",
    "claude-haiku-4": "claude-haiku-4-5",
    "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku": "claude-3-5-haiku-20241022",
    "claude-3-opus": "claude-3-opus-20240229",
    "claude-3-sonnet": "claude-3-sonnet-20240229",
    "claude-3-haiku": "claude-3-haiku-20240307",
}

# Fallback pricing used when the model is unknown (claude-sonnet-4 tier)
_FALLBACK_PRICING = ModelPricing(
    model_id="unknown",
    input_per_million=3.00,
    output_per_million=15.00,
)


def _resolve_pricing(model: str) -> ModelPricing:
    """Resolve a model string to a ``ModelPricing`` entry.

    Resolution order:
    1. Exact match in pricing index.
    2. Prefix match (longest prefix wins) via ``_PREFIX_ALIASES``.
    3. Regex-based family detection from the model string.
    4. Fallback to claude-sonnet-4 pricing (logged as a warning).
    """
    # 1. Exact match
    if model in _PRICING_INDEX:
        return _PRICING_INDEX[model]

    # 2. Prefix alias
    for prefix, canonical in sorted(_PREFIX_ALIASES.items(), key=lambda x: -len(x[0])):
        if model.startswith(prefix):
            return _PRICING_INDEX[canonical]

    # 3. Regex family detection
    lower = model.lower()
    if re.search(r"opus", lower):
        return _PRICING_INDEX["claude-opus-4-5"]
    if re.search(r"sonnet", lower):
        return _PRICING_INDEX["claude-sonnet-4-6"]
    if re.search(r"haiku", lower):
        return _PRICING_INDEX["claude-haiku-4-5"]

    # 4. Fallback
    import warnings

    warnings.warn(
        f"claude-trace: unknown model '{model}', using claude-sonnet-4 pricing as fallback.",
        stacklevel=3,
    )
    return _FALLBACK_PRICING


class CostCalculator:
    """Calculate USD cost for Claude API calls.

    Thread-safe (no mutable state after construction).

    Usage::

        calc = CostCalculator()
        bd = calc.calculate("claude-sonnet-4-6", 1000, 500)
        print(bd.total_usd)
    """

    def calculate(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> CostBreakdown:
        """Calculate a full cost breakdown for one API call.

        Args:
            model: Claude model identifier (any format recognised by the pricing table).
            input_tokens: Standard (non-cached) input tokens.
            output_tokens: Output tokens generated by the model.
            cache_read_tokens: Input tokens served from prompt cache.
            cache_creation_tokens: Input tokens that populated the cache.

        Returns:
            A ``CostBreakdown`` with per-component and total costs.
        """
        pricing = _resolve_pricing(model)
        m = 1_000_000.0

        input_cost = input_tokens * pricing.input_per_million / m
        output_cost = output_tokens * pricing.output_per_million / m
        cache_read_cost = cache_read_tokens * pricing.effective_cache_read / m
        cache_creation_cost = cache_creation_tokens * pricing.effective_cache_write / m

        return CostBreakdown(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_read_cost_usd=cache_read_cost,
            cache_creation_cost_usd=cache_creation_cost,
        )

    def list_models(self) -> list[str]:
        """Return all model IDs with known pricing."""
        return sorted(_PRICING_INDEX.keys())

    def get_pricing(self, model: str) -> ModelPricing:
        """Return the resolved ``ModelPricing`` for ``model``."""
        return _resolve_pricing(model)


@lru_cache(maxsize=1)
def get_calculator() -> CostCalculator:
    """Return the shared (singleton) ``CostCalculator`` instance."""
    return CostCalculator()
