"""CLI entry point for Claude Code hook events.

Usage (in hooks.json):
    {"type": "command", "command": "python -m claude_trace.hooks pre"}
    {"type": "command", "command": "python -m claude_trace.hooks post"}

Each invocation:
  1. Reads one JSON object from stdin (Claude Code hook event payload).
  2. Dispatches to ``pre_hook`` or ``post_hook`` in ``_hooks.py``.
  3. Writes the response JSON to stdout.
  4. Exits 0 on success; exits 1 on unrecoverable parse errors.

The hook commands must never crash with an unhandled exception — Claude Code
treats a non-zero exit or unreadable stdout as a hook failure, which blocks
tool execution. All errors are logged to stderr and we return ``{}`` as a
safe default.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] not in ("pre", "post"):
        print(
            "Usage: python -m claude_trace.hooks [pre|post]",
            file=sys.stderr,
        )
        return 1

    mode = argv[0]

    # Read event from stdin
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"claude-trace hooks: invalid JSON on stdin: {exc}", file=sys.stderr)
        # Return safe empty response — never block Claude Code
        print("{}", flush=True)
        return 0

    try:
        from claude_trace._hooks import post_hook, pre_hook

        if mode == "pre":
            response = pre_hook(event)
        else:
            response = post_hook(event)
    except Exception as exc:  # noqa: BLE001 — hook must never crash Claude Code
        print(f"claude-trace hooks: {mode}_hook raised: {exc}", file=sys.stderr)
        response = {}

    print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
