---
name: flaky-test-routine
description: Use when setting up a scheduled routine that finds flaky tests from CI history — a collector workflow mines recent test runs + JUnit artifacts into a flakiness digest, and the routine files a tracking issue with the evidence or, for strongly-confirmed cases, opens a PR that quarantines (skips) the test. Built on the shared routine skeleton; requires the project to upload JUnit/test-result artifacts.
---

# flaky-test-routine — Scheduled Flaky-Test Triage

> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md).

## Overview

Provisions a flaky-test triage loop in a target repo. A **collector workflow**
(`flaky-collector.yml`, scheduled daily) mines recent runs of your test workflow and
their **JUnit artifacts**, computes a flakiness digest using **same-SHA disagreement**
(a test that both passes and fails on the *same commit*), and force-pushes
`flaky-digest.json` to a dedicated `flaky-digest` data branch. A **scheduled Claude
routine** (weekly) reads that digest and either files/updates a tracking issue with the
evidence, or — for tests confirmed flaky on **≥2 distinct commits** — opens a PR that
quarantines (skips) the test. The routine **only edits test files** and **never deletes**
a test.

## Flow

    flaky-collector.yml (daily) -> mine runs + JUnit artifacts ->
        flaky_parse.py -> flaky-digest.json -> force-push `flaky-digest` branch
            |
            v
    cron fires the routine -> read flaky-digest.json ->
        classify by distinct_sha_count (>=2 quarantine, ==1 evidence) ->
        quarantine edits (skip tests) OR --allow-empty findings commit ->
        push claude/flaky-<id> (report in commit body)
            |
            v
    flaky-bridge.yml routes on merge-base tree-diff:
        test edits -> open/reuse a PR (quarantine)
        empty      -> open/update the "flaky tests pending triage" issue
            |
            v
    human reviews the quarantine PR / triages the issue

## How flakiness is judged

A test is flaky when, on the **same commit SHA**, it has both passed and failed (same
code, different result). The digest ranks tests by `distinct_sha_count` — how many
distinct commits show that disagreement. `>= 2` → quarantine PR; `== 1` → evidence-only
issue. This keeps a one-off fluke from masking a real intermittent bug.

## Components

- `templates/flaky-collector.yml` — the collector workflow. Copied into
  `.github/workflows/`. Configure its env: `TEST_WORKFLOW`, `ARTIFACT_NAME`,
  `WINDOW_DAYS`.
- `templates/flaky_parse.py` — the JUnit→digest parser. Copied into `.github/`.
- `templates/flaky-bridge.yml` — the PR-or-issue bridge. Copied into
  `.github/workflows/` as-is.
- `templates/routine-prompt.md` — the routine mandate (pasted after the shared
  preamble).

## Repo prerequisites

- **Your test workflow uploads JUnit/test-result XML as an artifact** (named to match
  `ARTIFACT_NAME`). Without per-test results the collector cannot name a flaky test.
- **Actions write permission.** Settings → Actions → General → Workflow permissions →
  **Read and write** (the collector pushes the digest branch; the bridge opens PRs and
  issues).
- **The Claude GitHub App is installed** so the routine can run and push `claude/`
  branches.

## Setup procedure

1. **Copy the files.** Copy `templates/flaky-collector.yml` and `templates/flaky-bridge.yml`
   into `.github/workflows/`, and `templates/flaky_parse.py` into `.github/`. Edit the
   collector's `TEST_WORKFLOW`, `ARTIFACT_NAME`, and `WINDOW_DAYS` env values for your
   repo. Commit on the **default branch**.
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`. Bind it to the target repo and grant at least
   `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set schedules.** The collector runs daily by default; set the routine to run
   **weekly** so it acts on an established digest.

## How to verify it works

On a throwaway repo with one deliberately ~50%-flaky test whose CI uploads JUnit
results:

```bash
# run the test workflow a few times on the SAME commit (re-run), then trigger the collector
gh workflow run flaky-collector.yml
git fetch origin flaky-digest && git show flaky-digest:flaky-digest.json   # the test is listed
# then trigger the routine:
gh pr list --head 'claude/flaky-' --state open       # >=2 flipping SHAs -> a quarantine PR
gh issue list --search 'in:title "flaky tests pending triage"'   # 1 SHA -> the rolling issue
```

## Guardrails (why it is safe)

- The routine pushes only to `claude/` branches and never merges.
- It edits only test files to **skip** a flaky test (with a reason linking the issue);
  it never deletes a test and never edits product code.
- It quarantines only tests confirmed flaky on **≥2 distinct commits**; a single
  occurrence is reported as evidence only, not skipped.
- If it can't locate a test or determine the skip idiom, it does not edit — evidence
  only.
- The collector pushes only to the `flaky-digest` data branch, never `main`.
- One quarantine PR **or** one rolling issue per run; a no-flaky run pushes nothing.
- Fork PRs are not supported (Actions cannot push to a fork's branch).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Digest is empty / `runs_missing_artifact` high | Your test workflow isn't uploading JUnit results as `ARTIFACT_NAME`. Add the artifact upload. |
| Collector finds no runs | `TEST_WORKFLOW` doesn't match your CI workflow filename, or no runs in `WINDOW_DAYS`. |
| Nothing flagged despite known flakes | Flakiness never recurred on the *same* SHA (only different commits failed) — by design, that's a regression signal, not flakiness. |
| Quarantine PR never appears, only issues | No test reached `distinct_sha_count >= 2`, or the routine couldn't determine the skip idiom. |
| Collector push fails (403) | Actions token is read-only. Settings → Actions → General → Workflow permissions → **Read and write**. |
