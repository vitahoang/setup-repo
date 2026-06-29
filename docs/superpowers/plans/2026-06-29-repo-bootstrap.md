# repo-bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `repo-bootstrap` skill — a one-shot, agent-run scaffolder that sets up the foundation the other setup-repo skills assume (a `check` gate, base CI, `CLAUDE.md`, PR template, squash-merge setting, and a default-branch protection ruleset), detecting what exists and filling only the gaps.

**Architecture:** Not a routine — no `_shared` skeleton, no `claude/`-branch bridge. `SKILL.md` drives the local agent through detect → fill gaps (never clobber) → preview → confirm → apply (`gh api`) → summarize. Template files (`ci.yml` with a `check` job, `ruleset.json`, PR template, `CLAUDE.md` starter) are the artifacts it writes; the agent adapts the ecosystem-specific bits.

**Tech Stack:** Markdown skill files, GitHub Actions YAML, JSON, `gh` CLI. No app runtime. "Tests" are validation commands: `python3` YAML/JSON validity, the keystone parse-and-assert (ci.yml job name == ruleset required context == `check`), and `grep` consistency.

## Global Constraints

- **Plugin / marketplace name:** both `setup-repo`.
- **Keystone:** the CI job name == the ruleset `required_status_checks` context == `check`. (If a target repo's existing CI uses a different job name, the agent uses that name in the ruleset — documented in SKILL.md.)
- **Ruleset (`ruleset.json`):** name `repo-bootstrap: default branch protection`; `target: branch`; `enforcement: active`; condition `ref_name.include: ["~DEFAULT_BRANCH"]`; rules `deletion`, `non_fast_forward`, `pull_request` (`required_approving_review_count: 0`), `required_status_checks` (context `check`, `strict_required_status_checks_policy: false`).
- **Squash setting:** `gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F delete_branch_on_merge=true`.
- **Never clobber:** create only what's missing; report each piece *created* / *skipped (already present)* / *applied*.
- **Outward changes (squash PATCH + ruleset POST) are previewed and confirmed before applying.**
- **`CLAUDE.md` starter's Commands section names the `check` command** (so routine gate-detection finds it).
- **Not a routine:** no `_shared` skeleton, no bridge, no cloud routine prompt.
- **Version:** bump `0.6.0` → `0.7.0`.
- **House style:** `SKILL.md` mirrors siblings where applicable (frontmatter, Overview, Setup/Procedure, How to verify, Guardrails, Common mistakes) — but NO Flow/bridge sections (it is a scaffolder, not a routine).
- **Tooling available:** `python3`, `node`, `ruby`, `bash`. No actionlint/yamllint/shellcheck.

---

## File Structure

**Create:**
- `skills/repo-bootstrap/templates/ci.yml` — base CI workflow; a job named `check`.
- `skills/repo-bootstrap/templates/ruleset.json` — default-branch ruleset payload.
- `skills/repo-bootstrap/templates/pull_request_template.md` — generic PR template.
- `skills/repo-bootstrap/templates/CLAUDE.md` — starter with a Commands section naming `check`.
- `skills/repo-bootstrap/SKILL.md` — the guided procedure.

**Modify:**
- `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — list docs; bump `0.7.0`.

---

### Task 1: CI workflow + ruleset (the keystone pair)

**Files:**
- Create: `skills/repo-bootstrap/templates/ci.yml`
- Create: `skills/repo-bootstrap/templates/ruleset.json`

**Interfaces:**
- Produces: a CI workflow whose job is named `check`, and a ruleset requiring a status context named `check`. SKILL.md (Task 3) references both; they MUST agree on `check`.

- [ ] **Step 1: Write the failing keystone check**

Run (expect FAIL — files absent):
```bash
python3 - <<'PY'
import os,sys,yaml,json
ci="skills/repo-bootstrap/templates/ci.yml"; rs="skills/repo-bootstrap/templates/ruleset.json"
if not (os.path.exists(ci) and os.path.exists(rs)): print("CHECK-FAIL: missing"); sys.exit()
d=yaml.safe_load(open(ci).read()); jobs=list(d['jobs'])
r=json.load(open(rs))
ctxs=[c['context'] for rule in r['rules'] if rule['type']=='required_status_checks'
      for c in rule['parameters']['required_status_checks']]
print("CHECK-PASS" if ('check' in jobs and ctxs==['check']) else f"CHECK-FAIL: jobs={jobs} ctxs={ctxs}")
PY
```
Expected: `CHECK-FAIL: missing`

- [ ] **Step 2: Create the CI workflow**

Create `skills/repo-bootstrap/templates/ci.yml` with exactly:
```yaml
name: CI

# Base CI gate scaffolded by repo-bootstrap. The job MUST stay named `check` so the
# default-branch ruleset can require it (the ruleset requires a status context named
# `check`). repo-bootstrap fills the language setup + the actual check command below.

on:
  pull_request:
  push:
    branches: [main, master]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      # repo-bootstrap replaces the step below with your stack's setup + check command,
      # e.g. actions/setup-node then `npm ci && npm run check`, or `make check`, or
      # `./check.sh`. Keep the job id `check`.
      - name: Run check
        run: |
          echo "repo-bootstrap: replace this with your project's check command (see CLAUDE.md Commands)." >&2
          exit 1
```

- [ ] **Step 3: Create the ruleset payload**

Create `skills/repo-bootstrap/templates/ruleset.json` with exactly:
```json
{
  "name": "repo-bootstrap: default branch protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [ { "context": "check" } ]
      }
    }
  ]
}
```

- [ ] **Step 4: Run the keystone check to verify it passes**

Run the Step 1 command. Expected: `CHECK-PASS`. Then confirm the ruleset has all four rule types:
```bash
python3 -c "import json;r=json.load(open('skills/repo-bootstrap/templates/ruleset.json'));t=sorted(x['type'] for x in r['rules']);print('RULES-OK' if t==['deletion','non_fast_forward','pull_request','required_status_checks'] else t)"
```
Expected: `RULES-OK`.

- [ ] **Step 5: Commit**

```bash
git add skills/repo-bootstrap/templates/ci.yml skills/repo-bootstrap/templates/ruleset.json
git commit -m "feat(repo-bootstrap): CI check gate + default-branch ruleset (keystone: check)"
```

---

### Task 2: PR template + CLAUDE.md starter

**Files:**
- Create: `skills/repo-bootstrap/templates/pull_request_template.md`
- Create: `skills/repo-bootstrap/templates/CLAUDE.md`

**Interfaces:**
- Produces: the two prose files repo-bootstrap writes when missing. The `CLAUDE.md` starter's Commands section names `check`.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
test -f skills/repo-bootstrap/templates/pull_request_template.md && \
  test -f skills/repo-bootstrap/templates/CLAUDE.md && \
  grep -q 'check' skills/repo-bootstrap/templates/CLAUDE.md && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the PR template**

Create `skills/repo-bootstrap/templates/pull_request_template.md` with exactly:
```markdown
## What & why

