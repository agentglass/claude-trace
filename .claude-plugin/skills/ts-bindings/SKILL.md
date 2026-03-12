# TypeScript Bindings Skill — wasm-bindgen and WASM Expert Context

<!--
skill:
  name: ts-bindings
  description: Expert context for TypeScript/WASM bindings via wasm-bindgen. Covers annotation patterns, serde-wasm-bindgen, TypeScript interface generation, build targets, and the TypeScript ergonomic layer.
  auto-invoke:
    - "typescript/**/*.ts"
    - "src/wasm_bindings/**/*.rs"
  triggers:
    - "typescript bindings"
    - "wasm"
    - "wasm-bindgen"
    - "wasm-pack"
    - "javascript bindings"
    - "node bindings"
-->

## Architecture Overview

```
claude-trace WASM layer:

Rust crate (feature = "wasm")
  src/wasm_bindings/
    mod.rs          ← #[wasm_bindgen] entry points and struct wrappers
    session.rs      ← WasmSessionSpan
    cost.rs         ← WasmCostBreakdown + wasm_calculate_cost()
    panic.rs        ← console_error_panic_hook setup

wasm-pack output → typescript/pkg/
  claude_trace_bg.wasm    ← The compiled WebAssembly binary
  claude_trace.js         ← JS glue code (auto-generated)
  claude_trace.d.ts       ← TypeScript declarations (auto-generated)
  package.json            ← npm package metadata

TypeScript ergonomic layer → typescript/src/
  index.ts        ← Public API re-exports with ergonomic wrappers
  types.ts        ← TypeScript interfaces mirroring Rust types
  init.ts         ← WASM initialization utilities
```

---

## wasm-bindgen Annotation Patterns

### Exposing Structs

```rust
// src/wasm_bindings/session.rs
use wasm_bindgen::prelude::*;
use crate::spans::session::SessionSpan;
use std::sync::Arc;

/// A session span exposed to JavaScript/TypeScript.
///
/// Note: wasm-bindgen structs are owned by JavaScript. When JS garbage-collects
/// the object, the Rust memory is freed via `WasmSessionSpan::free()` (generated).
#[wasm_bindgen]
pub struct WasmSessionSpan {
    inner: Arc<SessionSpan>,
}

#[wasm_bindgen]
impl WasmSessionSpan {
    /// Create a new session span.
    #[wasm_bindgen(constructor)]
    pub fn new(session_id: &str, model: &str) -> Result<WasmSessionSpan, JsError> {
        let inner = SessionSpan::new(session_id.to_owned(), model.to_owned())
            .map_err(|e| JsError::new(&e.to_string()))?;
        Ok(Self { inner: Arc::new(inner) })
    }

    /// Get the session ID.
    ///
    /// Returns a cloned String (WASM crosses the boundary by copy, not reference).
    #[wasm_bindgen(getter)]
    pub fn session_id(&self) -> String {
        self.inner.session_id.clone()
    }

    /// Get the configured model identifier.
    #[wasm_bindgen(getter)]
    pub fn model(&self) -> String {
        self.inner.model.clone()
    }

    /// End the session and flush all pending spans.
    ///
    /// In async JS/TS code, `await` this call.
    #[wasm_bindgen]
    pub async fn end(&self) -> Result<(), JsError> {
        self.inner.end().map_err(|e| JsError::new(&e.to_string()))?;
        Ok(())
    }

    /// Get the cost breakdown for this session.
    #[wasm_bindgen(getter)]
    pub fn cost(&self) -> WasmCostBreakdown {
        WasmCostBreakdown::from(self.inner.cost())
    }
}
```

### Exposing Free Functions

```rust
// src/wasm_bindings/cost.rs
use wasm_bindgen::prelude::*;
use serde::{Deserialize, Serialize};
use serde_wasm_bindgen;

/// Calculate the cost for a single API call.
///
/// Returns a `CostBreakdown` object with `totalUsd`, `inputCostUsd`, etc.
#[wasm_bindgen]
pub fn calculate_cost(
    model: &str,
    input_tokens: u32,
    output_tokens: u32,
    cache_read_tokens: u32,
    cache_creation_tokens: u32,
) -> Result<JsValue, JsError> {
    let calc = crate::cost::get_calculator();
    let breakdown = calc.calculate(
        model,
        input_tokens as u64,
        output_tokens as u64,
        cache_read_tokens as u64,
        cache_creation_tokens as u64,
    ).map_err(|e| JsError::new(&e.to_string()))?;

    // serde_wasm_bindgen converts the Rust struct to a JS object automatically
    serde_wasm_bindgen::to_value(&breakdown)
        .map_err(|e| JsError::new(&e.to_string()))
}
```

