# security-triage-routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `security-triage-routine` skill — a PR-triggered Claude routine that runs security scanners on the PR diff, triages the findings, posts a `security-triage` check + comment, auto-fixes only safe dependency bumps, and escalates secrets/SAST/code findings as `NEEDS-HUMAN`.

**Architecture:** Modeled on `auto-merge-pr`. A two-job `sec-bridge.yml`: the `register` job (on `pull_request`) posts a pending `security-triage` status and publishes the PR's code-scanning alerts to `claude/pr-<N>-secinput`; the `bridge` job (on push to `claude/pr-<N>-secverdict`) lands a dep-bump fix from `claude/pr-<N>-secfix` onto the PR head, posts the verdict comment, and resolves the check. The routine (fired by Claude's GitHub integration) runs gitleaks/semgrep/dep-audit diff-scoped, reads the alerts, triages, and pushes `secfix`/`secverdict`.

**Tech Stack:** Markdown skill files, GitHub Actions YAML, `gh` CLI. No app runtime, no unit-testable parser. "Tests" are validation commands: `python3` YAML/JSON validity, `bash -n` shell syntax, a focused behavioral check of the bridge's PR-number parsing + verdict→status mapping, and `grep` consistency.

## Global Constraints

- **Plugin / marketplace name:** both `setup-repo`.
- **Check name:** `security-triage` (pending from register; resolved by bridge).
- **Branches:** `claude/pr-<N>-secfix` (dep-bump fix), `claude/pr-<N>-secverdict` (report; triggers the bridge), `claude/pr-<N>-secinput` (code-scanning alerts, published by register).
- **Verdict tokens (first line of `verdict.md`):** `SECURE-suggested` → status success; `NEEDS-HUMAN` → status failure.
- **Scanners (diff-scoped, PR-introduced only):** gitleaks (secrets — **always escalate**, never auto-fix), per-ecosystem dep audit (the **only auto-fix**), semgrep `--baseline-commit <base>`, and code-scanning alerts read from `secinput` (best-effort).
- **Auto-fix:** dependency version bumps only (manifests/lockfiles), gate-verified green; never a major bump that breaks the gate; never edits product code; never "removes" a secret.
- **Blocking severity:** secrets + high/critical → `NEEDS-HUMAN` (check fails); medium/low → informational (non-blocking).
- **Routine pushes only** `claude/pr-<N>-sec{fix,verdict}`; never merges; the bridge does all API work.
- **Coexistence with auto-merge-pr:** distinct branch names + distinct check (`security-triage` vs `pr-review-em`); documented land-race caveat.
- **Bridge permissions:** workflow-level `contents: write`, `pull-requests: write`, `statuses: write`, `security-events: read` (register fetches code-scanning alerts).
- **Fork PRs unsupported.**
- **Version:** bump `0.5.0` → `0.6.0`.
- **House style:** `SKILL.md` mirrors siblings (frontmatter, Overview, ASCII Flow, Setup procedure, How to verify, Guardrails, Common mistakes table).
- **Tooling available:** `python3`, `node`, `ruby`, `bash`. No actionlint/yamllint/shellcheck. The routine installs gitleaks/semgrep in its own cloud env.

---

## File Structure

**Create:**
- `skills/security-triage-routine/templates/sec-bridge.yml` — two-job register+land/verdict bridge.
- `skills/security-triage-routine/templates/routine-prompt.md` — the triage mandate.
- `skills/security-triage-routine/SKILL.md` — setup + reference.

**Modify:**
- `skills/_shared/routine-skeleton.md` — one line (second land-onto-existing-PR + verdict flavor).
- `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — list docs; bump `0.6.0`.

---

### Task 1: The two-job bridge (`sec-bridge.yml`) + skeleton note

**Files:**
- Create: `skills/security-triage-routine/templates/sec-bridge.yml`
- Modify: `skills/_shared/routine-skeleton.md`

**Interfaces:**
- Consumes: the routine's `claude/pr-<N>-sec{fix,verdict}` branches (Task 2).
- Produces: the `register` job publishes `claude/pr-<N>-secinput` (`codeql-alerts.json`) that the routine reads; the `bridge` job lands fixes, comments, and resolves the `security-triage` check.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
test -f skills/security-triage-routine/templates/sec-bridge.yml && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the bridge**

Create `skills/security-triage-routine/templates/sec-bridge.yml` with exactly:
```yaml
name: Security triage bridge

