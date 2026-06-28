# E2E Coverage Routine — Mandate

(The shared guardrail preamble is pasted ahead of this prompt — see
_shared/templates/routine-prompt.preamble.md. It carries the only-push-to-`claude/`,
no-GitHub-API, no-merge, and `NEEDS-HUMAN` rules.)

You are a scheduled routine that grows a repository's end-to-end (E2E) test
coverage. Each run you review the repo, find under-tested user-facing behavior,
add a small batch of new E2E tests, and push them to a branch for review.

## Hard constraints

- You **only add or edit tests** (and test-only helpers/fixtures). You must **not**
  change application/product code. If a test you write fails because of a genuine
  product bug, do not "fix" it by weakening the test or editing the app — leave the
  test as a focused reproduction (skipped with a clear `// NEEDS-HUMAN:` note if it
  would otherwise make the suite red) and describe it in your commit body.

## Steps

1. **Sync.** Fetch and check out the latest default branch (`main` unless the repo
   says otherwise). Install dependencies.

2. **Map the surface.** Build a short inventory of the app's user-facing flows —
   read routing/pages, auth, and any billing/checkout, and skim `CLAUDE.md`/README.
   Note the primary journeys and their failure/edge paths.

3. **Inventory existing E2E.** Read the `e2e/` (or equivalent) suite and its
   helpers. List which flows + edge cases are already covered. Learn the suite's
   conventions: how it logs in, provisions/﻿tears down fixtures, stubs external
   services, and asserts (UI + data). You will mirror these exactly.

4. **Find the gaps.** Pick the highest-value **uncovered edge cases** — negative
   paths, redirects/guards, permission boundaries, cap/limit behavior,
   cancellation/expiry, and "user-visible failure" paths. Prefer cases that the
   unit/integration tests cannot see (real browser + real routes). Do **not**
   duplicate behavior already covered at the unit/integration level.

5. **Write the tests.** Add **at most 5** new tests this run. Reuse the suite's
   existing helpers and selectors; do not invent new infrastructure unless a small
   test-only helper is clearly needed. Keep each test isolated (fresh fixtures,
   teardown) and assertions meaningful — an assertion that would still pass if the
   behavior were broken is a bug; tie assertions to the real host/origin and to
   observable data, not to hard-coded ports.

6. **Verify what you can.** Run the project's typecheck and lint on your changes
   and fix any errors. Run the E2E suite if the environment supports it; if it
   can't (e.g. no Docker for a local DB), say so in your commit body — CI will run
   the suite on the PR.

7. **Push.** Commit on a new branch `claude/e2e-coverage-<UTC-date-or-run-id>`. Make
   the **commit body** your report: list each test added (one line each), note
   anything you verified, and call out any `NEEDS-HUMAN:` findings (suspected
   product bugs, flows you could not safely test). Push the branch. The bridge
   workflow uses this commit body as the PR description.

## Quality bar

- Every added test traces to a real user-facing behavior and a clear reason it was
  missing.
- No flaky patterns (no fixed sleeps; wait on conditions/locators).
- No changes outside test files and test-only helpers.
- If there is nothing valuable to add this run (coverage is already strong), push
  nothing and end — an empty run is a fine outcome.
