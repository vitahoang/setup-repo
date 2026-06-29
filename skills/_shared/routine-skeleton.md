# Routine Skeleton — shared pattern for setup-repo routine skills

Every routine-style skill in this plugin shares one shape. This doc names it so each
`SKILL.md` only has to describe what is *different* about its skill.

## The shape

    cron / GitHub event fires a Claude Code routine (bound to the repo on the web)
            |
            v
    routine inspects the repo, does its domain work, pushes claude/<purpose>-<id>
            |
            v
    a GitHub Actions BRIDGE turns that branch into a PR (or lands it) — because the
    cloud routine has no GitHub API access
            |
            v
    a human reviews and merges the PR

## Shared parts (use these — do not re-invent)

- **Branch convention.** The routine pushes only to `claude/<purpose>-<id>`. Never
  the default branch, never a PR head directly.
- **Guardrail preamble.** `templates/routine-prompt.preamble.md` — paste it FIRST,
  ahead of the skill's own routine prompt, when creating the routine on the web. It
  carries the only-push-to-`claude/`, no-API, no-merge, and `NEEDS-HUMAN` rules.
- **Open-a-PR bridge.** `templates/pr-bridge.yml` — a token-substituted workflow for
  routines that OPEN a fresh PR from their branch (dep-update, e2e-coverage, and the
  future docs-sync / flaky-test / security-triage). Copy it into the target repo's
  `.github/workflows/` and substitute `{{WORKFLOW_NAME}}`, `{{BRANCH_GLOB}}`,
  `{{CONCURRENCY_PREFIX}}`, `{{PR_TITLE}}`, `{{DEFAULT_BODY}}`. Token values are plain
  text: `{{DEFAULT_BODY}}` is set as a YAML block-scalar `env:` variable, so the
  script reads it back as a plain `"$DEFAULT_BODY"` — its contents are never re-parsed
  for shell metacharacters, and backticks / `$` stay literal with no escaping (keep it
  to a single line, or indent any continuation lines to match the block scalar). By
  contrast `{{PR_TITLE}}` is a normal double-quoted shell string, so it *may* use an
  expansion like `${BRANCH#claude/}` if a skill wants the branch name in the title.
  - Routines that instead LAND work onto an *existing* PR + post a verdict (today:
    `auto-merge-pr`) need a different, specialized bridge — they still follow the
    branch convention and preamble, but ship their own bridge workflow.
  - Routines that report findings as a GitHub **issue** when there is nothing to PR
    (e.g. docs-sync) ship their own **PR-or-issue** bridge for now; it is a candidate
    to promote into `templates/` once a second such routine exists.
    (Two such skills now exist — docs-sync and flaky-test — so promoting this bridge
    into `templates/` is a tracked follow-up.)
- **Escalation protocol.** Put anything the routine refuses to auto-do under a
  `NEEDS-HUMAN` heading in the commit/verdict body, with reason + evidence.
- **Gate auto-detection.** To find a project's check command: a `check` script in
  `package.json`, else the "Commands" section of `CLAUDE.md` / README, else a sane
  ecosystem default. Run it to verify the routine's changes before pushing.

## What each skill declares for itself

Its **trigger** (cron vs `pull_request` vs issue), its **inspection logic** (what it
reads and what it produces), and its **domain guardrails** (what it refuses to touch).
