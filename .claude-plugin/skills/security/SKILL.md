# Security Audit Skill — Comprehensive Security Review

<!--
skill:
  name: security
  description: Run a full security audit of the claude-trace codebase. Checks for span content leakage, API key capture, unsafe Rust without SAFETY comments, dependency vulnerabilities, hardcoded secrets, truncation coverage, and test coverage gate.
  disable-model-invocation: true
  allowed-tools: Bash, Read, Grep
  triggers:
    - "security audit"
    - "security review"
    - "check for leaks"
    - "audit dependencies"
    - "check unsafe"
-->

## Purpose and Scope

This skill runs a **non-interactive security audit** of the claude-trace codebase. It has `disable-model-invocation: true` because:

1. Security audits must be repeatable and deterministic
2. Every finding must reference specific file:line locations
3. The audit must not be "helped" by Claude reasoning around potential issues

All tools used are read-only (`Bash` with grep/search commands, `Read`, `Grep`). This audit never modifies files.

---

## Audit Execution Order

Run each check in sequence. Record PASS / FAIL / WARN for each. At the end, produce the structured report.

---

## Check 1: Span Content Security

**Question**: Is there any code that sets `claude.turn.input_text` or `claude.turn.output_text` attributes (or any attribute containing raw LLM content) without checking `config.capture_content`?

```bash
# Find all span attribute setting that references input/output text
grep -rn "input_text\|output_text\|turn\.input\|turn\.output\|prompt\|response" \
  src/ \
  --include="*.rs" \
  -l

# Then for each file found, check if the setting is gated on capture_content
grep -n "capture_content\|set_attribute.*input\|set_attribute.*output" \
  src/spans/turn.rs
```

**PASS** criteria: Every occurrence of `set_attribute` with content-like attribute names is inside an `if self.config.capture_content { ... }` or `if config.capture_content { ... }` block.

**FAIL** criteria: Any `set_attribute` call with a content attribute is NOT gated on `capture_content`.

**WARN** criteria: A function that takes content as a parameter but the gating happens at the call site (fragile — gating should be in the lowest-level function that knows about config).

---

## Check 2: API Key Leakage

**Question**: Is there any code that could log or set span attributes containing HTTP Authorization headers or API keys?

```bash
# Check for any code handling headers without redaction
grep -rn "authorization\|x-api-key\|api.key\|api_key\|Authorization" \
  src/ \
  --include="*.rs"

# Check that the redact_api_keys function exists and is called
grep -rn "redact_api_keys\|sk-ant-\|REDACTED" \
  src/ \
  --include="*.rs"

# Check for any HTTP header logging
grep -rn "set_attribute.*header\|header.*attribute\|log.*header" \
  src/ \
  --include="*.rs"
```