<!-- What does this change do, and why is it needed? -->

## How it was tested

<!-- How did you verify it? Link CI, or describe the manual checks. -->

## Checklist

- [ ] The `check` gate passes locally
- [ ] Docs updated if behavior changed
- [ ] No secrets, credentials, or generated artifacts committed
```

- [ ] **Step 3: Create the CLAUDE.md starter**

Create `skills/repo-bootstrap/templates/CLAUDE.md` with exactly:
```markdown
# <project name>

<!-- Scaffolded by repo-bootstrap. Replace the placeholders below. -->

## Commands

- **check** — the project's gate (lint + typecheck + test); run it before pushing.
  repo-bootstrap set this to your stack's command, e.g. `npm run check`, `make check`,
  or `./check.sh`. The CI workflow and the branch-protection ruleset both depend on this
  command (the CI job is named `check`).

## Conventions

<!-- Project conventions worth stating: directory layout, naming, testing approach,
     anything an agent should follow when changing this repo. -->
```

- [ ] **Step 4: Verify**

Run the Step 1 command. Expected: `CHECK-PASS`.

- [ ] **Step 5: Commit**

```bash
git add skills/repo-bootstrap/templates/pull_request_template.md skills/repo-bootstrap/templates/CLAUDE.md
git commit -m "feat(repo-bootstrap): PR template + CLAUDE.md starter (Commands names check)"
```

---

### Task 3: SKILL.md (the guided procedure)

**Files:**
- Create: `skills/repo-bootstrap/SKILL.md`

**Interfaces:**
- Consumes: all four templates (Tasks 1–2) by path.
- Produces: the installed skill's procedure doc; the local agent follows it.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
F=skills/repo-bootstrap/SKILL.md
test -f "$F" && grep -q 'never' "$F" && grep -q 'rulesets' "$F" && \
  grep -q 'allow_squash_merge' "$F" && grep -q 'already present' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the SKILL.md**

Create `skills/repo-bootstrap/SKILL.md` with exactly:
```markdown
---
name: repo-bootstrap
description: Use when setting up a new or existing GitHub repo with the foundation the other setup-repo skills assume — a check gate, base CI workflow, CLAUDE.md, PR template, squash-merge settings, and a default-branch protection ruleset (block force-push + deletion, require a PR and the CI check). A one-shot scaffolder the agent runs; it detects what already exists and fills only the gaps, and previews/confirms the GitHub settings changes before applying.
---

