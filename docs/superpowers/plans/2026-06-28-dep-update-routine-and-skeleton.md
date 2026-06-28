# Shared Routine Skeleton + dependency-update-routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the plugin's shared "Claude routine → `claude/` branch → Actions bridge → PR" pattern into reusable `skills/_shared/` assets, retrofit the two existing skills onto them, and add `dependency-update-routine` as the first skill built on the skeleton.

**Architecture:** Three shared artifacts — a guardrail preamble (prose), a token-substituted open-or-reuse-PR bridge workflow (YAML), and a reference doc tying them together. The two existing skills are edited to consume them (behavior-preserving: the e2e bridge reproduces its old generated workflow byte-for-byte except an intentional `checkout` bump; `auto-merge-pr` keeps its specialized fix/verdict bridge and only adopts the shared doc + preamble). `dependency-update-routine` is a scheduled routine that opens one PR per run of the dependency updates that are patch/minor, non-sensitive, and keep the project's check gate green.

**Tech Stack:** Markdown skill files, GitHub Actions YAML, `gh` CLI inside workflows. This is a Claude Code *plugin* — there is no application runtime and no unit-test framework. "Tests" are validation commands: `python3 -c "import yaml…"` / `json.load` for file validity, and `git diff` / `grep` for consistency and behavior-preservation checks.

## Global Constraints

- **Plugin name / marketplace name:** both `setup-repo` (skills install as `setup-repo@setup-repo`).
- **Branch convention (all routines):** routine pushes ONLY to `claude/<purpose>-<id>`; never the default branch, never a PR head directly.
- **`dependency-update-routine` branch glob:** `claude/dep-update-*` — must match verbatim across its `SKILL.md`, its `routine-prompt.md`, and the bridge token table.
- **PR title (dep-update):** `chore(deps): weekly safe updates`.
- **Safety policy (Approach C):** auto-include only patch/minor **and** non-sensitive **and** gate-green; ALWAYS escalate (never auto-include) majors, sensitive-category packages (auth, crypto, build toolchain, frameworks, native/ABI deps), and any `0.x` package; routine touches ONLY dependency manifests + lockfiles, never product code; if no gate detected, fall back to semver-only and say so in the PR body.
- **Ecosystem:** language-agnostic — detect whatever manifests/lockfiles exist (npm/pnpm/yarn, pip/poetry/uv, Cargo, go mod, bundler, …).
- **Cadence:** documented default **weekly** (cron set in the Claude web routine UI, NOT hardcoded in a workflow).
- **Escalation token:** uniform `NEEDS-HUMAN` marker in PR/commit bodies.
- **No merging:** routines never merge; a human merges the PR.
- **House style:** new `SKILL.md` files mirror the existing two — frontmatter (`name`, `description`), `## Overview`, ASCII `## Flow`, `## Setup procedure`, `## How to verify it works`, `## Guardrails`, `## Common mistakes` table.
- **Shared bridge template tokens (fixed set):** `{{WORKFLOW_NAME}}`, `{{BRANCH_GLOB}}`, `{{CONCURRENCY_PREFIX}}`, `{{PR_TITLE}}`, `{{DEFAULT_BODY}}`.

---

## File Structure

**Create:**
- `skills/_shared/templates/routine-prompt.preamble.md` — shared guardrail header pasted ahead of every routine prompt.
- `skills/_shared/templates/pr-bridge.yml` — token-substituted open-or-reuse-PR bridge workflow.
- `skills/_shared/routine-skeleton.md` — reference doc naming the pattern; cited by each skill.
- `skills/dependency-update-routine/SKILL.md`
- `skills/dependency-update-routine/templates/routine-prompt.md`

**Modify:**
- `skills/e2e-coverage-routine/SKILL.md` — cite skeleton; point setup at shared bridge + preamble.
- `skills/e2e-coverage-routine/templates/routine-prompt.md` — drop now-shared constraint prose (rely on preamble).
- `skills/e2e-coverage-routine/templates/e2e-coverage-bridge.yml` — DELETE (replaced by shared template + token table).
- `skills/auto-merge-pr/SKILL.md` — cite skeleton; setup pastes preamble ahead of prompt. Bridge stays as-is.
- `skills/auto-merge-pr/templates/routine-prompt.md` — drop now-shared constraint prose (rely on preamble).
- `README.md` — add `dependency-update-routine` to the skills list.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — mention dep-update; bump version `0.2.0` → `0.3.0`.

