# TDD Workflow Skill — Test-Driven Development for claude-trace

<!--
skill:
  name: test
  description: Enforces TDD cycle (Red → Green → Refactor) across Rust, Python, and TypeScript layers. Never write implementation before tests.
  context: fork
  agent: general-purpose
  triggers:
    - "write a test"
    - "add tests for"
    - "test coverage"
    - "implement with TDD"
    - "add feature"
    - "fix bug"
    - "write failing test"
-->

## The Immutable TDD Law

**No implementation code exists before its test exists and fails.**

This is not a preference. It is the workflow. Violating it produces untestable code, fragile designs, and gaps in the 85% coverage gate.

---

## The Three Phases

### Phase 1: RED — Write a Failing Test

Write the test *before* you write any implementation. The test must:
1. Import the function/type that does not exist yet
2. Assert the behavior you want
3. **Fail to compile** (or compile but assert incorrectly) — this is the "Red" state

Do not move to Phase 2 until you have seen the test fail. A test you've never seen fail is a test you don't trust.

**For Rust:**
```rust
#[cfg(test)]
mod tests {
    use super::*;

    // Write this FIRST. It will fail because calculate_cost doesn't exist yet.
    #[test]
    fn test_cost_calculator_returns_zero_for_zero_tokens() {
        let calc = CostCalculator::new();
        let breakdown = calc.calculate("claude-sonnet-4-6", 0, 0, 0, 0).unwrap();
        assert_eq!(breakdown.total_usd, 0.0);
    }
}
```

Run `cargo test test_cost_calculator_returns_zero` and confirm it fails with a compile error or assertion failure before writing any implementation.

**For Python:**
```python
# python/tests/test_cost.py — write this FIRST
def test_cost_calculator_returns_zero_for_zero_tokens() -> None:
    from claude_trace._cost.calculator import get_calculator
    calc = get_calculator()
    breakdown = calc.calculate("claude-sonnet-4-6", 0, 0, 0, 0)
    assert breakdown.total_usd == 0.0
```

Run `pytest python/tests/test_cost.py::test_cost_calculator_returns_zero_for_zero_tokens -x` and confirm it fails with `ImportError` or `AttributeError` before writing any implementation.

**For TypeScript:**
```typescript
// typescript/tests/cost.test.ts — write this FIRST
import { calculateCost } from '../src/cost';

it('returns zero cost for zero tokens', () => {
  const breakdown = calculateCost('claude-sonnet-4-6', 0, 0, 0, 0);
  expect(breakdown.totalUsd).toBe(0);
});
```

Run `npm test -- --testPathPattern=cost` and confirm it fails with a module not found error before writing any implementation.

---

### Phase 2: GREEN — Write Minimal Implementation

Write the **minimum** code to make the failing test pass.

**No extra code. No future-proofing. No handling cases the test doesn't cover yet.**

If you think "I should also handle X while I'm here," stop. Write a test for X first (go back to Phase 1).

```rust
// Minimal implementation to pass the zero-tokens test above
pub struct CostCalculator;

impl CostCalculator {
    pub fn new() -> Self { Self }

    pub fn calculate(
        &self,
        _model: &str,
        input_tokens: u64,
        output_tokens: u64,
        cache_read_tokens: u64,
        cache_creation_tokens: u64,
    ) -> Result<CostBreakdown, ClaudeTraceError> {
        // Minimal: all costs are zero
        Ok(CostBreakdown {
            model: _model.to_owned(),
            input_tokens: input_tokens as usize,
            output_tokens: output_tokens as usize,
            // ... all costs 0.0 for now
        })
    }
}
```

Run the test again. It should pass. If it doesn't, fix the implementation only enough to make it pass.

---

### Phase 3: REFACTOR — Clean Up

With the test passing and the contract established, improve the code:

1. Apply clippy pedantic: `cargo clippy -- -D warnings -D clippy::pedantic`
2. Check types are correct and ergonomic
3. Improve names for clarity
4. Remove duplication
5. Add proper `///` doc comments
6. **Tests must still pass after every refactor step**

After refactoring, add more tests to cover edge cases you identified:

