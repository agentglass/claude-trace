# claude-trace Roadmap

**Zero-configuration OpenTelemetry observability for Claude Agent SDK.**

This roadmap tracks the development milestones for claude-trace from initial plugin infrastructure to a stable, production-ready v1.0.0 release.

---

## Milestone 1 — Plugin + Skills Infrastructure (Current)

**Status**: In progress
**Goal**: Establish the developer tooling foundation that all future contributions will rely on.

### Deliverables

- [x] `.claude-plugin/plugin.json` — Plugin manifest
- [x] `skills/scaffold/SKILL.md` — Project bootstrap skill
- [x] `skills/rust/SKILL.md` — Rust conventions and expert context
- [x] `skills/test/SKILL.md` — TDD workflow enforcer (Red → Green → Refactor)
- [x] `skills/backend/SKILL.md` — Core Rust library development context
- [x] `skills/python-bindings/SKILL.md` — PyO3 + maturin expert context
- [x] `skills/ts-bindings/SKILL.md` — wasm-bindgen + TypeScript expert context
- [x] `skills/ui/SKILL.md` — Starlight/Astro docs site expert context
- [x] `skills/security/SKILL.md` — Security audit skill
- [x] `skills/semconv/SKILL.md` — Semantic convention management
- [x] `skills/release/SKILL.md` — Release workflow (11-step process)
- [x] `skills/deploy/SKILL.md` — Docs and marketplace deployment
- [x] `agents/rust-reviewer.md` — Rust code review agent (Opus, cyan)
- [x] `agents/security-auditor.md` — Security review agent (Opus, red)
- [x] `agents/docs-writer.md` — Documentation writing agent (Sonnet, green)
- [x] `hooks/hooks.json` — Clippy, coverage gate, and semconv guard hooks
- [x] `scripts/run-clippy.sh` — Auto-clippy on .rs file edit
- [x] `scripts/check-semconv-compat.sh` — Semconv backwards compat checker
- [x] `scripts/coverage-gate.sh` — 85% coverage enforcement
- [x] `.github/workflows/ci.yml` — Full CI matrix
- [x] `.github/workflows/security-audit.yml` — Weekly security audit
- [x] `.github/CODEOWNERS` — Code ownership for critical paths

### Acceptance Criteria

- [ ] All 11 skills are loadable by Claude Code plugin manager
- [ ] `hooks.json` is valid JSON and hooks fire correctly
- [ ] All 3 scripts are executable and return correct exit codes
- [ ] CI workflow passes on the main branch
- [ ] A new contributor can follow `skills/scaffold/SKILL.md` to bootstrap the project

---

## Milestone 2 — Rust Core + Python Bindings

**Status**: Planned
**Goal**: Working Rust library with full span hierarchy, semconv attributes, cost calculator, and Python bindings that instrument the Anthropic SDK.

### Deliverables

- [ ] `src/spans/session.rs` — `SessionSpan` with all semconv attributes
- [ ] `src/spans/turn.rs` — `TurnSpan` with token tracking and cost calculation
- [ ] `src/spans/tool.rs` — `ToolSpan` with input/output hashing
- [ ] `src/semconv/claude.rs` — All 47 `claude.*` attribute constants
- [ ] `src/cost/models.rs` — Complete pricing table (17 models, 2026-Q1)
- [ ] `src/cost/calculator.rs` — `CostCalculator` with cache pricing
- [ ] `src/config/mod.rs` — `Config` struct with security defaults
- [ ] `src/python_bindings/` — PyO3 wrappers for session, turn, tool, cost
- [ ] `python/claude_trace/__init__.py` — Public API: `instrument()`, `session()`
- [ ] `python/claude_trace/_instrumentation/` — Anthropic SDK monkey-patching
- [ ] `python/claude_trace/_claude_trace.pyi` — Type stubs
- [ ] Test coverage ≥ 85%
- [ ] `scripts/check_semconv_compat.py` — Semconv baseline checker (Python)

### Acceptance Criteria

- [ ] `pip install claude-trace && python -c "import claude_trace; claude_trace.instrument()"` works
- [ ] A traced session produces OTel spans with all required `claude.*` attributes
- [ ] Cost calculation is accurate to within 0.01% for all 17 models
- [ ] `capture_content = false` (default) produces zero prompt/response content in spans
- [ ] All security tests pass (see `skills/security/SKILL.md`)

---

## Milestone 3 — TypeScript/WASM Bindings + OTLP Export

**Status**: Planned
**Goal**: Working TypeScript package via wasm-bindgen. Full OTLP export to any compatible backend (Jaeger, Grafana Tempo, Honeycomb, Datadog, etc.).

### Deliverables

