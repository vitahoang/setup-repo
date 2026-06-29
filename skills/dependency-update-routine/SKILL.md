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

    cron fires the routine (a Claude Code cloud routine, schedule-bound to the repo)
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

- `templates/routine-prompt.md` — the routine's mandate (assembled after the shared preamble
  and given to the routine).
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
2. **Provision the routine with `/schedule`.** Assemble the prompt: the shared preamble
   (`../_shared/templates/routine-prompt.preamble.md`) followed by the full text of
   `templates/routine-prompt.md`. Invoke **`/schedule`** to create a **recurring cloud
   routine** bound to the target repo that runs that prompt on a weekly cron — a sensible
   default is `19 7 * * 1` (Mon ~07:19 local) — with tools
   `Bash, Read, Write, Edit, Glob, Grep`.

   *Manual fallback:* if `/schedule` can't bind the repo in your environment, create the
   routine in Claude Code on the web instead — paste the same preamble + prompt, bind it
   to the repo, grant the same tools, and set the same weekly cron.
3. **(Recommended) Auto-delete merged branches.** Settings → General → Pull Requests →
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