```rust
// Add these AFTER the green phase of the first test
#[test]
fn test_cost_calculator_charges_for_output_tokens() {
    let calc = CostCalculator::new();
    let breakdown = calc.calculate("claude-sonnet-4-6", 0, 1_000_000, 0, 0).unwrap();
    // Sonnet: $15.00 / M output tokens
    assert!((breakdown.total_usd - 15.0).abs() < 0.0001);
}

#[test]
fn test_cost_calculator_applies_cache_read_discount() {
    let calc = CostCalculator::new();
    let breakdown = calc.calculate("claude-sonnet-4-6", 1_000_000, 0, 0, 0).unwrap();
    let input_cost = breakdown.input_cost_usd;

    let breakdown_cached = calc.calculate("claude-sonnet-4-6", 0, 0, 1_000_000, 0).unwrap();
    let cache_read_cost = breakdown_cached.cache_read_cost_usd;

    // Cache reads should be ~10% of input token cost
    assert!(cache_read_cost < input_cost * 0.15);
    assert!(cache_read_cost > input_cost * 0.05);
}
```

---

## Test Naming Standard

Tests describe **behaviors**, not implementations. Use these patterns:

| Pattern | Example |
|---|---|
| `test_<subject>_<verb>_<condition>` | `test_session_span_accumulates_tokens_across_turns` |
| `test_<subject>_<verb>_when_<condition>` | `test_calculator_uses_fallback_when_model_unknown` |
| `test_<subject>_returns_<value>_for_<input>` | `test_calculator_returns_zero_for_zero_tokens` |
| `test_<subject>_rejects_<bad_input>` | `test_session_span_rejects_empty_session_id` |

Never name tests:
- `test_calculate` (what does it test?)
- `test_session` (which behavior?)
- `test_happy_path` (not descriptive)

---

## One Assertion Concept Per Test

You may have multiple `assert_eq!` calls in one test, but they should all test the same **concept**:

```rust
// CORRECT: all assertions test the same concept (token accumulation)
#[test]
fn test_session_accumulates_tokens_from_both_turns() {
    let mut session = SessionState::new();
    session.record_turn_tokens(100, 50, 0, 0);
    session.record_turn_tokens(200, 75, 0, 0);

    assert_eq!(session.total_input_tokens(), 300);   // same concept
    assert_eq!(session.total_output_tokens(), 125);  // same concept
}

// WRONG: tests two unrelated concepts
#[test]
fn test_session_everything() {
    let mut session = SessionState::new();
    session.record_turn_tokens(100, 50, 0, 0);
    assert_eq!(session.total_input_tokens(), 100);   // accumulation
    assert!(session.status() == SessionStatus::Running); // status — different concept!
    assert_eq!(session.cost().total_usd, 0.0003);   // cost — yet another concept!
}
```

---

## Snapshot Tests with `insta`

Use `insta` for testing complex, multi-field outputs that would be verbose to assert field-by-field:

```rust
#[test]
fn test_cost_breakdown_format_summary_snapshot() {
    let breakdown = build_test_breakdown();
    // First run creates the snapshot; subsequent runs compare against it
    insta::assert_snapshot!(breakdown.format_summary());
}

#[test]
fn test_session_span_attributes_snapshot() {
    let span = build_test_session_span();
    insta::assert_json_snapshot!(span.to_attribute_map());
}
```

**Snapshot workflow:**
1. Run test: creates `.snap.new` file
2. Run `cargo insta review` to inspect and approve
3. Approved snapshots become `.snap` files, committed to git
4. Never approve snapshots without reading them

---

## File and Directory Conventions

### Rust Tests
- Location: `#[cfg(test)] mod tests { ... }` at **bottom of the same file**
- Integration tests: `tests/` directory at crate root, each test in its own file
- Test utilities: `tests/helpers/mod.rs`

### Python Tests
- Location: `python/tests/test_<module_name>.py`
- Matches module structure: `python/claude_trace/_cost/calculator.py` → `python/tests/test_cost.py`
- Use `pytest` fixtures for shared setup
- Use `pytest-asyncio` for async code (`@pytest.mark.asyncio`)