# repo-bootstrap — Scaffold a Repo's Foundation

This skill is a one-shot scaffolder you (the agent) run in the target repo. It is **not**
a routine — there is no cloud routine or `claude/`-branch bridge. You detect what already
exists, create only what is missing (**never clobber**), and **preview + confirm** the
outward-facing GitHub changes before applying them.

## What it sets up

1. A **`check` gate** — the project's lint + typecheck + test entrypoint.
2. A **base CI workflow** (`.github/workflows/ci.yml`) with a job named `check`.
3. A **`CLAUDE.md`** whose Commands section names the `check` command.
4. A **PR template** (`.github/pull_request_template.md`).
5. **GitHub settings**: enable squash merging + auto-delete head branches, and a
   **default-branch protection ruleset** (block force-push + deletion, require a PR and
   the `check` status).

## Procedure

Work top to bottom. For each file piece, **if it already exists, leave it and report
"already present (skipped)"**. Set `REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"`.

### 1. Detect the ecosystem and create the check gate
Inspect the repo: `package.json` → npm/pnpm/yarn; `pyproject.toml`/`requirements*.txt` →
python; `Cargo.toml` → rust; `go.mod` → go; `Gemfile` → ruby. Create a real `check`
entrypoint for that stack (lint + typecheck + test):
- **npm/pnpm/yarn:** add a `"check"` script to `package.json` (e.g. lint + `tsc --noEmit`
  + test) if one is not already present.
- **other stacks:** add a `Makefile` `check:` target or a `./check.sh` running that
  stack's lint + typecheck + test.
- **unknown stack:** write a `./check.sh` stub that documents what to fill in.
If a check entrypoint already exists, use its command and skip creating one.

### 2. Base CI workflow
If no CI workflow already runs the check, copy `templates/ci.yml` to
`.github/workflows/ci.yml` and replace its `Run check` step with the stack's setup +
check command from step 1. **Keep the job id `check`.**

### 3. CLAUDE.md
If absent, copy `templates/CLAUDE.md` and fill the project name + set the Commands entry
to the actual `check` command. If a `CLAUDE.md` exists, leave it (optionally note that a
Commands/`check` entry helps the other skills).

### 4. PR template
If absent, copy `templates/pull_request_template.md` to `.github/pull_request_template.md`.

### 5. GitHub settings + ruleset (outward-facing — PREVIEW + CONFIRM first)
These change repo behavior, so show the exact commands and ask before running them.

- **Squash merging:**

      gh api -X PATCH "repos/$REPO" -F allow_squash_merge=true -F delete_branch_on_merge=true

  Skip if already enabled (`gh api "repos/$REPO" --jq '.allow_squash_merge'`).

