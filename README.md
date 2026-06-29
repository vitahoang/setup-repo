# setup-repo

A Claude Code plugin of repo-setup automations.

## Install

```
/plugin marketplace add <git-url-of-this-repo>
/plugin install setup-repo@setup-repo
```

## Skills

- **auto-merge-pr** — set up automated PR review + merge-on-approval for a GitHub
  repo. An engineering-manager routine (fired by Claude's GitHub integration)
  reviews each PR, runs the project's checks, fixes confident issues, posts a
  verdict, surfaces a `pr-review-em` check, and squash-merges only after a human
  approves. See [`skills/auto-merge-pr/SKILL.md`](skills/auto-merge-pr/SKILL.md).
- **e2e-coverage-routine** — set up a scheduled routine that periodically reviews
  the repo's end-to-end test coverage and opens a PR adding new edge-case E2E
  tests. Pairs with an E2E CI workflow that runs the Playwright suite against a
  local stack (Dockerized Supabase + dev server) and a bridge that turns the
  routine's `claude/` branch into a PR. See
  [`skills/e2e-coverage-routine/SKILL.md`](skills/e2e-coverage-routine/SKILL.md).
- **dependency-update-routine** — set up a scheduled routine that opens one PR per
  run with the patch/minor dependency updates that pass the project's check gate,
  listing majors and sensitive packages as `NEEDS-HUMAN`. Language-agnostic
  (npm/pip/cargo/go/…); built on the shared routine skeleton. See
  [`skills/dependency-update-routine/SKILL.md`](skills/dependency-update-routine/SKILL.md).
- **docs-sync-routine** — set up a scheduled routine that keeps docs in sync with
  code: it fixes verifiable code/doc drift (broken command/path refs, stale env vars,
  mismatched API signatures, failing examples, stale generated API docs) via a PR, and
  files a tracking issue for verified drift it can't safely auto-fix. Built on the
  shared routine skeleton. See
  [`skills/docs-sync-routine/SKILL.md`](skills/docs-sync-routine/SKILL.md).
- **flaky-test-routine** — set up a scheduled collector that mines CI runs + JUnit
  artifacts for flaky tests (same-SHA pass/fail disagreement), plus a routine that files
  a tracking issue with the evidence or opens a PR quarantining strongly-confirmed
  flaky tests. Built on the shared routine skeleton. See
  [`skills/flaky-test-routine/SKILL.md`](skills/flaky-test-routine/SKILL.md).
- **security-triage-routine** — set up PR security triage: a PR-triggered routine scans
  the diff (gitleaks, dependency audit, semgrep) plus GitHub code-scanning alerts, posts
  a `security-triage` check + triaged comment, auto-fixes only safe dependency bumps, and
  escalates secrets and code findings as `NEEDS-HUMAN`. See
  [`skills/security-triage-routine/SKILL.md`](skills/security-triage-routine/SKILL.md).

These routine skills share a common pattern (Claude routine → `claude/` branch →
Actions bridge → PR), documented in
[`skills/_shared/routine-skeleton.md`](skills/_shared/routine-skeleton.md). The four
cron-fired routines (dependency-update, docs-sync, flaky-test, e2e-coverage) are
auto-provisioned via `/schedule` (a recurring cloud routine); auto-merge-pr and
security-triage stay on the GitHub PR-event trigger.

`repo-bootstrap` is the exception — a one-shot scaffolder (not a routine) that sets up the
foundation the routines assume:

- **repo-bootstrap** — a one-shot scaffolder (run by the agent, not a routine) that sets
  up the foundation the other skills assume: a `check` gate, base CI, `CLAUDE.md`, PR
  template, squash-merge settings, and a default-branch protection ruleset (block
  force-push + deletion, require a PR + the CI check). Detects what exists and fills only
  the gaps. See [`skills/repo-bootstrap/SKILL.md`](skills/repo-bootstrap/SKILL.md).

## Layout

```
.claude-plugin/
  plugin.json        # plugin manifest
  marketplace.json   # makes this repo directly installable as a marketplace
skills/
  _shared/
    routine-skeleton.md  # the pattern every routine skill follows
    templates/           # shared guardrail preamble + open-a-PR bridge template
  auto-merge-pr/
    SKILL.md
    templates/       # the workflows + routine prompt the skill installs
  e2e-coverage-routine/
    SKILL.md
    templates/       # e2e CI workflow + routine prompt (bridge from _shared)
  dependency-update-routine/
    SKILL.md
    templates/       # routine prompt (bridge from _shared)
  docs-sync-routine/
    SKILL.md
    templates/       # routine prompt + PR-or-issue bridge
  flaky-test-routine/
    SKILL.md
    test_flaky_parse.py
    templates/       # collector + JUnit parser + routine prompt + PR-or-issue bridge
  security-triage-routine/
    SKILL.md
    templates/       # routine prompt + register/land-verdict bridge
  repo-bootstrap/
    SKILL.md
    templates/       # ci.yml + ruleset.json + PR template + CLAUDE.md starter
```