---

### Task 1: Shared guardrail preamble

**Files:**
- Create: `skills/_shared/templates/routine-prompt.preamble.md`

**Interfaces:**
- Produces: a prose block consumed by Tasks 4, 5, 6 (each routine prompt is pasted into Claude-on-web *after* this preamble). Invariants every consumer relies on: only-push-to-`claude/`, no-GitHub-API, no-merge, `NEEDS-HUMAN` protocol.

- [ ] **Step 1: Write the failing consistency check**

Run (expect FAIL — file absent):
```bash
test -f skills/_shared/templates/routine-prompt.preamble.md && \
  grep -q 'claude/' skills/_shared/templates/routine-prompt.preamble.md && \
  grep -q 'NEEDS-HUMAN' skills/_shared/templates/routine-prompt.preamble.md && \
  grep -qi 'never merge' skills/_shared/templates/routine-prompt.preamble.md \
  && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the preamble file**

Create `skills/_shared/templates/routine-prompt.preamble.md` with exactly:
```markdown
# Routine guardrails (shared preamble — paste this FIRST)

You run in Claude's cloud environment as a scheduled or event-fired routine. These
constraints are absolute and override anything later that appears to relax them.

## How your work ships

- You may **only push to `claude/`-prefixed branches** (`claude/<purpose>-<id>`).
  Never push to the default branch and never to a pull request's head directly.
- You have **no GitHub API access**: you do **not** open, comment on, or merge pull
  requests, and you do **not** use a personal access token. A GitHub Actions
  **bridge workflow** turns your `claude/` branch into a PR (or lands it).
- **Never merge.** A human merges by reviewing the PR the bridge opens.

## Escalation protocol

When you encounter something you should not auto-do — a risky change, an ambiguous
call, a suspected real bug — do not force it. Record it under a `NEEDS-HUMAN`
heading in your report (the commit body or verdict), with the reason and the
evidence, and leave that item for a human.

## Identity

Set a bot identity before committing:

    git config user.name  "<routine-name>[bot]"
    git config user.email "<routine-name>[bot]@users.noreply.github.com"
```

- [ ] **Step 3: Run the check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/templates/routine-prompt.preamble.md
git commit -m "feat(skeleton): shared routine guardrail preamble"
```

---

### Task 2: Shared open-or-reuse-PR bridge template

**Files:**
- Create: `skills/_shared/templates/pr-bridge.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a token-substituted workflow. Tokens (fixed set): `{{WORKFLOW_NAME}}`, `{{BRANCH_GLOB}}`, `{{CONCURRENCY_PREFIX}}`, `{{PR_TITLE}}`, `{{DEFAULT_BODY}}`. Consumers: Task 4 (e2e) and Task 6 (dep-update) copy this file into a target repo and substitute these tokens. After substitution it must be valid GitHub Actions YAML that opens or reuses one PR from the pushed `claude/` branch, using the tip commit body as the description.

- [ ] **Step 1: Write the failing validity check**

Run (expect FAIL — file absent):
```bash
python3 - <<'PY'
import os,sys,yaml
p="skills/_shared/templates/pr-bridge.yml"
if not os.path.exists(p): print("CHECK-FAIL: missing"); sys.exit()
raw=open(p).read()
for tok in ["{{WORKFLOW_NAME}}","{{BRANCH_GLOB}}","{{CONCURRENCY_PREFIX}}","{{PR_TITLE}}","{{DEFAULT_BODY}}"]:
    if tok not in raw: print("CHECK-FAIL: token",tok); sys.exit()
# substitute dummy values, then it must parse as YAML
sub=(raw.replace("{{WORKFLOW_NAME}}","Demo bridge")
        .replace("{{BRANCH_GLOB}}","claude/demo-*")
        .replace("{{CONCURRENCY_PREFIX}}","demo-bridge")
        .replace("{{PR_TITLE}}","demo: x")
        .replace("{{DEFAULT_BODY}}","demo body"))
yaml.safe_load(sub)
print("CHECK-PASS")
PY
```
Expected: `CHECK-FAIL: missing`

- [ ] **Step 2: Create the bridge template**

Create `skills/_shared/templates/pr-bridge.yml` with exactly:
```yaml
name: {{WORKFLOW_NAME}}

