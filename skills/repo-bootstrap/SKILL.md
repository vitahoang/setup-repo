---
name: repo-bootstrap
description: Use when setting up a new or existing GitHub repo with the foundation the other setup-repo skills assume — a check gate, base CI workflow, CLAUDE.md, PR template, squash-merge settings, and a default-branch protection ruleset (block force-push + deletion, require a PR and the CI check). A one-shot scaffolder the agent runs; it detects what already exists and fills only the gaps, and previews/confirms the GitHub settings changes before applying.
---

# repo-bootstrap — Scaffold a Repo's Foundation

This skill is a one-shot scaffolder you (the agent) run in the target repo. It is **not**
a routine — there is no cloud routine or `claude/`-branch bridge. You detect what already
exists, create only what is missing (**never clobber**), and **preview + confirm** the
outward-facing GitHub changes before applying them.

## What it sets up

1. A **`check` gate** — the project's lint + typecheck + test entrypoint.
2. A **base CI workflow** (`.github/workflows/ci.yml`) with a job named `check`.
3. A **`CLAUDE.md`** whose Commands section names the `check` command.
4. A **PR template** (`.github/pull_request_template.md`).
5. **GitHub settings**: enable squash merging + auto-delete head branches, and a
   **default-branch protection ruleset** (block force-push + deletion, require a PR and
   the `check` status).

## Procedure

Work top to bottom. For each file piece, **if it already exists, leave it and report
"already present (skipped)"**. Set `REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"`.

### 1. Detect the ecosystem and create the check gate
Inspect the repo: `package.json` → npm/pnpm/yarn; `pyproject.toml`/`requirements*.txt` →
python; `Cargo.toml` → rust; `go.mod` → go; `Gemfile` → ruby. Create a real `check`
entrypoint for that stack (lint + typecheck + test):
- **npm/pnpm/yarn:** add a `"check"` script to `package.json` (e.g. lint + `tsc --noEmit`
  + test) if one is not already present.
- **other stacks:** add a `Makefile` `check:` target or a `./check.sh` running that
  stack's lint + typecheck + test.
- **unknown stack:** write a `./check.sh` stub that documents what to fill in.
If a check entrypoint already exists, use its command and skip creating one.

### 2. Base CI workflow
If no CI workflow already runs the check, copy `templates/ci.yml` to
`.github/workflows/ci.yml` and replace its `Run check` step with the stack's setup +
check command from step 1. **Keep the job id `check`.**

### 3. CLAUDE.md
If absent, copy `templates/CLAUDE.md` and fill the project name + set the Commands entry
to the actual `check` command. If a `CLAUDE.md` exists, leave it (optionally note that a
Commands/`check` entry helps the other skills).

### 4. PR template
If absent, copy `templates/pull_request_template.md` to `.github/pull_request_template.md`.

### 5. GitHub settings + ruleset (outward-facing — PREVIEW + CONFIRM first)
These change repo behavior, so show the exact commands and ask before running them.

- **Squash merging:**

      gh api -X PATCH "repos/$REPO" -F allow_squash_merge=true -F delete_branch_on_merge=true

  Skip if already enabled (`gh api "repos/$REPO" --jq '.allow_squash_merge'`).

- **Default-branch ruleset:** first check it does not already exist:

      gh api "repos/$REPO/rulesets" --jq '.[].name'

  If `repo-bootstrap: default branch protection` is absent, confirm the keystone: the
  ruleset requires a status context named `check`, which must equal the CI job name from
  step 2. (If the repo's existing CI uses a different job name, set that context in the
  payload instead.) Then write this skill's `templates/ruleset.json` to a temp file and
  post it (`--input` needs a path that resolves from the target repo's working directory,
  so don't pass the plugin-relative template path):

      cp <path-to>/templates/ruleset.json /tmp/ruleset.json   # or write the JSON yourself
      gh api -X POST "repos/$REPO/rulesets" --input /tmp/ruleset.json

  `~DEFAULT_BRANCH` in the payload targets the repo's default branch automatically.

### 6. Summarize
Print a summary listing each of the five pieces as **created**, **skipped (already
present)**, or **applied**, and point to the routine skills (auto-merge-pr,
dependency-update-routine, docs-sync-routine, flaky-test-routine, security-triage-routine)
as next steps now that the `check` gate is enforced.

## Repo prerequisites

- **`gh` is authenticated** with admin rights on the repo (rulesets + settings need admin).
- Run from inside a clone of the target repo (so file writes land in the right place).

## How to verify it works

On a throwaway repo:

```bash
# first run: creates the missing files; after confirming, applies the ruleset + squash
gh api "repos/$REPO/rulesets" --jq '.[].name'   # shows "repo-bootstrap: default branch protection"
# re-run the skill: every piece should report "already present (skipped)" (idempotent)
```

## Guardrails (why it is safe)

- **Never clobbers**: existing files/settings are left untouched and reported as skipped.
- **Outward GitHub changes (squash setting + ruleset) are previewed and confirmed** before
  applying — they change repo behavior and the ruleset can block merges.
- The keystone (`check` job name == ruleset required context) is verified before posting,
  so the ruleset never blocks merges waiting on a check that does not exist.
- The default ruleset requires **0** approvals, so a solo maintainer is not blocked.
- It does not install the routine skills; it only sets up the foundation and points to them.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Ruleset blocks every merge | The CI job name and the ruleset's required context disagree. Make both `check` (or set the ruleset context to the real CI job name). |
| `gh api ... /rulesets` 403 | The token lacks admin on the repo; rulesets require admin. |
| CI always fails after bootstrap | The `ci.yml` `Run check` step still has the placeholder; fill it with the real check command. |
| A second bootstrap re-applies things | It shouldn't — it skips existing files and checks for the ruleset by name. Confirm the ruleset name matches `repo-bootstrap: default branch protection`. |
