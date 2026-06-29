# flaky-test-routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `flaky-test-routine` skill — a scheduled collector mines CI run history + JUnit artifacts into a flakiness digest, and a Claude routine files a tracking issue for flaky tests or opens a quarantine PR for strongly-confirmed ones.

**Architecture:** A collector GitHub Actions workflow (`flaky-collector.yml`) calls a standalone parser (`flaky_parse.py`) over downloaded per-run JUnit artifacts to compute `flaky-digest.json`, force-pushed to a `flaky-digest` data branch. The routine reads that digest over git (no API access), classifies by same-SHA-disagreement recurrence, and pushes `claude/flaky-*` — doc/test edits (quarantine) or an `--allow-empty` findings commit — which a concrete `flaky-bridge.yml` routes to a PR or the rolling tracking issue via merge-base tree-diff.

**Tech Stack:** Markdown skill files, GitHub Actions YAML, `gh` CLI, Python 3 stdlib (`xml.etree`, `json`). No app runtime. "Tests" are validation commands — plus one REAL unit test of `flaky_parse.py`.

## Global Constraints

- **Plugin / marketplace name:** both `setup-repo`.
- **Branch glob:** `claude/flaky-*` — identical across `SKILL.md`, `routine-prompt.md`, `flaky-bridge.yml`.
- **Digest:** file `flaky-digest.json` on data branch `flaky-digest`; collector pushes it, routine reads it.
- **Rolling issue title:** `flaky tests pending triage` (bridge dedupes on it).
- **Flakiness signal:** same-SHA disagreement (a test both passes and fails on one commit SHA); rank by `distinct_sha_count`.
- **Quarantine threshold:** `distinct_sha_count >= 2` (named, tunable) → quarantine PR; `== 1` → evidence-only.
- **Routine edits only test files** to add a framework skip-with-reason linking the issue; **never deletes** a test; never product code. If the test can't be located or the skip idiom is unclear → evidence-only (no edit).
- **Per-run output:** one quarantine PR **or** one rolling issue; a no-flaky run pushes nothing.
- **Collector:** trigger `schedule` (daily default) + `workflow_dispatch`; permissions `actions: read` + `contents: write`; config env `TEST_WORKFLOW`, `ARTIFACT_NAME`, `WINDOW_DAYS`, `DIGEST_BRANCH`; pushes only to `flaky-digest`, never `main`.
- **Bridge permissions:** `contents: write`, `pull-requests: write`, `issues: write`; routes on the merge-base tree-diff.
- **Cadence:** documented — collector **daily**, routine **weekly**.
- **Version:** bump `0.4.0` → `0.5.0`.
- **House style:** `SKILL.md` mirrors siblings (frontmatter, Overview, ASCII Flow, Setup procedure, How to verify, Guardrails, Common mistakes table).
- **Tooling available:** `python3`, `node`, `ruby`, `bash`. No actionlint/yamllint/shellcheck.

---

## File Structure

**Create:**
- `skills/flaky-test-routine/templates/flaky_parse.py` — the JUnit→digest parser (standalone, unit-tested).
- `skills/flaky-test-routine/test_flaky_parse.py` — the parser's unit test (NOT a template; not copied into target repos).
- `skills/flaky-test-routine/templates/flaky-collector.yml` — the collector workflow (calls the parser).
- `skills/flaky-test-routine/templates/flaky-bridge.yml` — concrete PR-or-issue bridge (merge-base routing).
- `skills/flaky-test-routine/templates/routine-prompt.md` — the routine mandate.
- `skills/flaky-test-routine/SKILL.md` — setup + reference.

**Modify:**
- `skills/_shared/routine-skeleton.md` — one line: a second issue-reporting routine exists; bridge promotion is a tracked follow-up.
- `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — list docs; bump `0.5.0`.

---

### Task 1: The JUnit→digest parser (`flaky_parse.py`) — TDD

**Files:**
- Create: `skills/flaky-test-routine/templates/flaky_parse.py`
- Test: `skills/flaky-test-routine/test_flaky_parse.py`

**Interfaces:**
- Produces: a CLI `python3 flaky_parse.py <runs_dir> [--workflow NAME] [--window-days N]` that reads a directory of per-run subdirs (each with `meta.json` `{sha,url,created_at}` + zero or more `*.xml` JUnit files) and writes the digest JSON to stdout. The collector (Task 2) calls it; the digest schema is consumed by the routine (Task 4).

- [ ] **Step 1: Write the failing unit test**

Create `skills/flaky-test-routine/test_flaky_parse.py` with exactly:
```python
#!/usr/bin/env python3
"""Unit test for flaky_parse.py — runs the real CLI on synthetic JUnit input."""
import json, os, subprocess, sys, tempfile

