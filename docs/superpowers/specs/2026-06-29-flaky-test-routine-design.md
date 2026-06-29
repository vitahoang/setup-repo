# Design — flaky-test-routine

**Date:** 2026-06-29
**Status:** Approved (brainstorm), pending implementation plan
**Plugin:** `setup-repo`
**Program:** skill #3 of the planned suite (docs-sync ✅ → **flaky-test** → security-triage → repo-bootstrap)

## Summary

`flaky-test-routine` is a cron-fired Claude routine that finds flaky tests from CI
history and either files a tracking issue with the evidence, or — for strongly
confirmed cases — opens a PR that quarantines (skips) the test. Because routines have
no GitHub API access, a scheduled **collector workflow** mines the CI runs and their
JUnit artifacts into a `flaky-digest.json` (committed to a dedicated data branch); the
routine reads the digest over git. Built on the existing `skills/_shared/` skeleton.

## Context

The plugin has a shared routine skeleton (`skills/_shared/`: guardrail preamble +
open-a-PR `pr-bridge.yml` + `routine-skeleton.md`) and five skills. flaky-test reuses
the preamble and skeleton doc, and ships its own PR-or-issue bridge (see Scope).

The hard problem is trust: a false positive could quarantine a test that is catching a
real intermittent bug. The design earns trust with an objective signal — **same-SHA
disagreement** (a test that both passes and fails on the *same commit*, i.e. identical
code, nondeterministic outcome) — and only takes the aggressive action (quarantine)
when that signal **recurs across ≥N distinct commits**.

## Scope

### Bridge: self-contained now, promote later (decided)

flaky-test is the second skill to need a PR-or-issue bridge (after docs-sync). Rather
than promote that bridge into `_shared` immediately, flaky-test **ships its own
`flaky-bridge.yml`** (adapted from docs-sync's, merge-base routing included). Rationale:
the routing logic has not yet run in production, so sharing now risks premature
abstraction and would churn the just-merged docs-sync. The promotion is a tracked
follow-up for when both consumers are stable. (See the `promote-pr-or-issue-bridge`
project note.)

### In scope
- `skills/flaky-test-routine/templates/flaky-collector.yml` — scheduled collector.
- `skills/flaky-test-routine/templates/flaky-bridge.yml` — own PR-or-issue bridge.
- `skills/flaky-test-routine/templates/routine-prompt.md` — the routine mandate.
- `skills/flaky-test-routine/SKILL.md`.
- One-line update to `skills/_shared/routine-skeleton.md` (now two issue-reporting
  skills; promotion tracked).
- `README.md` + `.claude-plugin/{plugin,marketplace}.json` (→ `0.5.0`).

### Out of scope (later, each its own spec)
- The bridge promotion into `_shared`; security-triage; repo-bootstrap.

## Section 1 — Deliverables

Built on the skeleton, house style matching the siblings:

- `templates/flaky-collector.yml` — the collector workflow (Section 2).
- `templates/flaky-bridge.yml` — a concrete PR-or-issue bridge: fires on push to
  `claude/flaky-*`, routes by merge-base tree-diff (doc/test edits → PR; empty commit →
  open/update the rolling issue). Same logic as docs-sync's bridge with the merge-base
  fix; `ISSUE_TITLE` = `flaky tests pending triage`.
- `templates/routine-prompt.md` — the mandate (Section 3); shared preamble pasted ahead.
- `SKILL.md` — setup, signal explanation, verify, guardrails, common mistakes.

Reuses from `_shared/`: the guardrail preamble and the routine-skeleton doc (cited).

## Section 2 — The collector (`flaky-collector.yml`)

A scheduled GitHub Actions workflow that turns CI history into a digest the routine
reads over git (the routine has no API access).

- **Trigger:** `schedule` (default daily cron). Stateless — each run recomputes from a
  trailing window, so there is no accumulated state to corrupt. (`workflow_run` on the
  test workflow completing is an optional add-on, not the default.)
- **Permissions:** `actions: read` (list runs, download artifacts) + `contents: write`
  (push the digest branch).
- **Per run:**
  1. List completed runs of the configured **test workflow** on the default branch
     within the window (default **14 days**).
  2. Download each run's **JUnit test-result artifact** (configurable artifact
     name/glob).
  3. Parse per-test outcomes keyed by `(test id, commit SHA, run id)`, where test id =
     classname/suite + test name + file.
  4. Compute **same-SHA disagreement** per test (SHAs where it both passed and failed);
     rank tests by **distinct-SHA count**.
  5. Write `flaky-digest.json` and **force-push it to a dedicated `flaky-digest` data
     branch** (single file; no `main` noise; the routine reads it via `git fetch`).
- **Parser:** an inline `python3` step using stdlib `xml.etree` (no extra deps;
  `ubuntu-latest` has Python).

**Digest schema:**

```json
{
  "generated_at": "<iso8601>",
  "window_days": 14,
  "workflow": "ci.yml",
  "runs_parsed": 42,
  "runs_missing_artifact": 3,
  "flaky": [
    {
      "test": "<suite> :: <name>",
      "file": "<path|null>",
      "distinct_sha_count": 3,
      "flip_shas": ["<sha>", "..."],
      "sample_run_urls": ["<url>", "..."],
      "first_seen": "<iso8601>",
      "last_seen": "<iso8601>"
    }
  ]
}
```