- [ ] `src/wasm_bindings/` — wasm-bindgen wrappers
- [ ] `typescript/src/index.ts` — Public TypeScript API
- [ ] `typescript/src/types.ts` — TypeScript interfaces
- [ ] WASM binary under 1MB (optimized with wasm-opt)
- [ ] `src/export/otlp.rs` — OTLP gRPC exporter
- [ ] `src/export/stdout.rs` — Human-readable console exporter for development
- [ ] End-to-end test: Node.js → instrument → export → Jaeger query
- [ ] npm package published to `claude-trace`
- [ ] TypeScript test coverage ≥ 85%

### Acceptance Criteria

- [ ] `npm install claude-trace && node -e "const ct = require('claude-trace'); ct.instrument();"` works
- [ ] OTLP export to `localhost:4317` (default Jaeger/Grafana endpoint) works out of the box
- [ ] WASM binary size ≤ 1MB
- [ ] Console exporter produces readable output for development mode

---

## Milestone 4 — Claude Code Plugin Integration

**Status**: Planned
**Goal**: claude-trace hooks directly into Claude Code's tool use events, enabling automatic tracing of claude.ai conversations and Claude Code agent sessions without any code changes.

### Deliverables

- [ ] Claude Code plugin manifest with hook bindings for tool use events
- [ ] Hook fires on every Claude Code tool invocation (`Bash`, `Read`, `Edit`, etc.)
- [ ] Session span wraps the full Claude Code conversation
- [ ] Turn span wraps each Claude Code message turn
- [ ] Tool span wraps each Claude Code tool use block
- [ ] Cost calculation works for Claude Code's model usage
- [ ] Privacy mode: tool inputs/outputs not captured by default
- [ ] Developer documentation: `site/src/content/docs/guides/claude-code.mdx`

### Acceptance Criteria

- [ ] Install claude-trace plugin → Claude Code sessions automatically produce OTel spans
- [ ] Spans are structurally identical to spans from the Python/TypeScript SDK
- [ ] `capture_content = false` (default) for Claude Code tool inputs/outputs
- [ ] Works with all Claude Code tool types

---

## Milestone 5 — Interactive Docs + Trace Viewer

**Status**: Planned
**Goal**: A best-in-class documentation site with interactive components that make the span hierarchy intuitive.

### Deliverables

- [ ] `site/src/components/TraceViewer.astro` — Interactive session → turn → tool hierarchy viewer
- [ ] `site/src/components/SemconvBrowser.astro` — Searchable, filterable attribute table
- [ ] `site/src/data/semconv.json` — Machine-readable semconv data
- [ ] `site/src/components/ModelPricingTable.astro` — Current pricing visualization
- [ ] All documentation pages from `skills/ui/SKILL.md` page inventory
- [ ] Live demo with sample trace data
- [ ] Deployment to `agentglass.dev/claude-trace`

### Acceptance Criteria

- [ ] All pages from the page inventory exist and have real content
- [ ] SemconvBrowser renders all 47 `claude.*` attributes with search
- [ ] TraceViewer renders a sample 3-turn session correctly
- [ ] Site builds with zero errors: `cd site && npm run build`
- [ ] Lighthouse score ≥ 90 for performance and accessibility

---

## v1.0.0 — Stable Release

**Status**: Future
**Goal**: API-stable, security-audited, semconv submitted to OTel upstream.

### Criteria for v1.0.0

- [ ] All Milestone 1–5 deliverables complete
- [ ] Zero CRITICAL or HIGH security findings from `skills/security/SKILL.md` audit
- [ ] `claude.*` semconv proposal submitted to [opentelemetry-specification](https://github.com/open-telemetry/opentelemetry-specification)
- [ ] semconv maintained in [opentelemetry-semconv](https://github.com/open-telemetry/semantic-conventions) format
- [ ] API marked stable: `[package] version = "1.0.0"` with semver guarantees
- [ ] Test coverage ≥ 90% (higher bar for stable)
- [ ] Documented upgrade path from 0.x → 1.0
- [ ] At least 2 maintainers listed in CODEOWNERS with active GitHub accounts

### API Stability Commitment for v1.0.0

Once v1.0.0 ships:
- All `claude.*` semconv attribute names are frozen (no removal, no renaming, ever)
- `Config` struct field names are part of the public API
- Python `claude_trace.*` public functions maintain their signatures
- TypeScript/WASM exported symbols maintain their interfaces
- Rust `pub` items in `src/lib.rs` re-exports maintain their signatures

---

## Contributing to the Roadmap

To propose a new milestone or change priorities:
1. Open a GitHub issue with the label `roadmap`
2. Include: motivation, proposed deliverables, acceptance criteria
3. Get approval from `@agentglass/maintainers`

To work on a milestone:
1. Check the current milestone's deliverables above
2. Pick an unchecked item
3. Use the appropriate skill (see `.claude-plugin/skills/`)
4. Submit a PR with the item checked off and acceptance criteria met