# The security-triage routine can only push to `claude/` branches and has no GitHub
# API access. This workflow bridges that gap:
#   - register (on pull_request): posts a pending `security-triage` check on the PR
#     head, AND publishes the PR's code-scanning alerts to claude/pr-<N>-secinput so
#     the routine can read them over git.
#   - bridge (on push to claude/pr-<N>-secverdict): lands the routine's dep-bump fix
#     (claude/pr-<N>-secfix) onto the PR head, posts the verdict comment, and resolves
#     the `security-triage` check from the verdict token.

on:
  push:
    branches:
      - 'claude/pr-*-secverdict'   # routine pushes this last; it triggers the bridge
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  statuses: write
  security-events: read

concurrency:
  group: sec-bridge-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  register:
    if: ${{ github.event_name == 'pull_request' }}
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
      REPO: ${{ github.repository }}
      N: ${{ github.event.pull_request.number }}
      HEAD_SHA: ${{ github.event.pull_request.head.sha }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Pending check + publish code-scanning alerts for the routine
        run: |
          set -euo pipefail

          # 1) Pending security-triage status so the check always appears.
          gh api -X POST "repos/${REPO}/statuses/${HEAD_SHA}" \
            -f state="pending" -f context="security-triage" \
            -f description="awaiting security triage"

          # 2) Fetch the PR's open code-scanning alerts (empty array if code scanning is
          #    off or none exist) so the routine can triage them too.
          gh api "repos/${REPO}/code-scanning/alerts?ref=refs/pull/${N}/head&state=open" \
            --paginate > codeql-alerts.json 2>/dev/null || echo '[]' > codeql-alerts.json
          [ -s codeql-alerts.json ] || echo '[]' > codeql-alerts.json

          # 3) Publish them on a per-PR input branch the routine reads over git.
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          tmp=$(mktemp -d); cp codeql-alerts.json "$tmp/codeql-alerts.json"
          git checkout --orphan "claude/pr-${N}-secinput"
          git rm -rf . >/dev/null 2>&1 || true
          cp "$tmp/codeql-alerts.json" codeql-alerts.json
          git add codeql-alerts.json
          git commit -m "code-scanning alerts for PR #${N}"
          git push -f origin "claude/pr-${N}-secinput"

  bridge:
    if: ${{ github.event_name == 'push' && github.event.deleted != true }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Land the dep-bump fix, post the verdict, resolve the check
        env:
          GH_TOKEN: ${{ github.token }}
          VERDICT_REF: ${{ github.ref_name }}
        run: |
          set -euo pipefail

          # claude/pr-<N>-secverdict -> N
          n=$(printf '%s' "$VERDICT_REF" | sed -E 's#^claude/pr-([0-9]+)-secverdict$#\1#')
          if ! printf '%s' "$n" | grep -qE '^[0-9]+$'; then
            echo "Could not parse a PR number from $VERDICT_REF; nothing to do."
            exit 0
          fi

          fix_ref="claude/pr-${n}-secfix"

          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          head_ref=$(gh pr view "$n" --json headRefName --jq .headRefName)

          # 1) Land the dep-bump fix, if the routine pushed one. Fast-forward the PR head
          #    to the fix branch when it descends from the current head; otherwise
          #    cherry-pick the routine's commits onto the (moved) head.
          if git ls-remote --exit-code --heads origin "$fix_ref" >/dev/null 2>&1; then
            landed=false
            for attempt in 1 2 3 4 5; do
              git fetch origin "$head_ref" "$fix_ref"
              if git merge-base --is-ancestor "origin/$head_ref" "origin/$fix_ref"; then
                git checkout -B "$head_ref" "origin/$fix_ref"
                if git push origin "HEAD:refs/heads/$head_ref"; then
                  echo "Fast-forwarded $head_ref to the fix branch (attempt $attempt)."
                  landed=true
                  break
                fi
              else
                git checkout -B "$head_ref" "origin/$head_ref"
                if git cherry-pick "origin/${head_ref}..origin/${fix_ref}" \
                   && git push origin "HEAD:refs/heads/$head_ref"; then
                  echo "Cherry-picked fix onto moved $head_ref (attempt $attempt)."
                  landed=true
                  break
                fi
                git cherry-pick --abort 2>/dev/null || true
              fi
              echo "Land attempt $attempt failed; retrying..."
              sleep 5
            done
            if [ "$landed" != true ]; then
              echo "Could not land the fix after 5 attempts; leaving $fix_ref for inspection." >&2
            fi
          else
            echo "No fix branch ($fix_ref); posting verdict only."
          fi

          # 2) Post the verdict comment from the verdict branch.
          git fetch origin "$VERDICT_REF"
          git checkout "origin/$VERDICT_REF" -- verdict.md
          gh pr comment "$n" --body-file verdict.md

          # 3) Resolve the security-triage status from the verdict token (first line).
          verdict_line=$(head -n1 verdict.md)
          if printf '%s' "$verdict_line" | grep -q 'NEEDS-HUMAN'; then
            state=failure
            description="NEEDS-HUMAN — a security finding needs a human"
          elif printf '%s' "$verdict_line" | grep -q 'SECURE-suggested'; then
            state=success
            description="SECURE-suggested — no blocking PR-introduced findings"
          else
            state=success
            description="security triage complete"
          fi

          head_sha=$(gh pr view "$n" --json headRefOid --jq .headRefOid)
          gh api -X POST "repos/${GITHUB_REPOSITORY}/statuses/${head_sha}" \
            -f state="$state" -f context="security-triage" -f description="$description"
```

- [ ] **Step 3: Add the skeleton note**

In `skills/_shared/routine-skeleton.md`, find the sub-bullet that begins "Routines that instead LAND work onto an *existing* PR" (the auto-merge-pr flavor) and append one sentence to it:
```markdown
    (Two such skills now exist — auto-merge-pr and security-triage — each ships its own
    register+land/verdict bridge with a distinct check name.)
```

- [ ] **Step 4: Verify YAML + permissions + both jobs + shell syntax + bridge logic**

Run:
```bash
F=skills/security-triage-routine/templates/sec-bridge.yml
python3 - <<PY
import yaml
d=yaml.safe_load(open("$F").read())
assert d['permissions']=={'contents':'write','pull-requests':'write','statuses':'write','security-events':'read'}, d['permissions']
jobs=d['jobs']
assert 'register' in jobs and 'bridge' in jobs, list(jobs)
open('/tmp/sec_reg.sh','w').write(jobs['register']['steps'][1]['run'])
open('/tmp/sec_br.sh','w').write(jobs['bridge']['steps'][1]['run'])
# push trigger must be the secverdict glob
on=d[True]
assert on['push']['branches']==['claude/pr-*-secverdict'], on['push']
print("YAML-OK; perms OK; both jobs OK; push-glob OK")
PY
bash -n /tmp/sec_reg.sh && bash -n /tmp/sec_br.sh && echo "SHELL-SYNTAX-OK"
# Behavioral check: PR-number parse + verdict-token -> status mapping (the real logic)
python3 - <<'PY'
import subprocess
def parse(ref):
    return subprocess.run(["sed","-E","s#^claude/pr-([0-9]+)-secverdict$#\\1#"],
                          input=ref, capture_output=True, text=True).stdout.strip()
assert parse("claude/pr-42-secverdict")=="42"
assert parse("claude/pr-7-secfix")=="claude/pr-7-secfix"  # non-match passes through
def status(line):
    if "NEEDS-HUMAN" in line: return "failure"
    if "SECURE-suggested" in line: return "success"
    return "success"
assert status("## Security Triage — NEEDS-HUMAN")=="failure"
assert status("## Security Triage — SECURE-suggested")=="success"
print("BRIDGE-LOGIC-OK")
PY
grep -q 'claude/pr-${N}-secinput' "$F" && grep -q 'code-scanning/alerts' "$F" && echo "SECINPUT-OK"
```
Expected: `YAML-OK; perms OK; both jobs OK; push-glob OK`, `SHELL-SYNTAX-OK`, `BRIDGE-LOGIC-OK`, `SECINPUT-OK`.

- [ ] **Step 5: Commit**

```bash
git add skills/security-triage-routine/templates/sec-bridge.yml skills/_shared/routine-skeleton.md
git commit -m "feat(security-triage): register+land/verdict bridge + skeleton note"
```

---

### Task 2: Routine prompt

**Files:**
- Create: `skills/security-triage-routine/templates/routine-prompt.md`

**Interfaces:**
- Consumes: the bridge's branch names + `secinput`/`codeql-alerts.json` (Task 1).
- Produces: the mandate pasted into the web routine after the shared preamble.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
F=skills/security-triage-routine/templates/routine-prompt.md
test -f "$F" && grep -q 'claude/pr-${PR_NUMBER}-secverdict' "$F" && grep -q 'gitleaks' "$F" && \
  grep -q 'SECURE-suggested' "$F" && grep -q 'baseline-commit' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the routine prompt**

Create `skills/security-triage-routine/templates/routine-prompt.md` with exactly:
```markdown
# Security Triage Routine — Mandate

(The shared guardrail preamble is pasted ahead of this prompt — only push to
`claude/` branches, no GitHub API, never merge, escalate via `NEEDS-HUMAN`.)

You are `security-triage`, a PR-triggered routine. You run once each time a pull
request is opened or updated. You scan the PR's changes for security problems, triage
what you find, and hand a verdict to a bridge workflow. You **only auto-fix dependency
version bumps** — never product code, and never a secret.

## How you're triggered and how your work ships

Identify the PR first: read its number as `PR_NUMBER` and its head branch as `HEAD_REF`
(e.g. `gh pr view --json number,headRefName`). You may ONLY push to `claude/`-prefixed
branches. Hand work to the `sec-bridge` workflow via:

- **A dependency fix** (optional) → `claude/pr-${PR_NUMBER}-secfix`
- **Your verdict** (always) → `claude/pr-${PR_NUMBER}-secverdict`

The bridge lands the fix onto the PR branch, posts your verdict as a comment, and sets
the `security-triage` check. Set your identity:

    git config user.email "security-triage[bot]@users.noreply.github.com"
    git config user.name "security-triage[bot]"

## Step 1 — Get the PR diff and base

    git fetch origin "$HEAD_REF" main
    base=$(gh pr view "$PR_NUMBER" --json baseRefName --jq .baseRefName)
    git fetch origin "$base"
    git checkout -B pr-head "origin/$HEAD_REF"
    git diff "origin/$base...HEAD"   # the PR's changes

## Step 2 — Run scanners, diff-scoped (only what the PR introduces)

Install the tools if missing, then run each against the PR's changes only:

- **Secrets — gitleaks:** scan the commit range, e.g. `gitleaks detect --log-opts
  "origin/$base..HEAD"`. Any hit is a leaked credential.
- **SAST — semgrep:** `semgrep --baseline-commit "origin/$base" --config auto` so only
  findings new relative to base, on changed code, are reported.
- **Dependency vulnerabilities:** run the ecosystem's audit (`npm`/`pnpm audit`,
  `pip-audit`, …) on the PR head, and compare against base, keeping only vulnerabilities
  the PR newly introduces (or whose fix it makes available).

## Step 3 — Read code-scanning alerts (best-effort)

    git fetch origin "claude/pr-${PR_NUMBER}-secinput" 2>/dev/null \
      && git show "origin/claude/pr-${PR_NUMBER}-secinput:codeql-alerts.json" > /tmp/codeql.json \
      || echo "code-scanning alerts unavailable this run"

If present, keep only alerts whose location is in the PR's changed files.

## Step 4 — Triage the union

Across all four sources, dedupe the same issue reported by multiple tools, rate each
finding's severity/exploitability, and drop obvious false positives. Then classify:

- **Secret** → `NEEDS-HUMAN`, **blocking**. Never try to remove it — it is already
  leaked; the comment must say to rotate the credential and purge it from history.
- **Dependency vulnerability with a safe patched version** → auto-fix candidate (Step 5).
- **Everything else** (no safe bump, SAST, code-scanning, …) → `NEEDS-HUMAN` comment;
  **blocking only if high/critical severity**, otherwise informational.

## Step 5 — Auto-fix dependencies only (optional)

For dependency findings with a safe **patch/minor** fix: on a branch based on the PR
head, bump the dependency to the patched version and regenerate the lockfile. Touch
**only manifests/lockfiles**. Run the project's check gate (a `check` script in
`package.json`, else the Commands section of `CLAUDE.md`/README). If green, push it:

    git push -f origin "HEAD:refs/heads/claude/pr-${PR_NUMBER}-secfix"

