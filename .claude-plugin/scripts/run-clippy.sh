#!/usr/bin/env bash
# run-clippy.sh — Run cargo clippy on the project when a .rs file is modified.
#
# Triggered by: PostToolUse Write|Edit hook in hooks.json
# Exit codes:
#   0 — success (no .rs file changed, or clippy passed)
#   2 — clippy failed with warnings/errors (blocks the workflow)
#
# Environment variables expected:
#   CLAUDE_TOOL_INPUT_PATH or CLAUDE_FILE_PATH — the file that was just written/edited

set -euo pipefail

# ─── Determine which file was modified ────────────────────────────────────────

# Claude Code provides the modified file path in different variables depending on context.
# Try each in order of likelihood.
MODIFIED_FILE="${CLAUDE_TOOL_INPUT_PATH:-${CLAUDE_FILE_PATH:-${1:-}}}"

if [[ -z "${MODIFIED_FILE}" ]]; then
  # No file path available — skip silently (not a file operation we care about)
  exit 0
fi

# ─── Check if the modified file is a Rust source file ─────────────────────────

if [[ "${MODIFIED_FILE}" != *.rs ]]; then
  # Not a Rust file — nothing to check
  exit 0
fi

echo "🦀 claude-trace clippy hook triggered by: ${MODIFIED_FILE}"
echo "   Running cargo clippy --all-targets -- -D warnings -D clippy::pedantic"
echo ""

# ─── Check cargo is available ─────────────────────────────────────────────────

if ! command -v cargo &>/dev/null; then
  echo "⚠️  cargo not found in PATH — skipping clippy check."
  echo "   Install Rust from https://rustup.rs to enable automatic linting."
  exit 0
fi

# ─── Find the project root (directory containing Cargo.toml) ──────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

if [[ ! -f "${PROJECT_ROOT}/Cargo.toml" ]]; then
  echo "⚠️  Could not find Cargo.toml in ${PROJECT_ROOT} — skipping clippy."
  exit 0
fi

# ─── Run clippy ───────────────────────────────────────────────────────────────

cd "${PROJECT_ROOT}"

# Run clippy with pedantic mode — same flags as CI
# --message-format=short: compact output for hook context
CLIPPY_OUTPUT=$(
  cargo clippy \
    --all-targets \
    --all-features \
    --message-format=short \
    -- \
    -D warnings \
    -D clippy::pedantic \
    -A clippy::module_name_repetitions \
    2>&1
) || CLIPPY_EXIT=$?

CLIPPY_EXIT="${CLIPPY_EXIT:-0}"

if [[ "${CLIPPY_EXIT}" -ne 0 ]]; then
  echo "❌ clippy FAILED — ${MODIFIED_FILE}"
  echo ""
  echo "${CLIPPY_OUTPUT}"
  echo ""
  echo "Fix the clippy warnings above before proceeding."
  echo "All warnings are treated as errors (#![deny(clippy::pedantic)] in lib.rs)."
  echo ""
  echo "Common fixes:"
  echo "  - Missing #[must_use]: add #[must_use] to the function"
  echo "  - Missing '# Errors' doc: add '# Errors' section to the /// comment"
  echo "  - unwrap() in lib: use .expect(\"invariant message\") or propagate with ?"
  echo "  - wildcard import: replace 'use foo::*' with explicit imports"
  exit 2
fi

echo "✅ clippy passed — ${MODIFIED_FILE}"
exit 0
