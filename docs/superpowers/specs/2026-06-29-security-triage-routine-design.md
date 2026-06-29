# Design — security-triage-routine

**Date:** 2026-06-29
**Status:** Approved (brainstorm), pending implementation plan
**Plugin:** `setup-repo`
**Program:** skill #4 of the planned suite (docs-sync ✅ → flaky-test ✅ → **security-triage** → repo-bootstrap)

## Summary

`security-triage-routine` is a PR-triggered Claude routine (fired on PR open/synchronize,
like `auto-merge-pr`) that runs security scanners on the PR diff, triages the union of
findings, posts a triaged comment, sets a `security-triage` check, auto-fixes only the
narrow safe case (a known-vulnerable dependency with a patched version), and escalates
everything else — secrets, SAST, code-scanning findings — as `NEEDS-HUMAN`. Built on the
`auto-merge-pr` land-fixes/verdict bridge pattern.

## Context

`auto-merge-pr` already establishes the PR-triggered pattern in this plugin: a routine
fired by Claude's GitHub integration, paired with a bridge workflow that registers a
pending check, lands the routine's fixes onto the PR head, posts a verdict comment, and
resolves the check. `security-triage-routine` reuses that pattern with a security focus
and its own distinct branch/check names so the two can coexist.

The hard problem is trust and safety: security scanners are noisy (false positives,
duplicates), and auto-fixing security-sensitive code is dangerous. The design earns
trust by **diff-scoping** (only PR-introduced findings), **LLM triage** of the scanner
union (dedupe, severity, false-positive suppression), and keeping the auto-fix surface
to **dependency version bumps only**.

## Scope

### In scope
- `skills/security-triage-routine/templates/routine-prompt.md` — the triage mandate.
- `skills/security-triage-routine/templates/sec-bridge.yml` — the two-job bridge
  (register + land/verdict), mirroring `auto-merge-pr`'s `pr-fix-bridge.yml`.
- `skills/security-triage-routine/SKILL.md`.
- One-line note in `skills/_shared/routine-skeleton.md` (second land-onto-existing-PR +
  verdict flavor, after auto-merge-pr).
- `README.md` + `.claude-plugin/{plugin,marketplace}.json` (→ `0.6.0`).

