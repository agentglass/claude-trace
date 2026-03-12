# Scaffold Skill — Bootstrap claude-trace from Scratch

<!--
skill:
  name: scaffold
  description: Bootstraps the complete claude-trace project structure from zero. Creates Rust workspace, Python bindings layer, TypeScript/WASM layer, GitHub Actions CI, docs site scaffolding, and all configuration files.
  disable-model-invocation: true
  allowed-tools: Bash, Write, Read, Edit, Glob
  triggers:
    - "scaffold the project"
    - "bootstrap claude-trace"
    - "set up project from scratch"
    - "initialize workspace"
-->

## Purpose

This skill creates the **complete claude-trace project structure** from scratch. It is authoritative — every path, file name, and command listed here is canonical. When in doubt about project structure, consult this skill.

This skill has `disable-model-invocation: true` because it creates files that define the project's entire contract. There is no room for improvisation.

---

## Step 0: Prerequisites

Verify all required tools are present before starting:

```bash
# Required: Rust toolchain
rustup --version          # >= 1.76.0
cargo --version           # >= 1.75.0
rustup target list --installed | grep wasm32-unknown-unknown

# Required: Python toolchain
python --version          # >= 3.11
pip install maturin       # >= 1.4.0
maturin --version

# Required: Node.js toolchain
node --version            # >= 20.0.0
npm --version             # >= 10.0.0
npm install -g wasm-pack  # >= 0.12.0
wasm-pack --version

# Required: Additional tools
gh --version              # GitHub CLI for workflows
git --version
```

If any tool is missing, **stop and install it**. Do not proceed with missing dependencies.

---

## Step 1: Rust Workspace — `Cargo.toml`

Create the root `Cargo.toml`. This is a Cargo workspace that also serves as the main crate:

```toml
[workspace]
members = ["."]
resolver = "2"

[package]
name = "claude-trace"
version = "0.1.0"
edition = "2021"
rust-version = "1.75"
description = "Zero-configuration OpenTelemetry observability for Claude Agent SDK"
license = "Apache-2.0"
repository = "https://github.com/agentglass/claude-trace"
homepage = "https://agentglass.dev/claude-trace"
documentation = "https://agentglass.dev/claude-trace/reference"
keywords = ["opentelemetry", "claude", "observability", "tracing", "agents"]
categories = ["api-bindings", "development-tools::debugging", "web-programming"]
readme = "README.md"
exclude = ["site/", "python/tests/", "typescript/tests/"]

[lib]
name = "claude_trace"
crate-type = ["cdylib", "rlib"]

[dependencies]
opentelemetry = { version = "0.25", features = ["trace"] }
opentelemetry_sdk = { version = "0.25", features = ["trace", "rt-tokio"] }
opentelemetry-otlp = { version = "0.25", features = ["grpc-tonic", "http-proto"] }
thiserror = "1.0"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
sha2 = "0.10"
hex = "0.4"
tokio = { version = "1.36", features = ["rt-multi-thread", "sync"] }
tracing = "0.1"

# PyO3 bindings (optional, enabled by default for maturin builds)
pyo3 = { version = "0.26", features = ["extension-module", "abi3-py311"], optional = true }

# wasm-bindgen (optional, enabled for wasm-pack builds)
wasm-bindgen = { version = "0.2", optional = true }
serde-wasm-bindgen = { version = "0.6", optional = true }
console_error_panic_hook = { version = "0.1", optional = true }
js-sys = { version = "0.3", optional = true }

[dev-dependencies]
insta = { version = "1.38", features = ["json", "yaml"] }
tokio = { version = "1.36", features = ["rt-multi-thread", "macros", "test-util"] }
opentelemetry-stdout = "0.25"
criterion = { version = "0.5", features = ["html_reports"] }
proptest = "1.4"

[features]
default = ["python"]
python = ["pyo3"]
wasm = ["wasm-bindgen", "serde-wasm-bindgen", "console_error_panic_hook", "js-sys"]

[[bench]]
name = "span_throughput"
harness = false

[profile.release]
opt-level = 3
lto = "thin"
codegen-units = 1
strip = true

[profile.dev]
debug = true
opt-level = 0
```