```python
# python/tests/conftest.py — shared fixtures
import pytest
from claude_trace._cost.calculator import get_calculator

@pytest.fixture
def calculator():
    return get_calculator()

# python/tests/test_cost.py
class TestCostCalculator:
    def test_returns_zero_for_zero_tokens(self, calculator) -> None:
        breakdown = calculator.calculate("claude-sonnet-4-6", 0, 0, 0, 0)
        assert breakdown.total_usd == 0.0

    def test_charges_for_input_tokens(self, calculator) -> None:
        breakdown = calculator.calculate("claude-sonnet-4-6", 1_000_000, 0, 0, 0)
        assert abs(breakdown.input_cost_usd - 3.0) < 0.01  # $3.00/M for sonnet-4
```

### TypeScript Tests
- Location: `typescript/tests/<module>.test.ts`
- Use Jest + ts-jest
- Describe blocks for grouping related tests:

```typescript
// typescript/tests/cost.test.ts
describe('CostCalculator', () => {
  it('returns zero cost for zero tokens', () => {
    const result = calculateCost('claude-sonnet-4-6', 0, 0, 0, 0);
    expect(result.totalUsd).toBe(0);
  });

  it('charges for input tokens at the correct rate', () => {
    const result = calculateCost('claude-sonnet-4-6', 1_000_000, 0, 0, 0);
    expect(result.inputCostUsd).toBeCloseTo(3.0, 2); // $3.00/M
  });
});
```

---

## Coverage Gate: 85% Minimum

CI enforces 85% line coverage across the Rust codebase. To check locally:

```bash
# Install coverage tool (one-time)
cargo install cargo-llvm-cov

# Run with coverage
cargo llvm-cov --html
open target/llvm-cov/html/index.html

# Check just the percentage (what CI checks)
cargo llvm-cov --summary-only 2>&1 | grep "TOTAL"
```

If coverage drops below 85%, the coverage gate script (`scripts/coverage-gate.sh`) will block the CI run with exit code 2.

**When you add new public functions**, always add corresponding tests in the same commit. Never create a PR with uncovered public APIs.

---

## Special Cases

### Testing Span Attributes

When testing OTel span output, use the in-memory span exporter from `opentelemetry-stdout`:

```rust
use opentelemetry_sdk::testing::trace::TestSpan;

#[test]
fn test_session_span_sets_session_id_attribute() {
    // Use the in-memory testing tracer
    let (tracer, exporter) = create_test_tracer();
    let span = create_session_span(&tracer, "sess_abc", "claude-sonnet-4-6");
    span.end();

    let exported = exporter.get_finished_spans().unwrap();
    assert_eq!(exported.len(), 1);

    let attrs = &exported[0].attributes;
    assert!(attrs.iter().any(|kv| {
        kv.key.as_str() == "claude.session.id" && kv.value.as_str() == "sess_abc"
    }));
}
```

### Testing Cost Security (No Content Capture)

```rust
#[test]
fn test_turn_span_does_not_capture_content_when_disabled() {
    let config = Config { capture_content: false, ..Default::default() };
    let (tracer, exporter) = create_test_tracer();
    let span = create_turn_span(&tracer, &config, "This is sensitive input text");
    span.end();

    let exported = exporter.get_finished_spans().unwrap();
    let attrs = &exported[0].attributes;
    // Verify content attributes are NOT present
    assert!(!attrs.iter().any(|kv| kv.key.as_str() == "claude.turn.input_text"));
    assert!(!attrs.iter().any(|kv| kv.key.as_str() == "claude.turn.output_text"));
}
```

### Property-Based Tests with `proptest`

For functions with wide input domains (string sanitization, token counting, cost calculation):

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn test_truncate_attribute_never_panics(s in ".*", max_len in 0usize..10_000) {
        let result = truncate_attribute(&s, max_len);
        prop_assert!(result.len() <= max_len);
        prop_assert!(std::str::from_utf8(result.as_bytes()).is_ok()); // Valid UTF-8
    }

    #[test]
    fn test_cost_is_always_non_negative(
        input in 0u64..1_000_000_000,
        output in 0u64..1_000_000_000,
        cache_r in 0u64..1_000_000_000,
        cache_w in 0u64..1_000_000_000,
    ) {
        let calc = get_calculator();
        let result = calc.calculate("claude-sonnet-4-6", input, output, cache_r, cache_w).unwrap();
        prop_assert!(result.total_usd >= 0.0);
    }
}
```
