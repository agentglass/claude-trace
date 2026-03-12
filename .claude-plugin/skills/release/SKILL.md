# Release Skill — Release Workflow

<!--
skill:
  name: release
  description: Step-by-step release process for claude-trace. Covers CI verification, version bumping, changelog, testing, artifact building, tagging, and post-release verification. Never deviate from this sequence.
  disable-model-invocation: true
  allowed-tools: Bash, Read, Edit
  triggers:
    - "release"
    - "publish"
    - "cut a release"
    - "bump version"
    - "tag"
-->

## Why This Skill Exists

The release process has exactly 11 steps. Every step exists for a reason. Skipping a step has caused real incidents:
- Skipping Step 1 → Released with failing tests
- Skipping Step 2 → Released with known CVE
- Skipping Step 3 → Version mismatch between packages
- Skipping Step 4 → CHANGELOG didn't reflect the release
- Skipping Step 6 → Artifacts didn't include the wasm build

This skill has `disable-model-invocation: true` because the release process must be executed exactly as written, with no creative interpretation.

---

## Pre-Flight: Know the Version Number

Before starting, determine the new version number using SemVer:
- **PATCH** (0.1.X): Bug fixes, documentation. No API changes.
- **MINOR** (0.X.0): New features, new semconv attributes. No breaking changes.
- **MAJOR** (X.0.0): Breaking changes to public API. New semconv categories. Semconv removals.

The version is stored in 4 places (Step 3 updates all of them):
1. `Cargo.toml` — `version = "X.Y.Z"`
2. `pyproject.toml` — `version = "X.Y.Z"`
3. `package.json` — `"version": "X.Y.Z"`
4. `.claude-plugin/plugin.json` — `"version": "X.Y.Z-dev"` → `"X.Y.Z"`

---

## Step 1: Verify All CI Checks Green

```bash
# Check the last 5 CI runs for the current branch
gh run list --limit 5

# Check the most recent run in detail
gh run view $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
```

**DO NOT PROCEED** if any of these workflows are failing:
- `ci.yml` (Rust clippy, test, fmt; Python ruff, mypy, pytest; TypeScript tsc, jest)
- `security-audit.yml`
- `semconv-compat.yml`

If any are failing, stop. Fix the failures in a separate PR. Then restart this release process.

---

## Step 2: Verify No Unreleased Security Advisories

```bash
# Rust
cargo audit
# Python
pip-audit
# JavaScript
npm audit --prefix typescript
```

If `cargo audit` or `pip-audit` report CRITICAL or HIGH vulnerabilities:
1. Open the advisory URL
2. Check if claude-trace actually calls the vulnerable code path
3. If yes: update the dependency and re-run CI before proceeding
4. If no: document the exception in `CHANGELOG.md` under the release notes

Only proceed if there are zero CRITICAL/HIGH vulnerabilities.

---

## Step 3: Bump Version in All 4 Files

Set the `NEW_VERSION` variable and update all files:

```bash
NEW_VERSION="X.Y.Z"  # Replace with actual version number

# 1. Cargo.toml — update the [package] version field
# Use Edit tool to change: version = "OLD" → version = "NEW"

# 2. pyproject.toml — update the [project] version field
# Use Edit tool to change: version = "OLD" → version = "NEW"

# 3. package.json — update the version field
# Use Edit tool to change: "version": "OLD" → "version": "NEW"

# 4. .claude-plugin/plugin.json — update and remove -dev suffix
# Use Edit tool to change: "version": "OLD-dev" → "version": "NEW"
```

Verify all 4 files were updated:

```bash
grep -r "version" Cargo.toml pyproject.toml package.json .claude-plugin/plugin.json \
  | grep -E '"version"|^version'
```

All 4 should show the same version number.

---

## Step 4: Update CHANGELOG.md

The `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/) format.

Move the `[Unreleased]` section to a versioned section:

```markdown
<!-- BEFORE: -->
## [Unreleased]

### Added
- ...

### Fixed
- ...

<!-- AFTER: -->
## [X.Y.Z] - YYYY-MM-DD

### Added
- ...

### Fixed
- ...

## [Unreleased]
<!-- empty — ready for next release -->
```

Also update the diff links at the bottom of `CHANGELOG.md`:

```markdown
[Unreleased]: https://github.com/agentglass/claude-trace/compare/vX.Y.Z...HEAD
[X.Y.Z]: https://github.com/agentglass/claude-trace/compare/vX.Y.Z-1...vX.Y.Z
```

---

## Step 5: Run the Full Test Suite

```bash
# Rust tests (all)
cargo test 2>&1
# Expected: "test result: ok. N passed; 0 failed"

