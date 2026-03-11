"""
basic_instrumentation.py — Complete claude-trace feature walkthrough.

Demonstrates:
    1. Zero-config instrumentation (console exporter via env or SDK default)
    2. Sync session context manager with cost reporting
    3. Async session context manager
    4. Manual tool span wrapping
    5. Config overrides
    6. Session tagging for filtering

Prerequisites:
    pip install claude-trace[console]

Run:
    ANTHROPIC_API_KEY=sk-... python examples/basic_instrumentation.py

For OTLP export add:
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
    pip install claude-trace[otlp]
"""

from __future__ import annotations

import asyncio
import os
import sys

# ---------------------------------------------------------------------------
# 1. Setup OpenTelemetry with a console exporter for local development
# ---------------------------------------------------------------------------

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

resource = Resource.create({"service.name": "claude-trace-demo", "service.version": "0.1.0"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

# ---------------------------------------------------------------------------
# 2. Instrument the Anthropic SDK before creating any clients
# ---------------------------------------------------------------------------

import claude_trace
from claude_trace.config import TraceConfig

config = TraceConfig(
    service_name="claude-trace-demo",
    tracer_provider=provider,
    record_costs=True,
    capture_inputs=False,   # Set True to log message content (may capture PII)
    capture_outputs=False,  # Set True to log response text (may capture PII)
)
claude_trace.instrument(config=config)

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "placeholder"))


# ---------------------------------------------------------------------------
# 3. Sync example: single-turn session with cost reporting
# ---------------------------------------------------------------------------

def sync_example() -> None:
    """Single-turn sync session showing basic cost attribution."""
    print("\n--- Sync Example ---")

    with claude_trace.session(
        model="claude-haiku-4-5",
        customer_id="demo-user-001",
        tags=["demo", "sync"],
        system_prompt="You are a helpful assistant.",
    ) as sess:
        if os.environ.get("ANTHROPIC_API_KEY", "placeholder") == "placeholder":
            print("  [SKIPPED: Set ANTHROPIC_API_KEY to make real API calls]")
            return

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": "What is 2 + 2? Reply in one sentence."}],
        )
        print(f"  Response: {response.content[0].text[:100]}")

    print(f"  Session ID  : {sess.session_id}")
    print(f"  Turns       : {sess._turn_count}")
    print(f"  Input tokens: {sess.cost.input_tokens}")
    print(f"  Output tokens: {sess.cost.output_tokens}")
    print(f"  Total cost  : ${sess.cost.total_usd:.6f}")


# ---------------------------------------------------------------------------
# 4. Async example: multi-turn session
# ---------------------------------------------------------------------------

async def async_example() -> None:
    """Multi-turn async session with streaming."""
    print("\n--- Async Example ---")

    async_client = anthropic.AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "placeholder")
    )

    async with claude_trace.session(
        model="claude-haiku-4-5",
        customer_id="demo-user-002",
        tags=["demo", "async", "streaming"],
        max_turns=3,
    ) as sess:
        if os.environ.get("ANTHROPIC_API_KEY", "placeholder") == "placeholder":
            print("  [SKIPPED: Set ANTHROPIC_API_KEY to make real API calls]")
            return

        # Turn 1
        response1 = await async_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=128,
            messages=[{"role": "user", "content": "Name three planets."}],
        )
        print(f"  Turn 1: {response1.content[0].text[:80]}")

        # Turn 2 (streaming)
        full_text = ""
        stream = await async_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=128,
            stream=True,
            messages=[
                {"role": "user", "content": "Name three planets."},
                {"role": "assistant", "content": response1.content[0].text},
                {"role": "user", "content": "Now name three moons."},
            ],
        )
        async for event in stream:
            if hasattr(event, "delta") and hasattr(event.delta, "text"):
                full_text += event.delta.text
        print(f"  Turn 2 (streaming): {full_text[:80]}")

    print(f"  Session ID   : {sess.session_id}")
    print(f"  Total turns  : {sess._turn_count}")
    print(f"  Total cost   : ${sess.cost.total_usd:.6f}")


