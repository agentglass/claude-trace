# UI / Docs Site Skill — Starlight and Astro Expert Context

<!--
skill:
  name: ui
  description: Complete context for the Starlight/Astro documentation site. Covers project structure, every required page, MDX patterns, the interactive trace viewer, semconv browser, multi-language code tabs, and deployment.
  auto-invoke:
    - "site/**/*"
  triggers:
    - "docs"
    - "documentation"
    - "starlight"
    - "astro"
    - "mdx"
    - "site"
    - "semconv browser"
    - "trace viewer"
-->

## Documentation Philosophy

**Future contributors should know every small detail.**

This is the guiding principle for every docs page. Assume the reader is a capable developer who has never seen this codebase before. Write for them — not for yourself.

Every page must answer:
1. What is this thing?
2. Why does it exist?
3. How do I use it (with real, runnable code examples)?
4. What can go wrong, and how do I fix it?

---

## Project Structure

```
site/
├── astro.config.mjs              # Starlight configuration
├── package.json                  # Node.js dependencies
├── tsconfig.json                 # TypeScript config
├── public/
│   ├── favicon.svg
│   └── og-image.png             # Social sharing image
└── src/
    ├── assets/
    │   ├── logo.svg
    │   └── hero-diagram.svg     # Session/turn/tool hierarchy diagram
    ├── components/
    │   ├── TraceViewer.astro    # Interactive span hierarchy viewer
    │   ├── SemconvBrowser.astro # Searchable attribute table
    │   └── ModelPricingTable.astro
    └── content/
        └── docs/                # All .mdx documentation pages
            ├── index.mdx
            ├── getting-started/
            ├── guides/
            ├── reference/
            ├── contributing/
            └── internals/
```

---

## Complete Page Inventory

Every page listed here MUST exist. If a page is missing, create it.

### Root

```
site/src/content/docs/index.mdx
```

Landing page. Must include:
- Hero with tagline: "Zero-config OTel observability for Claude agents"
- The span hierarchy diagram (`hero-diagram.svg`)
- 30-second quickstart (pip install + 5 lines of code)
- Links to Python guide, TypeScript guide, and Contributing overview

### Getting Started

```
site/src/content/docs/getting-started/
├── installation.mdx      # pip install, npm install, Rust dependency
├── quickstart.mdx        # End-to-end in 5 minutes with Jaeger
└── concepts.mdx          # Session → Turn → Tool hierarchy explained
```

**`concepts.mdx`** is the most important getting-started page. It must explain:
- What a "session" is and when it starts/ends
- What a "turn" is (one `messages.create()` call)
- What a "tool invocation" is
- The parent-child span relationship
- Why this hierarchy matters for debugging

### Guides

```
site/src/content/docs/guides/
├── python.mdx            # Full Python instrumentation guide
├── typescript.mdx        # Full TypeScript/Node.js guide
├── cost-attribution.mdx  # Using customer_id + tags for cost tracking
├── trace-diff.mdx        # Comparing traces between runs
└── security.mdx          # SANITIZE mode, PII protection, capture_content
```

**`security.mdx`** must prominently explain:
- `capture_content = false` is the DEFAULT (content is NOT captured)
- How to enable content capture for debugging (and the risks)
- API key redaction (`sk-ant-` pattern)
- Attribute truncation (default 512 chars)

### Reference

```
site/src/content/docs/reference/
├── semconv.mdx           # Interactive semconv browser — ALL claude.* attributes
├── api-python.mdx        # Python API reference
├── api-typescript.mdx    # TypeScript API reference
└── configuration.mdx     # All Config options with types and defaults
```

**`semconv.mdx`** contains the `<SemconvBrowser />` component and a complete, searchable table of all `claude.*` attributes. When new attributes are added to `src/semconv/claude.rs`, this page MUST be updated.

### Contributing

```
site/src/content/docs/contributing/
├── overview.mdx          # Contributor welcome + quick orientation
├── development-setup.mdx # How to set up the dev environment from scratch
├── skills-guide.mdx      # How to use the .claude-plugin skills
├── rust-guide.mdx        # Rust conventions reference (mirrors rust SKILL.md)
├── testing.mdx           # TDD workflow, coverage gate, test commands
├── semconv-proposals.mdx # RFC process for new claude.* attributes
└── release-process.mdx   # Full release checklist
```

### Internals

```
site/src/content/docs/internals/
├── architecture.mdx      # How the Rust core works
├── span-lifecycle.mdx    # Detailed span creation, attribute setting, export
└── cost-model.mdx        # Pricing table, model matching, cache pricing
```

---

## MDX Patterns

### Frontmatter

Every `.mdx` page must have correct frontmatter:

