# Design — Shared routine skeleton + dependency-update-routine

**Date:** 2026-06-28
**Status:** Approved (brainstorm), pending implementation plan
**Plugin:** `setup-repo`

## Summary

This spec covers two coupled deliverables in the `setup-repo` plugin:

1. **A shared "routine skeleton"** — a reference doc plus shared templates that
   codify the pattern every routine-style skill in this plugin already embodies
   (Claude routine → `claude/` branch → GitHub Actions bridge → PR, with uniform
   guardrails). The two existing skills are retrofitted to reference it.
2. **`dependency-update-routine`** — the first skill built *on* the skeleton: a
   scheduled routine that opens one PR per run with the dependency updates it
   deems safe, escalating risky ones as `NEEDS-HUMAN`.

Building the skeleton with a real first consumer (dep-update) keeps it concrete
rather than speculative.

## Context

The plugin currently has two skills — `auto-merge-pr` (PR review + merge-on-
approval) and `e2e-coverage-routine` (scheduled E2E coverage growth). Both share
the same architecture: a cloud Claude routine that can only push to `claude/`-
prefixed branches and has no GitHub API access, paired with a GitHub Actions
"bridge" workflow that does the API-side work (open PR, comment, land fixes, set
checks). That shared shape is currently duplicated across both skills.

This is the first of a planned set of routine skills (dep-update now; docs-sync,
flaky-test, security-triage, and a one-shot repo-bootstrap later). Extracting the
skeleton now pays off across all of them.

## Scope

### In scope

- `skills/_shared/routine-skeleton.md` — the reference doc.
- `skills/_shared/templates/pr-bridge.yml` — the parameterized bridge workflow
  (open PR / land branch), generalized from the two existing skills' bridges.
- `skills/_shared/templates/routine-prompt.preamble.md` — the shared guardrail
  header (branch discipline, `NEEDS-HUMAN` protocol, no-merge rule, fork-PR
  caveat).
- `skills/dependency-update-routine/SKILL.md` + templates
  (`routine-prompt.md`, `dep-update-bridge.yml`).
- **Retrofit** of `auto-merge-pr` and `e2e-coverage-routine` to reference the
  shared doc and drop their duplicated bridge/guardrail prose — genuinely-shared
  parts only, behavior-preserving.

### Out of scope (later, each its own spec)

