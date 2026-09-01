---
name: review-tests
description: Review this repo's tests for quality and hygiene — trivial tests written to satisfy the coverage floor, assertions on implementation rather than behavior, a fake defined inline where conftest already has one, tests that reach the network or the real library, and vague names. Also applies as guidelines when writing or modifying tests. Invoke with a file or directory path to audit.
argument-hint: "<file-or-directory>"
---

# Test Quality Review

Review test files for quality and hygiene. Also serves as guidelines when
writing tests — for the use cases in `application/`, the adapters under
`adapters/`, the FastAPI routes in `adapters/inbound/web/`, and the front end
under `web/src/`.

This repo gates coverage at 95%. That floor is why this skill exists: a hard
percentage rewards tests that execute lines without asserting anything worth
asserting, and those tests cost more than they return — they fail on refactors,
pass on regressions, and make the suite slower to read.

## When this activates

- The user invokes `/review-tests <path>`
- Reviewing tests before a commit, since `just check` runs them anyway
- Auditing an existing test module
- Writing or modifying `tests/test_*.py`, `tests/conftest.py`, or `web/src/**/*.test.ts{,x}`

## Input

When invoked with `$ARGUMENTS`:

- A file → review that file.
- A directory → review every `test_*.py` and `*.test.ts{,x}` under it.
- Empty → review the test files in the current diff
  (`git diff --name-only HEAD` filtered to test files).

## Rule index

Detailed rules live in `rules/`:

| # | File | Summary |
|---|------|---------|
| 1 | `rules/no-framework-testing.md` | Never test pydantic, FastAPI, SQLite or the standard library — only this app's rules |
| 2 | `rules/behavior-not-implementation.md` | Assert observable outcomes, not which collaborator got called |
| 3 | `rules/invariants-not-snapshots.md` | Test the rule, not a frozen copy of today's output |
| 4 | `rules/descriptive-test-names.md` | The name is the specification |
| 5 | `rules/one-behavior-per-test.md` | Each test has one reason to fail |
| 6 | `rules/fakes-over-monkeypatching.md` | Ports exist so a test can hand in a stand-in; one fake per port, in `conftest.py` |
| 7 | `rules/hermetic-by-default.md` | No network, no key, no `~/.upnext`; `integration` is the opt-out |
| 8 | `rules/coverage-is-not-the-goal.md` | The 95% floor is a floor, not a target to game |
| 9 | `rules/name-the-count-you-mean.md` | Watches, matched episodes and unmatched episodes are three numbers |
| 10 | `rules/migrations-from-the-old-shape.md` | A migration test must start from a database in the shape it migrates |
| 11 | `rules/frontend-pure-functions.md` | Logic in `lib/`, tested directly; render only what only exists rendered |

## Quick decision checklist

Before writing a test, ask:

| Question | If no |
|----------|-------|
| Does this verify a rule this app decided on? | Don't write it |
| Could it fail from a real behavior change? | If a library guarantees it, skip |
| Would it survive a refactor that kept behavior? | Decouple it from the implementation |
| Is the name a sentence about behavior? | Rename it |
| Does it have exactly one reason to fail? | Split it |
| Does this port already have a fake in `conftest.py`? | Use it rather than defining another |
| Does it stay off the network and out of `~/.upnext`? | Fix it, or mark it `integration` |
| Does an assertion on a count say *which* count? | Make it explicit |
| Does the module mirror the source module it covers? | Move it |

## Review process

### Step 1 — collect
Resolve the input to a list of test files and print it.

### Step 2 — read
For each file: read it in full, then read the source module it covers (follow
the imports). A test can only be judged against what it is supposed to protect.
Read `AGENTS.md` too — most of what looks like a missing assertion here is a
decision recorded there, and a test that contradicts it is the finding.

### Step 3 — classify
For each issue record:

- **file** and **test**: path, and the test function name
- **rule**: which of #1–#11
- **severity**: `high` (the test is worthless or actively harmful), `medium`
  (weak but marginally useful), `low` (naming or style)
- **finding**: one line on what is wrong
- **suggestion**: the concrete fix — "delete this", "assert the returned
  `TitleRow` instead of the call count", "use the `catalog` fixture rather than
  defining a fourth `FakeCatalog`"

### Step 4 — report

```
## Test review: <file-or-directory>

### Summary
- Files reviewed: N
- Tests reviewed: N
- Issues: N (high: N, medium: N, low: N)

### Findings

#### <file_path>

| Test | Rule | Severity | Finding | Suggestion |
|------|------|----------|---------|------------|

### Worth keeping
Two or three tests from what you read that show the bar, and why.
```

## Hard rules

- **Read-only.** Do not modify any file. Report, don't fix.
- **Do not suggest new tests.** Coverage gaps are a different job; this skill
  judges the tests that exist.
- **Fakes are not a finding.** A fake standing in for the `Catalog` port is the
  intended design — see rule #6. Flag the *assertion*, or a *duplicate* fake,
  never the double itself.
- **Simple is not a finding.** A one-line rule deserves a one-line test.
  `test_a_show_with_no_dates_yields_no_year` is doing its job.
- **A test that documents a failure is doing its job.** Several tests here name
  the failure they exist to prevent — a watched special counted as progress, a
  watch deleted along with its episode. That comment is the point, not noise.
- **Say so when a file is clean.** Do not manufacture findings to fill a table.
- **Cite exactly**: test function name and line number, every time.
