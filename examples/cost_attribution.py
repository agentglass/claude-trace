"""
cost_attribution.py — Per-customer cost attribution using claude-trace sessions.

This example shows how to build a multi-tenant application where each
customer's API costs are automatically attributed to OTel spans, enabling:
    - Per-customer cost dashboards in Grafana/Honeycomb/Datadog
    - Cost anomaly detection (customer suddenly using 10x more tokens)
    - Chargeback systems (export span data → billing)

The pattern is simple:
    1. Call ``claude_trace.instrument()`` once at startup.
    2. Wrap each customer's work in ``claude_trace.session(customer_id=...)``.
    3. All spans within that context carry ``claude.session.customer_id``.
    4. Export to your OTel backend and query by ``claude.session.customer_id``.

Prerequisites:
    pip install claude-trace

Run:
    ANTHROPIC_API_KEY=sk-... python examples/cost_attribution.py
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Setup: in-memory span collection for demo purposes
# ---------------------------------------------------------------------------

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))

import claude_trace
from claude_trace.config import TraceConfig
from claude_trace._cost.calculator import get_calculator

config = TraceConfig(
    tracer_provider=provider,
    record_costs=True,
)
claude_trace.instrument(config=config)

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "placeholder"))
async_client = anthropic.AsyncAnthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY", "placeholder")
)


# ---------------------------------------------------------------------------
# Customer cost ledger (aggregates from span attributes)
# ---------------------------------------------------------------------------


@dataclass
class CustomerCostLedger:
    """Aggregates cost data collected from OTel spans for reporting."""

    entries: list[dict[str, object]] = field(default_factory=list)

    def ingest_spans(self, spans: list[ReadableSpan]) -> None:
        """Process exported spans and extract session-level cost data."""
        for span in spans:
            attrs = dict(span.attributes or {})
            if span.name != "claude.session":
                continue
            customer_id = attrs.get("claude.session.customer_id", "unknown")
            cost = float(attrs.get("claude.session.total_cost_usd", "0.0"))
            turns = int(attrs.get("claude.session.total_turns", 0))
            input_tokens = int(attrs.get("claude.session.total_input_tokens", 0))
            output_tokens = int(attrs.get("claude.session.total_output_tokens", 0))
            self.entries.append(
                {
                    "customer_id": customer_id,
                    "session_id": attrs.get("claude.session.id", ""),
                    "cost_usd": cost,
                    "turns": turns,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            )

    def report(self) -> str:
        """Return a formatted cost report grouped by customer."""
        from collections import defaultdict

        by_customer: dict[str, dict[str, float]] = defaultdict(
            lambda: {"cost": 0.0, "sessions": 0.0, "turns": 0.0, "tokens": 0.0}
        )
        for e in self.entries:
            c = str(e["customer_id"])
            by_customer[c]["cost"] += float(e["cost_usd"])  # type: ignore[arg-type]
            by_customer[c]["sessions"] += 1
            by_customer[c]["turns"] += float(e["turns"])  # type: ignore[arg-type]
            by_customer[c]["tokens"] += float(e["input_tokens"]) + float(e["output_tokens"])  # type: ignore[arg-type]

        lines = ["Customer Cost Attribution Report", "=" * 40]
        for cust, stats in sorted(by_customer.items(), key=lambda x: -x[1]["cost"]):
            lines.append(
                f"  {cust:<25} "
                f"${stats['cost']:.6f}  "
                f"{int(stats['sessions'])} sessions  "
                f"{int(stats['turns'])} turns  "
                f"{int(stats['tokens'])} tokens"
            )
        lines.append("")
        total = sum(s["cost"] for s in by_customer.values())
        lines.append(f"  {'TOTAL':<25} ${total:.6f}")
        return "\n".join(lines)


ledger = CustomerCostLedger()


# ---------------------------------------------------------------------------
# Simulated customer work
# ---------------------------------------------------------------------------


CUSTOMERS = [
    {"id": "customer_acme", "prompt": "Summarise the benefits of OpenTelemetry in 2 sentences."},
    {"id": "customer_globex", "prompt": "What is the capital of France? One word answer."},
    {"id": "customer_initech", "prompt": "Write a haiku about observability."},
    {"id": "customer_acme", "prompt": "What is 100 + 200? Just the number."},  # acme 2nd session
]


def run_customer_session(customer_id: str, prompt: str) -> Optional[str]:
    """Run a single-turn session tagged to a specific customer."""
    with claude_trace.session(
        model="claude-haiku-4-5",
        customer_id=customer_id,
        tags=["cost-attribution-demo"],
    ) as sess:
        if os.environ.get("ANTHROPIC_API_KEY", "placeholder") == "placeholder":
            return None

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        print(f"  [{customer_id}] {text[:60]}")
        return text
    return None


async def run_customer_session_async(customer_id: str, prompt: str) -> Optional[str]:
    """Async variant — demonstrates that customer context is preserved in async tasks."""
    async with claude_trace.session(
        model="claude-haiku-4-5",
        customer_id=customer_id,
        tags=["cost-attribution-demo", "async"],
    ) as sess:
        if os.environ.get("ANTHROPIC_API_KEY", "placeholder") == "placeholder":
            return None

        response = await async_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        print(f"  [async][{customer_id}] {text[:60]}")
        return text
    return None


# ---------------------------------------------------------------------------
# Offline cost estimate (no API key needed)
# ---------------------------------------------------------------------------


def offline_cost_estimate_demo() -> None:
    """Demonstrate the cost calculator for pre-flight budget estimation."""
    print("\n--- Offline Cost Estimate Demo ---")
    calc = get_calculator()

    scenarios = [
        ("claude-haiku-4-5", 10_000, 2_000, "10 short tasks"),
        ("claude-sonnet-4-6", 50_000, 10_000, "50 medium tasks"),
        ("claude-opus-4-5", 100_000, 20_000, "10 complex reasoning tasks"),
    ]

    for model, inp, out, label in scenarios:
        bd = calc.calculate(model, input_tokens=inp, output_tokens=out)
        print(f"  {label:<35} {model:<30} ${bd.total_usd:.4f}")

    # Prompt caching saves money on repeated system prompts
    no_cache = calc.calculate("claude-sonnet-4-6", input_tokens=100_000, output_tokens=5_000)
    with_cache = calc.calculate(
        "claude-sonnet-4-6",
        input_tokens=10_000,          # first 90k cached
        output_tokens=5_000,
        cache_read_tokens=90_000,     # reading 90k from cache
        cache_creation_tokens=1_000,  # small new content
    )
    savings_pct = (1 - with_cache.total_usd / no_cache.total_usd) * 100
    print(f"\n  Prompt caching savings example:")
    print(f"    Without cache: ${no_cache.total_usd:.4f}")
    print(f"    With cache:    ${with_cache.total_usd:.4f}  ({savings_pct:.1f}% cheaper)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("claude-trace: Per-Customer Cost Attribution Demo")
    print("=" * 50)

    offline_cost_estimate_demo()

    has_key = os.environ.get("ANTHROPIC_API_KEY", "placeholder") != "placeholder"
    if not has_key:
        print("\n  [Skipping live API calls — set ANTHROPIC_API_KEY to enable]")
    else:
        print("\n--- Sync Customer Sessions ---")
        for customer in CUSTOMERS:
            run_customer_session(customer["id"], customer["prompt"])

        print("\n--- Async Customer Sessions (concurrent) ---")
        async_customers = CUSTOMERS[:2]  # run 2 concurrently

        async def run_all() -> None:
            tasks = [
                asyncio.create_task(
                    run_customer_session_async(c["id"], c["prompt"])
                )
                for c in async_customers
            ]
            await asyncio.gather(*tasks)

        asyncio.run(run_all())

    # Collect and report spans
    spans = list(exporter.get_finished_spans())
    ledger.ingest_spans(spans)  # type: ignore[arg-type]

    if ledger.entries:
        print()
        print(ledger.report())
    else:
        print("\n  No sessions recorded (no API key provided — that's OK).")
        print("  Span structure would appear in the OTel backend once connected.")

    claude_trace.uninstrument()
    provider.shutdown()
    print("\nDone.")


if __name__ == "__main__":
    main()