---

## Step 2: Python Build Config — `pyproject.toml`

This file governs the Python wheel build via maturin:

```toml
[build-system]
requires = ["maturin>=1.4,<2"]
build-backend = "maturin"

[project]
name = "claude-trace"
version = "0.1.0"
description = "Zero-configuration OpenTelemetry observability for Claude Agent SDK"
readme = "README.md"
license = { text = "Apache-2.0" }
requires-python = ">=3.11"
authors = [{ name = "agentglass contributors" }]
keywords = ["anthropic", "claude", "opentelemetry", "observability", "agents", "tracing"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Rust",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries",
    "Topic :: System :: Monitoring",
]
dependencies = [
    "anthropic>=0.40.0",
    "opentelemetry-api>=1.25.0",
    "opentelemetry-sdk>=1.25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.9",
    "ruff>=0.4",
    "opentelemetry-exporter-otlp>=1.25.0",
    "pip-audit>=2.7",
]
otlp = ["opentelemetry-exporter-otlp>=1.25.0"]

[project.urls]
Homepage = "https://agentglass.dev/claude-trace"
Repository = "https://github.com/agentglass/claude-trace"
Documentation = "https://agentglass.dev/claude-trace/reference"
Issues = "https://github.com/agentglass/claude-trace/issues"

[tool.maturin]
features = ["python"]
python-source = "python"
module-name = "claude_trace._claude_trace"
# ABI3 wheel works on Python 3.11+
abi3-python-version = "311"

[tool.ruff]
line-length = 100
target-version = "py311"
[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "ANN", "B", "C4", "PT"]
ignore = ["ANN101", "ANN102"]

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["python/tests"]
```

---

## Step 3: TypeScript/WASM Config — `package.json`

```json
{
  "name": "claude-trace",
  "version": "0.1.0",
  "description": "Zero-config OTel observability for Claude Agent SDK — TypeScript/WASM bindings",
  "main": "typescript/dist/index.js",
  "types": "typescript/dist/index.d.ts",
  "files": ["typescript/dist/", "typescript/src/"],
  "scripts": {
    "build": "wasm-pack build --target nodejs --out-dir typescript/pkg && tsc -p typescript/tsconfig.json",
    "build:web": "wasm-pack build --target web --out-dir typescript/pkg-web && tsc -p typescript/tsconfig.json",
    "test": "jest --config typescript/jest.config.js",
    "lint": "tsc --noEmit -p typescript/tsconfig.json && eslint typescript/src/**/*.ts",
    "clean": "rm -rf typescript/dist typescript/pkg typescript/pkg-web"
  },
  "keywords": ["claude", "opentelemetry", "observability", "wasm", "agents"],
  "license": "Apache-2.0",
  "repository": {
    "type": "git",
    "url": "https://github.com/agentglass/claude-trace"
  },
  "devDependencies": {
    "@types/jest": "^29.5.0",
    "@types/node": "^20.0.0",
    "jest": "^29.7.0",
    "ts-jest": "^29.1.0",
    "typescript": "^5.4.0"
  },
  "engines": {
    "node": ">=20.0.0"
  }
}
```

---

## Step 4: Initial Source Directory Structure

Create these directories and placeholder files:

```bash
# Rust source
mkdir -p src/spans src/semconv src/cost src/export src/config
touch src/lib.rs
touch src/spans/mod.rs src/spans/session.rs src/spans/turn.rs src/spans/tool.rs
touch src/semconv/mod.rs src/semconv/claude.rs
touch src/cost/mod.rs src/cost/calculator.rs src/cost/models.rs
touch src/export/mod.rs src/export/otlp.rs
touch src/config/mod.rs

# Python layer
mkdir -p python/claude_trace python/tests
touch python/claude_trace/__init__.py
touch python/claude_trace/py.typed
touch python/claude_trace/_claude_trace.pyi
touch python/tests/__init__.py
touch python/tests/test_spans.py
touch python/tests/test_cost.py
touch python/tests/test_semconv.py

# TypeScript layer
mkdir -p typescript/src typescript/tests
touch typescript/src/index.ts
touch typescript/src/types.ts
touch typescript/tests/index.test.ts
touch typescript/tsconfig.json

# Tests (integration)
mkdir -p tests
touch tests/integration_test.rs

# Docs site
mkdir -p site
```

