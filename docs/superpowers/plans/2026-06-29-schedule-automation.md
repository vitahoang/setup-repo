# Auto-provision cron routines via /schedule — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the four cron-routine SKILLs so their setup auto-provisions the routine via `/schedule` (a recurring cloud routine) instead of the manual "create on the web" step, keeping the manual web step as a fallback.

**Architecture:** Surgical prose edits to four `SKILL.md` files + `_shared/routine-skeleton.md` + README/manifests. The routines' runtime behavior is unchanged — no `routine-prompt.md` and no `routine-prompt.preamble.md` is touched (a guardrail verified by `git diff`). PR-triggered skills and repo-bootstrap are not touched.

**Tech Stack:** Markdown skill files, JSON manifests. No app runtime. "Tests" are `grep` consistency + `git diff --name-only` (to prove prompts/preamble/out-of-scope skills are untouched) + JSON/YAML validity.

## Global Constraints

- **In scope:** `skills/{dependency-update-routine,docs-sync-routine,flaky-test-routine,e2e-coverage-routine}/SKILL.md`, `skills/_shared/routine-skeleton.md`, `README.md`, `.claude-plugin/{plugin,marketplace}.json`.
- **Untouched (verify):** any `templates/routine-prompt.md`, `_shared/templates/routine-prompt.preamble.md`, and the `auto-merge-pr` / `security-triage-routine` / `repo-bootstrap` skills.
- **New setup step:** invoke **`/schedule`** to create a **recurring cloud routine** bound to the repo, running the assembled prompt (shared preamble + the skill's `routine-prompt.md`) on the cron below, with tools `Bash, Read, Write, Edit, Glob, Grep`; plus a **Manual fallback** (create on the web) note.
- **Recommended crons (staggered, off-minute):** dependency-update `19 7 * * 1`; docs-sync `34 7 * * 2`; e2e-coverage `47 7 * * 3`; flaky-test routine `52 7 * * 4`.
- **flaky-test:** only the **routine** is provisioned via `/schedule`; the **collector** (`flaky-collector.yml`) stays a daily GitHub Actions cron — its setup does not change.
- **Version:** bump `0.7.0` → `0.8.0`.
- **Tooling:** `python3`, `bash`, `git`, `grep`.

---

## File Structure

**Modify:**
- `skills/dependency-update-routine/SKILL.md` — setup step + ASCII line + one component-line wording.
- `skills/docs-sync-routine/SKILL.md` — setup step + ASCII line.
- `skills/flaky-test-routine/SKILL.md` — setup step (collector note).
- `skills/e2e-coverage-routine/SKILL.md` — setup step + ASCII line + renumber.
- `skills/_shared/routine-skeleton.md` — "on the web" wording.
- `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — note + version `0.8.0`.

---

### Task 1: dependency-update-routine SKILL

**Files:** Modify `skills/dependency-update-routine/SKILL.md`

- [ ] **Step 1: Replace the setup steps 2–3 with the `/schedule` step**

Replace exactly:
```
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`, as the instructions. Bind it to the target repo and
   grant at least `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set the schedule.** Configure the routine to run on a cron — **weekly** is the
   recommended default.
```
with:
```
2. **Provision the routine with `/schedule`.** Assemble the prompt: the shared preamble
   (`../_shared/templates/routine-prompt.preamble.md`) followed by the full text of
   `templates/routine-prompt.md`. Invoke **`/schedule`** to create a **recurring cloud
   routine** bound to the target repo that runs that prompt on a weekly cron — a sensible
   default is `19 7 * * 1` (Mon ~07:19 local) — with tools
   `Bash, Read, Write, Edit, Glob, Grep`.

   *Manual fallback:* if `/schedule` can't bind the repo in your environment, create the
   routine in Claude Code on the web instead — paste the same preamble + prompt, bind it
   to the repo, grant the same tools, and set the same weekly cron.
```

- [ ] **Step 2: Renumber the following step 4 → 3**

Replace `4. **(Recommended) Auto-delete merged branches.**` with `3. **(Recommended) Auto-delete merged branches.**` (only the leading number changes).

- [ ] **Step 3: Fix the component-line wording**

Replace `- \`templates/routine-prompt.md\` — the routine's mandate (pasted into the web routine` with `- \`templates/routine-prompt.md\` — the routine's mandate (assembled after the shared preamble`. Then on the next line replace `  after the shared preamble).` with `  and given to the routine).`

- [ ] **Step 4: Update the ASCII flow line**

Replace `    cron fires the routine (Claude Code on the web, schedule-bound to the repo)` with `    cron fires the routine (a Claude Code cloud routine, schedule-bound to the repo)`.

- [ ] **Step 5: Verify**

Run:
```bash
F=skills/dependency-update-routine/SKILL.md
grep -q '/schedule' "$F" && grep -q '19 7 \* \* 1' "$F" && grep -q 'Manual fallback' "$F" && \
  grep -q 'Bash, Read, Write, Edit, Glob, Grep' "$F" && \
  ! grep -q '2. \*\*Create the routine\*\* in Claude Code on the web' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 6: Commit**

```bash
git add skills/dependency-update-routine/SKILL.md
git commit -m "feat(dependency-update): provision the routine via /schedule (web fallback)"
```

---

### Task 2: docs-sync-routine SKILL

**Files:** Modify `skills/docs-sync-routine/SKILL.md`

- [ ] **Step 1: Replace the setup steps 2–3 with the `/schedule` step**

Replace exactly:
```
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`, as the instructions. Bind it to the target repo and
   grant at least `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set the schedule.** Configure the routine to run on a cron — **weekly** is the
   recommended default.
```
with:
```
2. **Provision the routine with `/schedule`.** Assemble the prompt: the shared preamble
   (`../_shared/templates/routine-prompt.preamble.md`) followed by the full text of
   `templates/routine-prompt.md`. Invoke **`/schedule`** to create a **recurring cloud
   routine** bound to the target repo that runs that prompt on a weekly cron — a sensible
   default is `34 7 * * 2` (Tue ~07:34 local) — with tools
   `Bash, Read, Write, Edit, Glob, Grep`.

   *Manual fallback:* if `/schedule` can't bind the repo in your environment, create the
   routine in Claude Code on the web instead — paste the same preamble + prompt, bind it
   to the repo, grant the same tools, and set the same weekly cron.
```

- [ ] **Step 2: Update the ASCII flow line**

Replace `    cron fires the routine (Claude Code on the web, schedule-bound to the repo)` with `    cron fires the routine (a Claude Code cloud routine, schedule-bound to the repo)`.

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/docs-sync-routine/SKILL.md
grep -q '/schedule' "$F" && grep -q '34 7 \* \* 2' "$F" && grep -q 'Manual fallback' "$F" && \
  grep -q 'Bash, Read, Write, Edit, Glob, Grep' "$F" && \
  ! grep -q '2. \*\*Create the routine\*\* in Claude Code on the web' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/docs-sync-routine/SKILL.md
git commit -m "feat(docs-sync): provision the routine via /schedule (web fallback)"
```

---

### Task 3: flaky-test-routine SKILL

**Files:** Modify `skills/flaky-test-routine/SKILL.md`

- [ ] **Step 1: Replace the setup steps 2–3 with the `/schedule` step (keep the collector note)**

Replace exactly:
```
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`. Bind it to the target repo and grant at least
   `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set schedules.** The collector runs daily by default; set the routine to run
   **weekly** so it acts on an established digest.
```
with:
```
2. **Provision the routine with `/schedule`.** Assemble the prompt: the shared preamble
   (`../_shared/templates/routine-prompt.preamble.md`) followed by the full text of
   `templates/routine-prompt.md`. Invoke **`/schedule`** to create a **recurring cloud
   routine** bound to the target repo that runs that prompt on a weekly cron — a sensible
   default is `52 7 * * 4` (Thu ~07:52 local) — with tools
   `Bash, Read, Write, Edit, Glob, Grep`. The collector workflow you copied in step 1
   runs on its own daily Actions cron; only the routine is provisioned here.

   *Manual fallback:* if `/schedule` can't bind the repo in your environment, create the
   routine in Claude Code on the web instead — paste the same preamble + prompt, bind it
   to the repo, grant the same tools, and set the same weekly cron.
```

- [ ] **Step 2: Verify**

Run:
```bash
F=skills/flaky-test-routine/SKILL.md
grep -q '/schedule' "$F" && grep -q '52 7 \* \* 4' "$F" && grep -q 'Manual fallback' "$F" && \
  grep -q 'collector workflow you copied in step 1' "$F" && \
  ! grep -q '2. \*\*Create the routine\*\* in Claude Code on the web' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 3: Commit**

```bash
git add skills/flaky-test-routine/SKILL.md
git commit -m "feat(flaky-test): provision the routine via /schedule (collector stays Actions cron)"
```

---

### Task 4: e2e-coverage-routine SKILL

**Files:** Modify `skills/e2e-coverage-routine/SKILL.md`

- [ ] **Step 1: Replace the setup steps 3–4 with the `/schedule` step**

Replace exactly:
```
3. **Create the routine** in Claude Code on the web. New routine → paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`, as its instructions → bind it to the target repo →
   grant at least `Bash, Read, Write, Edit, Glob, Grep`.

4. **Schedule it.** Set the routine to run on a cron cadence (weekly is a sensible
   default — frequent enough to keep coverage growing, infrequent enough that PRs
   stay reviewable). This is the load-bearing step: without a schedule the routine
   never fires.
```
with:
```
3. **Provision the routine with `/schedule`.** Assemble the prompt: the shared preamble
   (`../_shared/templates/routine-prompt.preamble.md`) followed by the full text of
   `templates/routine-prompt.md`. Invoke **`/schedule`** to create a **recurring cloud
   routine** bound to the target repo that runs that prompt on a weekly cron — a sensible
   default is `47 7 * * 3` (Wed ~07:47 local) — with tools
   `Bash, Read, Write, Edit, Glob, Grep`. This is the load-bearing step: without a
   schedule the routine never fires.

   *Manual fallback:* if `/schedule` can't bind the repo in your environment, create the
   routine in Claude Code on the web instead — paste the same preamble + prompt, bind it
   to the repo, grant the same tools, and set the same weekly cron.
```

- [ ] **Step 2: Renumber the following step 5 → 4**

Replace `5. **(Optional) Reuse an existing E2E workflow.**` with `4. **(Optional) Reuse an existing E2E workflow.**` (only the leading number changes).

- [ ] **Step 3: Update the ASCII flow line**

Replace `    cron fires the routine (Claude Code on the web, schedule-bound to the repo)` with `    cron fires the routine (a Claude Code cloud routine, schedule-bound to the repo)`.

- [ ] **Step 4: Verify**

Run:
```bash
F=skills/e2e-coverage-routine/SKILL.md
grep -q '/schedule' "$F" && grep -q '47 7 \* \* 3' "$F" && grep -q 'Manual fallback' "$F" && \
  grep -q '4. \*\*(Optional) Reuse an existing E2E workflow' "$F" && \
  ! grep -q '3. \*\*Create the routine\*\* in Claude Code on the web' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 5: Commit**

```bash
git add skills/e2e-coverage-routine/SKILL.md
git commit -m "feat(e2e-coverage): provision the routine via /schedule (web fallback)"
```

---

### Task 5: _shared/routine-skeleton.md wording

**Files:** Modify `skills/_shared/routine-skeleton.md`

- [ ] **Step 1: Update the ASCII shape line**

Replace `    cron / GitHub event fires a Claude Code routine (bound to the repo on the web)` with `    cron / GitHub event fires a Claude Code routine (a cloud routine bound to the repo)`.

- [ ] **Step 2: Update the preamble bullet wording**

Replace exactly:
```
- **Guardrail preamble.** `templates/routine-prompt.preamble.md` — paste it FIRST,
  ahead of the skill's own routine prompt, when creating the routine on the web. It
```
with:
```
- **Guardrail preamble.** `templates/routine-prompt.preamble.md` — assemble it FIRST,
  ahead of the skill's own routine prompt, when provisioning the routine (via `/schedule`
  or on the web). It
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/_shared/routine-skeleton.md
grep -q '/schedule' "$F" && ! grep -q 'bound to the repo on the web' "$F" && \
  ! grep -q 'when creating the routine on the web' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/routine-skeleton.md