```mdx
---
title: Session, Turn, and Tool — Core Concepts
description: Understand the three-level span hierarchy that is the foundation of claude-trace observability.
sidebar:
  order: 3                    # Controls position within the sidebar group
  badge:
    text: Core
    variant: note             # note | tip | caution | danger | success
tableOfContents:
  minHeadingLevel: 2
  maxHeadingLevel: 3
---
```

### Starlight Components

```mdx
import { Aside, Card, CardGrid, Steps, Tabs, TabItem, Code } from '@astrojs/starlight/components';

<Aside type="note">
This is informational context.
</Aside>

<Aside type="caution">
This warns about non-obvious behavior.
</Aside>

<Aside type="danger">
This warns about security or data loss risks.
</Aside>
```

### Multi-Language Code Tabs

Every guide page that shows API usage must have multi-language tabs:

```mdx
import { Tabs, TabItem } from '@astrojs/starlight/components';

<Tabs>
<TabItem label="Python">
```python
import claude_trace

claude_trace.instrument()

with claude_trace.session(customer_id="acme") as sess:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}],
    )
print(f"Cost: ${sess.cost.total_usd:.4f}")
```
</TabItem>
<TabItem label="TypeScript">
```typescript
import { session } from 'claude-trace';

const result = await session({ customerId: 'acme' }, async (sess) => {
  const response = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1024,
    messages: [{ role: 'user', content: 'Hello' }],
  });
  return response;
});
```
</TabItem>
</Tabs>
```

### Steps Component (For Tutorials)

```mdx
import { Steps } from '@astrojs/starlight/components';

<Steps>

1. Install claude-trace:

   ```bash
   pip install claude-trace
   ```

2. Add instrumentation at startup:

   ```python
   import claude_trace
   claude_trace.instrument()
   ```

3. Wrap your agent loop in a session context...

</Steps>
```

---

## Interactive Trace Viewer Component

The `<TraceViewer />` component renders a visual session → turn → tool hierarchy. It is used on the `concepts.mdx` and `span-lifecycle.mdx` pages.

### Component Interface

```astro
---
// site/src/components/TraceViewer.astro
export interface Props {
  /** Sample trace data to display. If omitted, shows a static example. */
  trace?: TraceData;
  /** Whether to show cost annotations next to each span. Default: true */
  showCosts?: boolean;
  /** Whether to show token counts. Default: true */
  showTokens?: boolean;
}

interface TraceData {
  session: {
    id: string;
    model: string;
    status: string;
    totalCostUsd: number;
    turns: TurnData[];
  };
}

interface TurnData {
  index: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  stopReason: string;
  tools: ToolData[];
}

interface ToolData {
  name: string;
  status: string;
  latencyMs: number;
}
---
<div class="trace-viewer" data-component="trace-viewer">
  <!-- Rendered server-side by Astro; no JavaScript required for static display -->
  <div class="session-span">
    <span class="span-label">claude.agent.session</span>
    <!-- ... turns nested inside ... -->
  </div>
</div>
<style>
  .trace-viewer { font-family: var(--sl-font-mono); }
  .session-span { border-left: 3px solid var(--sl-color-blue-high); padding-left: 1rem; }
  /* ... more styles ... */
</style>
```

### Usage in MDX

```mdx
import TraceViewer from '@/components/TraceViewer.astro';

Here's what a typical 3-turn agent session looks like:

<TraceViewer showCosts={true} showTokens={true} />
```

---

## Semconv Browser Component

The `<SemconvBrowser />` renders a searchable, filterable table of all `claude.*` span attributes.

### Component Contract