# A cloud Claude routine can only push to `claude/` branches and has no GitHub API
# access, so it cannot open a PR itself. This workflow fires when the routine pushes
# its branch and opens (or reuses) a PR into the default branch, using the tip
# commit's body as the PR description.
#
# This file is a TEMPLATE. Copy it into the target repo's .github/workflows/ and
# replace every {{TOKEN}} with the values your skill's SKILL.md specifies.

on:
  push:
    branches:
      - '{{BRANCH_GLOB}}'

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: {{CONCURRENCY_PREFIX}}-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  open-pr:
    if: ${{ github.event.deleted != true }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Open or reuse a PR for the routine's branch
        env:
          GH_TOKEN: ${{ github.token }}
          BRANCH: ${{ github.ref_name }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail

          base=$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name)

          # Reuse an existing open PR for this branch if there is one.
          existing=$(gh pr list --repo "$REPO" --head "$BRANCH" --state open \
            --json number --jq '.[0].number // empty')
          if [ -n "$existing" ]; then
            echo "PR #$existing already open for $BRANCH."
            exit 0
          fi

          # Use the tip commit body as the PR description (the routine writes its
          # report there); fall back to a default if it's empty.
          body=$(git log -1 --format=%b "origin/$BRANCH")
          if [ -z "$body" ]; then
            body="{{DEFAULT_BODY}}"
          fi

          gh pr create --repo "$REPO" --base "$base" --head "$BRANCH" \
            --title "{{PR_TITLE}}" \
            --body "$body"
```

- [ ] **Step 3: Run the validity check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/templates/pr-bridge.yml
git commit -m "feat(skeleton): token-substituted open-or-reuse-PR bridge template"
```

---

### Task 3: Shared skeleton reference doc

**Files:**
- Create: `skills/_shared/routine-skeleton.md`

**Interfaces:**
- Consumes: the two template files from Tasks 1–2 (by path).
- Produces: a doc each `SKILL.md` links to. Later tasks add a one-line "Built on the shared routine skeleton (`../_shared/routine-skeleton.md`)" reference; this task defines the link target and the section names they point at.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL — file absent):
```bash
test -f skills/_shared/routine-skeleton.md && \
  grep -q 'routine-prompt.preamble.md' skills/_shared/routine-skeleton.md && \
  grep -q 'pr-bridge.yml' skills/_shared/routine-skeleton.md && \
  grep -q 'Gate auto-detection' skills/_shared/routine-skeleton.md \
  && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the skeleton doc**

Create `skills/_shared/routine-skeleton.md` with exactly:
```markdown
# Routine Skeleton — shared pattern for setup-repo routine skills

Every routine-style skill in this plugin shares one shape. This doc names it so each
`SKILL.md` only has to describe what is *different* about its skill.

## The shape

    cron / GitHub event fires a Claude Code routine (bound to the repo on the web)
            |
            v
    routine inspects the repo, does its domain work, pushes claude/<purpose>-<id>
            |
            v
    a GitHub Actions BRIDGE turns that branch into a PR (or lands it) — because the
    cloud routine has no GitHub API access
            |
            v
    a human reviews and merges the PR

## Shared parts (use these — do not re-invent)

- **Branch convention.** The routine pushes only to `claude/<purpose>-<id>`. Never
  the default branch, never a PR head directly.
- **Guardrail preamble.** `templates/routine-prompt.preamble.md` — paste it FIRST,
  ahead of the skill's own routine prompt, when creating the routine on the web. It
  carries the only-push-to-`claude/`, no-API, no-merge, and `NEEDS-HUMAN` rules.
- **Open-a-PR bridge.** `templates/pr-bridge.yml` — a token-substituted workflow for
  routines that OPEN a fresh PR from their branch (dep-update, e2e-coverage, and the
  future docs-sync / flaky-test / security-triage). Copy it into the target repo's
  `.github/workflows/` and substitute `{{WORKFLOW_NAME}}`, `{{BRANCH_GLOB}}`,
  `{{CONCURRENCY_PREFIX}}`, `{{PR_TITLE}}`, `{{DEFAULT_BODY}}`.
  - Routines that instead LAND work onto an *existing* PR + post a verdict (today:
    `auto-merge-pr`) need a different, specialized bridge — they still follow the
    branch convention and preamble, but ship their own bridge workflow.
- **Escalation protocol.** Put anything the routine refuses to auto-do under a
  `NEEDS-HUMAN` heading in the commit/verdict body, with reason + evidence.
