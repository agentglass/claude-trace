# Deploy Skill — Deployment to Docs and Plugin Marketplace

<!--
skill:
  name: deploy
  description: Deploy the documentation site to Netlify/Vercel and update the plugin marketplace registry. Two deployment targets with distinct procedures.
  disable-model-invocation: true
  triggers:
    - "deploy"
    - "deploy docs"
    - "publish docs"
    - "update marketplace"
    - "deploy site"
-->

## Two Deployment Targets

This skill covers two independent deployment operations:

1. **Docs site** (`site/`) → Netlify or Vercel (static hosting)
2. **Plugin marketplace** → Update `marketplace.json`, push to registry

These are independent. You can deploy docs without updating the marketplace, and vice versa.

---

## Target 1: Documentation Site

### Prerequisites

```bash
# Verify site builds cleanly
cd /Users/rajasekharkarawalla/dev/2026/prod/anthropic-projs/claude-trace/site
npm run build
# Expected: "build complete" with zero errors
ls dist/index.html  # Should exist
```

### Deploy to Netlify

```bash
# Ensure Netlify CLI is installed and authenticated
netlify --version
netlify status  # Should show your team/account

# Deploy to production
cd site
npm run build
netlify deploy --prod --dir=dist --site=agentglass-claude-trace

# Verify deployment
netlify sites:list | grep claude-trace
```

If `netlify status` shows "Not logged in":
```bash
netlify login  # Opens browser for OAuth
```

**Netlify configuration** (`netlify.toml` in project root):
```toml
[build]
  base = "site"
  command = "npm run build"
  publish = "dist"

[build.environment]
  NODE_VERSION = "20"

[[redirects]]
  from = "/claude-trace"
  to = "/claude-trace/"
  status = 301

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"
```

### Deploy to Vercel (Alternative)

```bash
# Ensure Vercel CLI is installed and authenticated
vercel --version
vercel whoami

# Deploy to production
cd site
vercel --prod
```

**Vercel configuration** (`vercel.json` in `site/`):
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "astro",
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" }
      ]
    }
  ]
}
```

### Verify Deployment

After deployment, verify key pages load correctly:

```bash
# Use curl to check HTTP status codes
curl -s -o /dev/null -w "%{http_code}" https://agentglass.dev/claude-trace/
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" https://agentglass.dev/claude-trace/reference/semconv/
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" https://agentglass.dev/claude-trace/getting-started/quickstart/
# Expected: 200
```

---

## Target 2: Plugin Marketplace

The Claude Code plugin marketplace is a registry of community plugins. When claude-trace is published, contributors who search for "observability" or "claude-trace" will find it.

### Marketplace Registry File

The `marketplace.json` file in the repository root contains the plugin's marketplace listing:

```json
{
  "id": "claude-trace",
  "name": "claude-trace",
  "version": "0.1.0",
  "description": "Development plugin for contributing to claude-trace — zero-config OTel observability for Claude Agent SDK",
  "author": "agentglass contributors",
  "homepage": "https://agentglass.dev/claude-trace",
  "repository": "https://github.com/agentglass/claude-trace",
  "license": "Apache-2.0",
  "keywords": ["rust", "observability", "opentelemetry", "claude", "development"],
  "pluginRoot": ".claude-plugin",
  "compatibleWithClaudeCode": ">=1.0.0",
  "updatedAt": "YYYY-MM-DD"
}
```

### Update and Publish Steps

```bash
# 1. Read current marketplace.json
cat marketplace.json

# 2. Update the version and updatedAt fields using Edit tool
#    version: match the current plugin.json version
#    updatedAt: today's date in YYYY-MM-DD format

# 3. Verify the JSON is valid
python -m json.tool marketplace.json > /dev/null && echo "Valid JSON"

# 4. Commit the marketplace update
git add marketplace.json
git commit -m "chore: update marketplace.json to v$(cat .claude-plugin/plugin.json | python -m json.tool | grep version | head -1 | tr -d '", '| cut -d: -f2)"

# 5. Push — this triggers marketplace update notifications
git push origin main
```

### How Plugin Users Discover Updates

When claude-trace contributors install the plugin (via Claude Code plugin manager), they pin to a version or track `main`. On `git push origin main` with an updated `marketplace.json`, Claude Code's plugin manager can detect the update via the repository's RSS feed or webhook.

---

## CI-Triggered Docs Deployment

The GitHub Actions `ci.yml` workflow deploys docs automatically on push to `main`. This means **manual deployment is rarely needed**. Only run the manual steps above if:

1. CI deployment is broken and you need an emergency hotfix to the docs
2. You're deploying from a feature branch for preview purposes

To check if CI deployed docs successfully:

```bash
gh run list --workflow=ci.yml --limit 3
gh run view $(gh run list --workflow=ci.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

Look for the `deploy-docs` job in the workflow output.
