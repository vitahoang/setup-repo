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

These routine skills share a common pattern (Claude routine → `claude/` branch →
Actions bridge → PR), documented in
[`skills/_shared/routine-skeleton.md`](skills/_shared/routine-skeleton.md).

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
```