- **Gate auto-detection.** To find a project's check command: a `check` script in
  `package.json`, else the "Commands" section of `CLAUDE.md` / README, else a sane
  ecosystem default. Run it to verify the routine's changes before pushing.

## What each skill declares for itself

Its **trigger** (cron vs `pull_request` vs issue), its **inspection logic** (what it
reads and what it produces), and its **domain guardrails** (what it refuses to touch).
```

- [ ] **Step 3: Run the check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/routine-skeleton.md
git commit -m "docs(skeleton): routine-skeleton reference doc"
```

---

### Task 4: Retrofit e2e-coverage-routine onto the skeleton

**Files:**
- Delete: `skills/e2e-coverage-routine/templates/e2e-coverage-bridge.yml`
- Modify: `skills/e2e-coverage-routine/SKILL.md`
- Modify: `skills/e2e-coverage-routine/templates/routine-prompt.md`

**Interfaces:**
- Consumes: `_shared/templates/pr-bridge.yml` (Task 2), `_shared/templates/routine-prompt.preamble.md` (Task 1), `_shared/routine-skeleton.md` (Task 3).
- Produces: nothing new for later tasks. This is behavior-preserving — the workflow generated into a target repo must equal the old `e2e-coverage-bridge.yml` except the intentional `actions/checkout@v4`→`@v5` modernization.

- [ ] **Step 1: Write the behavior-preserving check**

This substitutes e2e's token values into the shared template and diffs against the OLD bridge (read from git). Run (expect FAIL now — the test asserts the *only* diff is the checkout line, but the file/edits don't exist yet):
```bash
python3 - <<'PY'
import subprocess,sys
old=subprocess.run(["git","show","HEAD:skills/e2e-coverage-routine/templates/e2e-coverage-bridge.yml"],
                   capture_output=True,text=True).stdout
tmpl=open("skills/_shared/templates/pr-bridge.yml").read()
sub=(tmpl.replace("{{WORKFLOW_NAME}}","E2E coverage PR bridge")
        .replace("{{BRANCH_GLOB}}","claude/e2e-coverage-*")
        .replace("{{CONCURRENCY_PREFIX}}","e2e-coverage-bridge")
        .replace("{{PR_TITLE}}","test(e2e): routine-proposed edge cases (${BRANCH#claude/})")
        .replace("{{DEFAULT_BODY}}",
                 "Automated E2E coverage pass — new end-to-end tests proposed by the "
                 "e2e-coverage routine. The `e2e` check will run them on this PR; "
                 "review and merge if green."))
import difflib
diff=[l for l in difflib.unified_diff(old.splitlines(),sub.splitlines(),lineterm="")
      if l.startswith(('+','-')) and not l.startswith(('+++','---'))]
# Allowed delta: exactly the checkout version bump + commentary/title wording.
print("DIFF LINES:"); print("\n".join(diff) if diff else "(none)")
# Acceptance: every -/+ pair is explainable (checkout v4->v5, name/title/body wording).
PY
```
Expected now: prints a diff (the substituted body/title/name wording differs from the original phrasing). **Use this output to reconcile token values in Step 2** so the only residual diff is `actions/checkout@v4` → `@v5`.

- [ ] **Step 2: Reconcile token values, then delete the old bridge**

Adjust the `{{PR_TITLE}}` / `{{DEFAULT_BODY}}` / `{{WORKFLOW_NAME}}` / `{{CONCURRENCY_PREFIX}}` strings you will document in `SKILL.md` (Step 3) until the Step 1 diff is reduced to exactly the checkout line. The original values to match are, verbatim from the old bridge:
- name: `E2E coverage PR bridge`
- glob: `claude/e2e-coverage-*`
- concurrency prefix: `e2e-coverage-bridge`
- title: `test(e2e): routine-proposed edge cases (${BRANCH#claude/})`
- default body: `Automated E2E coverage pass — new end-to-end tests proposed by the e2e-coverage routine. The \`e2e\` check will run them on this PR; review and merge if green.`

Then delete the now-redundant concrete bridge:
```bash
git rm skills/e2e-coverage-routine/templates/e2e-coverage-bridge.yml
```

- [ ] **Step 3: Update the e2e SKILL.md setup to use the shared bridge + preamble**

In `skills/e2e-coverage-routine/SKILL.md`:
1. Add, near the top under the title, the line:
   `> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md).`
