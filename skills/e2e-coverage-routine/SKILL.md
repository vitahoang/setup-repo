---
name: e2e-coverage-routine
description: Use when setting up a scheduled routine that periodically reviews a repo's end-to-end test coverage and opens a PR adding new edge-case E2E tests — paired with an E2E CI workflow that runs the Playwright suite against a local stack (Supabase + dev server), and a bridge that turns the routine's claude/ branch into a PR.
---

# e2e-coverage-routine — Scheduled E2E Coverage Growth

> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md).

## Overview

Provisions a self-maintaining E2E loop in a target repo:

1. A **scheduled Claude Code routine** (cron, e.g. weekly) reviews the repo and its
   existing end-to-end tests, identifies uncovered user-facing flows and edge
   cases, and **writes new E2E tests** following the project's existing patterns.
2. It pushes them to a `claude/e2e-coverage-<id>` branch.
3. A **bridge workflow** opens a PR from that branch (cloud routines can't call the
   GitHub API).
4. An **E2E CI workflow** spins up a local stack (Dockerized Supabase + the dev
   server + any test doubles) and runs the full Playwright suite on the PR, so the
   proposed tests are actually executed before a human reviews and merges.

The routine **only adds tests**. If it discovers a real product bug while writing a
test, it reports it in the PR body as `NEEDS-HUMAN` rather than changing app code.

## Flow

    cron fires the routine (Claude Code on the web, schedule-bound to the repo)
            |
            v
    routine: pull default branch -> enumerate user-facing flows ->
             diff against existing e2e/ coverage -> write new edge-case tests
             (reusing existing helpers) -> typecheck/lint -> push
             claude/e2e-coverage-<id>
            |
            v
    e2e-coverage-bridge.yml (push to claude/e2e-coverage-*) -> gh pr create
            |
            v
    e2e-local.yml (pull_request) -> supabase start + migrate + seed +
             `pnpm test:e2e` (mock services + dev server) -> pass/fail check
            |
            v
    human reviews the PR + the `e2e` check result -> merges if green

## Components (templates/)

- `routine-prompt.md` — the routine's mandate (review coverage, add tests, push a
  `claude/` branch). Goes into the routine, NOT into the repo.
- `e2e-local.yml` — E2E CI workflow: boots a local Supabase stack, migrates, seeds,
  and runs the Playwright suite on every PR. Copied into `.github/workflows/`.
- The bridge is the shared `../_shared/templates/pr-bridge.yml` — on push to
  `claude/e2e-coverage-*`, it opens (or reuses) a PR into the default branch. Copy it
  into `.github/workflows/e2e-coverage-bridge.yml` and substitute this token table:

  | token | value |
  | --- | --- |
  | `{{WORKFLOW_NAME}}` | `E2E coverage PR bridge` |
  | `{{BRANCH_GLOB}}` | `claude/e2e-coverage-*` |
  | `{{CONCURRENCY_PREFIX}}` | `e2e-coverage-bridge` |
  | `{{PR_TITLE}}` | `test(e2e): routine-proposed edge cases (${BRANCH#claude/})` |
  | `{{DEFAULT_BODY}}` | `Automated E2E coverage pass — new end-to-end tests proposed by the e2e-coverage routine. The `e2e` check will run them on this PR; review and merge if green.` |

## Repo prerequisites (silent failures live here)