**PASS** criteria:
- All code that accesses headers calls `sanitize_header()` before setting span attributes
- `redact_api_keys()` function exists in `src/config/mod.rs`
- No occurrence of `"sk-ant-"` as a literal value (except in test files asserting it's redacted)

**FAIL** criteria:
- Any header value set as a span attribute without going through `sanitize_header()`
- `"authorization"` or `"x-api-key"` set as span attribute values

---

## Check 3: Unsafe Rust Audit

**Question**: Do all `unsafe` blocks have the required three-line SAFETY/INVARIANT/REVIEWED comment?

```bash
# Find all unsafe blocks
grep -rn "unsafe {" src/ --include="*.rs"

# For each unsafe block found, check the preceding 3 lines
# (manual inspection required for each hit)
grep -rn -B 3 "unsafe {" src/ --include="*.rs"
```

**PASS** criteria: Zero `unsafe` blocks exist. (This is the expected state for this project.)

**FAIL** criteria: Any `unsafe` block exists without all three lines:
- `// SAFETY: <justification>`
- `// INVARIANT: <what must be true>`
- `// REVIEWED: <github-username> on YYYY-MM-DD — see PR #NNN`

**WARN** criteria: An `unsafe` block exists but has the required comments. Document it and note it needs future review.

---

## Check 4: Dependency Audit

**Question**: Are there known vulnerabilities in our Rust, Python, or JavaScript dependencies?

```bash
# Rust dependencies
cargo audit 2>&1
# Expected output: "No vulnerable packages found"

# Python dependencies
pip-audit 2>&1
# Expected output: "No known vulnerabilities found"

# JavaScript/TypeScript dependencies
npm audit --prefix typescript 2>&1
# Expected output: "found 0 vulnerabilities"
```

**PASS** criteria: All three audits report zero vulnerabilities.

**FAIL** criteria: Any CRITICAL or HIGH severity vulnerability in any dependency. These must be fixed before release.

**WARN** criteria: MEDIUM or LOW severity vulnerabilities. Document them with the CVE number and reasoning for why they are acceptable (if they are).

---

## Check 5: Hardcoded Secrets

**Question**: Are there any hardcoded API keys, tokens, or secrets in the source code?

```bash
# Search for Anthropic API key patterns
grep -rn "sk-ant-" \
  src/ python/ typescript/ \
  --include="*.rs" \
  --include="*.py" \
  --include="*.ts" \
  --include="*.js"

# EXCEPTION: test files asserting redaction are allowed
# These should match the pattern: assert!(...contains("[REDACTED]"))

# Search for other common secret patterns
grep -rn \
  -e "password\s*=\s*['\"][^'\"]\+['\"]" \
  -e "token\s*=\s*['\"][^'\"]\+['\"]" \
  -e "secret\s*=\s*['\"][^'\"]\+['\"]" \
  src/ python/ typescript/ \
  --include="*.rs" \
  --include="*.py" \
  --include="*.ts"
```

**PASS** criteria: No `sk-ant-` values found except in test files that assert they are redacted. No credential assignments found.

**FAIL** criteria: Any live-looking API key or secret found anywhere in source.

---

## Check 6: Attribute Truncation Coverage

**Question**: Do all `set_attribute` calls for string values go through the `truncate_attribute` function?

```bash
# Find all set_attribute calls with string values
grep -rn "set_attribute(KeyValue::new" src/ --include="*.rs"

# Check how many go through truncate_attribute
grep -rn "truncate_attribute" src/ --include="*.rs"

# Find set_attribute calls that do NOT go through truncation
# (look for string literals or variables passed directly without truncation)
grep -n "KeyValue::new.*,\s*[a-z_]*\s*)" src/spans/ --include="*.rs"
```

**PASS** criteria: Every `set_attribute` call that sets a string value calls `truncate_attribute(value, &config)` (or a wrapper that does).

**Exceptions** (don't fail these):
- Integer attributes (e.g., `KeyValue::new("claude.turn.index", 0u64)`)
- Boolean attributes
- Attributes from the semconv constants (which are string literals, not values)

**FAIL** criteria: Any string value attribute set without truncation.

---

## Check 7: Test Coverage Gate

**Question**: Is test coverage at or above 85%?

```bash
# Check if cargo-llvm-cov is available
cargo llvm-cov --version 2>/dev/null && \
  cargo llvm-cov --summary-only 2>&1 | grep -E "TOTAL|Lines|Functions" || \
  echo "cargo-llvm-cov not installed; trying tarpaulin"

# Fallback: cargo-tarpaulin
cargo tarpaulin --out Stdout 2>&1 | tail -5
```

**PASS** criteria: Line coverage ≥ 85.0%

**FAIL** criteria: Line coverage < 85.0%

If coverage is failing, identify the uncovered public functions:
```bash
cargo llvm-cov --html
# Open target/llvm-cov/html/index.html and look for red lines in public functions
```

---

## Check 8: Config Default Verification

**Question**: Does `Config::default()` have `capture_content = false`?

```bash
grep -A 10 "impl Default for Config" src/config/mod.rs
```

**PASS** criteria: The `Default` implementation has `capture_content: false`.

**FAIL** criteria: `capture_content: true` in the default. This would silently capture all prompt/response content in production, which is a PII risk.

---

## Structured Security Report Output

After running all checks, produce this report:

```
=== claude-trace Security Audit ===
Date: YYYY-MM-DD HH:MM UTC
Commit: <git rev-parse HEAD>
Auditor: claude-code security skill

CHECK 1: Span Content Security ............... PASS / FAIL / WARN
  Details: <findings or "No issues found">

CHECK 2: API Key Leakage ..................... PASS / FAIL / WARN
  Details: <findings>

CHECK 3: Unsafe Rust Audit ................... PASS / FAIL / WARN
  Details: <findings or "No unsafe blocks found (PASS)">

CHECK 4: Dependency Audit .................... PASS / FAIL / WARN
  Rust:   PASS (0 vulnerabilities)
  Python: PASS (0 vulnerabilities)
  npm:    PASS (0 vulnerabilities)

CHECK 5: Hardcoded Secrets ................... PASS / FAIL / WARN
  Details: <findings>

CHECK 6: Attribute Truncation Coverage ....... PASS / FAIL / WARN
  Details: <findings>

CHECK 7: Test Coverage Gate .................. PASS / FAIL / WARN
  Current coverage: XX.X%
  Required:         85.0%

CHECK 8: Config Default Verification ......... PASS / FAIL / WARN
  capture_content default: false (PASS)

=== Summary ===
PASS: N checks
WARN: N checks
FAIL: N checks

CRITICAL FAILURES (block release):
  - <list any FAIL items>

WARNINGS (investigate before release):
  - <list any WARN items>
```

---

## Severity Definitions

| Level | Meaning | Release Blocker? |
|---|---|---|
| CRITICAL | Hardcoded secret, API key in spans, unsafe without SAFETY comment | YES — fix immediately |
| HIGH | Dependency with known CVE (CRITICAL/HIGH severity), content captured by default | YES |
| MEDIUM | Dependency with known CVE (MEDIUM severity), coverage below 85% | Strongly recommended to fix |
| LOW | Dependency with LOW severity CVE, WARN in truncation coverage | Document and schedule fix |
| INFO | Observation that warrants attention but has no security impact | No |

---

## When to Run This Audit

Run this skill before:
1. Every release (required — see `skills/release/SKILL.md`)
2. Any PR that touches `src/spans/`, `src/config/mod.rs`, or `src/semconv/`
3. Any dependency version bump
4. Any change to the `Config` struct defaults

The `security-audit.yml` GitHub Actions workflow runs checks 4 (cargo audit, pip-audit, npm audit) automatically on a weekly schedule and on every PR.