2. In the setup step that currently says to copy `templates/e2e-coverage-bridge.yml`, replace it with: copy `../_shared/templates/pr-bridge.yml` into `.github/workflows/e2e-coverage-bridge.yml` and substitute the token table (the five values from Step 2, shown as a markdown table).
3. In the step that creates the routine, change "paste `routine-prompt.md`" to "paste `../_shared/templates/routine-prompt.preamble.md` first, then `templates/routine-prompt.md`".

- [ ] **Step 4: Trim the e2e routine prompt's now-shared prose**

In `skills/e2e-coverage-routine/templates/routine-prompt.md`, delete the `## Hard constraints` bullets that duplicate the preamble (only-push-to-`claude/`, no-API/no-PR/no-merge). KEEP the e2e-specific constraint "only add or edit tests; never change product code." Add one line under the title: `(The shared guardrail preamble is pasted ahead of this prompt — see _shared/templates/routine-prompt.preamble.md.)`

- [ ] **Step 5: Run the behavior-preserving check to verify it passes**

Re-run the Step 1 command. Expected: `DIFF LINES:` followed by exactly the two lines:
```
-      - uses: actions/checkout@v4
+      - uses: actions/checkout@v5
```
Also confirm the preamble invariants are no longer duplicated in the trimmed prompt:
```bash
grep -c 'no GitHub API access' skills/e2e-coverage-routine/templates/routine-prompt.md
```
Expected: `0`

- [ ] **Step 6: Commit**

```bash
git add -A skills/e2e-coverage-routine
git commit -m "refactor(e2e-coverage): adopt shared skeleton bridge + preamble

Behavior-preserving: generated bridge differs only by actions/checkout v4->v5."
```

---

### Task 5: Retrofit auto-merge-pr onto the skeleton (doc + preamble only)

**Files:**
- Modify: `skills/auto-merge-pr/SKILL.md`
- Modify: `skills/auto-merge-pr/templates/routine-prompt.md`

**Interfaces:**
- Consumes: `_shared/routine-skeleton.md` (Task 3), `_shared/templates/routine-prompt.preamble.md` (Task 1).
- Produces: nothing for later tasks. The specialized `pr-fix-bridge.yml` (land-onto-existing-PR + verdict + status) is intentionally NOT changed — it is a different flavor than the shared open-a-PR bridge.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL — edits not made):
```bash
grep -q 'routine-skeleton.md' skills/auto-merge-pr/SKILL.md && \
  grep -q 'routine-prompt.preamble.md' skills/auto-merge-pr/SKILL.md \
  && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Add the skeleton reference + preamble paste step to SKILL.md**

In `skills/auto-merge-pr/SKILL.md`:
1. Add under the title: `> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md). This skill uses the skeleton's guardrail preamble but ships its own specialized land-fixes-and-verdict bridge (not the shared open-a-PR bridge).`
2. In setup step 3 (create the routine), change "paste the full text of `templates/routine-prompt.md`" to "paste `../_shared/templates/routine-prompt.preamble.md` first, then the full text of `templates/routine-prompt.md`".

- [ ] **Step 3: Trim the auto-merge routine prompt's now-shared prose**

In `skills/auto-merge-pr/templates/routine-prompt.md`, in the `## How your changes ship (READ FIRST)` section, delete the sentences that duplicate the preamble (may only push to `claude/`-prefixed branches; no PAT; may not open/merge a PR). KEEP the skill-specific mechanics: the two branches `claude/pr-${PR_NUMBER}-fix` and `claude/pr-${PR_NUMBER}-verdict` and what the bridge does with them. Add: `(The shared guardrail preamble is pasted ahead of this prompt.)`

- [ ] **Step 4: Run the check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`. Then confirm the fix/verdict mechanics survived the trim:
```bash
grep -q 'claude/pr-${PR_NUMBER}-fix' skills/auto-merge-pr/templates/routine-prompt.md && \
  grep -q 'claude/pr-${PR_NUMBER}-verdict' skills/auto-merge-pr/templates/routine-prompt.md \
  && echo MECHANICS-OK || echo MECHANICS-MISSING
