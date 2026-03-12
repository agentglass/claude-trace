#!/usr/bin/env bash
# coverage-gate.sh — Enforce 85% minimum test coverage for the Rust codebase.
#
# Triggered by: PostToolUse Bash(cargo test*) hook in hooks.json
# Exit codes:
#   0 — coverage at or above 85%
#   2 — coverage below 85% (blocks the workflow)
#
# Requires one of:
#   - cargo-llvm-cov (preferred): cargo install cargo-llvm-cov
#   - cargo-tarpaulin (fallback):  cargo install cargo-tarpaulin

set -euo pipefail

REQUIRED_COVERAGE=85
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# ─── Check cargo is available ─────────────────────────────────────────────────

if ! command -v cargo &>/dev/null; then
  echo "⚠️  cargo not found — skipping coverage check."
  exit 0
fi

cd "${PROJECT_ROOT}"

# ─── Try cargo-llvm-cov first ─────────────────────────────────────────────────

if cargo llvm-cov --version &>/dev/null 2>&1; then
  echo "📊 Running coverage check with cargo-llvm-cov..."
  echo ""

  # Run coverage and capture output
  # --summary-only: no per-file breakdown, just totals (faster)
  # --all-features: test all features
  COVERAGE_OUTPUT=$(
    cargo llvm-cov \
      --all-features \
      --summary-only \
      2>&1
  ) || COV_EXIT=$?
  COV_EXIT="${COV_EXIT:-0}"

  if [[ "${COV_EXIT}" -ne 0 ]]; then
    echo "❌ cargo-llvm-cov failed to run:"
    echo "${COVERAGE_OUTPUT}"
    echo ""
    echo "Try: cargo llvm-cov clean && cargo llvm-cov --all-features --summary-only"
    exit 2
  fi

  # Extract the TOTAL line coverage percentage
  # cargo-llvm-cov output format: "TOTAL  Lines: NNN/NNN (XX.XX%)"
  COVERAGE_PCT=$(
    echo "${COVERAGE_OUTPUT}" \
    | grep -E "^TOTAL" \
    | grep -oE "[0-9]+\.[0-9]+%" \
    | head -1 \
    | tr -d '%'
  )

  if [[ -z "${COVERAGE_PCT}" ]]; then
    # Try alternative format parsing
    COVERAGE_PCT=$(
      echo "${COVERAGE_OUTPUT}" \
      | grep -iE "lines.*[0-9]+\.[0-9]+%" \
      | grep -oE "[0-9]+\.[0-9]+" \
      | tail -1
    )
  fi

# ─── Fallback to cargo-tarpaulin ──────────────────────────────────────────────

elif cargo tarpaulin --version &>/dev/null 2>&1; then
  echo "📊 Running coverage check with cargo-tarpaulin..."
  echo "   (cargo-llvm-cov not found; install it for faster coverage: cargo install cargo-llvm-cov)"
  echo ""

  COVERAGE_OUTPUT=$(
    cargo tarpaulin \
      --all-features \
      --out Stdout \
      --skip-clean \
      2>&1
  ) || COV_EXIT=$?
  COV_EXIT="${COV_EXIT:-0}"

  if [[ "${COV_EXIT}" -ne 0 ]]; then
    echo "❌ cargo-tarpaulin failed to run:"
    echo "${COVERAGE_OUTPUT}"
    exit 2
  fi

  # Tarpaulin output format: "XX.XX% coverage, NNN/NNN lines covered"
  COVERAGE_PCT=$(
    echo "${COVERAGE_OUTPUT}" \
    | grep -oE "[0-9]+\.[0-9]+% coverage" \
    | grep -oE "[0-9]+\.[0-9]+" \
    | head -1
  )

# ─── Neither tool available ───────────────────────────────────────────────────

else
  echo "⚠️  Neither cargo-llvm-cov nor cargo-tarpaulin is installed."
  echo ""
  echo "   To enable the coverage gate, install one of:"
  echo "     cargo install cargo-llvm-cov  (faster, recommended)"
  echo "     cargo install cargo-tarpaulin  (alternative)"
  echo ""
  echo "   Skipping coverage check for now."
  exit 0
fi

# ─── Evaluate coverage percentage ─────────────────────────────────────────────

if [[ -z "${COVERAGE_PCT}" ]]; then
  echo "⚠️  Could not parse coverage percentage from output."
  echo "   Raw output:"
  echo "${COVERAGE_OUTPUT}" | tail -10
  echo ""
  echo "   Skipping coverage gate (could not determine percentage)."
  exit 0
fi

# Use awk for floating-point comparison (bash can only do integers)
PASSED=$(awk -v actual="${COVERAGE_PCT}" -v required="${REQUIRED_COVERAGE}" \
  'BEGIN { print (actual >= required) ? "yes" : "no" }')

echo "Coverage: ${COVERAGE_PCT}% (required: ${REQUIRED_COVERAGE}%)"
echo ""

if [[ "${PASSED}" == "yes" ]]; then
  echo "✅ Coverage gate PASSED — ${COVERAGE_PCT}% >= ${REQUIRED_COVERAGE}%"
  exit 0
else
  echo "❌ Coverage gate FAILED"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "COVERAGE TOO LOW: ${COVERAGE_PCT}% (minimum: ${REQUIRED_COVERAGE}%)"
  echo ""
  echo "Every public function must have at least one test."
  echo "See skills/test/SKILL.md for the TDD workflow."
  echo ""
  echo "To find uncovered lines:"
  echo "  cargo llvm-cov --html && open target/llvm-cov/html/index.html"
  echo "  (or: cargo tarpaulin --all-features --out Html)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 2
fi