# ---------------------------------------------------------------------------
# 5. Manual tool span example
# ---------------------------------------------------------------------------

from claude_trace._spans.tool import tool_span


@tool_span(name="calculator", config=config)
def calculator(expression: str) -> str:
    """A simple calculator tool wrapped with a tool span."""
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def manual_tool_example() -> None:
    """Shows how to manually wrap a tool function with a span."""
    print("\n--- Manual Tool Span Example ---")
    result = calculator("2 ** 10 + 42")
    print(f"  calculator('2 ** 10 + 42') = {result}")


# ---------------------------------------------------------------------------
# 6. Configuration introspection
# ---------------------------------------------------------------------------

def config_example() -> None:
    """Shows config helper methods."""
    print("\n--- Configuration ---")
    cfg = TraceConfig()
    print(f"  Enabled        : {cfg.enabled}")
    print(f"  Service name   : {cfg.service_name}")
    print(f"  Span prefix    : {cfg.span_name_prefix}")
    print(f"  Session span   : {cfg.span_name('session')}")
    print(f"  Turn span      : {cfg.span_name('turn')}")
    print(f"  Tool span      : {cfg.span_name('tool')}")
    print(f"  Record costs   : {cfg.record_costs}")
    print(f"  Max attr len   : {cfg.max_attribute_length}")
    print(f"  Truncate demo  : {cfg.truncate('x' * 2000)[:20]}...")

    # Create a debug variant
    debug = cfg.replace(capture_inputs=True, capture_outputs=True)
    print(f"  Debug captures : inputs={debug.capture_inputs}, outputs={debug.capture_outputs}")


# ---------------------------------------------------------------------------
# 7. Trace diff example (no API key needed)
# ---------------------------------------------------------------------------

from claude_trace._diff.trace_diff import TraceSnapshot, compare


def trace_diff_example() -> None:
    """Shows how to diff two trace snapshots for regression testing."""
    print("\n--- Trace Diff Example ---")

    # Simulate two trace snapshots (normally captured from real sessions)
    baseline = TraceSnapshot(
        session_id="sess_baseline",
        model="claude-haiku-4-5",
        total_turns=3,
        total_input_tokens=5000,
        total_output_tokens=1200,
        total_cache_read_tokens=3000,
        total_cache_creation_tokens=1000,
        total_cost_usd=0.025,
        total_tool_calls=4,
        distinct_tool_names=["bash", "read_file"],
        final_status="completed",
    )

    candidate = TraceSnapshot(
        session_id="sess_candidate",
        model="claude-haiku-4-5",
        total_turns=3,
        total_input_tokens=5100,   # slightly more
        total_output_tokens=1250,
        total_cache_read_tokens=3000,
        total_cache_creation_tokens=1000,
        total_cost_usd=0.026,
        total_tool_calls=4,
        distinct_tool_names=["bash", "read_file"],
        final_status="completed",
    )

    diff = compare(baseline, candidate)
    print(f"  Turn count delta    : {diff.turn_count_delta:+d}")
    print(f"  Input token delta   : {diff.input_token_delta:+d}")
    print(f"  Cost delta          : ${diff.cost_delta_usd:+.6f}")
    print(f"  Tools added         : {diff.tool_names_added}")
    print(f"  Tools removed       : {diff.tool_names_removed}")
    print(f"  Equivalent (5% rtol): {diff.is_equivalent(rtol=0.05)}")

    # This would pass in a test suite:
    try:
        diff.assert_equivalent(rtol=0.10)
        print("  assert_equivalent(rtol=0.10): PASSED")
    except AssertionError as e:
        print(f"  assert_equivalent FAILED: {e}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    config_example()
    manual_tool_example()
    trace_diff_example()
    sync_example()
    asyncio.run(async_example())

    print("\n--- Shutting down ---")
    claude_trace.uninstrument()
    provider.shutdown()
    print("Done. Check console output above for exported spans.")
    sys.exit(0)