```astro
---
// site/src/components/SemconvBrowser.astro
// Data is imported from a JSON file that is the source of truth
import semconvData from '../data/semconv.json';

export interface SemconvEntry {
  attribute: string;     // "claude.session.id"
  category: string;      // "session" | "turn" | "tool" | "cost"
  type: string;          // "string" | "int" | "float" | "bool" | "string[]"
  description: string;
  example: string;
  addedVersion: string;  // "0.1.0"
  deprecated?: string;   // semver when deprecated, if ever
}
---
<!-- Client-side search using a small vanilla JS snippet (no framework needed) -->
<div class="semconv-browser">
  <input type="search" placeholder="Search attributes (e.g. 'session.id' or 'cost')..." />
  <select>
    <option value="">All categories</option>
    <option value="session">session</option>
    <option value="turn">turn</option>
    <option value="tool">tool</option>
    <option value="cost">cost</option>
  </select>
  <table>
    <thead>
      <tr>
        <th>Attribute</th>
        <th>Type</th>
        <th>Description</th>
        <th>Example</th>
      </tr>
    </thead>
    <tbody>
      {semconvData.map(entry => (
        <tr data-category={entry.category}>
          <td><code>{entry.attribute}</code></td>
          <td><code>{entry.type}</code></td>
          <td>{entry.description}</td>
          <td><code>{entry.example}</code></td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

### Data File: `site/src/data/semconv.json`

This file is the source of truth for the semconv browser. It MUST be kept in sync with `src/semconv/claude.rs`:

```json
[
  {
    "attribute": "claude.session.id",
    "category": "session",
    "type": "string",
    "description": "Unique identifier for the agent session.",
    "example": "sess_01HV2Y3K8P9Q0R1S2T3U4V5W6X",
    "addedVersion": "0.1.0"
  },
  {
    "attribute": "claude.session.model",
    "category": "session",
    "type": "string",
    "description": "Model identifier configured for this session.",
    "example": "claude-sonnet-4-6",
    "addedVersion": "0.1.0"
  }
  // ... all other attributes
]
```

**When adding a new `claude.*` attribute:**
1. Add the constant in `src/semconv/claude.rs`
2. Add an entry to `site/src/data/semconv.json`
3. The browser updates automatically on next build

---

## Adding a New Docs Page: Step by Step

1. Determine the correct directory:
   - Getting started concept → `getting-started/`
   - How-to guide → `guides/`
   - API or attribute reference → `reference/`
   - Contributor instructions → `contributing/`
   - How the code works → `internals/`

2. Create the file with correct frontmatter:
   ```mdx
   ---
   title: Your Page Title
   description: One sentence that describes the page for search engines and the sidebar tooltip.
   sidebar:
     order: 5
   ---
   ```

3. Write the content. Use components from `@astrojs/starlight/components`. Include multi-language code tabs if showing API usage.

4. Verify the build:
   ```bash
   cd site && npm run build
   # Zero errors/warnings expected
   ```

5. Check it renders correctly:
   ```bash
   cd site && npm run dev
   # Open http://localhost:4321 in browser
   ```

---

## Deployment

### Build

```bash
cd site
npm run build
# Output: site/dist/
```

### Netlify

```bash
cd site
npm run build
netlify deploy --prod --dir=dist
```

Configure in `netlify.toml` at the site root:
```toml
[build]
  base = "site"
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/claude-trace/*"
  to = "/:splat"
  status = 200
```

### Vercel

Add `vercel.json` in `site/`:
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "astro"
}
```

### GitHub Pages (via CI)

The `ci.yml` workflow builds and deploys the site on pushes to `main`. It uses `actions/deploy-pages`.

---

## Model Pricing Table Component

Used in `internals/cost-model.mdx`:

```astro
---
// site/src/components/ModelPricingTable.astro
// Matches the pricing table in src/cost/models.rs
const models = [
  { id: "claude-opus-4-5",            input: 15.00, output: 75.00,  cacheWrite: 18.75, cacheRead: 1.50  },
  { id: "claude-opus-4-0",            input: 15.00, output: 75.00,  cacheWrite: 18.75, cacheRead: 1.50  },
  { id: "claude-sonnet-4-6",          input: 3.00,  output: 15.00,  cacheWrite: 3.75,  cacheRead: 0.30  },
  { id: "claude-sonnet-4-5",          input: 3.00,  output: 15.00,  cacheWrite: 3.75,  cacheRead: 0.30  },
  { id: "claude-haiku-4-5",           input: 0.80,  output: 4.00,   cacheWrite: 1.00,  cacheRead: 0.08  },
  { id: "claude-3-5-sonnet-20241022", input: 3.00,  output: 15.00,  cacheWrite: 3.75,  cacheRead: 0.30  },
  { id: "claude-3-5-haiku-20241022",  input: 0.80,  output: 4.00,   cacheWrite: 1.00,  cacheRead: 0.08  },
  { id: "claude-3-opus-20240229",     input: 15.00, output: 75.00,  cacheWrite: 18.75, cacheRead: 1.50  },
  { id: "claude-3-haiku-20240307",    input: 0.25,  output: 1.25,   cacheWrite: 0.31,  cacheRead: 0.025 },
];
---
<table>
  <thead>
    <tr>
      <th>Model</th>
      <th>Input $/M</th>
      <th>Output $/M</th>
      <th>Cache Write $/M</th>
      <th>Cache Read $/M</th>
    </tr>
  </thead>
  <tbody>
    {models.map(m => (
      <tr>
        <td><code>{m.id}</code></td>
        <td>${m.input.toFixed(2)}</td>
        <td>${m.output.toFixed(2)}</td>
        <td>${m.cacheWrite.toFixed(2)}</td>
        <td>${m.cacheRead.toFixed(3)}</td>
      </tr>
    ))}
  </tbody>
</table>
```