PARSER = os.path.join(os.path.dirname(__file__), "templates", "flaky_parse.py")

PASS_XML = '<testsuite name="s"><testcase classname="pkg.Foo" name="testX" file="t/foo_test.py"/></testsuite>'
FAIL_XML = '<testsuite name="s"><testcase classname="pkg.Foo" name="testX" file="t/foo_test.py"><failure>boom</failure></testcase></testsuite>'


def write_run(base, rid, sha, xml):
    d = os.path.join(base, rid)
    os.makedirs(d)
    json.dump({"sha": sha, "url": "http://x/" + rid, "created_at": "2026-06-29T00:00:00Z"},
              open(os.path.join(d, "meta.json"), "w"))
    if xml is not None:
        open(os.path.join(d, "results.xml"), "w").write(xml)


def digest_for(base):
    out = subprocess.run([sys.executable, PARSER, base, "--workflow", "ci.yml"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    # Case 1: same SHA AAA shows pass and fail -> testX flaky, distinct_sha_count == 1
    with tempfile.TemporaryDirectory() as base:
        write_run(base, "1", "AAA", PASS_XML)
        write_run(base, "2", "AAA", FAIL_XML)
        d = digest_for(base)
        flaky = {f["test"]: f for f in d["flaky"]}
        assert "pkg.Foo :: testX" in flaky, d
        assert flaky["pkg.Foo :: testX"]["distinct_sha_count"] == 1, d
        assert flaky["pkg.Foo :: testX"]["file"] == "t/foo_test.py", d
        assert d["runs_parsed"] == 2 and d["runs_missing_artifact"] == 0, d

    # Case 2: add a second flipping SHA BBB -> distinct_sha_count == 2
    with tempfile.TemporaryDirectory() as base:
        write_run(base, "1", "AAA", PASS_XML)
        write_run(base, "2", "AAA", FAIL_XML)
        write_run(base, "3", "BBB", PASS_XML)
        write_run(base, "4", "BBB", FAIL_XML)
        d = digest_for(base)
        flaky = {f["test"]: f for f in d["flaky"]}
        assert flaky["pkg.Foo :: testX"]["distinct_sha_count"] == 2, d

    # Case 3: a test that only ever passes is NOT flaky; a run with no xml is "missing"
    with tempfile.TemporaryDirectory() as base:
        write_run(base, "1", "AAA", PASS_XML)
        write_run(base, "2", "AAA", PASS_XML)
        write_run(base, "3", "CCC", None)  # no artifact
        d = digest_for(base)
        assert d["flaky"] == [], d
        assert d["runs_missing_artifact"] == 1, d

    print("PARSER-TESTS-PASS")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 skills/flaky-test-routine/test_flaky_parse.py`
Expected: FAIL — `flaky_parse.py` does not exist (FileNotFoundError / non-zero exit from subprocess).

- [ ] **Step 3: Implement the parser**

Create `skills/flaky-test-routine/templates/flaky_parse.py` with exactly:
```python
#!/usr/bin/env python3
"""Compute a flaky-test digest from per-run JUnit results.

Input: a directory with one subdir per CI run. Each run subdir contains:
  - meta.json : {"sha": "<commit>", "url": "<run url>", "created_at": "<iso8601>"}
  - zero or more *.xml : JUnit XML test-result files for that run

A test is "flaky" if, for some single commit SHA, it has BOTH a passing and a
failing outcome across runs (same code, different result). Tests are ranked by the
number of distinct SHAs showing such a pass/fail disagreement.

Usage: flaky_parse.py <runs_dir> [--workflow NAME] [--window-days N]  (digest -> stdout)
"""
import sys, os, json, glob, argparse, datetime
import xml.etree.ElementTree as ET


def _outcome(testcase):
    # A <testcase> with a <failure>/<error> child is a failure; <skipped> means it did
    # not run (ignored); otherwise it passed.
    for child in testcase:
        tag = child.tag.split('}')[-1]  # strip any XML namespace
        if tag in ("failure", "error"):
            return "fail"
        if tag == "skipped":
            return "skip"
    return "pass"


def _test_id(testcase):
    name = testcase.get("name") or "<unnamed>"
    classname = testcase.get("classname") or "<no-class>"
    return classname + " :: " + name


def parse_runs(runs_dir):
    records = {}
    runs_parsed = 0
    runs_missing = 0
    for run_dir in sorted(glob.glob(os.path.join(runs_dir, "*"))):
        if not os.path.isdir(run_dir):
            continue
        meta_path = os.path.join(run_dir, "meta.json")
        if not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        sha = meta.get("sha", "")
        url = meta.get("url", "")
        created = meta.get("created_at", "")
        xmls = glob.glob(os.path.join(run_dir, "**", "*.xml"), recursive=True)
        if not xmls:
            runs_missing += 1
            continue
        runs_parsed += 1
        for xml in xmls:
            try:
                root = ET.parse(xml).getroot()
            except ET.ParseError:
                continue
            for tc in root.iter("testcase"):
                outcome = _outcome(tc)
                if outcome == "skip":
                    continue
                tid = _test_id(tc)
                rec = records.setdefault(tid, {"file": None, "by_sha": {}, "urls": {}, "created": []})
                if rec["file"] is None and tc.get("file"):
                    rec["file"] = tc.get("file")
                rec["by_sha"].setdefault(sha, set()).add(outcome)
                rec["urls"].setdefault(sha, [])
                if url and url not in rec["urls"][sha]:
                    rec["urls"][sha].append(url)
                if created:
                    rec["created"].append(created)
    return records, runs_parsed, runs_missing


def build_digest(records, runs_parsed, runs_missing, workflow, window_days):
    flaky = []
    for tid, rec in records.items():
        flip_shas = [sha for sha, outs in rec["by_sha"].items()
                     if "pass" in outs and "fail" in outs]
        if not flip_shas:
            continue
        sample_urls = []
        for sha in flip_shas:
            sample_urls.extend(rec["urls"].get(sha, []))
        created = sorted(c for c in rec["created"] if c)
        flaky.append({
            "test": tid,
            "file": rec["file"],
            "distinct_sha_count": len(flip_shas),
            "flip_shas": sorted(flip_shas),
            "sample_run_urls": sample_urls[:5],
            "first_seen": created[0] if created else None,
            "last_seen": created[-1] if created else None,
        })
    flaky.sort(key=lambda f: f["distinct_sha_count"], reverse=True)
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_days": window_days,
        "workflow": workflow,
        "runs_parsed": runs_parsed,
        "runs_missing_artifact": runs_missing,
        "flaky": flaky,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_dir")
    ap.add_argument("--workflow", default="")
    ap.add_argument("--window-days", type=int, default=14)
    args = ap.parse_args(argv)
    records, parsed, missing = parse_runs(args.runs_dir)
    digest = build_digest(records, parsed, missing, args.workflow, args.window_days)
    json.dump(digest, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 skills/flaky-test-routine/test_flaky_parse.py`
Expected: `PARSER-TESTS-PASS`

- [ ] **Step 5: Commit**

```bash
git add skills/flaky-test-routine/templates/flaky_parse.py skills/flaky-test-routine/test_flaky_parse.py
git commit -m "feat(flaky-test): JUnit->digest parser with same-SHA flakiness detection"
```

---

### Task 2: The collector workflow (`flaky-collector.yml`)

**Files:**
- Create: `skills/flaky-test-routine/templates/flaky-collector.yml`

**Interfaces:**
- Consumes: `flaky_parse.py` (Task 1), invoked as `python3 .github/flaky_parse.py runs ...`.
- Produces: `flaky-digest.json` force-pushed to the `flaky-digest` branch. The routine (Task 4) reads it.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL — file absent):
```bash
test -f skills/flaky-test-routine/templates/flaky-collector.yml && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the collector**

Create `skills/flaky-test-routine/templates/flaky-collector.yml` with exactly:
```yaml
name: flaky-test collector

# Mines recent runs of your test workflow + their JUnit artifacts into
# flaky-digest.json on the `flaky-digest` data branch, which the flaky-test routine
# reads. Configure the four env values below for your repo. Also: your test workflow
# must upload its JUnit/test-result XML as an artifact named ARTIFACT_NAME.

on:
  schedule:
    - cron: '17 6 * * *'   # daily; adjust as you like
  workflow_dispatch: {}

permissions:
  actions: read
  contents: write

concurrency:
  group: flaky-collector
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
      REPO: ${{ github.repository }}
      TEST_WORKFLOW: ci.yml          # the workflow whose tests you track
      ARTIFACT_NAME: test-results    # the JUnit artifact name your CI uploads
      WINDOW_DAYS: '14'
      DIGEST_BRANCH: flaky-digest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Download recent runs + JUnit artifacts
        run: |
          set -euo pipefail
          base=$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name)
          since=$(date -u -d "-${WINDOW_DAYS} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
                  || date -u -v-"${WINDOW_DAYS}"d +%Y-%m-%dT%H:%M:%SZ)
          mkdir -p runs
          gh run list --repo "$REPO" --workflow "$TEST_WORKFLOW" --branch "$base" \
            --status completed --limit 200 \
            --json databaseId,headSha,url,createdAt \
            --jq ".[] | select(.createdAt >= \"$since\")" > runs.ndjson || true
          while IFS= read -r line; do
            [ -n "$line" ] || continue
            id=$(printf '%s' "$line" | python3 -c "import sys,json;print(json.load(sys.stdin)['databaseId'])")
            mkdir -p "runs/$id"
            printf '%s' "$line" | python3 -c "import sys,json;d=json.load(sys.stdin);json.dump({'sha':d['headSha'],'url':d['url'],'created_at':d['createdAt']},open('runs/$id/meta.json','w'))"
            gh run download "$id" --repo "$REPO" -n "$ARTIFACT_NAME" -D "runs/$id" 2>/dev/null || true
          done < runs.ndjson

      - name: Build the digest
        run: |
          set -euo pipefail
          python3 .github/flaky_parse.py runs --workflow "$TEST_WORKFLOW" --window-days "$WINDOW_DAYS" > flaky-digest.json
          cat flaky-digest.json

      - name: Publish the digest to its data branch
        run: |
          set -euo pipefail
          git config user.name "flaky-collector[bot]"
          git config user.email "flaky-collector[bot]@users.noreply.github.com"
          tmp=$(mktemp -d)
          cp flaky-digest.json "$tmp/flaky-digest.json"
          git checkout --orphan "$DIGEST_BRANCH"
          git rm -rf . >/dev/null 2>&1 || true
          cp "$tmp/flaky-digest.json" flaky-digest.json
          git add flaky-digest.json
          git commit -m "flaky digest $(date -u +%Y-%m-%dT%H:%M:%SZ)"
          git push -f origin "$DIGEST_BRANCH"
```

- [ ] **Step 3: Verify YAML + permissions + shell syntax + references**

Run:
```bash
F=skills/flaky-test-routine/templates/flaky-collector.yml
python3 - <<PY
import yaml
d=yaml.safe_load(open("$F").read())
assert d['permissions']=={'actions':'read','contents':'write'}, d['permissions']
steps=d['jobs']['collect']['steps']
for s in steps:
    if 'run' in s:
        open('/tmp/c_%d.sh' % steps.index(s),'w').write(s['run'])
assert d['jobs']['collect']['env']['DIGEST_BRANCH']=='flaky-digest'
print("YAML-OK; perms OK; digest branch OK")
PY
for f in /tmp/c_*.sh; do bash -n "$f" || exit 1; done; echo "SHELL-SYNTAX-OK"
grep -q 'flaky_parse.py' "$F" && grep -q 'gh run download' "$F" && grep -q 'git push -f origin "\$DIGEST_BRANCH"' "$F" && echo "REFS-OK"
```
Expected: `YAML-OK; perms OK; digest branch OK`, `SHELL-SYNTAX-OK`, `REFS-OK`.

- [ ] **Step 4: Commit**

```bash
git add skills/flaky-test-routine/templates/flaky-collector.yml
git commit -m "feat(flaky-test): collector workflow (runs+artifacts -> flaky-digest branch)"
```

---

### Task 3: PR-or-issue bridge (`flaky-bridge.yml`) + skeleton note

**Files:**
- Create: `skills/flaky-test-routine/templates/flaky-bridge.yml`
- Modify: `skills/_shared/routine-skeleton.md`

**Interfaces:**
- Consumes: the routine's `claude/flaky-*` branch + `--allow-empty` convention (Task 4).
- Produces: routing — doc/test edits → PR; empty commit → open/update the `flaky tests pending triage` issue.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
test -f skills/flaky-test-routine/templates/flaky-bridge.yml && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the bridge**

Create `skills/flaky-test-routine/templates/flaky-bridge.yml` with exactly:
```yaml
name: flaky-test PR-or-issue bridge

# The flaky-test routine can only push to `claude/` branches and has no GitHub API
# access. This workflow fires on push to claude/flaky-* and routes:
#   - branch carries test edits (quarantine) -> open a PR
#   - findings-only empty commit             -> open/update the tracking issue
# The tip commit body is the report in both cases.

on:
  push:
    branches:
      - 'claude/flaky-*'

permissions:
  contents: write
  pull-requests: write
  issues: write

concurrency:
  group: flaky-bridge-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  route:
    if: ${{ github.event.deleted != true }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Open a PR (quarantine) or open/update the tracking issue (findings only)
        env:
          GH_TOKEN: ${{ github.token }}
          BRANCH: ${{ github.ref_name }}
          REPO: ${{ github.repository }}
          ISSUE_TITLE: "flaky tests pending triage"
        run: |
          set -euo pipefail

          base=$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name)
          git fetch origin "$base" "$BRANCH"

          # The report is the pushed branch's tip commit body (a plain variable, so
          # backticks / $ in it are never re-expanded by the shell).
          report=$(git log -1 --format=%b "origin/$BRANCH")

          # Decide PR vs issue from what THIS branch changed since it forked from the
          # default branch. Diffing against the merge-base (not the live base tip) keeps
          # the decision correct even if the default branch advances after the push.
          fork=$(git merge-base "origin/$base" "origin/$BRANCH")
          if [ -n "$(git diff --name-only "$fork" "origin/$BRANCH")" ]; then
            existing=$(gh pr list --repo "$REPO" --head "$BRANCH" --state open \
              --json number --jq '.[0].number // empty')
            if [ -n "$existing" ]; then
              echo "PR #$existing already open for $BRANCH."
              exit 0
            fi
            if [ -z "$report" ]; then
              report="Automated flaky-test quarantine — strongly-confirmed flaky tests skipped pending triage. Review and merge if correct."
            fi
            gh pr create --repo "$REPO" --base "$base" --head "$BRANCH" \
              --title "test: quarantine flaky tests (${BRANCH#claude/})" \
              --body "$report"
          else
            if [ -z "$report" ]; then
              report="flaky-test routine recorded findings but no report body."
            fi
            num=$(gh issue list --repo "$REPO" --state open --search "in:title \"$ISSUE_TITLE\"" \
              --json number,title --jq "map(select(.title==\"$ISSUE_TITLE\")) | .[0].number // empty")
            if [ -n "$num" ]; then
              gh issue edit "$num" --repo "$REPO" --body "$report"
              echo "Updated tracking issue #$num."
            else
              gh issue create --repo "$REPO" --title "$ISSUE_TITLE" --body "$report"
            fi
          fi
```

- [ ] **Step 3: Add the skeleton note**

In `skills/_shared/routine-skeleton.md`, find the existing sub-bullet that begins "Routines that report findings as a GitHub **issue**" (added for docs-sync) and append one sentence to it:
```markdown
    (Two such skills now exist — docs-sync and flaky-test — so promoting this bridge
    into `templates/` is a tracked follow-up.)
```

- [ ] **Step 4: Verify**

Run:
```bash
F=skills/flaky-test-routine/templates/flaky-bridge.yml
python3 - <<PY
import yaml
d=yaml.safe_load(open("$F").read())
assert d['permissions']=={'contents':'write','pull-requests':'write','issues':'write'}, d['permissions']
run=d['jobs']['route']['steps'][1]['run']
open('/tmp/fb.sh','w').write(run)
assert d['jobs']['route']['steps'][1]['env']['ISSUE_TITLE']=="flaky tests pending triage"
print("YAML-OK; perms OK; issue-title OK")
PY
bash -n /tmp/fb.sh && echo "SHELL-SYNTAX-OK"
grep -q 'git merge-base' /tmp/fb.sh && grep -q 'gh pr create' /tmp/fb.sh && grep -q 'gh issue create' /tmp/fb.sh && grep -q 'gh issue edit' /tmp/fb.sh && echo "ROUTES+MERGEBASE-OK"
```
Expected: `YAML-OK; perms OK; issue-title OK`, `SHELL-SYNTAX-OK`, `ROUTES+MERGEBASE-OK`.

- [ ] **Step 5: Commit**

```bash
git add skills/flaky-test-routine/templates/flaky-bridge.yml skills/_shared/routine-skeleton.md
git commit -m "feat(flaky-test): PR-or-issue bridge + skeleton note"
```

---

### Task 4: Routine prompt

**Files:**
- Create: `skills/flaky-test-routine/templates/routine-prompt.md`

**Interfaces:**
- Consumes: the digest schema (Task 1), the `flaky-digest` branch (Task 2), the bridge's `claude/flaky-*` + `--allow-empty` convention (Task 3).
- Produces: the mandate pasted into the web routine after the shared preamble.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
F=skills/flaky-test-routine/templates/routine-prompt.md
test -f "$F" && grep -q 'claude/flaky-' "$F" && grep -q 'flaky-digest' "$F" && \
  grep -q -- '--allow-empty' "$F" && grep -q 'distinct_sha_count' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the routine prompt**

Create `skills/flaky-test-routine/templates/routine-prompt.md` with exactly:
```markdown
# Flaky Test Routine — Mandate

(The shared guardrail preamble is pasted ahead of this prompt — only push to
`claude/` branches, no GitHub API, never merge, escalate via `NEEDS-HUMAN`.)

You are a scheduled routine that triages flaky tests. A companion collector workflow
publishes a digest of flaky tests to the `flaky-digest` branch; you read it, file (or
update) a tracking issue with the evidence, and — only for strongly-confirmed cases —
open a PR that quarantines (skips) the test. You **only edit test files**, never
product code.

## Steps

1. **Sync.** Fetch and check out the latest default branch. Set your bot identity.

2. **Read the digest.** `git fetch origin flaky-digest` and read `flaky-digest.json`
   from that branch. If the branch or file is missing, or `flaky` is empty, there is
   nothing to do — end the run without pushing.

3. **Classify** each entry in `flaky` by `distinct_sha_count` (the number of distinct
   commit SHAs on which the test both passed and failed — same code, different result):
   - `>= 2` (the tunable QUARANTINE_THRESHOLD) → **quarantine candidate**.
   - `== 1` (a single occurrence) → **evidence-only**.

4. **Quarantine candidates.** For each, locate the test from its `file` and `test`
   name, and identify the test framework's skip idiom. If you can do this confidently,
   edit ONLY that test file to skip it with a reason that links the tracking issue —
   for example `it.skip`/`test.skip` (jest/vitest), `@pytest.mark.skip(reason="flaky:
   …")` (pytest), `@Disabled("flaky: …")` (JUnit), `t.Skip("flaky: …")` (Go),
   `skip "flaky: …"` (RSpec). **Never delete a test** — only skip it. If you cannot
   locate the test or are unsure of the skip idiom, do NOT edit it — downgrade it to
   evidence-only.

5. **Commit + push `claude/flaky-<UTC-date-or-run-id>`.** Make the **commit body** your
   report in this exact format:

       ## Quarantined (same-SHA flip on >=N distinct SHAs)
       - <test> (<file>): flipped on <k> SHAs — <sample run urls>; skipped pending triage

       ## Flaky — evidence only (not quarantined)
       - <test>: flipped on <k> SHA — <sample run urls>

   - If you quarantined any tests, commit the test-file edits normally (report = body).
   - If you have only evidence (no quarantine edits), make an **empty** commit
     (`git commit --allow-empty`) so the report still ships — the bridge turns an
     empty-commit branch into the tracking issue instead of a PR.
   - If the digest had no flaky tests, push nothing and end.

## Quality bar

- Quarantine only tests with `distinct_sha_count >= 2`; never delete a test; never edit
  product code.
- Every quarantine links the tracking issue and names the evidence (SHAs + run URLs).
- One push per run: a quarantine PR, or the rolling issue, or nothing.
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/flaky-test-routine/templates/routine-prompt.md
grep -q 'claude/flaky-' "$F" && grep -q 'flaky-digest' "$F" && grep -q -- '--allow-empty' "$F" && \
  grep -q 'distinct_sha_count' "$F" && grep -q 'Never delete a test' "$F" && \
  grep -q '## Quarantined (same-SHA flip on >=N distinct SHAs)' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-PASS`

- [ ] **Step 4: Commit**

```bash
git add skills/flaky-test-routine/templates/routine-prompt.md
git commit -m "feat(flaky-test): routine mandate (digest -> issue or quarantine PR)"
```

---

### Task 5: SKILL.md

**Files:**
- Create: `skills/flaky-test-routine/SKILL.md`

**Interfaces:**
- Consumes: all templates (Tasks 1–4) by path; the shared preamble + skeleton doc.
- Produces: the installed skill's setup/reference doc.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
F=skills/flaky-test-routine/SKILL.md
test -f "$F" && grep -q 'claude/flaky-\*' "$F" && grep -q 'routine-skeleton.md' "$F" && \
  grep -q 'routine-prompt.preamble.md' "$F" && grep -q 'flaky-digest' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Create the SKILL.md**

Create `skills/flaky-test-routine/SKILL.md` with exactly:
```markdown
---
name: flaky-test-routine
description: Use when setting up a scheduled routine that finds flaky tests from CI history — a collector workflow mines recent test runs + JUnit artifacts into a flakiness digest, and the routine files a tracking issue with the evidence or, for strongly-confirmed cases, opens a PR that quarantines (skips) the test. Built on the shared routine skeleton; requires the project to upload JUnit/test-result artifacts.
---

# flaky-test-routine — Scheduled Flaky-Test Triage

> Built on the shared routine skeleton — see [`../_shared/routine-skeleton.md`](../_shared/routine-skeleton.md).

## Overview

Provisions a flaky-test triage loop in a target repo. A **collector workflow**
(`flaky-collector.yml`, scheduled daily) mines recent runs of your test workflow and
their **JUnit artifacts**, computes a flakiness digest using **same-SHA disagreement**
(a test that both passes and fails on the *same commit*), and force-pushes
`flaky-digest.json` to a dedicated `flaky-digest` data branch. A **scheduled Claude
routine** (weekly) reads that digest and either files/updates a tracking issue with the
evidence, or — for tests confirmed flaky on **≥2 distinct commits** — opens a PR that
quarantines (skips) the test. The routine **only edits test files** and **never deletes**
a test.

## Flow

    flaky-collector.yml (daily) -> mine runs + JUnit artifacts ->
        flaky_parse.py -> flaky-digest.json -> force-push `flaky-digest` branch
            |
            v
    cron fires the routine -> read flaky-digest.json ->
        classify by distinct_sha_count (>=2 quarantine, ==1 evidence) ->
        quarantine edits (skip tests) OR --allow-empty findings commit ->
        push claude/flaky-<id> (report in commit body)
            |
            v
    flaky-bridge.yml routes on merge-base tree-diff:
        test edits -> open/reuse a PR (quarantine)
        empty      -> open/update the "flaky tests pending triage" issue
            |
            v
    human reviews the quarantine PR / triages the issue

## How flakiness is judged

A test is flaky when, on the **same commit SHA**, it has both passed and failed (same
code, different result). The digest ranks tests by `distinct_sha_count` — how many
distinct commits show that disagreement. `>= 2` → quarantine PR; `== 1` → evidence-only
issue. This keeps a one-off fluke from masking a real intermittent bug.

## Components

- `templates/flaky-collector.yml` — the collector workflow. Copied into
  `.github/workflows/`. Configure its env: `TEST_WORKFLOW`, `ARTIFACT_NAME`,
  `WINDOW_DAYS`.
- `templates/flaky_parse.py` — the JUnit→digest parser. Copied into `.github/`.
- `templates/flaky-bridge.yml` — the PR-or-issue bridge. Copied into
  `.github/workflows/` as-is.
- `templates/routine-prompt.md` — the routine mandate (pasted after the shared
  preamble).

## Repo prerequisites

- **Your test workflow uploads JUnit/test-result XML as an artifact** (named to match
  `ARTIFACT_NAME`). Without per-test results the collector cannot name a flaky test.
- **Actions write permission.** Settings → Actions → General → Workflow permissions →
  **Read and write** (the collector pushes the digest branch; the bridge opens PRs and
  issues).
- **The Claude GitHub App is installed** so the routine can run and push `claude/`
  branches.

## Setup procedure

1. **Copy the files.** Copy `templates/flaky-collector.yml` and `templates/flaky-bridge.yml`
   into `.github/workflows/`, and `templates/flaky_parse.py` into `.github/`. Edit the
   collector's `TEST_WORKFLOW`, `ARTIFACT_NAME`, and `WINDOW_DAYS` env values for your
   repo. Commit on the **default branch**.
2. **Create the routine** in Claude Code on the web. Paste
   `../_shared/templates/routine-prompt.preamble.md` first, then the full text of
   `templates/routine-prompt.md`. Bind it to the target repo and grant at least
   `Bash, Read, Write, Edit, Glob, Grep`.
3. **Set schedules.** The collector runs daily by default; set the routine to run
   **weekly** so it acts on an established digest.

## How to verify it works

On a throwaway repo with one deliberately ~50%-flaky test whose CI uploads JUnit
results:

```bash
# run the test workflow a few times on the SAME commit (re-run), then trigger the collector
gh workflow run flaky-collector.yml
git fetch origin flaky-digest && git show flaky-digest:flaky-digest.json   # the test is listed
# then trigger the routine:
gh pr list --head 'claude/flaky-' --state open       # >=2 flipping SHAs -> a quarantine PR
gh issue list --search 'in:title "flaky tests pending triage"'   # 1 SHA -> the rolling issue
```

## Guardrails (why it is safe)

- The routine pushes only to `claude/` branches and never merges.
- It edits only test files to **skip** a flaky test (with a reason linking the issue);
  it never deletes a test and never edits product code.
- It quarantines only tests confirmed flaky on **≥2 distinct commits**; a single
  occurrence is reported as evidence only, not skipped.
- If it can't locate a test or determine the skip idiom, it does not edit — evidence
  only.
- The collector pushes only to the `flaky-digest` data branch, never `main`.
- One quarantine PR **or** one rolling issue per run; a no-flaky run pushes nothing.
- Fork PRs are not supported (Actions cannot push to a fork's branch).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Digest is empty / `runs_missing_artifact` high | Your test workflow isn't uploading JUnit results as `ARTIFACT_NAME`. Add the artifact upload. |
| Collector finds no runs | `TEST_WORKFLOW` doesn't match your CI workflow filename, or no runs in `WINDOW_DAYS`. |
| Nothing flagged despite known flakes | Flakiness never recurred on the *same* SHA (only different commits failed) — by design, that's a regression signal, not flakiness. |
| Quarantine PR never appears, only issues | No test reached `distinct_sha_count >= 2`, or the routine couldn't determine the skip idiom. |
| Collector push fails (403) | Actions token is read-only. Settings → Actions → General → Workflow permissions → **Read and write**. |
```

- [ ] **Step 3: Verify**

Run:
```bash
F=skills/flaky-test-routine/SKILL.md
python3 -c "import re,sys;t=open('$F').read();m=re.match(r'^---\n(.*?)\n---\n',t,re.S);sys.exit(0 if (m and 'name:' in m.group(1) and 'description:' in m.group(1)) else 1)" && echo FRONTMATTER-OK
grep -q 'claude/flaky-\*' "$F" && grep -q 'routine-skeleton.md' "$F" && grep -q 'routine-prompt.preamble.md' "$F" && \
  grep -q 'flaky tests pending triage' "$F" && grep -q 'flaky-digest' "$F" && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `FRONTMATTER-OK`, `CHECK-PASS`.

- [ ] **Step 4: Commit**

```bash
git add skills/flaky-test-routine/SKILL.md
git commit -m "feat(flaky-test): SKILL.md (collector setup, signal, verify, guardrails)"
```

---

### Task 6: Update plugin metadata + README

**Files:**
- Modify: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: the skill (Tasks 1–5) by name. Final task.

- [ ] **Step 1: Write the failing check**

Run (expect FAIL):
```bash
grep -q 'flaky-test-routine' README.md && grep -q 'flaky-test-routine' .claude-plugin/plugin.json && \
  python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('JSON-OK')" && \
  grep -q '0.5.0' .claude-plugin/plugin.json && echo CHECK-PASS || echo CHECK-FAIL
```
Expected: `CHECK-FAIL`

- [ ] **Step 2: Add flaky-test-routine to the README**

In `README.md`, add a bullet to the `## Skills` list:
```markdown
- **flaky-test-routine** — set up a scheduled collector that mines CI runs + JUnit
  artifacts for flaky tests (same-SHA pass/fail disagreement), plus a routine that files
  a tracking issue with the evidence or opens a PR quarantining strongly-confirmed
  flaky tests. Built on the shared routine skeleton. See
  [`skills/flaky-test-routine/SKILL.md`](skills/flaky-test-routine/SKILL.md).
```
And add to the `## Layout` tree, after the `docs-sync-routine/` block:
```
  flaky-test-routine/
    SKILL.md
    templates/       # collector + JUnit parser + routine prompt + PR-or-issue bridge
```

- [ ] **Step 3: Bump version + mention flaky-test in the manifests**

In `.claude-plugin/plugin.json`: change `"version": "0.4.0"` to `"version": "0.5.0"` and extend the `description` to mention `flaky-test-routine (CI-history flaky-test triage via issue or quarantine PR)`.

In `.claude-plugin/marketplace.json`: extend the plugin `description` the same way.

- [ ] **Step 4: Verify**

Run the Step 1 command. Expected: `CHECK-PASS`.

- [ ] **Step 5: Commit**

```bash
git add README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs: list flaky-test-routine; bump plugin to 0.5.0"
```

---

## Final verification (after all tasks)

- [ ] **Parser unit test:** `python3 skills/flaky-test-routine/test_flaky_parse.py` → `PARSER-TESTS-PASS`.
- [ ] **Collector + bridge valid:** re-run Task 2 Step 3 and Task 3 Step 4 checks (YAML, perms, `bash -n`, refs/routes).
- [ ] **All JSON valid:** `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'));print('OK')"`.
- [ ] **Consistency:** `grep -rl 'claude/flaky-' skills/flaky-test-routine` shows SKILL.md, routine-prompt.md, flaky-bridge.yml; `grep -rl 'flaky-digest' skills/flaky-test-routine` shows collector, routine-prompt, SKILL; the issue title `flaky tests pending triage` appears in flaky-bridge.yml and SKILL.md.
- [ ] **Six skills present:** `ls skills` shows `_shared`, `auto-merge-pr`, `dependency-update-routine`, `docs-sync-routine`, `e2e-coverage-routine`, `flaky-test-routine`.
- [ ] **All shipped workflow YAMLs parse** (excluding the raw `_shared/templates/pr-bridge.yml` token template): a `python3` `yaml.safe_load` loop over `skills/**/templates/*.yml`.
