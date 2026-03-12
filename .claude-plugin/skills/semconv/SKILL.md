# Semconv Skill — Semantic Convention Management

<!--
skill:
  name: semconv
  description: Manages claude.* semantic conventions. Enforces additive-only changes, naming patterns, category rules, type constraints, and backwards compatibility. Auto-invoked when working on semconv files.
  auto-invoke:
    - "src/semconv/**/*.rs"
    - "scripts/check_semconv_compat.py"
    - "site/src/data/semconv.json"
    - "*semconv*"
  triggers:
    - "add attribute"
    - "new semconv"
    - "semconv"
    - "span attribute"
    - "breaking change"
    - "rename attribute"
-->

## The Prime Directive: Only Additive Changes

`claude.*` attributes are part of the **public API contract** of claude-trace. Users build dashboards, alerts, and queries on top of these attribute names. A renamed or removed attribute silently breaks every customer's monitoring pipeline.

**The law**: You MAY add new `claude.*` attributes. You MAY NEVER remove or rename existing ones.

This is non-negotiable. It is enforced by:
1. This skill (informational)
2. The `PreToolUse` hook in `hooks/hooks.json` (automated blocking)
3. The `semconv-compat.yml` GitHub Actions workflow (CI blocking)
4. The `scripts/check_semconv_compat.py` script (the actual checker)

If you believe an existing attribute name was a mistake, the correct path is:
1. Mark it deprecated in `src/semconv/claude.rs` with a `@deprecated` comment
2. Add a new attribute with the correct name
3. Keep the old name working in code for at least 2 major versions
4. Open a GitHub issue with the label `semconv-deprecation`

---

## Naming Rules

Every new `claude.*` attribute name MUST match this pattern:

```
^claude\.[a-z]+\.[a-z_]+$
```

Breaking this down:
- `claude.` — mandatory prefix
- `[a-z]+` — category, one of: `session`, `turn`, `tool`, `cost`
- `.` — separator
- `[a-z_]+` — name using lowercase letters and underscores only

**Valid examples**:
- `claude.session.customer_id` ✓
- `claude.turn.time_to_first_token_ms` ✓
- `claude.tool.input_hash` ✓
- `claude.cost.cache_read_usd` ✓

**Invalid examples**:
- `claude.agent.session_id` — `agent` is not a valid category ✗
- `claude.session.customerId` — camelCase not allowed ✗
- `claude.SESSION.id` — uppercase not allowed ✗
- `claude.turn_latency_ms` — missing category segment ✗
- `session.id` — missing `claude.` prefix ✗

---

## Valid Categories

There are exactly **4 categories**: `session`, `turn`, `tool`, `cost`.

| Category | Span | Description |
|---|---|---|
| `session` | `claude.agent.session` | Root span for one full agent.run() call |
| `turn` | `claude.agent.turn` | One complete LLM API call (request → response) |
| `tool` | `claude.tool.invocation` | One tool execution (call → result) |
| `cost` | session and turn spans | Financial cost breakdown |

**Adding a new category requires an RFC.** File a GitHub issue with the label `semconv-rfc` and get approval from `@agentglass/maintainers` before adding any attributes in a new category.

---

## Valid Types

Only these types are allowed for `claude.*` attributes:

| Type | OTel Type | Example Value |
|---|---|---|
| `string` | `AttributeValue::String` | `"claude-sonnet-4-6"` |
| `int` | `AttributeValue::I64` | `42` |
| `float` | `AttributeValue::F64` | `3.14` |
| `bool` | `AttributeValue::Bool` | `true` |
| `string[]` | `AttributeValue::Array(StringArray(...))` | `["bash", "read_file"]` |

**Note on float storage**: Monetary values (`claude.cost.*`) are stored as `string` (not `float`) to avoid IEEE 754 precision loss in OTel backends that deserialize and re-serialize values. The `CostAttributes` fields are typed as strings in the constant definitions but their documentation says "stored as string for OTel compatibility."

---

## Complete Existing Attribute List

This is the authoritative list of all `claude.*` attributes that exist as of the initial release. **These must never be removed or renamed.**

### Session Attributes

| Attribute | Type | Status |
|---|---|---|
| `claude.session.id` | string | stable |
| `claude.session.system_prompt_hash` | string | stable |
| `claude.session.system_prompt_length` | int | stable |
| `claude.session.model` | string | stable |
| `claude.session.max_turns` | int | stable |
| `claude.session.total_turns` | int | stable |
| `claude.session.status` | string | stable |
| `claude.session.customer_id` | string | stable |
| `claude.session.tags` | string | stable |
| `claude.session.total_input_tokens` | int | stable |
| `claude.session.total_output_tokens` | int | stable |
| `claude.session.total_cache_read_tokens` | int | stable |
| `claude.session.total_cache_creation_tokens` | int | stable |
| `claude.session.total_cost_usd` | string | stable |
| `claude.session.tool_names` | string | stable |
| `claude.session.total_tool_calls` | int | stable |

### Turn Attributes

