---
name: auto-merge-pr
description: Use when setting up automated pull-request review and merge-on-approval for a GitHub repo — an engineering-manager routine (fired by Claude's GitHub integration) that reviews each PR, runs the project's checks, fixes confident issues, posts a verdict, shows a pr-review-em check, and squash-merges only after a human approves.
---

# auto-merge-pr — Automated PR Review + Merge-on-Approval

## Overview

Provisions a PR pipeline in a target repo. A Claude Code routine — fired by
**Claude's GitHub integration** on every pull request — acts as an engineering
manager: it runs the project's checks, fixes issues it is confident about,
reviews the diff against project conventions, and applies safety guardrails. It
**never merges**; a human merges by approving the review, which auto-squash-merges.

**Why a bridge.** Cloud routines may only push to `claude/`-prefixed branches and
have no GitHub API access, so the routine cannot push to the PR branch or comment
itself. It pushes fixes to `claude/pr-<N>-fix` and its verdict to
`claude/pr-<N>-verdict`; the bridge workflow (running with the Actions token)
lands the fixes onto the PR branch and posts the verdict as a comment.

## Flow

    PR opened / new commits (Claude GitHub integration fires the routine)
            |                                   |
   pr-fix-bridge.yml `register` job       routine: resolves main conflicts,
   posts a PENDING pr-review-em check      runs gate, reviews, pushes
            |                              claude/pr-<N>-fix + claude/pr-<N>-verdict
            |                                   |
            |                                   v
            |                          pr-fix-bridge.yml `bridge` job:
            |                          lands fixes onto the PR branch, posts the
            |                          verdict comment, resolves pr-review-em to
            |                          success / failure
            v
    human submits an approving review
            |
            v
    pr-approve-merge.yml --> gh pr merge --squash
            |
            v
    pr-branch-cleanup.yml deletes claude/pr-<N>-{fix,verdict} on merge

## Components (templates/)

- `routine-prompt.md` — the EM mandate; the routine's instructions.
- `pr-fix-bridge.yml` — two jobs in one workflow:
  - `register` (on `pull_request`): posts a **pending** `pr-review-em` status on
    the PR head so the check always appears, even before/if the routine runs.
  - `bridge` (on push to `claude/pr-*-verdict`): lands `claude/pr-<N>-fix` onto
    the PR branch (fast-forwards when the fix branch descends from the PR head,
    else cherry-picks onto a moved head), posts the verdict comment, and resolves
    `pr-review-em` to success/failure. Does NOT delete branches.
- `pr-branch-cleanup.yml` — deletes `claude/pr-<N>-{fix,verdict}` once PR `<N>` merges.
- `pr-approve-merge.yml` — squash-merges on an approving review.

There is intentionally **no** `pr-review.yml` — the routine is fired by Claude's
GitHub integration, not a workflow.

## Two systems that must agree

This pipeline has **two independently-configured triggers** that the skill keeps
in lockstep — get this wrong and you get a check with no resolver (or vice versa):

1. **Claude's GitHub integration** fires the *routine* (the reviewer). Configured
   in Claude Code on the web — NOT in this repo's workflows.
2. **The `pull_request` workflow** (`pr-fix-bridge.yml`) fires inside GitHub
   Actions and posts/resolves the `pr-review-em` check.

Both must be scoped to the same PR events (open + new commits). The workflow half
is fixed by the template (`opened, synchronize, reopened`); you must set the
routine half to match in step 4.

## Repo prerequisites (check these first — silent failures live here)

- **Actions write permission.** GitHub → repo **Settings → Actions → General →
  Workflow permissions → Read and write**. Default-read-only repos make the
  `register` status POST, the branch deletes, and `gh pr merge` all fail with 403.
- **Squash merge allowed.** Settings → General → Pull Requests → enable **Allow
  squash merging**. `pr-approve-merge.yml` runs `gh pr merge --squash`; it fails if
  squash is disabled.
- **The Claude GitHub App is installed** on the target repo (or its org), so the
  integration can see PRs and the routine can push `claude/` branches.

## Setup procedure

1. **Copy the workflows.** Copy `templates/pr-fix-bridge.yml`,
   `templates/pr-branch-cleanup.yml`, and `templates/pr-approve-merge.yml` into
   the target repo's `.github/workflows/`. Commit on the **default branch** —
   `pull_request` workflows run from the base branch's copy, so the `register`
   check only appears for PRs opened after this lands. (`routine-prompt.md` is
   NOT copied into the repo; it goes into the routine in step 3.)
2. **Confirm the gate.** The routine auto-detects the check command (a `check`
   script in `package.json`, or the Commands section of `CLAUDE.md`/README;
   default `pnpm check`). No edit needed unless the project has no check script;
   if so, add one or name the command in the routine prompt's Step 3.
3. **Create the routine** in Claude Code on the web (claude.ai). Create a new
   routine/automation, paste the full text of `templates/routine-prompt.md` as its
   instructions, set its repository/source to the target repo, and grant at least
   `Bash, Read, Write, Edit, Glob, Grep`. (The routine runs in Claude's cloud
   environment, which can install deps and run the gate.) Exact menu labels live
   in the product UI and may shift — the invariant is: a routine, with this prompt,
   bound to this repo.
4. **Wire the GitHub trigger.** Connect Claude's GitHub integration to the target
   repo and set the routine to fire on pull-request **open + synchronize** (same
   events as the workflow — see "Two systems that must agree"). This is the
   load-bearing step: if it is not wired, the `pr-review-em` check posts pending
   and never resolves.
5. **(Recommended) Branch protection.** Require 1 approving review so the
   merge-on-approval gate is enforced. Optionally add `pr-review-em` as a required
   status check so an un-reviewed PR cannot merge.

## How to verify it works

Open a throwaway PR (an empty commit is fine) **after** the workflows land on the
default branch, then confirm both halves:

```bash
gh pr view <N> --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select((.context // .name)=="pr-review-em")'
# expect: pr-review-em = PENDING immediately on open
# then, once the routine pushes claude/pr-<N>-verdict, it flips to success/failure
gh run list --workflow pr-fix-bridge.yml --branch <head-branch>
```

## Guardrails (why it is safe)

- The routine pushes only to `claude/` branches; the bridge lands fixes with
  `[skip-review]` commits, so the routine's own work never re-fires review.
- The routine never merges. Merge happens only via `pr-approve-merge.yml` on a
  human approving review.
- The routine refuses to auto-fix risky areas (secrets, migrations, deps, auth,
  large refactors) and escalates with a `NEEDS-HUMAN` verdict instead.
- Fork PRs are not supported (Actions cannot push to a fork's branch).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| No `pr-review-em` check on a PR at all | Workflows not on the **default** branch yet, or PR opened before they landed. `pull_request` workflows run from the base branch. |
| Check stays `pending` forever | Routine never ran (GitHub integration not connected/enabled) or never pushed `claude/pr-<N>-verdict`. Check the routine's run history. |
| Bridge never fires | It triggers on push to `claude/pr-*-verdict`; the verdict branch must carry `.github/workflows/`. The routine bases the verdict branch on the PR head (which has them). |
| `register`/cleanup/merge fail with **403** | Actions token is read-only. Settings → Actions → General → Workflow permissions → **Read and write**. |
| `pr-approve-merge` fails on `gh pr merge --squash` | Squash merging is disabled. Settings → General → Pull Requests → **Allow squash merging**. |
| PR merges without review | Add `pr-review-em` to required status checks in branch protection. |