```
Expected: `MECHANICS-OK`

- [ ] **Step 5: Commit**

```bash
git add -A skills/auto-merge-pr
git commit -m "refactor(auto-merge-pr): cite shared skeleton, adopt guardrail preamble"
```

---

### Task 6: dependency-update-routine skill

**Files:**
- Create: `skills/dependency-update-routine/SKILL.md`
- Create: `skills/dependency-update-routine/templates/routine-prompt.md`

**Interfaces:**
- Consumes: `_shared/templates/pr-bridge.yml`, `_shared/templates/routine-prompt.preamble.md`, `_shared/routine-skeleton.md`.
- Produces: the third installed skill. Bridge is the shared `pr-bridge.yml` with the dep-update token table (no separate bridge file).

- [ ] **Step 1: Write the failing consistency check**

Run (expect FAIL — files absent):
```bash
SK=skills/dependency-update-routine
test -f $SK/SKILL.md && test -f $SK/templates/routine-prompt.md && \
  grep -q 'claude/dep-update-\*' $SK/SKILL.md && \
  grep -q 'claude/dep-update-' $SK/templates/routine-prompt.md && \
  grep -q 'chore(deps): weekly safe updates' $SK/SKILL.md && \
  grep -q 'routine-prompt.preamble.md' $SK/SKILL.md && \
  grep -q 'routine-skeleton.md' $SK/SKILL.md && \
  grep -qi 'sensitive' $SK/templates/routine-prompt.md \
  && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the routine prompt**

Create `skills/dependency-update-routine/templates/routine-prompt.md` with exactly:
```markdown
# Dependency Update Routine — Mandate

(The shared guardrail preamble is pasted ahead of this prompt — only push to
`claude/` branches, no GitHub API, never merge, escalate via `NEEDS-HUMAN`.)

You are a scheduled routine that keeps a repository's dependencies current and safe.
Each run you propose ONE pull request containing only the updates that are low-risk
and verified green, and you list everything risky for a human instead of applying it.

## Hard constraints

- You **only edit dependency manifests and lockfiles** (e.g. `package.json` +
  lockfile, `pyproject.toml`/`requirements*.txt`, `Cargo.toml`/`Cargo.lock`,
  `go.mod`/`go.sum`, `Gemfile`/`Gemfile.lock`). You must **not** change product
  code. If an update needs code changes to pass the gate, do not make them —
  escalate that dependency.
- One PR per run. If nothing is safely updatable, push nothing and end.

## Steps

1. **Sync.** Fetch and check out the latest default branch. Set your bot identity.

2. **Detect ecosystems.** Find every dependency manifest + lockfile in the repo. For
   each, list outdated direct dependencies and the latest compatible version (use the
   ecosystem's own tooling, e.g. `npm outdated`, `pip list --outdated`,
   `cargo update --dry-run`, `go list -m -u all`).

3. **Classify each outdated dependency.**
   - **Candidate (auto-batch):** the bump is **patch or minor** AND the package is
     **not sensitive** (see list) AND it is **not** a `0.x` version.
   - **Escalate (never auto-apply):** any **major** bump; any **sensitive** package;
     any `0.x` package (where a minor bump can be breaking).
   - Sensitive categories: authentication/authorization, cryptography, the build
     toolchain/bundler/compiler, web/app frameworks, and native/ABI bindings. When
     unsure whether a package is sensitive, treat it as sensitive and escalate.

4. **Apply candidates.** Update all candidates together and regenerate the
   lockfile(s). Touch nothing outside manifests/lockfiles.

5. **Run the gate ONCE.** Determine the project's check command (a `check` script in
   `package.json`, else the "Commands" section of `CLAUDE.md`/README, else the
   ecosystem default). Install deps and run it against the updated state.
   - **Green:** keep the whole batch.
   - **Red:** identify the offending update, move it to `NEEDS-HUMAN`, and re-run the
     gate on the remaining batch until green (or empty).
   - **No gate detected:** skip empirical verification, keep the semver-classified
     batch, and state plainly in the report that no gate was run.

6. **Push.** Commit the manifest/lockfile changes on a new branch
   `claude/dep-update-<UTC-date-or-run-id>`. Make the **commit body** your report —
   the bridge uses it as the PR description. Format:

       ## Included (safe: patch/minor, gate green)

       | package | ecosystem | old -> new |
       | --- | --- | --- |
       | <name> | <eco> | <old> -> <new> |

       ## NEEDS-HUMAN (majors / sensitive / failed the gate)

       - <name> <old> -> <new> (<reason>): <one-line changelog/risk summary>

   If the gate could not be run, add a line: `No check gate detected — updates were
   classified by semver only and NOT verified by a build.`

   If there are no safe updates this run, push nothing and end.

## Quality bar

- Every included update is patch/minor, non-sensitive, non-`0.x`, and the batch's
  gate is green.
- No product-code edits. No more than one PR.
- Every escalated item has a reason and a short risk summary in the report.
```

