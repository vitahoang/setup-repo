# Design — repo-bootstrap

**Date:** 2026-06-29
**Status:** Approved (brainstorm), pending implementation plan
**Plugin:** `setup-repo`
**Program:** skill #7 — the final skill (docs-sync ✅ → flaky-test ✅ → security-triage ✅ → **repo-bootstrap**)

## Summary

`repo-bootstrap` is a one-shot scaffolder, run by the **local agent** (not a cloud
routine), that sets up the foundation the other setup-repo skills assume: a `check`
gate, a base CI workflow, a `CLAUDE.md`, a PR template, squash-merge settings, and a
default-branch protection **ruleset** (block force-push + deletion, require a PR + the
CI check). It detects what already exists and fills only the gaps (never clobbers), and
it previews + confirms the outward-facing GitHub changes before applying them.

## Context

Unlike the six routine skills, `repo-bootstrap` is not a cron/PR-triggered routine and
does not use the `_shared` routine skeleton or a `claude/`-branch bridge. The local
agent runs it interactively in the target repo, writing files and configuring the repo
via `gh api`. It establishes the keystone the routine skills auto-detect — a `check`
command and an enforced CI gate.

The user requested branch protection specifically: block force-pushing and deletion, and
require status checks before merging.

## Scope

### In scope
- `skills/repo-bootstrap/SKILL.md` — the guided procedure.
- `skills/repo-bootstrap/templates/ci.yml` — base CI workflow (a job **named `check`**).
- `skills/repo-bootstrap/templates/pull_request_template.md` — generic PR template.
- `skills/repo-bootstrap/templates/CLAUDE.md` — starter with a Commands section naming
  the `check` command.
- `skills/repo-bootstrap/templates/ruleset.json` — default-branch ruleset payload.
- `README.md` + `.claude-plugin/{plugin,marketplace}.json` (→ `0.7.0`).

### Out of scope
- Installing the routine skills themselves (auto-merge-pr, etc.) — repo-bootstrap sets up
  the foundation; the routines are documented as next steps.
- Any `_shared` skeleton use (not a routine).

## Section 1 — Deliverables

A one-shot scaffolder run by the local agent (no cloud routine, no bridge):

- `SKILL.md` — the guided procedure: detect → fill gaps → preview → confirm → apply →
  summarize.
- `templates/ci.yml` — a base CI workflow skeleton with a job **named `check`** that runs
  the project's check command on PRs + default-branch pushes (the agent fills the
  ecosystem-specific setup/install steps).
- `templates/pull_request_template.md` — a generic PR template.
- `templates/CLAUDE.md` — a starter whose **Commands** section names the `check` command
  (so the routine skills' gate-detection finds it).
- `templates/ruleset.json` — the default-branch ruleset payload for `gh api`.
- One-line README note + manifests → `0.7.0`.

## Section 2 — What it sets up (detect + fill gaps, never clobber)

Five foundation pieces; each is created only if missing, else reported "already present
(skipped)":

1. **Check gate** — detect the ecosystem (`package.json`→npm/pnpm/yarn,
   `pyproject`/`requirements`→python, `Cargo.toml`→rust, `go.mod`→go, `Gemfile`→ruby) and
   scaffold a real `check` entrypoint (lint + typecheck + test for that stack): an npm
   `check` script, or a `Makefile`/`check.sh` target elsewhere. Unknown stack → a
   documented `check.sh` stub. Skip if a check already exists.
2. **Base CI** — `.github/workflows/ci.yml` with a **`check` job** running the gate on PRs
   + default-branch pushes. Skip if a CI workflow already runs the check.
3. **CLAUDE.md** — a starter whose Commands section names the `check` command. Skip if
   present.
4. **PR template** — `.github/pull_request_template.md`. Skip if present.
5. **GitHub settings + ruleset (outward-facing → preview + confirm before applying):**
   enable **squash merging** + auto-delete head branches
   (`gh api -X PATCH repos/{owner}/{repo}`); create the default-branch **ruleset** from
   `ruleset.json`. Detect an existing ruleset by name → skip / offer update.

It ends with a **summary**: each piece marked *created* / *skipped (already present)* /
*applied*, plus a next-step pointer to the routine skills.

## Section 3 — The ruleset payload + the keystone `check`-name wiring

The default-branch ruleset (`templates/ruleset.json`, POSTed via
`gh api -X POST repos/{owner}/{repo}/rulesets --input ruleset.json`):

```json
{
  "name": "repo-bootstrap: default branch protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": { "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false,
        "require_last_push_approval": false, "required_review_thread_resolution": false } },
    { "type": "required_status_checks",
      "parameters": { "strict_required_status_checks_policy": false,
        "required_status_checks": [ { "context": "check" } ] } }
  ]
}
```

- `~DEFAULT_BRANCH` is GitHub's special ref for the repo's default branch — no hardcoded
  `main`.
- `deletion` blocks deletion; `non_fast_forward` blocks force-push; `pull_request` with
  **0** approvals requires a PR but not a review; `required_status_checks` requires the
  `check` context.

**The keystone (single most important wiring):** the CI workflow's job is named **`check`**,
so its status context is `check`, and the ruleset requires the `check` context. These
**must match exactly** — otherwise the ruleset either blocks every merge waiting on a
check that never reports, or fails to gate at all. `SKILL.md` makes the agent verify they
agree (and if the repo's *existing* CI uses a different job name, use that name in the
ruleset instead).

The squash-merge setting is a separate
`gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F delete_branch_on_merge=true`.

Both outward changes are **previewed and confirmed** before applying. Idempotency checks
`gh api repos/{owner}/{repo}/rulesets` for the bootstrap ruleset name (skip if present)
and the current squash setting.

## Section 4 — Verification

(A skill of templates + an agent procedure — checks + a documented smoke test.)

- `templates/ci.yml` parses as valid YAML and its job is named **`check`**;
  `templates/ruleset.json` parses as valid JSON and contains the `deletion`,
  `non_fast_forward`, `pull_request`, and `required_status_checks` rules;
  `pull_request_template.md` and the `CLAUDE.md` starter are present and non-empty.
- **Keystone consistency check:** the CI job name in `ci.yml` == the
  `required_status_checks` context in `ruleset.json` == `check` (parse both, assert
  equal) — the one thing that, if mismatched, silently breaks merges.
- `SKILL.md` contains the exact `gh api` commands (PATCH for squash, POST for the ruleset)
  and documents the never-clobber / preview-confirm / summary structure.
- **Documented smoke test:** run on a throwaway repo → creates the missing files and
  (after confirm) applies the ruleset + squash setting; **re-run → everything reports
  "already present (skipped)"** (idempotency); `gh api repos/{owner}/{repo}/rulesets --jq
  '.[].name'` shows the bootstrap ruleset.

## Open questions / deferred

- Whether to also disable merge-commit / rebase-merge (squash-only) — left enabled-squash
  + keep others; a stricter squash-only is a documented option, not the default.
- Per-ecosystem `check` contents (which linters/typecheckers) — start with the common
  tools per stack and degrade to a documented stub when unsure; the agent uses judgment.
- Offering to install the routine skills at the end — kept as a documented pointer, not an
  action, to keep repo-bootstrap focused.