### serde-wasm-bindgen for Automatic Serialization

Use `serde_wasm_bindgen` for complex return types instead of manually constructing JS objects:

```rust
// The Rust type must implement Serialize
#[derive(Serialize, Deserialize)]
pub struct CostBreakdown {
    pub model: String,
    #[serde(rename = "inputCostUsd")]   // camelCase for JS conventions
    pub input_cost_usd: f64,
    #[serde(rename = "outputCostUsd")]
    pub output_cost_usd: f64,
    #[serde(rename = "totalUsd")]
    pub total_usd: f64,
    // ...
}

// In wasm_bindgen function, convert to JsValue:
serde_wasm_bindgen::to_value(&my_rust_struct)?
// To convert back from JS to Rust:
let my_struct: MyRust = serde_wasm_bindgen::from_value(js_val)?;
```

**Use camelCase field names in Serde attributes** when the type is exposed to JavaScript. TypeScript convention is camelCase; Rust convention is snake_case.

---

## Panic Hook Setup

Always install the panic hook at module initialization. Without it, Rust panics appear as an unhelpful "RuntimeError: unreachable" in JavaScript:

```rust
// src/wasm_bindings/mod.rs
use wasm_bindgen::prelude::*;

/// Initialize the WASM module.
///
/// This MUST be called before using any other claude-trace WASM functions.
/// For Node.js, call this in your module's initialization code.
/// For browsers, await the WASM init() function before calling this.
#[wasm_bindgen(start)]
pub fn wasm_init() {
    // Set up better panic messages in the browser/Node.js console
    #[cfg(feature = "wasm")]
    console_error_panic_hook::set_once();
}
```

This function is called automatically when the WASM module is loaded because of `#[wasm_bindgen(start)]`.

---

## Error Handling in wasm-bindgen

**Use `JsError` for all errors** (not `JsValue`). `JsError` becomes a proper JavaScript `Error` object with a `.message` property:

```rust
// CORRECT: JsError becomes a real JS Error
pub fn my_fn() -> Result<String, JsError> {
    something_risky().map_err(|e| JsError::new(&e.to_string()))
}

// WRONG: JsValue(String) becomes a plain string, not an Error
pub fn my_fn() -> Result<String, JsValue> {
    something_risky().map_err(|e| JsValue::from_str(&e.to_string()))
}
```

On the TypeScript side, errors become standard `Error` objects:
```typescript
try {
  const span = new WasmSessionSpan('invalid', '');
} catch (e: unknown) {
  if (e instanceof Error) {
    console.error(e.message); // Proper error message from Rust
  }
}
```

---

## Build Commands

### Development

```bash
# Build for Node.js (commonjs output)
wasm-pack build --target nodejs --out-dir typescript/pkg

# Build for browsers (ES module output)
wasm-pack build --target web --out-dir typescript/pkg-web

# Build for bundlers (webpack, vite, etc.)
wasm-pack build --target bundler --out-dir typescript/pkg-bundler

# Development build (no optimization, includes debug info)
wasm-pack build --dev --target nodejs --out-dir typescript/pkg
```

### What wasm-pack Produces

After `wasm-pack build --target nodejs`:

```
typescript/pkg/
├── claude_trace_bg.wasm      # The WASM binary (~500KB optimized)
├── claude_trace.js           # CommonJS glue code (require() friendly)
├── claude_trace.d.ts         # TypeScript declarations (auto-generated)
└── package.json              # npm package metadata
```

The `.d.ts` file is the source of truth for the TypeScript interface. Do not edit it manually — it is regenerated on every build.

### Full Build Pipeline

```bash
# 1. Build Rust → WASM
wasm-pack build --target nodejs --out-dir typescript/pkg

# 2. Compile TypeScript ergonomic layer
cd typescript && npx tsc -p tsconfig.json

# 3. Run TypeScript tests
npm test -- --config typescript/jest.config.js
```