If the gate goes red, or only a major version fixes it, do NOT push the fix — escalate
that vulnerability as `NEEDS-HUMAN` instead.

## Step 6 — Push your verdict (ALWAYS)

Base the verdict branch on the PR head so it carries `.github/workflows/`. Write
`verdict.md` in this exact format, then push:

    ## Security Triage — <SECURE-suggested | NEEDS-HUMAN>
    **Auto-fixed:** <dep bumps landed, or "none">
    **Blocking (NEEDS-HUMAN):**
    - [secret] <file>:<line> <rule> — rotate the credential and purge it from history
    - [high] <tool> <rule> <file>:<line> — <one-line triage>
    **Non-blocking (informational):**
    - [medium/low] <tool> <rule> <file>:<line> — <note>
    **Coverage:** gitleaks ✓ · semgrep ✓ · <eco> audit ✓ · code-scanning <✓|unavailable>

The first line's token must be exactly `SECURE-suggested` (no blocking findings) or
`NEEDS-HUMAN` (any secret, or any high/critical finding not resolved by an auto-fix).

    git checkout -B verdict-tmp "origin/$HEAD_REF"
    git add verdict.md
    git commit -m "security triage verdict [skip-review]"
    git push -f origin "HEAD:refs/heads/claude/pr-${PR_NUMBER}-secverdict"

