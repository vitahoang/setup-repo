# Design — auto-provision cron routines via /schedule

**Date:** 2026-06-29
**Status:** Approved (brainstorm), pending implementation plan
**Plugin:** `setup-repo`

## Summary

Change the four **cron-fired** routine skills so their setup auto-provisions the routine
via the `/schedule` skill (a persistent cloud routine) instead of requiring the user to
manually "create the routine in Claude Code on the web." The manual web step is kept as a
documented fallback. Only provisioning changes — the routines' behavior, prompts, and
workflows are untouched.

## Context

Today each routine skill's setup says: "Create the routine in Claude Code on the web …
then set a cron schedule." `/schedule` provisions a persistent **cloud** routine
server-side (confirmed: it runs even with the user's local session closed), bound to the
repo, on a cron — exactly what the cron routines need. The setup is already performed by a
local Claude agent reading the SKILL, so it can invoke `/schedule` directly.

`CronCreate` (the local-session, REPL-idle, 7-day primitive) is NOT the mechanism here;
the `/schedule` skill manages real cloud routines.

## Scope

### In scope (the 4 cron routines)
- `skills/dependency-update-routine/SKILL.md`
- `skills/docs-sync-routine/SKILL.md`
- `skills/flaky-test-routine/SKILL.md`
- `skills/e2e-coverage-routine/SKILL.md`
- `skills/_shared/routine-skeleton.md` — the lines saying routines are created "on the web."
- `README.md` + `.claude-plugin/{plugin,marketplace}.json` (→ `0.8.0`).

### Out of scope (unchanged)
- `auto-merge-pr` and `security-triage-routine` — PR-event-triggered (fired by Claude's
  GitHub integration on PR events). `/schedule` is cron-only and cannot trigger on PR
  events, so these keep their existing trigger.
- `repo-bootstrap` — a one-shot scaffolder, not a routine.
- Every `templates/routine-prompt.md` and the shared preamble — the routine's runtime
  behavior does not change; only *how it is provisioned* changes.
- `flaky-collector.yml` — the flaky-test **collector** stays a GitHub Actions cron
  workflow; only the flaky-test **routine** is provisioned via `/schedule`.

## Section 1 — The new setup step

In each of the four `SKILL.md` files, the current two steps — "Create the routine on the
web" + "Set the schedule" — collapse into one `/schedule`-driven step:

> **Provision the routine with `/schedule`.** Assemble the prompt = the shared preamble
> (`../_shared/templates/routine-prompt.preamble.md`) followed by this skill's
> `templates/routine-prompt.md`. Invoke **`/schedule`** to create a **recurring cloud
> routine** bound to the target repo, running that prompt on the cron below, with tools
> `Bash, Read, Write, Edit, Glob, Grep`.
>
> Recommended cron (off-minute, staggered so the four don't all fire at once):
> - dependency-update → `19 7 * * 1` (Mon ~07:19)
> - docs-sync → `34 7 * * 2` (Tue ~07:34)
> - e2e-coverage → `47 7 * * 3` (Wed ~07:47)
> - flaky-test **routine** → `52 7 * * 4` (Thu ~07:52)
>
> **Manual fallback:** if `/schedule` cannot bind the repo in your environment, create the
> routine in Claude Code on the web instead — paste the same preamble + prompt, bind it to
> the repo, grant the same tools, set the same cadence.

Each skill uses its own cron line above. **flaky-test nuance:** only the routine is
provisioned via `/schedule`; the **collector** (`flaky-collector.yml`) stays a copied
GitHub Actions cron workflow — that setup step does not change.

The `_shared/routine-skeleton.md` references to creating routines "on the web" become
"via `/schedule` (or the web)."

## Section 2 — Verification

(Docs change — checks + consistency.)

- Each of the four `SKILL.md` files references **`/schedule`**, the **assembled
  preamble + prompt**, the recommended **cron**, the **repo binding + tool grants**, and a
  **Manual fallback** note.
- The two PR-triggered skills and `repo-bootstrap` are **unchanged** — `grep` confirms no
  `/schedule` provisioning was added to them.
- The `templates/routine-prompt.md` files and the shared preamble are **byte-unchanged**
  (`git diff` touches no `routine-prompt*.md` and no preamble) — the routine's behavior is
  identical; only provisioning changed.
- `_shared/routine-skeleton.md` no longer says routines are created only "on the web."
- Manifests valid; version `0.8.0`; all shipped workflow YAMLs still parse (no workflow
  changed).
- **Documented smoke test:** run one cron skill's setup → confirm `/schedule` creates a
  recurring repo-bound routine (visible in the `/schedule` list) running the assembled
  prompt on the cron.

## Open questions / deferred

- Exact recommended cron times per skill are suggestions (off-minute, staggered); users
  adjust freely. Kept as documented defaults.
- If a future `/schedule` exposes event triggers, the two PR-triggered skills could move
  too — deferred; out of scope now.