---

## TypeScript Ergonomic Layer

The raw `wasm-pack` output is not ergonomic. The `typescript/src/` layer adds wrappers:

```typescript
// typescript/src/index.ts
// Re-export everything from the WASM package
export { WasmSessionSpan, calculate_cost as rawCalculateCost } from '../pkg/claude_trace';

// Export ergonomic interfaces
export type { CostBreakdown, SessionOptions } from './types';

// Export ergonomic wrappers
export { session, instrument } from './api';
```

```typescript
// typescript/src/types.ts
/** Cost breakdown for a single API call or session. */
export interface CostBreakdown {
  model: string;
  inputCostUsd: number;
  outputCostUsd: number;
  cacheReadCostUsd: number;
  cacheCreationCostUsd: number;
  totalUsd: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
}

/** Options for starting a session. */
export interface SessionOptions {
  model?: string;
  customerId?: string;
  tags?: string[];
}
```

```typescript
// typescript/src/api.ts
import { WasmSessionSpan } from '../pkg/claude_trace';
import type { SessionOptions } from './types';

/**
 * Run a callback within a traced session.
 *
 * @example
 * ```typescript
 * const result = await session({ customerId: 'acme' }, async (sess) => {
 *   const response = await client.messages.create({ ... });
 *   return response;
 * });
 * ```
 */
export async function session<T>(
  options: SessionOptions,
  callback: (span: WasmSessionSpan) => Promise<T>,
): Promise<T> {
  const sessionId = `sess_${Math.random().toString(36).slice(2, 18)}`;
  const span = new WasmSessionSpan(sessionId, options.model ?? 'claude-sonnet-4-6');

  try {
    const result = await callback(span);
    await span.end();
    return result;
  } catch (err) {
    await span.endWithError(String(err));
    throw err;
  }
}
```

---

## TypeScript Configuration

```json
// typescript/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "esModuleInterop": true,
    "moduleResolution": "node",
    "paths": {
      "../pkg/*": ["./pkg/*"]
    }
  },
  "include": ["src/**/*"],
  "exclude": ["tests/**/*", "dist/**/*", "node_modules/**/*"]
}
```

---

## Testing TypeScript Bindings

```typescript
// typescript/tests/cost.test.ts
import { rawCalculateCost } from '../src/index';
import type { CostBreakdown } from '../src/types';

describe('calculateCost', () => {
  it('returns zero cost for zero tokens', () => {
    const result = rawCalculateCost('claude-sonnet-4-6', 0, 0, 0, 0) as CostBreakdown;
    expect(result.totalUsd).toBe(0);
  });

  it('charges correct rate for sonnet-4 input tokens', () => {
    // claude-sonnet-4-6: $3.00 per million input tokens
    const result = rawCalculateCost('claude-sonnet-4-6', 1_000_000, 0, 0, 0) as CostBreakdown;
    expect(result.inputCostUsd).toBeCloseTo(3.0, 2);
  });

  it('throws an error for empty model string', () => {
    expect(() => rawCalculateCost('', 100, 100, 0, 0)).toThrow(Error);
  });
});
```

---

## Publishing to npm

```bash
# After wasm-pack build, the pkg/ directory is the npm package
cd typescript/pkg

# Add the TypeScript dist files
cp -r ../dist/* .

# Publish (requires npm login)
npm publish --access public

# Or using wasm-pack directly (handles the publishing step)
wasm-pack publish
```

The npm package name is `claude-trace` (from `package.json` `name` field). Users install it with:

```bash
npm install claude-trace
```

---

## WASM Size Optimization

WASM binary size affects cold-start time in serverless environments. Keep it minimal:

```toml
# Cargo.toml — release profile for minimum WASM size
[profile.release]
opt-level = "s"   # Optimize for size (use instead of opt-level=3 for WASM)
lto = true
codegen-units = 1
strip = true
panic = "abort"   # Smaller panic handler for WASM
```

```bash
# Verify WASM size after changes
ls -lh typescript/pkg/claude_trace_bg.wasm
# Target: < 1MB for the core spans + cost calculator
```

Use `wasm-opt` (part of binaryen, included in wasm-pack) to further reduce size:

```bash
wasm-opt -Oz -o output.wasm input.wasm
```
