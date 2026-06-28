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