- [ ] **Step 3: Create the SKILL.md**

Create `skills/dependency-update-routine/SKILL.md` with exactly:
```markdown
---
name: dependency-update-routine
description: Use when setting up a scheduled routine that keeps a GitHub repo's dependencies current — each run it opens one PR with the patch/minor updates that pass the project's check gate, and lists majors and sensitive packages as NEEDS-HUMAN for a human. Language-agnostic (npm/pip/cargo/go/…); built on the shared routine skeleton.
---

# dependency-update-routine — Scheduled Safe Dependency Updates

> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md).

## Overview

Provisions a self-maintaining dependency-update loop in a target repo. A **scheduled
Claude Code routine** (cron, default weekly) detects every dependency ecosystem in
the repo, classifies outdated packages, applies only the safe ones, verifies them
against the project's check gate, and pushes a `claude/dep-update-<id>` branch. The
shared **open-a-PR bridge** turns that branch into one PR. Majors, sensitive
packages, and anything that fails the gate are listed as `NEEDS-HUMAN` instead of
being applied. A human reviews and merges.

The routine **only edits manifests and lockfiles** — never product code.

## Flow

    cron fires the routine (Claude Code on the web, schedule-bound to the repo)
            |
            v
    routine: detect ecosystems -> classify outdated deps ->
             apply patch/minor non-sensitive candidates -> run gate ONCE
             (red -> drop offender to NEEDS-HUMAN, re-run remainder) ->
             push claude/dep-update-<id> (report in the commit body)
            |
            v
    pr-bridge.yml: opens ONE PR, using the commit body as the description
            |
            v
    human reviews and merges

## Safety policy (Approach C — semver scopes, gate confirms)

- **Auto-included** only if: bump is **patch/minor** AND not **sensitive** AND not a
  `0.x` package AND the post-update gate is **green**.
- **Always escalated** (never auto-included, regardless of the gate): **majors**, the
  **sensitive** categories (auth, crypto, build toolchain, frameworks, native/ABI),
  and any `0.x` package.
- If **no gate** is detected, the routine falls back to semver-only classification
  and says so in the PR body, so the reduced assurance is visible.

## Components

- `templates/routine-prompt.md` — the routine's mandate (pasted into the web routine
  after the shared preamble).
- The bridge is the shared `../_shared/templates/pr-bridge.yml`, copied into the
  target repo with this token table:

  | token | value |
  | --- | --- |
  | `{{WORKFLOW_NAME}}` | `Dependency update PR bridge` |
  | `{{BRANCH_GLOB}}` | `claude/dep-update-*` |
  | `{{CONCURRENCY_PREFIX}}` | `dep-update-bridge` |
  | `{{PR_TITLE}}` | `chore(deps): weekly safe updates` |
  | `{{DEFAULT_BODY}}` | `Automated dependency update — safe patch/minor updates that pass the project's check gate. Review and merge if green.` |

## Repo prerequisites

- **Actions write permission.** Settings → Actions → General → Workflow permissions →
  **Read and write** (the bridge opens the PR with the Actions token).
- **The Claude GitHub App is installed** on the repo/org, so the integration can run
  the routine and the routine can push `claude/` branches.

## Setup procedure

1. **Copy the bridge.** Copy `../_shared/templates/pr-bridge.yml` into the target
   repo's `.github/workflows/dep-update-bridge.yml` and replace every `{{TOKEN}}`
   with the value from the token table above. Commit on the **default branch**.
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`, as the instructions. Bind it to the target repo and
   grant at least `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set the schedule.** Configure the routine to run on a cron — **weekly** is the
   recommended default.
4. **(Recommended) Auto-delete merged branches.** Settings → General → Pull Requests →
   **Automatically delete head branches**, so merged `claude/dep-update-*` branches
   are cleaned up.

## How to verify it works

On a throwaway repo with one deliberately-outdated **minor** dependency and one
outdated **major**, trigger a routine run, then:

```bash
gh pr list --head 'claude/dep-update-' --state open
gh pr view <N> --json title,body
# expect: the minor in the "Included" table (gate green),
#         the major under "NEEDS-HUMAN".
```

## Guardrails (why it is safe)

