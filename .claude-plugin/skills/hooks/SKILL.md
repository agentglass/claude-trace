---
name: hooks
description: >
  Claude Code plugin hook development for claude-trace. Generates OTel spans
  automatically for every tool Claude Code executes inside a session.
version: 0.1.0
author: agentglass
tags: [hooks, otel, claude-code, observability]
---

# claude-trace Hooks Skill

You are implementing or extending the **Milestone 5 hook system** for claude-trace.

## Architecture

```
Claude Code session
  │
  ├─ PreToolUse  ──→ python -m claude_trace.hooks pre
  │                    writes /tmp/claude-trace/{session_id}/{tool_name}.json
  │                    {trace_id, span_id, start_ns, start_epoch_ns, input_hash}
  │
  ├─ [Tool executes]
  │
  └─ PostToolUse ──→ python -m claude_trace.hooks post
                       reads state file, calculates duration
                       exports claude.tool.invocation span via OTLP HTTP
                       deletes state file
```

## Span Schema

| Attribute | Type | Description |
|---|---|---|
| `claude.tool.name` | string | Tool name (Write, Bash, Read, …) |
| `claude.tool.input_hash` | string | SHA-256[:16] of JSON-encoded input |
| `claude.tool.output_hash` | string | SHA-256[:16] of tool response |
| `claude.tool.duration_ms` | float | Wall-clock duration in milliseconds |
| `claude.tool.outcome` | string | "success" or error message (truncated) |
| `claude.tool.session_id` | string | Claude Code session ID |
| `claude.tool.hook_source` | string | Always "claude_code_plugin" |
| `claude.tool.plugin_version` | string | Plugin version string |

## Security Rules

**MANDATORY** for any change to `_hooks.py` or `_hooks_cli.py`:

1. **Never store raw tool inputs** — only the SHA-256[:16] hash.
2. **Never store raw tool outputs** — only the SHA-256[:16] hash.
3. **Redact API keys** — `sk-ant-*` patterns must be stripped before any storage.
4. **State files** must be written with mode `0o600` (owner-read-write only).
5. **Hook processes must never crash** — all exceptions caught, logged to stderr, `{}` returned.
6. **No blocking** — hooks return `{}` (allow) by default; only the semconv pre-hook can block.
7. **OTLP timeouts** — HTTP export uses a 3-second timeout; failure is silent (logged to stderr).

## State File Format

```json
{
  "trace_id": "32 hex chars (128-bit W3C)",
  "span_id":  "16 hex chars (64-bit W3C)",
  "session_id": "claude-code-session-id",
  "tool_name": "Write",
  "input_hash": "sha256[:16] of tool_input",
  "start_ns": 1234567890000000000,
  "start_epoch_ns": 1234567890000000000,
  "parent_span_id": "",
  "parent_trace_id": "",
  "plugin_version": "0.1.0"
}
```

State directory: `$CLAUDE_TRACE_STATE_DIR` (default `/tmp/claude-trace/`)
State path: `{state_dir}/{session_id[:64]}/{tool_name[:64]}.json`

## OTLP Export

Format: OTLP/HTTP JSON (`application/json`)
Endpoint: `$OTEL_EXPORTER_OTLP_ENDPOINT/v1/traces` (default `http://localhost:4318/v1/traces`)
Timeout: 3 seconds (non-blocking, fire-and-forget)
Fallback: NDJSON log to `$CLAUDE_TRACE_HOOKS_LOG` (if set)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTLP collector base URL |
| `CLAUDE_TRACE_STATE_DIR` | `/tmp/claude-trace` | Hook state directory |
| `CLAUDE_TRACE_HOOKS_LOG` | (empty) | NDJSON fallback log path |
| `CLAUDE_TRACE_MAX_ATTR_LENGTH` | `512` | Max chars per span attribute |
| `CLAUDE_TRACE_SANITIZE` | `false` | Strip all text attributes |

## TDD Rules

**MANDATORY**: Before any implementation change, write a failing test.

Tests live in: `python/tests/test_hooks.py`
Run: `pytest python/tests/test_hooks.py -v`

## Extending the Hook System

### Adding new attributes to hook spans

1. Add the attribute to `_build_otlp_payload()` in `_hooks.py`
2. Add it to `src/semconv.rs` with name `claude.tool.*` (additive only)
3. Write a test verifying the attribute appears in the OTLP payload
4. Update the span schema table above and in the docs page

### Adding a new hook event type

1. Add handler in `_hooks.py` following the pre/post pattern
2. Add CLI dispatch in `_hooks_cli.py`
3. Register in `.claude-plugin/hooks/hooks.json`
4. Write tests with `capsys` to verify stdout JSON output
5. Document in `site/src/content/docs/guides/claude-code-hooks.mdx`

## Testing the Hooks Without a Live Collector

```bash
# Start a simple OTLP receiver
CLAUDE_TRACE_HOOKS_LOG=/tmp/hook-spans.ndjson \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  python -m claude_trace.hooks pre <<'EOF'
{"session_id": "test-123", "tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}}
EOF

# View the fallback log
cat /tmp/hook-spans.ndjson | python -m json.tool
```