## Hard rules

- NEVER merge the PR. NEVER edit product code. NEVER try to remove a leaked secret.
- The only auto-fix is a gate-green dependency bump (manifests/lockfiles only).
- Report only PR-introduced findings. Be honest in the Coverage line about what ran.
- Only ever push to `claude/`-prefixed branches.
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/security-triage-routine/templates/routine-prompt.md
grep -q 'claude/pr-${PR_NUMBER}-secverdict' "$F" && grep -q 'claude/pr-${PR_NUMBER}-secfix' "$F" && \
  grep -q 'gitleaks' "$F" && grep -q 'baseline-commit' "$F" && grep -q 'SECURE-suggested' "$F" && \
  grep -q 'NEVER edit product code' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/security-triage-routine/templates/routine-prompt.md
git commit -m "feat(security-triage): routine mandate (scan diff, triage, dep-only auto-fix)"
```

---

### Task 3: SKILL.md

**Files:**
- Create: `skills/security-triage-routine/SKILL.md`

**Interfaces:**
- Consumes: the bridge (Task 1) + prompt (Task 2) by path; the shared preamble + skeleton doc.
- Produces: the installed skill's setup/reference doc.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
F=skills/security-triage-routine/SKILL.md
test -f "$F" && grep -q 'security-triage' "$F" && grep -q 'routine-skeleton.md' "$F" && \
  grep -q 'routine-prompt.preamble.md' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the SKILL.md**

Create `skills/security-triage-routine/SKILL.md` with exactly:
```markdown
---
name: security-triage-routine
description: Use when setting up automated security triage for pull requests — a PR-triggered Claude routine runs secret/dependency/SAST scanners on the diff (gitleaks, npm/pip audit, semgrep) plus GitHub code-scanning alerts, posts a triaged security-triage check + comment, auto-fixes only safe dependency bumps, and escalates secrets and code findings as NEEDS-HUMAN. Built on the auto-merge-pr bridge pattern.
---

