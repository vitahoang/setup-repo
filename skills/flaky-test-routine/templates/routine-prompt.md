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
   edit ONLY that test file to skip it with a reason that references the tracking issue
   by its title (`flaky tests pending triage`) — you cannot include a URL, since the
   bridge opens the issue after you push —
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
- Every quarantine references the tracking issue by title and names the evidence (SHAs + run URLs).
- One push per run: a quarantine PR, or the rolling issue, or nothing.