- **Default-branch ruleset:** first check it does not already exist:

      gh api "repos/$REPO/rulesets" --jq '.[].name'

  If `repo-bootstrap: default branch protection` is absent, confirm the keystone: the
  ruleset requires a status context named `check`, which must equal the CI job name from
  step 2. (If the repo's existing CI uses a different job name, set that context in the
  payload instead.) Then write this skill's `templates/ruleset.json` to a temp file and
  post it (`--input` needs a path that resolves from the target repo's working directory,
  so don't pass the plugin-relative template path):

      cp <path-to>/templates/ruleset.json /tmp/ruleset.json   # or write the JSON yourself
      gh api -X POST "repos/$REPO/rulesets" --input /tmp/ruleset.json

  `~DEFAULT_BRANCH` in the payload targets the repo's default branch automatically.

### 6. Summarize
Print a summary listing each of the five pieces as **created**, **skipped (already
present)**, or **applied**, and point to the routine skills (auto-merge-pr,
dependency-update-routine, docs-sync-routine, flaky-test-routine, security-triage-routine)
as next steps now that the `check` gate is enforced.

## Repo prerequisites

- **`gh` is authenticated** with admin rights on the repo (rulesets + settings need admin).
- Run from inside a clone of the target repo (so file writes land in the right place).

## How to verify it works

On a throwaway repo:

```bash
# first run: creates the missing files; after confirming, applies the ruleset + squash
gh api "repos/$REPO/rulesets" --jq '.[].name'   # shows "repo-bootstrap: default branch protection"
# re-run the skill: every piece should report "already present (skipped)" (idempotent)
```

## Guardrails (why it is safe)

- **Never clobbers**: existing files/settings are left untouched and reported as skipped.
- **Outward GitHub changes (squash setting + ruleset) are previewed and confirmed** before
  applying — they change repo behavior and the ruleset can block merges.
- The keystone (`check` job name == ruleset required context) is verified before posting,
  so the ruleset never blocks merges waiting on a check that does not exist.
- The default ruleset requires **0** approvals, so a solo maintainer is not blocked.
- It does not install the routine skills; it only sets up the foundation and points to them.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Ruleset blocks every merge | The CI job name and the ruleset's required context disagree. Make both `check` (or set the ruleset context to the real CI job name). |
| `gh api ... /rulesets` 403 | The token lacks admin on the repo; rulesets require admin. |
| CI always fails after bootstrap | The `ci.yml` `Run check` step still has the placeholder; fill it with the real check command. |
| A second bootstrap re-applies things | It shouldn't — it skips existing files and checks for the ruleset by name. Confirm the ruleset name matches `repo-bootstrap: default branch protection`. |
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/repo-bootstrap/SKILL.md
python3 -c "import re,sys;t=open('$F').read();m=re.match(r'^---\n(.*?)\n---\n',t,re.S);sys.exit(0 if (m and 'name:' in m.group(1) and 'description:' in m.group(1)) else 1)" && echo FRONTMATTER-OK
grep -q 'never' "$F" && grep -q 'rulesets' "$F" && grep -q 'allow_squash_merge' "$F" && \
  grep -q 'already present' "$F" && grep -q 'check' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `FRONTMATTER-OK`, `CHECK-PASS`.

- [ ] **Step 4: Commit**

```bash
git add skills/repo-bootstrap/SKILL.md
git commit -m "feat(repo-bootstrap): SKILL.md (detect+fill-gaps procedure, preview/confirm GitHub changes)"
```

---

### Task 4: Update plugin metadata + README

**Files:**
- Modify: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: the skill (Tasks 1–3) by name. Final task.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
grep -q 'repo-bootstrap' README.md && grep -q 'repo-bootstrap' .claude-plugin/plugin.json && \
  python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('JSON-OK')" && \
  grep -q '0.7.0' .claude-plugin/plugin.json && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Add repo-bootstrap to the README**

In `README.md`, add a bullet to the `## Skills` list (place it FIRST, since it's the
foundation, or last — either is fine; keep it distinct from the routine skills):
```markdown
- **repo-bootstrap** — a one-shot scaffolder (run by the agent, not a routine) that sets
  up the foundation the other skills assume: a `check` gate, base CI, `CLAUDE.md`, PR
  template, squash-merge settings, and a default-branch protection ruleset (block
  force-push + deletion, require a PR + the CI check). Detects what exists and fills only
  the gaps. See [`skills/repo-bootstrap/SKILL.md`](skills/repo-bootstrap/SKILL.md).
```
And add to the `## Layout` tree, after the `security-triage-routine/` block:
```
  repo-bootstrap/
    SKILL.md
    templates/       # ci.yml + ruleset.json + PR template + CLAUDE.md starter
```

- [ ] **Step 3: Bump version + mention repo-bootstrap in the manifests**

In `.claude-plugin/plugin.json`: change `"version": "0.6.0"` to `"version": "0.7.0"` and extend the `description` to mention `repo-bootstrap (one-shot scaffolder: check gate, CI, CLAUDE.md, PR template, squash settings, branch-protection ruleset)`.

In `.claude-plugin/marketplace.json`: extend the plugin `description` the same way.

- [ ] **Step 4: Verify**

Run the Step 1 command. Expected: `CHECK-PASS`.

- [ ] **Step 5: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs: list repo-bootstrap; bump plugin to 0.7.0"
```

---

## Final verification (after all tasks)

- [ ] **Keystone:** re-run Task 1 Step 1 → `CHECK-PASS` (ci.yml job `check` == ruleset context `check`); Task 1 Step 4 → `RULES-OK`.
- [ ] **Templates valid:** `ci.yml` parses as YAML; `ruleset.json` parses as JSON; PR template + `CLAUDE.md` starter are non-empty.
- [ ] **All JSON valid:** `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('OK')"`.
- [ ] **SKILL self-consistency:** `SKILL.md` names the `check` keystone, the `gh api` PATCH (squash) and POST (ruleset) commands, and the never-clobber / preview-confirm / "already present (skipped)" structure.
- [ ] **Seven skills + scaffolder present:** `ls skills` shows `_shared`, `auto-merge-pr`, `dependency-update-routine`, `docs-sync-routine`, `e2e-coverage-routine`, `flaky-test-routine`, `repo-bootstrap`, `security-triage-routine`.
- [ ] **All shipped workflow YAMLs parse** (excluding the raw `_shared/templates/pr-bridge.yml` token template): a `python3` `yaml.safe_load` loop over `skills/**/templates/*.yml` (includes `repo-bootstrap/templates/ci.yml`).