# Python tests
pytest python/tests/ -v 2>&1
# Expected: "N passed, 0 failed"

# TypeScript tests
npm test --prefix typescript 2>&1
# Expected: "Tests: N passed, 0 failed"

# Semconv compat check (must pass before release)
python scripts/check_semconv_compat.py 2>&1
# Expected: "Semconv compatibility check PASSED"
```

**DO NOT PROCEED** if any test suite fails. Fix the failures, then restart from Step 1.

---

## Step 6: Build Release Artifacts

```bash
# Build Python wheels (release optimization)
maturin build --release
# Output: target/wheels/claude_trace-X.Y.Z-*.whl

# Build WASM package (Node.js target)
wasm-pack build --target nodejs --out-dir typescript/pkg
# Output: typescript/pkg/

# Build docs site
cd site && npm run build && cd ..
# Output: site/dist/
```

Verify artifacts exist:

```bash
ls target/wheels/*.whl    # Should show at least one .whl file
ls typescript/pkg/*.wasm  # Should show the .wasm binary
ls site/dist/index.html   # Should exist
```

---

## Step 7: Commit the Version Bump

```bash
# Stage only the version files and CHANGELOG
git add Cargo.toml pyproject.toml package.json .claude-plugin/plugin.json CHANGELOG.md

# Review what we're committing
git diff --staged

# Commit
git commit -m "chore: release v${NEW_VERSION}"
```

The commit message format is exactly `chore: release v$VERSION`. No deviations.

---

## Step 8: Create a Signed Tag

```bash
# Create an annotated, signed tag
git tag -s "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"

# Verify the tag exists and is signed
git show "v${NEW_VERSION}" | head -10
```

If you don't have a GPG key configured for signing:
1. Do NOT use `git tag -a` (unsigned tag) for releases
2. Set up GPG signing: `git config user.signingkey YOUR_KEY_ID`
3. See GitHub docs: "Signing commits and tags"

---

## Step 9: Push Branch and Tag

```bash
# Push the release commit
git push origin main

# Push the tag (triggers release.yml workflow)
git push origin "v${NEW_VERSION}"
```

After pushing the tag, the `release.yml` GitHub Actions workflow will:
1. Build multi-platform wheels (Linux/macOS/Windows × Python 3.11/3.12/3.13)
2. Build WASM package
3. Create a GitHub Release with the CHANGELOG section as the release notes
4. Publish to PyPI (via `PYPI_TOKEN` secret)
5. Publish to npm (via `NPM_TOKEN` secret)

---

## Step 10: Monitor the Release Workflow

```bash
# Watch the release workflow progress
gh run watch $(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

If the workflow fails:
- **PyPI publish fails**: Check `PYPI_TOKEN` secret is valid and not expired
- **npm publish fails**: Check `NPM_TOKEN` secret; verify package name isn't taken
- **Wheel build fails**: Check that the Rust source compiles on all platforms

---

## Step 11: Verify Publication

```bash
# Verify PyPI
pip install claude-trace==${NEW_VERSION} --dry-run 2>&1 | head -5

# Verify GitHub Release
gh release view "v${NEW_VERSION}"

# Verify npm (may take 5-10 minutes to propagate)
npm info claude-trace version
```

If PyPI or npm packages are not visible after 15 minutes:
1. Check the release workflow logs: `gh run view <run-id>`
2. Check PyPI/npm package pages for errors
3. If needed, manually publish: `maturin publish` or `npm publish typescript/pkg/`

---

## Post-Release: Prepare for Next Development Cycle

After the release is verified:

```bash
# Bump plugin.json back to dev version for the next cycle
# Change "version": "X.Y.Z" → "X.Y+1.0-dev" in .claude-plugin/plugin.json
# (Or X+1.0.0-dev if this was a major release)

# Commit the dev marker
git add .claude-plugin/plugin.json
git commit -m "chore: begin development of v$(echo ${NEW_VERSION} | awk -F. '{print $1"."$2+1".0-dev"}')"
git push origin main
```

---

## Rollback Procedure

If you discover a critical bug immediately after release:

1. **Do NOT delete the PyPI package.** PyPI does not allow re-publishing the same version. Always release a patch (X.Y.Z+1).
2. **Do NOT delete the npm package.** Use `npm deprecate` to mark the bad version.
3. **Yank the GitHub Release** if the artifacts are broken: `gh release edit vX.Y.Z --draft`
4. Fix the bug. Then run the full release process for the patch version.

```bash
# Deprecate the bad npm version
npm deprecate "claude-trace@${BAD_VERSION}" "Critical bug — use ${PATCH_VERSION} instead"

# Create a bug fix PR, get it reviewed and merged, then release the patch
```
