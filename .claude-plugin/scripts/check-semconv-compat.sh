#!/usr/bin/env bash
# check-semconv-compat.sh — Run the Python semconv compatibility checker.
#
# Checks that no existing claude.* attribute has been removed or renamed.
# Exits 2 if backwards compatibility is broken.
#
# Usage:
#   bash check-semconv-compat.sh           # check only
#   bash check-semconv-compat.sh --diff    # show what changed
#   bash check-semconv-compat.sh --update  # update baseline (requires approval)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

MODE="${1:-check}"

# ─── Verify Python is available ───────────────────────────────────────────────

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "❌ Python not found — cannot run semconv compatibility check."
  echo "   Install Python 3.11+ to enable semconv validation."
  exit 2
fi

PYTHON="${PYTHON:-$(command -v python3 || command -v python)}"

# ─── Check if the compat script exists ────────────────────────────────────────

COMPAT_SCRIPT="${PROJECT_ROOT}/scripts/check_semconv_compat.py"

if [[ ! -f "${COMPAT_SCRIPT}" ]]; then
  echo "⚠️  ${COMPAT_SCRIPT} not found."
  echo "   This script is created in Milestone 2. Skipping compatibility check."
  exit 0
fi

# ─── Run the checker ──────────────────────────────────────────────────────────

echo "🔍 Checking claude.* semconv backwards compatibility..."
echo "   Script: ${COMPAT_SCRIPT}"
echo ""

case "${MODE}" in
  "--diff")
    "${PYTHON}" "${COMPAT_SCRIPT}" --diff
    ;;
  "--update"|"--update-baseline")
    echo "⚠️  WARNING: You are about to update the semconv baseline."
    echo "   This operation should ONLY be performed after RFC approval."
    echo "   See skills/semconv/SKILL.md for the deprecation process."
    echo ""
    read -r -p "Have you received RFC approval? (yes/no): " CONFIRM
    if [[ "${CONFIRM}" != "yes" ]]; then
      echo "Aborted. Get RFC approval before updating the baseline."
      exit 1
    fi
    "${PYTHON}" "${COMPAT_SCRIPT}" --update-baseline
    echo "✅ Baseline updated. Commit the updated baseline file."
    ;;
  *)
    # Default: check only
    COMPAT_OUTPUT=$("${PYTHON}" "${COMPAT_SCRIPT}" 2>&1) || COMPAT_EXIT=$?
    COMPAT_EXIT="${COMPAT_EXIT:-0}"

    if [[ "${COMPAT_EXIT}" -ne 0 ]]; then
      echo "❌ Semconv compatibility check FAILED"
      echo ""
      echo "${COMPAT_OUTPUT}"
      echo ""
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo "BACKWARDS COMPATIBILITY VIOLATION DETECTED"
      echo ""
      echo "One or more claude.* attributes have been removed or renamed."
      echo "This is a BREAKING CHANGE that silently breaks user dashboards,"
      echo "alerts, and OTel queries."
      echo ""
      echo "The correct procedure is:"
      echo "  1. DO NOT remove or rename existing attributes"
      echo "  2. If the name was wrong, add the correct name as a NEW attribute"
      echo "  3. Mark the old name as @deprecated in src/semconv/claude.rs"
      echo "  4. See skills/semconv/SKILL.md for the full deprecation process"
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      exit 2
    fi

    echo "${COMPAT_OUTPUT}"
    echo "✅ Semconv compatibility check PASSED — no attributes removed or renamed."
    ;;
esac

exit 0