- **Project-specific config** (documented in `SKILL.md`, adapted per repo like
  `e2e-local.yml` is stack-specific): the test-workflow filename, the JUnit artifact
  name/glob, and the window. `runs_missing_artifact` makes the "did the project upload
  results?" prerequisite visible.

## Section 3 — The routine (`flaky-test-routine`)

```
cron fires the routine (Claude on the web, schedule-bound; its own cadence)
   │
   ├─ 1. pull default branch; set bot identity
   ├─ 2. git fetch origin flaky-digest; read flaky-digest.json
   │        (branch/file missing or flaky[] empty -> nothing to do, end)
   ├─ 3. CLASSIFY each flaky test by distinct_sha_count:
   │        >= QUARANTINE_THRESHOLD (default 2)  -> quarantine candidate
   │        == 1 (one-off)                        -> evidence-only
   ├─ 4. For quarantine candidates: locate the test (digest file + name), detect the
   │        framework's skip idiom; if confident, edit ONLY that test file to skip it
   │        with a reason linking the tracking issue. If the test can't be located or
   │        the idiom is unclear -> no edit, downgrade to evidence-only.
   ├─ 5. COMMIT + PUSH claude/flaky-<id>:
   │        quarantine edits -> normal commit (test-file skips); body = report
   │        evidence-only    -> empty commit (--allow-empty);    body = report
   └─ 6. flaky-bridge.yml routes on merge-base tree-diff:
            test edits -> open/reuse a PR (quarantine), body = report
            empty      -> open/update the "flaky tests pending triage" issue, body = report
            no flaky   -> push nothing
```

**Thresholds:** `distinct_sha_count >= 2` (tunable) = strongly confirmed → quarantine;
`== 1` = evidence-only. Same-SHA disagreement is the trust anchor; requiring ≥2 distinct
SHAs before skipping keeps a one-off fluke from masking a real intermittent bug.

**Quarantine mechanism (framework-aware, safe):** apply the framework's skip idiom with
a reason linking the issue — `it.skip`/`test.skip` (jest/vitest),
`@pytest.mark.skip(reason=…)` (pytest), `@Disabled("flaky: …")` (JUnit),
`t.Skip("flaky: …")` (Go), `skip "flaky: …"` (RSpec), etc. **Never deletes** a test —
only skips, so it is trivially recoverable. Edits only test files.

**Issue model:** one rolling **"flaky tests pending triage"** issue (fixed title,
deduped by the bridge), refreshed each run; quarantines go via PR whose body also lists
the evidence-only tests — mirroring docs-sync and fitting the single-action bridge.

**Report format** (commit body → PR description or issue body):

```
## Quarantined (same-SHA flip on >=N distinct SHAs)
- <test> (<file>): flipped on <k> SHAs — <sample run urls>; skipped pending triage

## Flaky — evidence only (not quarantined)
- <test>: flipped on <k> SHA — <sample run urls>
```

## Section 4 — Guardrails & verification

**Guardrails** (atop the shared preamble):

- The routine edits **only test files** (to skip); never product code, never an
  assertion beyond adding the skip.
- Quarantine = skip-with-reason linking the issue; **never delete** a test.
- Quarantine only for `>= N` distinct-SHA same-SHA flips; a single occurrence is
  evidence-only.
- If the framework skip idiom is unclear or the test cannot be located → no edit,
  evidence-only.
- One quarantine PR **or** one rolling issue per run; a no-flaky run pushes nothing.
- The collector pushes only to the `flaky-digest` data branch; never to `main`.
- Fork PRs unsupported (Actions cannot push to a fork's branch).

**Verification** (docs/YAML plugin — checks, not unit tests, with one real exception):

- `flaky-collector.yml` + `flaky-bridge.yml` parse as valid YAML; collector declares
  `actions: read` + `contents: write`; bridge declares `contents`/`pull-requests`/
  `issues: write`; bridge run-script passes `bash -n` with both routes + the merge-base
  diff present.
- **Real parser unit test:** extract the collector's inline `python3` JUnit parser and
  feed two synthetic JUnit files for the **same SHA** (one where `testX` passes, one
  where it fails) → assert the digest flags `testX` with `distinct_sha_count == 1`; add
  a second flipping SHA → assert `== 2`. Genuinely unit-testable; worth doing.
- **Consistency:** `claude/flaky-*` glob across SKILL/prompt/bridge; the `flaky-digest`
  branch name across collector/prompt/SKILL; the rolling issue title `flaky tests
  pending triage` across bridge/SKILL.
- **Documented smoke test:** a throwaway repo with a ~50%-flaky test + JUnit upload; run
  CI a few times on one SHA; the collector → digest lists it; the routine → ≥2 flipping
  SHAs yields a quarantine PR, a single SHA yields the rolling issue.

## Open questions / deferred

- The exact `QUARANTINE_THRESHOLD` default (2) — tune from real data; keep it a named,
  documented knob in the routine prompt.
- Per-framework skip-idiom coverage — start with the common frameworks above; when the
  routine can't determine an idiom, it degrades to evidence-only (no unsafe edit).
- Whether to also trigger the collector on `workflow_run` completion (incremental) in
  addition to the schedule — deferred; schedule-only is the v1.