# security-triage-routine — PR Security Triage

> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md). Uses the same register+land/verdict bridge pattern as `auto-merge-pr`, with its own `security-triage` check.

## Overview

Provisions PR security triage in a target repo. A Claude routine — fired by **Claude's
GitHub integration** on every pull request — scans the **PR diff** for security problems
(secrets, vulnerable dependencies, SAST, and existing code-scanning alerts), triages the
union, and hands a verdict to a bridge workflow. The bridge posts a `security-triage`
check + a triaged comment, and lands the routine's **dependency-bump fix** (the only
thing it auto-fixes). Secrets, SAST, and code findings are escalated as `NEEDS-HUMAN`;
the routine never edits product code and never tries to remove a leaked secret.

## Flow

    PR opened / new commits (Claude GitHub integration fires the routine)
            |                                   |
    sec-bridge.yml `register` job          routine: scan diff (gitleaks, semgrep,
    posts a PENDING security-triage        dep audit) + read code-scanning alerts ->
    check + publishes code-scanning        triage -> push claude/pr-<N>-secfix
    alerts to claude/pr-<N>-secinput       (dep bump) + claude/pr-<N>-secverdict
            |                                   |
            v                                   v
            |                          sec-bridge.yml `bridge` job: land the dep fix,
            |                          post the verdict comment, resolve security-triage
            v
    human reviews the comment / merges when the check is acceptable

