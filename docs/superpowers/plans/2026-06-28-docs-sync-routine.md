# docs-sync-routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `docs-sync-routine` skill — a cron-fired Claude routine that fixes verifiable code/doc drift via a PR, or files a tracking issue for drift it can verify but not safely auto-fix.

**Architecture:** Built on the existing `skills/_shared/` routine skeleton (guardrail preamble + `routine-skeleton.md`). It ships a skill-specific `docs-sync-bridge.yml` that routes a pushed `claude/docs-sync-*` branch to a **PR** (when it carries doc edits) or to an **open/updated tracking issue** (when it's a findings-only empty commit). The routine prompt implements checker-anchored detection with LLM-authored fixes (Approach C); the routine edits only doc files.

**Tech Stack:** Markdown skill files, GitHub Actions YAML, `gh` CLI. This is a Claude Code *plugin* — no app runtime, no unit-test framework. "Tests" are validation commands: `python3 -c "import yaml…"` / `json.load` for validity, `bash -n` for the bridge's shell syntax, and `grep` for consistency.

## Global Constraints

- **Plugin / marketplace name:** both `setup-repo`.
- **Branch glob:** `claude/docs-sync-*` — identical across `SKILL.md`, `routine-prompt.md`, and the bridge.
- **Fixed tracking-issue title:** `docs-sync: verified doc drift pending review` (used by the bridge to dedupe; on repeat runs it updates the issue body).
- **Drift policy:** verifiable mismatches only; **code is source of truth**; auto-fix only when verified + unambiguous + re-verified green; always escalate ambiguous/judgment/generated-without-generator/would-need-code-change as `NEEDS-HUMAN`.
- **Edits scope:** doc files only (`README*`, `CLAUDE.md`, `docs/**`, generated-API outputs via the project's own doc-gen command). Never product code.
- **Per-run output:** one PR **or** one deduped issue; a no-drift run pushes nothing.
- **Cadence:** documented default **weekly** (cron set in the web routine UI, not hardcoded).
- **Escalation token:** `NEEDS-HUMAN`.
- **House style:** `SKILL.md` mirrors siblings — frontmatter (`name`, `description`), `## Overview`, ASCII `## Flow`, `## Setup procedure`, `## How to verify it works`, `## Guardrails`, `## Common mistakes` table.
- **Bridge permissions:** `contents: write`, `pull-requests: write`, `issues: write`.
- **Available tooling:** `python3`+`pyyaml`, `node`, `ruby`, `bash`. No actionlint/yamllint/shellcheck.

---

## File Structure

**Create:**
- `skills/docs-sync-routine/templates/docs-sync-bridge.yml` — PR-or-issue routing bridge.
- `skills/docs-sync-routine/templates/routine-prompt.md` — the routine mandate.
- `skills/docs-sync-routine/SKILL.md` — setup + reference.

**Modify:**
- `skills/_shared/routine-skeleton.md` — one line noting issue-reporting routines ship their own PR-or-issue bridge for now.
- `README.md` — list the new skill + layout entry.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — mention docs-sync; bump `0.3.0` → `0.4.0`.

---

### Task 1: PR-or-issue routing bridge + skeleton note

**Files:**
- Create: `skills/docs-sync-routine/templates/docs-sync-bridge.yml`
- Modify: `skills/_shared/routine-skeleton.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a workflow that fires on push to `claude/docs-sync-*`. If the branch's tree differs from the default branch → opens/reuses a PR (tip commit body as description). If the tree is identical (empty commit) → opens or updates the issue titled exactly `docs-sync: verified doc drift pending review` with the tip commit body. Later tasks (prompt, SKILL) must use this same glob and issue title.

- [ ] **Step 1: Write the failing checks**

Run (expect FAIL — file absent):
```bash
F=skills/docs-sync-routine/templates/docs-sync-bridge.yml
test -f "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the bridge**

Create `skills/docs-sync-routine/templates/docs-sync-bridge.yml` with exactly:
```yaml
name: docs-sync PR-or-issue bridge

# The docs-sync routine can only push to `claude/` branches and has no GitHub API
# access. This workflow fires when it pushes a claude/docs-sync-* branch and routes:
#   - branch carries doc edits (tree differs from the default branch) -> open a PR
#   - findings-only empty commit (tree identical)                     -> open/update
#     the single tracking issue
# In both cases the tip commit body is the report (the routine writes it there).

on:
  push:
    branches:
      - 'claude/docs-sync-*'

permissions:
  contents: write
  pull-requests: write
  issues: write

concurrency:
  group: docs-sync-bridge-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  route:
    if: ${{ github.event.deleted != true }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Open a PR (doc edits) or open/update the tracking issue (findings only)
        env:
          GH_TOKEN: ${{ github.token }}
          BRANCH: ${{ github.ref_name }}
          REPO: ${{ github.repository }}
          ISSUE_TITLE: "docs-sync: verified doc drift pending review"
        run: |
          set -euo pipefail

          base=$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name)
          git fetch origin "$base" "$BRANCH"

          # The report is the pushed branch's tip commit body (referenced via a plain
          # variable, so backticks / $ in it are never re-expanded by the shell).
          report=$(git log -1 --format=%b "origin/$BRANCH")

          # Decide PR vs issue from what THIS branch changed since it forked from the
          # default branch. Diffing against the merge-base (not the live base tip) keeps
          # the decision correct even if the default branch advances after the push, and
          # captures every commit the routine added to the branch.
          fork=$(git merge-base "origin/$base" "origin/$BRANCH")
          if [ -n "$(git diff --name-only "$fork" "origin/$BRANCH")" ]; then
            # Real doc edits -> open or reuse a PR.
            existing=$(gh pr list --repo "$REPO" --head "$BRANCH" --state open \
              --json number --jq '.[0].number // empty')
            if [ -n "$existing" ]; then
              echo "PR #$existing already open for $BRANCH."
              exit 0
            fi
            if [ -z "$report" ]; then
              report="Automated docs-sync — verified documentation fixes. Review and merge if correct."
            fi
            gh pr create --repo "$REPO" --base "$base" --head "$BRANCH" \
              --title "docs: sync docs with code (${BRANCH#claude/})" \
              --body "$report"
          else
            # Findings-only empty commit -> open or update the single tracking issue.
            if [ -z "$report" ]; then
              report="docs-sync found verified drift but recorded no report body."
            fi
            num=$(gh issue list --repo "$REPO" --state open --search "in:title \"$ISSUE_TITLE\"" \
              --json number,title --jq "map(select(.title==\"$ISSUE_TITLE\")) | .[0].number // empty")
            if [ -n "$num" ]; then
              gh issue edit "$num" --repo "$REPO" --body "$report"
              echo "Updated tracking issue #$num."
            else
              gh issue create --repo "$REPO" --title "$ISSUE_TITLE" --body "$report"
            fi
          fi
```

- [ ] **Step 3: Add the skeleton note**

In `skills/_shared/routine-skeleton.md`, under the "Open-a-PR bridge" bullet (the sub-bullet that begins "Routines that instead LAND work…"), add a second sub-bullet:
```markdown
  - Routines that report findings as a GitHub **issue** when there is nothing to PR
    (e.g. docs-sync) ship their own **PR-or-issue** bridge for now; it is a candidate
    to promote into `templates/` once a second such routine exists.
```

- [ ] **Step 4: Verify YAML validity + shell syntax + both routing paths**

Run:
```bash
F=skills/docs-sync-routine/templates/docs-sync-bridge.yml
python3 - <<PY
import yaml
d=yaml.safe_load(open("$F").read())
perms=d['permissions']
assert perms=={'contents':'write','pull-requests':'write','issues':'write'}, perms
run=d['jobs']['route']['steps'][1]['run']
open('/tmp/docs_sync_run.sh','w').write(run)
print("YAML-OK; permissions OK")
PY
bash -n /tmp/docs_sync_run.sh && echo "SHELL-SYNTAX-OK"
grep -q 'gh pr create' /tmp/docs_sync_run.sh && grep -q 'gh issue create' /tmp/docs_sync_run.sh && \
  grep -q 'gh issue edit' /tmp/docs_sync_run.sh && grep -q 'git diff --name-only' /tmp/docs_sync_run.sh && \
  echo "BOTH-ROUTES-PRESENT"
grep -q 'docs-sync: verified doc drift pending review' "$F" && echo "ISSUE-TITLE-OK"
```
Expected: `YAML-OK; permissions OK`, `SHELL-SYNTAX-OK`, `BOTH-ROUTES-PRESENT`, `ISSUE-TITLE-OK`.

- [ ] **Step 5: Commit**

```bash
git add skills/docs-sync-routine/templates/docs-sync-bridge.yml skills/_shared/routine-skeleton.md
git commit -m "feat(docs-sync): PR-or-issue routing bridge + skeleton note"
```

---

### Task 2: Routine prompt

**Files:**
- Create: `skills/docs-sync-routine/templates/routine-prompt.md`

**Interfaces:**
- Consumes: the shared preamble (pasted ahead at setup time); the bridge's `claude/docs-sync-*` branch + empty-commit convention from Task 1.
- Produces: the mandate the human pastes into the web routine. Must push `claude/docs-sync-<id>`, use `git commit --allow-empty` for findings-only runs, and write the report in the commit body in the exact format the bridge surfaces.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL — file absent):
```bash
F=skills/docs-sync-routine/templates/routine-prompt.md
test -f "$F" && grep -q 'claude/docs-sync-' "$F" && grep -q -- '--allow-empty' "$F" && \
  grep -qi 'source of truth' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the routine prompt**

Create `skills/docs-sync-routine/templates/routine-prompt.md` with exactly:
```markdown
# Docs Sync Routine — Mandate

(The shared guardrail preamble is pasted ahead of this prompt — only push to
`claude/` branches, no GitHub API, never merge, escalate via `NEEDS-HUMAN`.)

You are a scheduled routine that keeps a repository's documentation in sync with its
code. Each run you detect **verifiable** drift between docs and code, fix what you can
fix unambiguously, and report the rest. You **only edit documentation files** —
`README*`, `CLAUDE.md`, files under `docs/`, and generated-API output (only by
re-running the project's own doc-gen command). You must **not** edit product code.

**Code is the source of truth.** Docs are made to match code, never the reverse. When
it is genuinely ambiguous whether the doc or the code is wrong (e.g. a documented env
var the code never reads — possibly a code bug), do not guess — escalate it.

## Steps

1. **Sync.** Fetch and check out the latest default branch. Set your bot identity.

2. **Detect (the check battery).** Across `README*`, `CLAUDE.md`, and `docs/**`, find
   only drift that has a deterministic code anchor:
   1. **Command/script refs** — commands shown in docs (`npm`/`pnpm run X`, `make Y`,
      `just Z`, …) with no matching script/target.
   2. **Path refs** — file paths / relative links in docs that do not resolve.
   3. **Env vars (both directions)** — documented but read nowhere in code (stale), or
      read by code but undocumented (missing).
   4. **Runnable code blocks** — fenced blocks tagged runnable that error when run.
   5. **API signatures** — function/CLI signatures quoted in docs that do not match
      source.
   6. **Generated API reference** — if an API doc section is tool-generated (a
      detectable generator config/command) and stale, regenerate via that command; if
      no generator is detectable, escalate.

3. **Classify.**
   - **Auto-fix candidate:** the drift is verified AND the correction is unambiguous
     (a single obvious replacement, or a regen via a detected command).
   - **Escalate (`NEEDS-HUMAN`):** ambiguous corrections (several candidate paths), a
     broken example needing a real rewrite, generated docs with no detectable
     generator, or anything whose only fix would be a code change.

4. **Apply** the candidate fixes to doc files only.

5. **Re-verify.** Re-run the relevant check on each edited doc so the fix actually
   resolves the drift and introduces no new broken reference. Drop any fix that does
   not re-verify and escalate it instead.

6. **Commit + push `claude/docs-sync-<UTC-date-or-run-id>`.** Make the **commit body**
   your report in this exact format:

       ## Fixed (verified mechanical doc corrections)
       - <file>: <what drifted> -> <fix>  (<which check caught it>)

       ## NEEDS-HUMAN (verified drift, not safely auto-fixable)
       - <file>: <drift>  (<check>): <why a human is needed / what is ambiguous>

   - If you applied fixes, commit the doc edits normally (the report is the body).
   - If you have **only** escalations and no fixes, make an **empty** commit so the
     report still ships: `git commit --allow-empty`. The bridge will turn an
     empty-commit branch into a tracking issue instead of a PR.
   - If there is **no drift at all** this run, push nothing and end.

## Quality bar

- Every fix traces to one of the six checks and was re-verified after applying.
- No product-code edits. No fabricated content. One push per run.
- Every escalated item names the file, the check, and why it needs a human.
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/docs-sync-routine/templates/routine-prompt.md
test -f "$F" && grep -q 'claude/docs-sync-' "$F" && grep -q -- '--allow-empty' "$F" && \
  grep -qi 'source of truth' "$F" && grep -q 'NEEDS-HUMAN' "$F" && \
  grep -q '## Fixed (verified mechanical doc corrections)' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/docs-sync-routine/templates/routine-prompt.md
git commit -m "feat(docs-sync): routine mandate (verifiable drift + PR-or-issue report)"
```

---

### Task 3: SKILL.md

**Files:**
- Create: `skills/docs-sync-routine/SKILL.md`

**Interfaces:**
- Consumes: the bridge (Task 1) and prompt (Task 2) by path; the shared preamble + skeleton doc.
- Produces: the installed skill's user-facing setup doc.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL — file absent):
```bash
F=skills/docs-sync-routine/SKILL.md
test -f "$F" && grep -q 'claude/docs-sync-\*' "$F" && grep -q 'routine-skeleton.md' "$F" && \
  grep -q 'routine-prompt.preamble.md' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the SKILL.md**

Create `skills/docs-sync-routine/SKILL.md` with exactly:
```markdown
---
name: docs-sync-routine
description: Use when setting up a scheduled routine that keeps a repo's docs in sync with its code — each run it fixes verifiable code/doc drift (broken command/path refs, stale env vars, mismatched API signatures, failing examples, stale generated API docs) via a PR, and files a tracking issue for verified drift it cannot safely auto-fix. Built on the shared routine skeleton.
---

# docs-sync-routine — Scheduled Code/Doc Drift Sync

> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md).

## Overview

Provisions a self-maintaining docs loop in a target repo. A **scheduled Claude Code
routine** (cron, default weekly) detects **verifiable** drift between the repo's code
and its docs (`README*`, `CLAUDE.md`, `docs/**`, generated API reference), fixes what
it can fix unambiguously, and pushes a `claude/docs-sync-<id>` branch. A
**PR-or-issue bridge** then opens a PR (when the branch has doc edits) or opens/updates
a single tracking issue (when the run only has findings). The routine **only edits
docs** — never product code — and **code is the source of truth**.

## Flow

    cron fires the routine (Claude Code on the web, schedule-bound to the repo)
            |
            v
    routine: run the 6-check battery -> classify (unambiguous fix vs escalate) ->
             apply doc-only fixes -> re-verify -> commit/push claude/docs-sync-<id>
             (doc edits, or an --allow-empty findings commit); report in commit body
            |
            v
    docs-sync-bridge.yml routes on tree-vs-base:
      doc edits      -> open/reuse a PR  (body = report)
      empty commit   -> open/update the "docs-sync: verified doc drift pending
                        review" issue (body = report)
            |
            v
    human reviews the PR / triages the issue

## The check battery (verifiable drift only)

1. **Command/script refs** — documented commands with no matching script/target.
2. **Path refs** — file paths / relative links in docs that do not resolve.
3. **Env vars** — documented but unused in code (stale), or used by code but
   undocumented (missing).
4. **Runnable code blocks** — fenced runnable blocks that error when executed.
5. **API signatures** — signatures quoted in docs that do not match source.
6. **Generated API reference** — regenerate via the project's doc-gen command if
   stale; escalate if no generator is detectable.

Auto-fix only when verified AND unambiguous AND the fix re-verifies; everything else
is escalated as `NEEDS-HUMAN`.

## Components

- `templates/routine-prompt.md` — the routine mandate (pasted after the shared
  preamble).
- `templates/docs-sync-bridge.yml` — the PR-or-issue bridge. Copied into
  `.github/workflows/` as-is (no token substitution).

## Repo prerequisites

- **Actions write permission.** Settings → Actions → General → Workflow permissions →
  **Read and write** (the bridge opens PRs and issues with the Actions token).
- **The Claude GitHub App is installed** on the repo/org, so the integration can run
  the routine and the routine can push `claude/` branches.

## Setup procedure

1. **Copy the bridge.** Copy `templates/docs-sync-bridge.yml` into the target repo's
   `.github/workflows/`. Commit on the **default branch**.
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`, as the instructions. Bind it to the target repo and
   grant at least `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set the schedule.** Configure the routine to run on a cron — **weekly** is the
   recommended default.

## How to verify it works

On a throwaway repo, trigger a run for each case:

```bash
# (a) stale command ref: README says `npm run buildx` but the script is `build`
#     -> expect a PR fixing it
gh pr list --head 'claude/docs-sync-' --state open
# (b) only a broken runnable code block needing a rewrite
#     -> expect the tracking issue, no PR
gh issue list --search 'in:title "docs-sync: verified doc drift pending review"'
# (c) a clean repo -> expect nothing (no branch pushed)
```

## Guardrails (why it is safe)

- The routine pushes only to `claude/` branches and never merges.
- It edits only doc files — never product code; a fix that would need a code change is
  escalated (it may be a code bug).
- Detection is mechanical (every reported item has a code anchor); fixes are
  re-verified before they ship, so PRs are trustworthy and low-noise.
- One PR **or** one deduped issue per run; a no-drift run pushes nothing.
- Generated API docs are only ever regenerated via the project's own command, never
  hand-faked.
- Fork PRs are not supported (Actions cannot push to a fork's branch).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Nothing happens on a run | No drift found (normal), or routine not scheduled/connected. Check the routine's run history. |
| Branch pushed but no PR or issue | The bridge isn't on the default branch, or Actions is read-only (403). Settings → Actions → **Read and write**. |
| Findings reported as a PR with no file changes | The routine committed edits that the bridge saw as a tree diff; ensure findings-only runs use `git commit --allow-empty`. |
| A new tracking issue every run | The issue title drifted from `docs-sync: verified doc drift pending review`; the bridge dedupes on that exact title. |
| Generated API docs hand-edited | The routine must regenerate via the doc-gen command or escalate; never edit generated output by hand. |
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/docs-sync-routine/SKILL.md
python3 -c "import re,sys;t=open('$F').read();m=re.match(r'^---\n(.*?)\n---\n',t,re.S);sys.exit(0 if (m and 'name:' in m.group(1) and 'description:' in m.group(1)) else 1)" && echo FRONTMATTER-OK
grep -q 'claude/docs-sync-\*' "$F" && grep -q 'routine-skeleton.md' "$F" && \
  grep -q 'routine-prompt.preamble.md' "$F" && grep -q 'docs-sync: verified doc drift pending review' "$F" && \
  echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `FRONTMATTER-OK`, `CHECK-PASS`.

- [ ] **Step 4: Commit**

```bash
git add skills/docs-sync-routine/SKILL.md
git commit -m "feat(docs-sync): SKILL.md (setup, check battery, verify, guardrails)"
```

---

### Task 4: Update plugin metadata + README

**Files:**
- Modify: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: the skill from Tasks 1–3 (by name).
- Produces: the user-facing listing; final task.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
grep -q 'docs-sync-routine' README.md && \
  grep -q 'docs-sync-routine' .claude-plugin/plugin.json && \
  python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('JSON-OK')" && \
  grep -q '0.4.0' .claude-plugin/plugin.json \
  && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Add docs-sync-routine to the README**

In `README.md`, add a bullet to the `## Skills` list:
```markdown
- **docs-sync-routine** — set up a scheduled routine that keeps docs in sync with
  code: it fixes verifiable code/doc drift (broken command/path refs, stale env vars,
  mismatched API signatures, failing examples, stale generated API docs) via a PR, and
  files a tracking issue for verified drift it can't safely auto-fix. Built on the
  shared routine skeleton. See
  [`skills/docs-sync-routine/SKILL.md`](skills/docs-sync-routine/SKILL.md).
```
And add to the `## Layout` tree, after the `dependency-update-routine/` block:
```
  docs-sync-routine/
    SKILL.md
    templates/       # routine prompt + PR-or-issue bridge
```

- [ ] **Step 3: Bump version + mention docs-sync in the manifests**

In `.claude-plugin/plugin.json`: change `"version": "0.3.0"` to `"version": "0.4.0"` and extend the `description` to mention `docs-sync-routine (scheduled code/doc drift sync via PR or tracking issue)`.

In `.claude-plugin/marketplace.json`: extend the plugin `description` the same way.

- [ ] **Step 4: Verify**

Run the Step 1 command. Expected: `CHECK-PASS`.

- [ ] **Step 5: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs: list docs-sync-routine; bump plugin to 0.4.0"
```

---

## Final verification (after all tasks)

- [ ] **Bridge valid + safe:** re-run Task 1 Step 4. Expected all OK lines.
- [ ] **All JSON valid:** `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('OK')"`.
- [ ] **Glob consistent:** `grep -rl 'claude/docs-sync-' skills/docs-sync-routine` shows `SKILL.md`, `templates/routine-prompt.md`, `templates/docs-sync-bridge.yml`.
- [ ] **Issue title consistent:** `grep -rc 'docs-sync: verified doc drift pending review' skills/docs-sync-routine` — the exact title appears in both `SKILL.md` and the bridge.
- [ ] **Four skills present:** `ls skills` shows `_shared`, `auto-merge-pr`, `dependency-update-routine`, `docs-sync-routine`, `e2e-coverage-routine`.
- [ ] **All shipped workflow YAMLs parse** (excluding the raw `_shared/templates/pr-bridge.yml` token template): a `python3` `yaml.safe_load` loop over `skills/**/templates/*.yml`.