- `repo-bootstrap` (#7), `docs-sync-routine` (#2), `flaky-test-routine` (#3),
  `security-triage-routine` (#4). Each reuses the skeleton.

## Section 1 — Deliverables & retrofit

Two coupled things ship together:

**(a) Shared routine skeleton.** A new `skills/_shared/` area:

- `routine-skeleton.md` names the pattern and is cited by each skill's `SKILL.md`.
- `templates/pr-bridge.yml` — the "turn a `claude/<purpose>-<id>` branch into a
  PR / land it" Action, parameterized by purpose + branch-glob. Today this logic
  is duplicated in `pr-fix-bridge.yml` and `e2e-coverage-bridge.yml`.
- `templates/routine-prompt.preamble.md` — the shared guardrail header each
  routine prompt includes by reference.

**(b) `dependency-update-routine`.** The first skill built on the skeleton, so the
skeleton is proven by a real consumer.

**Retrofit constraint (behavior-preserving).** `auto-merge-pr` and
`e2e-coverage-routine` are edited to reference the shared doc and dedupe only the
genuinely-shared bridge/guardrail parts. Their domain-specific workflows
(`pr-approve-merge.yml`, `pr-branch-cleanup.yml`, `e2e-local.yml`, etc.) stay put.
The workflows generated into a target repo must be byte-identical (or trivially
so) before vs after the retrofit.

## Section 2 — The shared routine skeleton

`routine-skeleton.md` codifies the invariant all routine skills share, so each
`SKILL.md` shrinks to "what's different":

- **Branch convention.** The routine pushes only to `claude/<purpose>-<id>`; never
  to the default branch, never to a PR head directly.
- **The bridge.** Because cloud routines have no GitHub API, a `pull_request`- or
  push-triggered Action does the API-side work (open PR, comment, land fixes, set
  checks). `pr-bridge.yml` is parameterized by purpose + branch-glob.
- **Escalation protocol.** A uniform `NEEDS-HUMAN` block format in the PR/comment
  body for anything the routine refuses to auto-do, with reason + evidence.
- **Guardrail preamble.** The no-merge rule, the "refuse risky areas" list, and
  fork-PR non-support — shared prose each routine prompt includes by reference.
- **Gate auto-detection.** The existing "find the `check` command (package.json
  script → CLAUDE.md/README Commands section → default)" logic, lifted to the
  skeleton because every routine skill needs it.

Each skill declares only its **trigger** (cron vs `pull_request` vs issue), its
**inspection logic**, and its **domain guardrails**.

## Section 3 — dependency-update-routine

**Trigger / cadence.** A scheduled Claude Code routine (cron), default **weekly**.
The schedule is set when wiring the routine in Claude on the web; the skill
documents the recommended cron but does not hardcode it in a workflow (matching
`e2e-coverage-routine`).

**Flow (one run):**

```
cron fires routine (schedule-bound to repo)
   │
   ├─ 1. pull default branch
   ├─ 2. DETECT manifests/lockfiles present (package.json, requirements/pyproject,
   │      Cargo.toml, go.mod, Gemfile, …) → per-ecosystem update list
   ├─ 3. CLASSIFY each outdated dep:
   │        patch/minor & NOT on sensitive list → candidate (auto-batch)
   │        major  OR  sensitive (auth/crypto/build-toolchain/framework/
   │                    native-ABI/0.x) → escalate
   ├─ 4. APPLY all candidates, regenerate lockfiles
   ├─ 5. RUN the auto-detected gate ONCE
   │        green → keep batch
   │        red   → bisect: drop offender → NEEDS-HUMAN, re-run remainder
   │        no gate detected → fall back to semver-only, note it in PR body
   ├─ 6. PUSH claude/dep-update-<id>
   └─ 7. bridge (pr-bridge.yml) opens ONE PR:
            title: "chore(deps): weekly safe updates"
            body: table of included updates (name, old→new, ecosystem)
                  + NEEDS-HUMAN section listing majors/sensitive/bisected-out,
                    each with a one-line changelog/risk summary
```

**Safety policy (Approach C — semver scopes, gate confirms):**

- *Auto-included* only if: bump is patch/minor **and** the dep is not on the
  sensitive list **and** the post-update gate is green.
- *Always escalated* (never auto-included, regardless of gate result): majors,
  the sensitive-category list (auth, crypto, build toolchain, frameworks,
  native/ABI deps), and any `0.x` package (where, by semver convention, a minor
  bump may be breaking).
- The routine **only touches dependency manifests + lockfiles.** If an update
  would require app-code changes to pass the gate, that dep is escalated, not
  patched — the routine never edits product code.
- **Degradation:** if no gate is detected, the routine falls back to semver-only
  classification (Approach B) and states this explicitly in the PR body, so the
  reduced assurance is visible to the human reviewer.

**Domain guardrails (on top of the shared preamble):**

- No merging — a human merges the PR.
- One PR per run — no PR spam.
- If nothing is safely updatable, **skip silently** — no empty PR.

**Templates shipped by this skill:**

- `routine-prompt.md` — the dep-update mandate; includes the shared preamble.
- `dep-update-bridge.yml` — a thin instantiation of `pr-bridge.yml` for the
  `claude/dep-update-*` branch glob.
- Gate detection is inherited from the skeleton (not re-specified here).

## Section 4 — Verification

A routine can't be unit-tested conventionally, so verification is:

- **Behavior-preserving retrofit.** Diff the workflow files that `auto-merge-pr`
  and `e2e-coverage-routine` would generate into a target repo, before vs after
  the retrofit. They must be byte-identical (or trivially so). This is the
  regression check that the refactor changed nothing observable.
- **Skill self-consistency.** The `SKILL.md` setup steps, the `pr-bridge.yml`
  parameters, and the routine prompt's branch names must all agree on the
  `claude/dep-update-*` glob — the "two systems must agree" failure mode
  documented in `auto-merge-pr`.
- **Live smoke test (documented in SKILL.md).** Set up the routine on a throwaway
  repo with one deliberately-outdated minor dep and one outdated major; trigger a
  run; confirm a PR appears with the minor included (gate green) and the major in
  the `NEEDS-HUMAN` section.

## Open questions / deferred

- Exact sensitive-package list contents (auth/crypto/etc.) — refine during
  implementation; start conservative (escalate when unsure).
- Whether the skeleton's `pr-bridge.yml` fully subsumes both existing bridges or
  leaves thin per-skill shims — determined empirically during the retrofit diff.