- **Actions write permission.** Settings → Actions → General → Workflow permissions
  → **Read and write** (the bridge's `gh pr create` and the artifact upload need it).
- **A local-stack E2E setup that runs headless.** The project must boot its full
  stack without interactive steps — here that means a `supabase/config.toml`
  (Dockerized local Supabase), a `pnpm db:migrate`, a seed script, and a
  `test:e2e` script whose Playwright config starts the dev server itself
  (`webServer`). If your stack differs (no Supabase, different DB), adapt
  `e2e-local.yml` — it is the one template that is stack-specific.
- **The Claude GitHub App** is installed on the repo so the routine can push
  `claude/` branches.
- **Docker** is available on the CI runner (`ubuntu-latest` has it) for
  `supabase start`.

## Setup procedure

1. **Copy the workflows.** Copy `templates/e2e-local.yml` into the target repo's
   `.github/workflows/`, and copy `../_shared/templates/pr-bridge.yml` into
   `.github/workflows/e2e-coverage-bridge.yml` with the token substitutions from the
   Components section above. Commit on the **default branch** (`pull_request`
   workflows run from the base branch's copy). `routine-prompt.md` is NOT copied — it
   goes into the routine.

2. **Adapt `e2e-local.yml` to the stack.** The template assumes
   pnpm + local Supabase + drizzle + a `test:e2e` script. Update:
   - the install/migrate/seed step names if your scripts differ;
   - the dummy `env()` placeholders — open the target's `supabase/config.toml`,
     find every `env(NAME)` reference for an `enabled = true` section, and add a
     dummy value for each so `supabase start` resolves them (real OAuth is never
     performed; the OAuth E2E tests intercept the authorize request);
   - keep `localhost` (not `127.0.0.1`) for the Supabase URL so the app's
     session-cookie origin matches the dev server.
   Add `retries: process.env.CI ? 2 : 0` to the Playwright config so the first
   test doesn't flake on the dev server's cold per-route compile.

3. **Create the routine** in Claude Code on the web. New routine → paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`, as its instructions → bind it to the target repo →
   grant at least `Bash, Read, Write, Edit, Glob, Grep`.

4. **Schedule it.** Set the routine to run on a cron cadence (weekly is a sensible
   default — frequent enough to keep coverage growing, infrequent enough that PRs
   stay reviewable). This is the load-bearing step: without a schedule the routine
   never fires.

5. **(Optional) Reuse an existing E2E workflow.** If the repo already has an E2E CI
   workflow, skip `e2e-local.yml` and just confirm its job is named `e2e` (the
   bridge and the routine refer to the `e2e` check by name).

## How to verify it works

Trigger the routine once manually from its run page (don't wait for the cron).
Then:

```bash
# A coverage branch + PR should appear:
gh pr list --state open --search "head:claude/e2e-coverage"
# The e2e check should run on that PR:
gh pr checks <N>
```

If the routine pushes a branch but no PR appears, the bridge didn't fire — check
that `e2e-coverage-bridge.yml` is on the default branch and Actions has write
permission.

## Guardrails (why it is safe)

- The routine pushes only to `claude/e2e-coverage-*` branches and opens a PR; it
  never pushes to the default branch and never merges.
- It **only adds/edits tests** (and test-only helpers). It must not change app
  code; a test that fails because of a real bug is reported as `NEEDS-HUMAN` in the
  PR body, not "fixed" by weakening the test or editing the product.
- It must not weaken or delete existing assertions, and must keep tests isolated
  (fresh fixtures per test, teardown), matching the suite's conventions.
- It caps new tests per run (default ≤ 5) so each PR stays reviewable.
- The real validation is CI: the proposed tests are executed by `e2e-local.yml` on
  the PR before a human merges.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Routine never runs | No schedule set (step 4), or the routine isn't bound to the repo. |
| Branch pushed but no PR | `e2e-coverage-bridge.yml` not on the default branch, or Actions is read-only (403). |
| `e2e` check missing on the PR | `e2e-local.yml` not on the default branch, or its job isn't named `e2e`. |
| `supabase start` fails on an unset `env()` | A provider/section is `enabled = true` with an `env(NAME)` whose var isn't set — add a dummy in `e2e-local.yml`'s `env:`. |
| First test always flakes in CI | Add `retries: process.env.CI ? 2 : 0` to the Playwright config (cold dev-server compile). |
| Session cookie dropped → tests bounce to /login | App ran on `127.0.0.1` while the auth stack is pinned to `localhost` (or vice versa). Use one host — `localhost`. |
| PRs are huge / hard to review | Lower the per-run test cap in the routine prompt. |