## Scanners (diff-scoped — only PR-introduced findings)

- **Secrets (gitleaks)** — always `NEEDS-HUMAN`; a leaked secret needs rotation + history
  purge, never a code fix.
- **Dependency vulnerabilities (per-ecosystem audit)** — the only auto-fixable category
  (bump to a patched version, gate-verified).
- **SAST (semgrep `--baseline-commit`)** — new findings on changed code; triaged, never
  auto-fixed.
- **Code-scanning alerts** — the register job publishes the PR's existing alerts; the
  routine triages those in changed files (best-effort if alerts are still running).

## Repo prerequisites

- **Actions write permission.** Settings → Actions → General → Workflow permissions →
  **Read and write** (register posts the status + publishes alerts; bridge lands fixes,
  comments, sets the check).
- **The Claude GitHub App is installed**, so the integration fires the routine and the
  routine can push `claude/` branches.
- **(Optional) GitHub code scanning enabled** so the `register` job has alerts to publish;
  without it, code-scanning input is simply an empty list.

## Setup procedure

1. **Copy the bridge.** Copy `templates/sec-bridge.yml` into the target repo's
   `.github/workflows/`. Commit on the **default branch** (`pull_request` workflows run
   from the base branch's copy).
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`. Bind it to the target repo and grant at least
   `Bash, Read, Write, Edit, Glob, Grep`.
3. **Wire the GitHub trigger.** Set the routine to fire on pull-request **open +
   synchronize** — the same events as the bridge's `register` job. (Two systems must
   agree: if the routine isn't wired, the `security-triage` check posts pending and never
   resolves.)
4. **(Recommended) Branch protection.** Add `security-triage` as a required status check
   so a PR with an unresolved security finding cannot merge.

## How to verify it works

Open a throwaway PR after the workflow lands on the default branch:

```bash
# (a) add a fake secret to the diff -> security-triage FAILS, comment flags NEEDS-HUMAN
gh pr checks <N> | grep security-triage
# (b) introduce a known-vulnerable dependency with a safe patch -> a dep-bump lands and
#     the check passes
# (c) a clean PR -> security-triage passes with "no PR-introduced findings"
```

## Guardrails (why it is safe)

- The routine pushes only to `claude/pr-<N>-sec*` branches and never merges.
- It auto-fixes **only** dependency bumps (manifests/lockfiles, gate-verified); it never
  edits product code and never tries to remove a leaked secret (it escalates with
  rotate+purge guidance).
- **Diff-scoped:** only PR-introduced findings; it never blocks a PR for pre-existing debt.
- The check fails only on a secret or a high/critical finding; medium/low are
  informational, so the gate stays high-signal.
- Distinct branch + check names from `auto-merge-pr`, so the two coexist (if both land a
  fix onto one PR head, those landings can race — a documented limitation).
- Fork PRs are not supported (Actions can't push to a fork head; secrets/alerts are
  restricted on fork PRs).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| `security-triage` stuck pending | Routine not wired to fire on PR events, or it never pushed `claude/pr-<N>-secverdict`. Check the routine's run history. |
| No `security-triage` check at all | `sec-bridge.yml` not on the default branch, or PR opened before it landed (`pull_request` runs from the base copy). |
| Check fails on a pre-existing issue | A scanner wasn't diff-scoped. The routine must compare against the base and report only PR-introduced findings. |
| `register`/bridge fail with **403** | Actions token is read-only. Settings → Actions → General → Workflow permissions → **Read and write**. |
| Code-scanning always "unavailable" | Code scanning isn't enabled, or alerts are still running when the routine fires (best-effort). Enable code scanning for full coverage. |
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/security-triage-routine/SKILL.md
python3 -c "import re,sys;t=open('$F').read();m=re.match(r'^---\n(.*?)\n---\n',t,re.S);sys.exit(0 if (m and 'name:' in m.group(1) and 'description:' in m.group(1)) else 1)" && echo FRONTMATTER-OK
grep -q 'security-triage' "$F" && grep -q 'routine-skeleton.md' "$F" && grep -q 'routine-prompt.preamble.md' "$F" && \
  grep -q 'claude/pr-<N>-secinput' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `FRONTMATTER-OK`, `CHECK-PASS`.

- [ ] **Step 4: Commit**

```bash
git add skills/security-triage-routine/SKILL.md
git commit -m "feat(security-triage): SKILL.md (setup, scanners, verify, guardrails)"
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
grep -q 'security-triage-routine' README.md && grep -q 'security-triage-routine' .claude-plugin/plugin.json && \
  python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('JSON-OK')" && \
  grep -q '0.6.0' .claude-plugin/plugin.json && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Add security-triage-routine to the README**

In `README.md`, add a bullet to the `## Skills` list:
```markdown
- **security-triage-routine** — set up PR security triage: a PR-triggered routine scans
  the diff (gitleaks, dependency audit, semgrep) plus GitHub code-scanning alerts, posts
  a `security-triage` check + triaged comment, auto-fixes only safe dependency bumps, and
  escalates secrets and code findings as `NEEDS-HUMAN`. See
  [`skills/security-triage-routine/SKILL.md`](skills/security-triage-routine/SKILL.md).
```
And add to the `## Layout` tree, after the `flaky-test-routine/` block:
```
  security-triage-routine/
    SKILL.md
    templates/       # routine prompt + register/land-verdict bridge
```

- [ ] **Step 3: Bump version + mention security-triage in the manifests**

In `.claude-plugin/plugin.json`: change `"version": "0.5.0"` to `"version": "0.6.0"` and extend the `description` to mention `security-triage-routine (PR security triage via scanners + code-scanning alerts, dep-only auto-fix)`.

In `.claude-plugin/marketplace.json`: extend the plugin `description` the same way.

- [ ] **Step 4: Verify**

Run the Step 1 command. Expected: `CHECK-PASS`.

- [ ] **Step 5: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs: list security-triage-routine; bump plugin to 0.6.0"
```

---

## Final verification (after all tasks)

- [ ] **Bridge valid + logic:** re-run Task 1 Step 4 (YAML, perms, both jobs, `bash -n`, `BRIDGE-LOGIC-OK`, `SECINPUT-OK`).
- [ ] **All JSON valid:** `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('OK')"`.
- [ ] **Consistency:** `grep -rl 'security-triage' skills/security-triage-routine` shows SKILL.md, routine-prompt.md, sec-bridge.yml; the `claude/pr-` `sec{fix,verdict,input}` branch names appear in the bridge and prompt; `SECURE-suggested`/`NEEDS-HUMAN` appear in both prompt and bridge.
- [ ] **Seven skills present:** `ls skills` shows `_shared`, `auto-merge-pr`, `dependency-update-routine`, `docs-sync-routine`, `e2e-coverage-routine`, `flaky-test-routine`, `security-triage-routine`.
- [ ] **All shipped workflow YAMLs parse** (excluding the raw `_shared/templates/pr-bridge.yml` token template): a `python3` `yaml.safe_load` loop over `skills/**/templates/*.yml`.