| Attribute | Type | Status |
|---|---|---|
| `claude.turn.index` | int | stable |
| `claude.turn.model` | string | stable |
| `claude.turn.stop_reason` | string | stable |
| `claude.turn.input_tokens` | int | stable |
| `claude.turn.output_tokens` | int | stable |
| `claude.turn.cache_read_tokens` | int | stable |
| `claude.turn.cache_creation_tokens` | int | stable |
| `claude.turn.tool_use_count` | int | stable |
| `claude.turn.tool_names` | string | stable |
| `claude.turn.content_block_types` | string | stable |
| `claude.turn.text_content_length` | int | stable |
| `claude.turn.is_streaming` | bool | stable |
| `claude.turn.request_id` | string | stable |
| `claude.turn.latency_ms` | float | stable |
| `claude.turn.time_to_first_token_ms` | float | stable |
| `claude.turn.error_type` | string | stable |
| `claude.turn.error_message` | string | stable |
| `claude.turn.cost_usd` | string | stable |

### Tool Attributes

| Attribute | Type | Status |
|---|---|---|
| `claude.tool.use_id` | string | stable |
| `claude.tool.name` | string | stable |
| `claude.tool.turn_index` | int | stable |
| `claude.tool.call_index` | int | stable |
| `claude.tool.input_hash` | string | stable |
| `claude.tool.input_size_bytes` | int | stable |
| `claude.tool.output_size_bytes` | int | stable |
| `claude.tool.status` | string | stable |
| `claude.tool.error_type` | string | stable |
| `claude.tool.error_message` | string | stable |
| `claude.tool.latency_ms` | float | stable |
| `claude.tool.is_parallel` | bool | stable |

### Cost Attributes

| Attribute | Type | Status |
|---|---|---|
| `claude.cost.input_usd` | string | stable |
| `claude.cost.output_usd` | string | stable |
| `claude.cost.cache_read_usd` | string | stable |
| `claude.cost.cache_creation_usd` | string | stable |
| `claude.cost.total_usd` | string | stable |
| `claude.cost.model` | string | stable |
| `claude.cost.pricing_tier` | string | stable |

---

## Backwards Compatibility Checker

The script `scripts/check_semconv_compat.py` checks that the current `src/semconv/claude.rs` does not remove or rename any attribute from the baseline.

### Running the Checker

```bash
# Check compatibility (run after every semconv change)
python scripts/check_semconv_compat.py
# Expected output: "Semconv compatibility check PASSED — no attributes removed or renamed."

# Show what would change (dry run)
python scripts/check_semconv_compat.py --diff

# Update the baseline (ONLY after RFC approval — see below)
python scripts/check_semconv_compat.py --update-baseline
```

### When to Update the Baseline

**NEVER update the baseline without RFC approval.**

The baseline update workflow:
1. File a GitHub issue: `semconv: deprecate claude.XXX.YYY`
2. Wait for approval from `@agentglass/maintainers`
3. Add the deprecation notice to `src/semconv/claude.rs` (do NOT remove the constant)
4. Add the replacement attribute
5. Wait for the next major version
6. ONLY THEN run `--update-baseline` to remove the deprecated attribute from the baseline

---

## How to Add a New Attribute: Complete Checklist

1. **Verify the name** matches `^claude\.[a-z]+\.[a-z_]+$`
2. **Verify the category** is one of `session`, `turn`, `tool`, `cost`
3. **Verify the type** is one of `string`, `int`, `float`, `bool`, `string[]`

4. **Add to `src/semconv/claude.rs`**:
   ```rust
   // In the appropriate *Attributes struct:
   NEW_ATTR_NAME: str = "claude.session.new_attr_name"
   """One-line description.

   Detailed explanation of semantics and when this is set.
   Type: <type>
   Example: <example value>
   """
   ```

5. **Add to `site/src/data/semconv.json`**:
   ```json
   {
     "attribute": "claude.session.new_attr_name",
     "category": "session",
     "type": "string",
     "description": "One-line description.",
     "example": "example_value",
     "addedVersion": "0.X.0"
   }
   ```

6. **Add setting code** in the appropriate span file:
   - Session attributes → `src/spans/session.rs`
   - Turn attributes → `src/spans/turn.rs`
   - Tool attributes → `src/spans/tool.rs`

7. **Add a test** asserting the attribute is present in the span:
   ```rust
   #[test]
   fn test_session_span_sets_new_attr_name() {
       let (tracer, exporter) = create_test_tracer();
       let span = create_session_span(&tracer, "sess_test", "claude-sonnet-4-6");
       span.set_new_attr("expected_value");
       span.end();
       let attrs = get_exported_attributes(&exporter);
       assert!(attrs.get("claude.session.new_attr_name") == Some("expected_value"));
   }
   ```

8. **Run the compat checker**: `python scripts/check_semconv_compat.py`
   - New attributes always PASS (they aren't in the baseline yet, so removing them isn't a break)

9. **Commit with the message format**: `feat(semconv): add claude.<category>.<name> — <why>`

---

## Deprecation Process

When an attribute needs to be deprecated (not removed yet):

1. Add a deprecation comment to the constant in `src/semconv/claude.rs`:
   ```rust
   /// @deprecated since 0.5.0 — use `claude.session.customer_id` instead.
   /// This attribute will be removed in 2.0.0.
   TENANT_ID: str = "claude.session.tenant_id"
   ```

2. Update `site/src/data/semconv.json`:
   ```json
   {
     "attribute": "claude.session.tenant_id",
     "category": "session",
     "type": "string",
     "description": "Deprecated. Use claude.session.customer_id instead.",
     "example": "acme_corp",
     "addedVersion": "0.1.0",
     "deprecated": "0.5.0"
   }
   ```

3. The constant continues to exist and work in code until the next major version.
4. File a GitHub issue labeled `semconv-deprecation` with the removal target version.