### Out of scope (later)
- repo-bootstrap (#7, the final skill, includes branch-protection rulesets).
- In-routine CodeQL DB builds (we consume GitHub's existing code-scanning alerts instead).

## Section 1 — Deliverables

A PR-triggered routine modeled on `auto-merge-pr` (fired by Claude's GitHub integration
on PR open/synchronize; configured on the web):

- `templates/routine-prompt.md` — the triage mandate (shared preamble pasted ahead).
- `templates/sec-bridge.yml` — two jobs, mirroring `pr-fix-bridge.yml`:
  - **`register`** (on `pull_request` open/synchronize/reopen): posts a **pending**
    `security-triage` status on the PR head; **and** fetches the PR's code-scanning
    alerts (`gh api .../code-scanning/alerts`) and pushes them as
    `claude/pr-<N>-secinput` (`codeql-alerts.json`) for the routine to read over git.
  - **`bridge`** (on push to `claude/pr-<N>-secverdict`): lands a dep-bump fix from
    `claude/pr-<N>-secfix` onto the PR head (fast-forward or cherry-pick) if present,
    posts the triaged-findings comment, and resolves the `security-triage` check to
    success/failure from the verdict token.
- `SKILL.md` — house style (setup, scanners, verify, guardrails, common mistakes).
- One line in `_shared/routine-skeleton.md`.

**Coexistence with `auto-merge-pr`:** both are PR-triggered. They stay separate via
**distinct branch names** (`claude/pr-<N>-sec{fix,verdict,input}` vs
`claude/pr-<N>-{fix,verdict}`) and **distinct checks** (`security-triage` vs
`pr-review-em`). Known caveat: if both are installed and both land a fix onto the PR
head, those landings can race; security's only auto-fix is a dep bump, which rarely
overlaps a review fix. Documented as a limitation.

## Section 2 — Finding sources & diff-scoping

Four sources, each reduced to **PR-introduced** findings (compared against base):

1. **Secrets — gitleaks** on the commit range `base..head` (secrets in added lines).
   **Always `NEEDS-HUMAN`, blocking** — a leaked secret needs rotation + history purge;
   the routine never "fixes" it.
2. **Dependency vulns — per-ecosystem audit** (`npm`/`pnpm audit`, `pip-audit`, …):
   audit head vs base, report only vulns the PR newly introduces (or whose fix it makes
   available). The **only auto-fixable** category.
3. **SAST — semgrep** with `--baseline-commit <base>` (reports only findings new
   relative to base, on changed code).
4. **Code-scanning alerts** — provided by the bridge's `register` job (CodeQL + any
   SARIF uploader), filtered to alerts whose location is in the PR's changed files.
   **Best-effort:** if the `claude/pr-<N>-secinput` branch is not present yet (alerts are
   async), the routine proceeds with the three it ran and notes "code-scanning alerts
   unavailable this run."

Each finding carries tool + rule + file/line + severity so triage can dedupe and rate.

## Section 3 — Triage flow, verdict, auto-fix & bridge routing

```
PR opened/updated -> Claude's GitHub integration fires the routine
   │
   ├─ 1. Identify PR (PR_NUMBER, HEAD_REF); set bot identity
   ├─ 2. Fetch base + PR head; compute base...head diff
   ├─ 3. RUN scanners diff-scoped:
   │       gitleaks on base..head added lines | semgrep --baseline-commit base |
   │       per-ecosystem audit head-vs-base (newly-introduced vulns)
   ├─ 4. FETCH code-scanning alerts: git fetch claude/pr-<N>-secinput (best-effort);
   │       filter to PR-changed files; if absent, note "unavailable"
   ├─ 5. TRIAGE the union — dedupe across tools, rate severity/exploitability,
   │       suppress obvious false positives. Classify each kept finding:
   │         secret                       -> NEEDS-HUMAN (rotate+purge), blocking
   │         dep vuln w/ safe patch bump   -> auto-fix candidate
   │         else (no safe bump, SAST,
   │           code-scanning, …)           -> NEEDS-HUMAN comment; blocking if high/critical
   ├─ 6. AUTO-FIX (deps only): on claude/pr-<N>-secfix, bump the vulnerable dep to the
   │       patched version, regen lockfile, re-run the gate. green -> keep;
   │       red or only-major-available -> drop to NEEDS-HUMAN. Manifests/lockfiles ONLY.
   ├─ 7. PUSH: claude/pr-<N>-secfix (only if a bump landed green);
   │           claude/pr-<N>-secverdict (ALWAYS; report in verdict.md)
   └─ 8. sec-bridge.yml `bridge`: land secfix onto PR head, post the comment,
           resolve the security-triage check
```

**Verdict token** (first line of `verdict.md`): `SECURE-suggested` (no blocking
PR-introduced findings) or `NEEDS-HUMAN` (any secret, or any high/critical finding not
resolved by an auto-fix). The check **fails only on `NEEDS-HUMAN`**; medium/low findings
are informational, so the gate stays high-signal.

**Report format** (`verdict.md` → PR comment):

```
## Security Triage — <SECURE-suggested | NEEDS-HUMAN>
**Auto-fixed:** <dep bumps landed, or "none">
**Blocking (NEEDS-HUMAN):**
- [secret] <file>:<line> <rule> — rotate the credential and purge it from history
- [high] <tool> <rule> <file>:<line> — <one-line triage>
**Non-blocking (informational):**
- [medium/low] <tool> <rule> <file>:<line> — <note>
**Coverage:** gitleaks ✓ · semgrep ✓ · <eco> audit ✓ · code-scanning <✓|unavailable>
```

The **Coverage** line distinguishes a genuinely clean result from "a scanner did not run."

## Section 4 — Guardrails & verification

**Guardrails** (atop the shared preamble):

- Never auto-edits product code, and never tries to "remove" a secret — secrets are
  always escalated with rotate+purge guidance.
- The **only** auto-fix is a gate-verified dependency version bump (manifests/lockfiles
  only); never a major bump that breaks the gate.
- **Diff-scoped:** only PR-introduced findings; never blocks a PR for pre-existing debt.
- Pushes only to `claude/pr-<N>-sec{fix,verdict}`; never merges; the bridge does all API
  work.
- Distinct branch/check names from `auto-merge-pr` so the two coexist (documented
  land-race caveat).
- Reports coverage honestly (which scanners ran; code-scanning availability).
- Fork PRs unsupported (Actions can't push to a fork head; secrets/alerts are restricted
  on fork PRs).

**Verification** (prompt + YAML skill — checks + smoke test):

- `sec-bridge.yml` parses as valid YAML; the `register` job declares
  `security-events: read` + `statuses: write` + `contents: write`; the `bridge` job
  declares `contents`/`pull-requests`/`statuses: write`; both run-scripts pass `bash -n`;
  both jobs present (`register` on `pull_request`, `bridge` on push to
  `claude/pr-*-secverdict`); the verdict-token→status mapping
  (`SECURE-suggested`→success, `NEEDS-HUMAN`→failure) present.
- **Consistency:** the `security-triage` check name and the
  `claude/pr-<N>-sec{fix,verdict,input}` branch names across SKILL/prompt/bridge; the
  "two systems must agree" note (the web routine fires on the same PR events as the
  register job), as in `auto-merge-pr`.
- **Documented smoke test:** a throwaway PR that (a) adds a fake secret → `security-triage`
  **fails**, comment flags it `NEEDS-HUMAN`; (b) introduces a known-vulnerable dep with a
  safe patch → auto-fix landed, check **passes**; (c) a clean PR → **passes** with "no
  PR-introduced findings."

## Open questions / deferred

- Exact severity cutoff for "blocking" (currently high/critical) — keep it a documented,
  tunable line in the routine prompt.
- Per-ecosystem audit command coverage — start with the common ecosystems (npm/pnpm,
  pip), degrade gracefully (note "no audit tool for <eco>") when unsupported.
- The code-scanning-alert availability race (alerts async vs routine firing) — handled
  best-effort in v1 (proceed + note "unavailable"); a later enhancement could have the
  routine re-check or the bridge re-run.