git commit -m "docs(skeleton): routines are provisioned via /schedule (or the web)"
```

---

### Task 6: README + manifests (version 0.8.0)

**Files:** Modify `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: Add the /schedule note to the README**

In `README.md`, replace:
```
These routine skills share a common pattern (Claude routine → `claude/` branch →
Actions bridge → PR), documented in
[`skills/_shared/routine-skeleton.md`](skills/_shared/routine-skeleton.md).
```
with:
```
These routine skills share a common pattern (Claude routine → `claude/` branch →
Actions bridge → PR), documented in
[`skills/_shared/routine-skeleton.md`](skills/_shared/routine-skeleton.md). The four
cron-fired routines (dependency-update, docs-sync, flaky-test, e2e-coverage) are
auto-provisioned via `/schedule` (a recurring cloud routine); auto-merge-pr and
security-triage stay on the GitHub PR-event trigger.
```

- [ ] **Step 2: Bump the version in both manifests**

In `.claude-plugin/plugin.json`: change `"version": "0.7.0"` to `"version": "0.8.0"`.
(The `description` does not need to change.)

In `.claude-plugin/marketplace.json`: no version field — leave the description as-is.
(If the marketplace plugin entry has no version, no change is needed beyond plugin.json.)

- [ ] **Step 3: Verify**

