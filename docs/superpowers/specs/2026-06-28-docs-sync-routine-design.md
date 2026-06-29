# Design — docs-sync-routine

**Date:** 2026-06-28
**Status:** Approved (brainstorm), pending implementation plan
**Plugin:** `setup-repo`
**Program:** skill #2 of the planned suite (docs-sync → flaky-test → security-triage → repo-bootstrap)

## Summary

`docs-sync-routine` is a cron-fired Claude routine that detects **verifiable** drift
between a repo's code and its docs (READMEs, `CLAUDE.md`, `docs/**`, generated API
reference) and either opens a PR fixing the drift it can fix unambiguously, or opens
a tracking issue for drift it has verified but cannot safely auto-fix. It is built on
the existing `skills/_shared/` routine skeleton.

## Context

The plugin already has a shared routine skeleton (`skills/_shared/`: guardrail
preamble + open-a-PR `pr-bridge.yml` + `routine-skeleton.md`) and three skills.
`docs-sync-routine` reuses the preamble and skeleton doc, but needs a **PR-or-issue**
bridge that the shared open-a-PR bridge does not provide.

The hard part of a docs-sync tool is trust: "the docs are stale" is usually a
judgment call, which produces noisy, low-value PRs. This design avoids that by
targeting **only mechanically verifiable drift** — every reported item has a
deterministic code anchor — and applying LLM judgment only to the *correction*.

## Scope

### In scope
- `skills/docs-sync-routine/SKILL.md`
- `skills/docs-sync-routine/templates/routine-prompt.md`
- `skills/docs-sync-routine/templates/docs-sync-bridge.yml` (skill-specific PR-or-issue bridge)
- One added line in `skills/_shared/routine-skeleton.md` noting that issue-reporting
  routines ship their own PR-or-issue bridge for now (candidate for `_shared`
  promotion once flaky-test is a second consumer).

### Out of scope (later, each its own spec)
- flaky-test-routine, security-triage-routine, repo-bootstrap.

## Section 1 — Deliverables

Built on the skeleton, mirroring the sibling skills' house style:

- `SKILL.md` — overview, flow, check battery, setup, verify, guardrails, common
  mistakes.
- `templates/routine-prompt.md` — the mandate; the shared guardrail preamble is
  pasted ahead of it (setup step instructs pasting preamble first, then this).
- `templates/docs-sync-bridge.yml` — a **skill-specific** bridge (the shared
  `pr-bridge.yml` only opens PRs). Triggers on push to `claude/docs-sync-*` and
  routes by the branch's tree vs the default branch:
  - branch carries real doc-file edits → **open or reuse a PR** (same logic as the
    shared bridge), tip commit body as the description;
  - branch is a findings-only **empty commit** (tree identical to base) → **open or
    update a single tracking issue** from the commit body, deduped by a fixed title
    so repeated runs update rather than spam.

Reuses from `_shared/`: the guardrail preamble and the routine-skeleton doc (cited).