- The routine pushes only to `claude/` branches and never merges.
- It edits only manifests/lockfiles — never product code.
- Majors, sensitive packages, and `0.x` packages are always escalated, never
  auto-applied; a green gate cannot wave a sensitive major through.
- One PR per run; an empty run (nothing safe to update) pushes nothing.
- Fork PRs are not supported (Actions cannot push to a fork's branch).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| No PR ever appears | Routine not scheduled/connected, or there were no safe updates (an empty run is normal). Check the routine's run history. |
| Bridge never fires | It triggers on push to `claude/dep-update-*`; the pushed branch must carry `.github/workflows/`. The routine bases its branch on the default branch (which has them). |
| Bridge fails with **403** | Actions token is read-only. Settings → Actions → General → Workflow permissions → **Read and write**. |
| A major/sensitive update got auto-applied | The routine prompt was edited to weaken the classification. Restore the "always escalate majors/sensitive/0.x" rule in Step 3. |
| PR body says no gate was run | No `check` command was detected. Add a `check` script or name the command in `CLAUDE.md`'s Commands section. |
```

- [ ] **Step 4: Run the consistency check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`. Then confirm the bridge token table substitutes into valid YAML:
```bash
python3 - <<'PY'
import yaml
tmpl=open("skills/_shared/templates/pr-bridge.yml").read()
sub=(tmpl.replace("{{WORKFLOW_NAME}}","Dependency update PR bridge")
        .replace("{{BRANCH_GLOB}}","claude/dep-update-*")
        .replace("{{CONCURRENCY_PREFIX}}","dep-update-bridge")
        .replace("{{PR_TITLE}}","chore(deps): weekly safe updates")
        .replace("{{DEFAULT_BODY}}","Automated dependency update — safe patch/minor updates that pass the project's check gate. Review and merge if green."))
yaml.safe_load(sub); print("YAML-OK")
PY
```
Expected: `YAML-OK`

- [ ] **Step 5: Commit**

```bash
git add skills/dependency-update-routine
git commit -m "feat(dependency-update-routine): scheduled safe dependency updates"
```

---

### Task 7: Update plugin metadata + README

**Files:**
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: the skill created in Task 6 (by name).
- Produces: the user-facing listing; final task.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL — edits not made):
```bash
grep -q 'dependency-update-routine' README.md && \
  grep -q 'dependency-update-routine' .claude-plugin/plugin.json && \
  python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('JSON-OK')" && \
  grep -q '0.3.0' .claude-plugin/plugin.json \
  && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Add dependency-update-routine to README skills list**

In `README.md`, add a bullet to the `## Skills` list:
```markdown
- **dependency-update-routine** — set up a scheduled routine that opens one PR per
  run with the patch/minor dependency updates that pass the project's check gate,
  listing majors and sensitive packages as `NEEDS-HUMAN`. Language-agnostic; built on
  the shared routine skeleton. See
  [`skills/dependency-update-routine/SKILL.md`](skills/dependency-update-routine/SKILL.md).
```
Also add to the `## Layout` tree a `_shared/` entry and the `dependency-update-routine/` entry alongside the existing skills.

- [ ] **Step 3: Bump version and mention dep-update in the manifests**

In `.claude-plugin/plugin.json`: change `"version": "0.2.0"` to `"version": "0.3.0"` and extend the `description` to mention `dependency-update-routine (scheduled safe dependency updates)`.

In `.claude-plugin/marketplace.json`: extend the plugin `description` the same way (mention dependency-update-routine).

- [ ] **Step 4: Run the check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`

- [ ] **Step 5: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs: list dependency-update-routine; bump plugin to 0.3.0"
```

---

## Final verification (after all tasks)

- [ ] **All YAML templates parse (after token substitution):** re-run the Task 2 and Task 6 Step-4 YAML checks. Expected: `CHECK-PASS` / `YAML-OK`.
- [ ] **All JSON valid:** `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('OK')"`.
- [ ] **e2e behavior preserved:** re-run the Task 4 Step-1 check; the only diff is `actions/checkout@v4`→`@v5`.
- [ ] **Three skills present:** `ls skills` shows `_shared`, `auto-merge-pr`, `e2e-coverage-routine`, `dependency-update-routine`.
- [ ] **No stray `{{TOKEN}}` left in any non-template file:** `grep -rn '{{' skills --include=SKILL.md` returns nothing (tokens live only in `_shared/templates/pr-bridge.yml` and token tables, which are fenced).
```