Run:
```bash
grep -q '/schedule' README.md && \
  python3 -c "import json;p=json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));assert p['version']=='0.8.0',p['version'];print('JSON-OK 0.8.0')"
```
Expected: `JSON-OK 0.8.0`

- [ ] **Step 4: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs: note /schedule auto-provisioning; bump plugin to 0.8.0"
```

---

## Final verification (after all tasks)

- [ ] **The four cron SKILLs each provision via /schedule:** for each of the four files, `grep -q '/schedule'` and `grep -q 'Manual fallback'` pass, and none still has a numbered `**Create the routine** in Claude Code on the web` step.
- [ ] **GUARDRAIL — prompts + preamble + out-of-scope skills untouched:** run
  ```bash
  git diff --name-only main...HEAD -- skills | sort
  ```
  The list must contain ONLY the four cron `SKILL.md` files and `skills/_shared/routine-skeleton.md`. It must NOT contain any `routine-prompt.md`, any `routine-prompt.preamble.md`, or any file under `skills/auto-merge-pr`, `skills/security-triage-routine`, or `skills/repo-bootstrap`.
- [ ] **JSON valid + version:** `python3 -c "import json;p=json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print(p['version'])"` → `0.8.0`.
- [ ] **All shipped workflow YAMLs still parse** (none changed): `python3` `yaml.safe_load` loop over `skills/**/templates/*.yml` (excluding the raw `_shared/templates/pr-bridge.yml` token template).
- [ ] **Eight skills still present:** `ls skills` unchanged.