---

## Step 5: Initial `src/lib.rs`

```rust
//! claude-trace: Zero-configuration OpenTelemetry observability for Claude Agent SDK.
//!
//! # Architecture
//!
//! ```text
//! claude.agent.session  (root span — one per claude.run() call)
//!   └── claude.agent.turn  (one LLM call + all its tool calls)
//!         └── claude.tool.invocation  (one tool + result)
//! ```
//!
//! # Quick Start
//!
//! ```rust,no_run
//! use claude_trace::{Config, Tracer};
//!
//! let tracer = Tracer::new(Config::default())?;
//! let session = tracer.start_session("my-session");
//! # Ok::<(), claude_trace::ClaudeTraceError>(())
//! ```

#![deny(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)] // Documented exception: module prefix aids discoverability
#![cfg_attr(docsrs, feature(doc_cfg))]

pub mod config;
pub mod cost;
pub mod export;
pub mod semconv;
pub mod spans;

#[cfg(feature = "python")]
mod python_bindings;

#[cfg(feature = "wasm")]
mod wasm_bindings;

pub use config::Config;
pub use spans::session::AgentSession;

use thiserror::Error;

/// Top-level error type for claude-trace operations.
#[derive(Debug, Error)]
pub enum ClaudeTraceError {
    /// OpenTelemetry initialization or export failed.
    #[error("OpenTelemetry error: {0}")]
    OtelError(String),

    /// A model identifier was provided that has no pricing data.
    #[error("Unknown model '{0}' — add it to src/cost/models.rs")]
    UnknownModel(String),

    /// A semconv attribute value exceeded the configured maximum length.
    #[error("Attribute '{attribute}' exceeded max length {max} (was {actual})")]
    AttributeTooLong {
        attribute: String,
        max: usize,
        actual: usize,
    },

    /// Configuration was invalid.
    #[error("Invalid configuration: {0}")]
    InvalidConfig(String),
}
```

---

## Step 6: GitHub Actions Workflows

### `.github/workflows/ci.yml`

See the `ci.yml` file in `.github/workflows/` — created separately (use the workflow skill or the CI file specified in the project root).

### `.github/workflows/release.yml`

This file is created as part of the CI infrastructure step. It triggers on `v*` tags and:
1. Builds maturin wheels for Linux/macOS/Windows × Python 3.11/3.12/3.13
2. Builds wasm-pack package
3. Creates GitHub release with all artifacts
4. Publishes to PyPI and npm

---

## Step 7: Configuration Files

### `.rustfmt.toml`

```toml
edition = "2021"
max_width = 100
tab_spaces = 4
newline_style = "Unix"
use_small_heuristics = "Default"
reorder_imports = true
reorder_modules = true
remove_nested_parens = true
merge_derives = true
use_try_shorthand = true
force_explicit_abi = true
normalize_comments = true
```

### `.clippy.toml`

```toml
# Documented clippy::pedantic exceptions for this codebase.
# Every entry MUST have a justification comment.

# Module name repetitions: "claude_trace::spans::session::SessionSpan" is clearer than
# "claude_trace::spans::session::Span" even though it repeats "session".
# Allow this project-wide.
# Note: enforced via #![allow(clippy::module_name_repetitions)] in lib.rs

msrv = "1.75.0"
```

### `.gitignore`

```
# Rust
/target/
Cargo.lock  # Libraries do not commit lock files per Cargo guidelines

# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.venv/
venv/
dist/
*.egg-info/
.mypy_cache/
.ruff_cache/
.pytest_cache/
htmlcov/
.coverage

# TypeScript/Node
node_modules/
typescript/dist/
typescript/pkg/
typescript/pkg-web/
*.tsbuildinfo

# Docs site
site/.astro/
site/dist/
site/node_modules/

# IDE
.idea/
.vscode/settings.json
*.swp
*.swo
.DS_Store

# Build artifacts
*.wasm
*.so
*.dylib
*.dll

# Test snapshots (committed snapshots are in tests/snapshots/)
!tests/snapshots/
```

---

## Step 8: Starlight Docs Site — `site/`

Initialize the Astro Starlight site:

```bash
cd site
npm create astro@latest . -- --template starlight --no-install
npm install
```

Then configure `site/astro.config.mjs`:

```js
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  integrations: [
    starlight({
      title: 'claude-trace',
      description: 'Zero-config OTel observability for Claude Agent SDK',
      logo: { src: './src/assets/logo.svg' },
      social: {
        github: 'https://github.com/agentglass/claude-trace',
      },
      sidebar: [
        { label: 'Getting Started', autogenerate: { directory: 'getting-started' } },
        { label: 'Guides', autogenerate: { directory: 'guides' } },
        { label: 'Reference', autogenerate: { directory: 'reference' } },
        { label: 'Contributing', autogenerate: { directory: 'contributing' } },
        { label: 'Internals', autogenerate: { directory: 'internals' } },
      ],
      editLink: { baseUrl: 'https://github.com/agentglass/claude-trace/edit/main/site/' },
    }),
  ],
  site: 'https://agentglass.dev/claude-trace',
  base: '/claude-trace',
});
```

---

## Step 9: Verification

After all files are created:

```bash
# Verify Rust project structure
cargo check 2>&1
# Expected: "Finished dev [unoptimized + debuginfo] target(s)"

# Verify Python layer (requires maturin installed)
maturin develop 2>&1
python -c "import claude_trace; print(claude_trace.__version__)"

# Verify TypeScript config parses
cd typescript && npx tsc --noEmit 2>&1

# Verify docs site builds
cd site && npm run build 2>&1
```

If `cargo check` fails, the most common causes are:
1. Missing `pyo3` dependency when `python` feature is default — ensure `Cargo.toml` has pyo3 listed
2. `cdylib` + `rlib` in crate-type requires both `lib.rs` and a proper `#[pymodule]` entry point
3. MSRV mismatch — check `rustup show` and ensure rust-version = "1.75" in Cargo.toml

---

## Canonical Directory Map

After scaffolding, the repository looks like this:

```
claude-trace/
├── .claude-plugin/           # This plugin (do not modify unless updating plugin)
│   ├── plugin.json
│   ├── skills/
│   ├── agents/
│   ├── hooks/
│   └── scripts/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   ├── release.yml
│   │   ├── semconv-compat.yml
│   │   └── security-audit.yml
│   └── CODEOWNERS
├── src/                      # Rust library source
│   ├── lib.rs
│   ├── config/
│   ├── cost/
│   ├── export/
│   ├── semconv/
│   └── spans/
├── python/                   # Python public layer
│   ├── claude_trace/
│   │   ├── __init__.py       # Public API surface
│   │   ├── py.typed          # PEP 561 marker
│   │   └── _claude_trace.pyi # Rust extension type stubs
│   └── tests/
├── typescript/               # TypeScript/WASM layer
│   ├── src/
│   │   ├── index.ts          # Public API re-exports
│   │   └── types.ts          # TypeScript types mirroring Rust types
│   ├── tests/
│   └── tsconfig.json
├── tests/                    # Rust integration tests
├── site/                     # Starlight documentation site
├── Cargo.toml
├── pyproject.toml
├── package.json
├── CHANGELOG.md
├── ROADMAP.md
├── .rustfmt.toml
├── .clippy.toml
└── .gitignore
```
