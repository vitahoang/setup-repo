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
