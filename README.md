# claude-trace

**Zero-configuration OpenTelemetry observability for Claude Agent SDK applications.**

Every agent decision — every LLM call, every tool invocation, every token spent — captured as first-class structured OTel spans. Drop it in, point your existing OTel exporter at it, and immediately see what your agents are actually doing.

[![PyPI](https://img.shields.io/pypi/v/claude-trace)](https://pypi.org/project/claude-trace/)
[![Python](https://img.shields.io/pypi/pyversions/claude-trace)](https://pypi.org/project/claude-trace/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why existing tools fall short

Most APM tools treat LLM calls as opaque HTTP requests. You see:
- 200ms latency to `api.anthropic.com` — but not *which turn* of a multi-step agent
- Token counts buried in response JSON — but not *cumulative cost per session*
- Tool calls as log lines — but not *nested as children of the turn that invoked them*

claude-trace is built on the premise that **agent reasoning has structure**, and your observability tooling should reflect that structure natively in spans.

---

## 30-second quickstart

```bash
pip install claude-trace
```

```python
import claude_trace
import anthropic

# One line. Done.
claude_trace.instrument()

client = anthropic.Anthropic()

with claude_trace.session(customer_id="acme", tags=["prod"]) as sess:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Write a bash script to list all Python files."}],
    )

print(f"Session cost: ${sess.cost.total_usd:.4f}")
print(f"Input tokens: {sess.cost.input_tokens}")
```

Works with async too:

```python
async with claude_trace.session(customer_id="acme") as sess:
    response = await async_client.messages.create(...)
```

---

## How the span hierarchy works

```
claude.session  [root span]
│  claude.session.id          = "sess_01HV..."
│  claude.session.customer_id = "acme"
│  claude.session.model       = "claude-sonnet-4-6"
│  claude.session.total_turns = 3
│  claude.cost.total_usd      = "0.04523"
│
├── claude.turn  [turn_index=0]
│   │  claude.turn.stop_reason  = "tool_use"
│   │  claude.turn.input_tokens = 1204
│   │  claude.turn.latency_ms   = 841.3
│   │
│   ├── claude.tool  [bash_0]
│   │      claude.tool.name         = "bash"
│   │      claude.tool.use_id       = "toolu_01A2..."
│   │      claude.tool.input_hash   = "a3f2b8c1..."
│   │      claude.tool.latency_ms   = 47.2
│   │      claude.tool.status       = "success"
│   │
│   └── claude.tool  [read_file_0]
│          claude.tool.name         = "read_file"
│          claude.tool.status       = "success"
│
├── claude.turn  [turn_index=1]
│   │  claude.turn.stop_reason  = "tool_use"
│   └── claude.tool  [bash_1]
│
└── claude.turn  [turn_index=2]
       claude.turn.stop_reason  = "end_turn"
       claude.turn.tool_use_count = 0
```

Every span attribute follows the `claude.{category}.{name}` naming convention, making it easy to filter and aggregate in any OTel-compatible backend.

---

## Features

### Automatic instrumentation — zero code changes to agent logic

```python
claude_trace.instrument()  # patches anthropic.Anthropic AND AsyncAnthropic
```

All existing `client.messages.create()` calls are wrapped automatically. No need to change your agent code.

### Complete token & cost tracking

```python
with claude_trace.session(model="claude-opus-4-5") as sess:
    # ... agent runs ...

print(sess.cost.input_tokens)           # 12450
print(sess.cost.output_tokens)          # 3201
print(sess.cost.cache_read_tokens)      # 8900
print(f"${sess.cost.total_usd:.4f}")   # $0.1523
```

Prompt caching costs are tracked separately (`cache_read` and `cache_creation`) so you can measure the actual savings.

### Streaming support

Both `create(stream=True)` and `client.messages.stream(...)` are supported:

```python
# Streaming — first-token latency is captured automatically
stream = client.messages.create(model=..., stream=True, messages=[...])
for event in stream:
    process(event)
# Turn span ends here, with time_to_first_token_ms set
```

### Per-customer cost attribution

Tag sessions with a `customer_id` and filter your dashboards by it:

```python
with claude_trace.session(customer_id=request.user_id, tags=["api-v2"]) as sess:
    result = run_agent(user_request)

# In your OTel backend, query:
# SELECT sum(claude.cost.total_usd) GROUP BY claude.session.customer_id
```

### Manual tool span wrapping

For tools executed outside the agentic loop:

```python
from claude_trace._spans.tool import tool_span

@tool_span(name="web_search")
def web_search(query: str) -> str:
    return requests.get(f"https://search.example.com?q={query}").text
```

### Trace diffing for regression testing

Detect behavioural regressions between agent versions:

```python
from claude_trace._diff.trace_diff import TraceSnapshot, compare

# Capture golden trace
golden = TraceSnapshot.from_session(baseline_session)
golden.save("tests/golden/my_task.json")

# In CI:
actual = TraceSnapshot.from_session(candidate_session)
golden = TraceSnapshot.load("tests/golden/my_task.json")
diff = compare(golden, actual)

# Typed assertions — not string matching
assert diff.turn_count_delta == 0
assert diff.tool_names_added == set()
assert diff.cost_delta_usd < 0.01
diff.assert_equivalent(rtol=0.05)  # 5% tolerance on tokens/cost
```

---

## Semantic conventions

All span attributes follow the `claude.{category}.{name}` pattern.

### `claude.session.*`

| Attribute | Type | Description |
|-----------|------|-------------|
| `claude.session.id` | string | Unique session identifier |
| `claude.session.model` | string | Configured model |
| `claude.session.customer_id` | string | Tenant/customer for cost attribution |
| `claude.session.total_turns` | int | Total agentic loop iterations |
| `claude.session.total_input_tokens` | int | Cumulative input tokens |
| `claude.session.total_output_tokens` | int | Cumulative output tokens |
| `claude.session.total_cost_usd` | string | Total estimated USD cost |
| `claude.session.status` | string | `completed` / `error` / `max_turns_reached` |

### `claude.turn.*`

| Attribute | Type | Description |
|-----------|------|-------------|
| `claude.turn.index` | int | Zero-based turn index |
| `claude.turn.model` | string | Model returned by API |
| `claude.turn.stop_reason` | string | `end_turn` / `tool_use` / `max_tokens` / `error` |
| `claude.turn.input_tokens` | int | Input tokens for this call |
| `claude.turn.output_tokens` | int | Output tokens for this call |
| `claude.turn.latency_ms` | float | End-to-end latency |
| `claude.turn.time_to_first_token_ms` | float | TTFT (streaming only) |
| `claude.turn.request_id` | string | Anthropic `x-request-id` header |

### `claude.tool.*`

| Attribute | Type | Description |
|-----------|------|-------------|
| `claude.tool.name` | string | Tool function name |
| `claude.tool.use_id` | string | Anthropic `toolu_XXXX` ID |
| `claude.tool.status` | string | `success` / `error` / `timeout` / `cancelled` |
| `claude.tool.latency_ms` | float | Tool execution time |
| `claude.tool.input_hash` | string | SHA-256 of input (16 hex chars) |
| `claude.tool.is_parallel` | bool | True if called alongside other tools |

### `claude.cost.*`

| Attribute | Type | Description |
|-----------|------|-------------|
| `claude.cost.input_usd` | string | Input token cost |
| `claude.cost.output_usd` | string | Output token cost |
| `claude.cost.cache_read_usd` | string | Cache-read cost |
| `claude.cost.cache_creation_usd` | string | Cache-write cost |
| `claude.cost.total_usd` | string | Sum of all costs |

---

## Installation

```bash
# Core
pip install claude-trace

# With rich console exporter (for local development)
pip install "claude-trace[console]"

# With OTLP exporter (for production: Grafana, Datadog, Honeycomb, etc.)
pip install "claude-trace[otlp]"

# Full development environment
pip install "claude-trace[dev]"
```

---

## Configuration

All settings can be configured via environment variables (12-factor style) or programmatically:

```python
from claude_trace.config import TraceConfig

config = TraceConfig(
    service_name="my-agent",          # CLAUDE_TRACE_SERVICE_NAME
    capture_inputs=False,             # CLAUDE_TRACE_CAPTURE_INPUTS  (PII risk)
    capture_outputs=False,            # CLAUDE_TRACE_CAPTURE_OUTPUTS (PII risk)
    record_costs=True,                # CLAUDE_TRACE_RECORD_COSTS
    max_attribute_length=1024,        # CLAUDE_TRACE_MAX_ATTRIBUTE_LEN
    tracer_provider=my_provider,      # programmatic only
)

claude_trace.instrument(config=config)
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_TRACE_ENABLED` | `true` | Master on/off switch |
| `CLAUDE_TRACE_SERVICE_NAME` | `claude-agent` | OTel `service.name` |
| `CLAUDE_TRACE_CAPTURE_INPUTS` | `false` | Log full message content |
| `CLAUDE_TRACE_CAPTURE_OUTPUTS` | `false` | Log full response text |
| `CLAUDE_TRACE_RECORD_COSTS` | `true` | Attach cost attributes |
| `CLAUDE_TRACE_MAX_ATTRIBUTE_LEN` | `1024` | Truncation limit (chars) |

### Sending to Grafana / Honeycomb / Datadog

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
    endpoint="http://localhost:4317",
)))

claude_trace.instrument(config=TraceConfig(tracer_provider=provider))
```

Or set `OTEL_EXPORTER_OTLP_ENDPOINT` and use the global provider.

---

## Cost model

Pricing data is built into the library and updated regularly.  All models from Claude 3 through Claude 4 are supported.  Prompt caching pricing (creation at 125% of input, reads at 10% of input) is tracked separately.

```python
from claude_trace._cost.calculator import get_calculator

calc = get_calculator()
bd = calc.calculate(
    "claude-sonnet-4-6",
    input_tokens=5000,
    output_tokens=800,
    cache_read_tokens=10000,
)
print(f"Total: ${bd.total_usd:.6f}")
print(f"Breakdown: {bd.format_summary()}")
```

---

## Testing your agents

### Golden file testing

```python
# tests/test_my_agent.py
import pytest
from claude_trace._diff.trace_diff import TraceSnapshot, compare

def test_agent_behaviour_stable(run_agent_with_session):
    session = run_agent_with_session(task="summarise the README")
    actual = TraceSnapshot.from_session(session)

    golden = TraceSnapshot.load("tests/golden/summarise_readme.json")
    diff = compare(golden, actual)

    diff.assert_equivalent(rtol=0.10)  # allow 10% token variation
    assert diff.tool_names_added == set(), "New tools appeared unexpectedly"
    assert diff.errors_introduced == 0
```

### Regression on turn count

```python
diff = compare(golden, actual)
assert diff.turn_count_delta <= 1, (
    f"Agent used {diff.candidate.total_turns} turns vs "
    f"{diff.baseline.total_turns} expected (delta={diff.turn_count_delta})"
)
```

---

## Contributing

Contributions are welcome. The project uses:
- `hatch` for builds
- `ruff` for linting
- `mypy --strict` for type checking
- `pytest` with `asyncio_mode = auto`

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

### Adding a new model's pricing

Edit `src/claude_trace/_cost/calculator.py` and add a `ModelPricing` entry to `_PRICING_TABLE`. Add corresponding unit tests in `tests/unit/test_cost_calculator.py`.

### Semantic convention changes

All attribute names live in `src/claude_trace/_semconv/claude.py`.  Every new attribute needs:
1. A constant field on the appropriate frozen dataclass
2. A docstring explaining the legal values and semantics
3. A test in `tests/unit/test_semconv.py` verifying the name format

---

## License

MIT — see [LICENSE](LICENSE).