**Note (#3 flaky-test):** flaky-test also files issues, so this PR-or-issue bridge is
a likely future `_shared` promotion. Per the plugin's empirical rule, it is NOT
shared until that second consumer exists.

## Section 2 — The check battery (what "verifiable drift" means)

A fixed set of mechanical checks; every reported drift has a deterministic anchor.
Run across READMEs, `CLAUDE.md`, and `docs/**`:

1. **Command/script refs** — commands shown in docs (`npm`/`pnpm run X`, `make Y`,
   `just Z`, etc.) with no matching script/target. → fix to the real name if the
   rename is unambiguous, else escalate.
2. **Path refs** — file paths / relative links in docs that don't resolve. → update
   to the moved location if unambiguous, else escalate.
3. **Env vars (both directions)** — documented in README/`CLAUDE.md` but read nowhere
   in code (stale → flag/remove), or read by code but undocumented (missing → add).
4. **Runnable code blocks** — fenced blocks tagged as a runnable language/shell that
   error when executed. → mechanical fix if obvious (a renamed flag), else escalate
   as a broken-example finding.
5. **API signatures** — function/CLI signatures quoted in docs that don't match
   source. → update the doc to match source (code is truth).
6. **Generated API reference** — if an API doc section is tool-generated (a detectable
   generator config/command) and stale → **regenerate via that command**; if no
   generator is detectable → escalate (never hand-fake generated output).

**Source-of-truth rule:** code is authoritative; docs conform to code. When it is
genuinely ambiguous whether the *doc* or the *code* is wrong (e.g. a documented env
var the code never reads — could be a code bug), the routine escalates rather than
guessing.

## Section 3 — Flow, PR-or-issue routing & safety policy

```
cron fires the routine (Claude on the web, schedule-bound to the repo)
   │
   ├─ 1. pull default branch; set bot identity
   ├─ 2. DETECT — run the 6-check battery across README(s), CLAUDE.md, docs/**
   ├─ 3. CLASSIFY each verified drift:
   │       unambiguous mechanical fix (incl. regen via a detected doc-gen command)
   │            → auto-fix candidate
   │       ambiguous / needs authoring judgment / generated-but-no-generator
   │            → escalate (NEEDS-HUMAN)
   ├─ 4. APPLY candidate fixes to DOC FILES ONLY (never product code)
   ├─ 5. RE-VERIFY — re-run the relevant checks on the edited docs so each applied
   │       fix actually resolves its drift and introduces no new broken ref;
   │       any fix that doesn't re-verify is dropped → escalated
   ├─ 6. COMMIT + PUSH claude/docs-sync-<id>:
   │       fixes applied → normal commit (doc edits); commit body = report
   │       only escalations → empty commit (git commit --allow-empty); body = report
   └─ 7. docs-sync-bridge.yml routes on the branch's tree vs base:
            tree differs (real doc edits) → open/reuse a PR, body = report
            tree identical (empty commit) → open/UPDATE the single docs-sync
                 tracking issue (deduped by a fixed title), body = report
            no drift at all → routine pushes nothing, ends
```

**Safety policy (Approach C — checker-anchored detection, LLM-authored fix):**

- *Auto-fix* only when: the drift is mechanically verified **and** the correction is
  unambiguous **and** re-running the check confirms it is resolved.
- *Always escalate*: ambiguous corrections (several candidate paths), broken examples
  needing a real rewrite, generated docs with no detectable generator, and any case
  where the only "fix" would be editing product code (a possible code bug — code is
  truth, but this routine never edits code).
- The routine edits ONLY doc files.

**Report format** (the commit body — becomes the PR description or the issue body):

```
## Fixed (verified mechanical doc corrections)
- <file>: <what drifted> -> <fix>  (<which check caught it>)

## NEEDS-HUMAN (verified drift, not safely auto-fixable)
- <file>: <drift>  (<check>): <why a human is needed / what's ambiguous>
```

**Issue dedupe:** a fixed issue title (e.g. `docs-sync: verified doc drift pending
review`). The bridge finds an existing open issue with that title and updates its
body (or comments) rather than opening a new one each run.

## Section 4 — Guardrails & verification

**Guardrails** (atop the shared preamble):

- Edits only doc files (`README*`, `CLAUDE.md`, `docs/**`, and generated-API outputs
  *via the project's own doc-gen command*). Never edits product code.
- Code is source of truth; never edits code to match docs; ambiguous direction
  escalates.
- Never fabricates content — every fix traces to a check and is re-verified after
  applying.
- One PR **or** one deduped issue per run; a no-drift run pushes nothing.
- For generated API docs, only ever regenerate via the detected command; never
  hand-write generated output.
- Fork PRs unsupported (Actions can't push to a fork's branch).

**Verification** (it is a docs/YAML plugin — checks, not unit tests):

- `docs-sync-bridge.yml` parses as valid YAML and declares
  `permissions: contents: write, pull-requests: write, issues: write`.
- **Consistency:** the `claude/docs-sync-*` glob is identical across `SKILL.md`,
  `routine-prompt.md`, and the bridge; `SKILL.md` cites the skeleton + preamble.
- **Live smoke test (documented in SKILL.md):** on a throwaway repo —
  (a) a stale command ref (`npm run buildx` where the script is `build`) → expect a
  **PR** with the fix; (b) only a broken runnable code block needing a rewrite →
  expect a **tracking issue**, no PR; (c) a clean repo → expect **nothing**.

## Open questions / deferred

- Exact issue title string and whether to update-body vs append-comment on repeated
  runs — settle during implementation; default to update-body for a single living
  report.
- The precise per-ecosystem detection of a "doc-gen command" (check #6) — start with
  common cases (e.g. a `docs`/`typedoc`/`sphinx` script) and escalate when unsure.
