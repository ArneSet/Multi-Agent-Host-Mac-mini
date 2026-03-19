# QA Gate Rules

**Status**: Sprint 11A — QA Gate Hardening
**Date**: 2026-03-19
**Purpose**: Canonical rules for the QA gate, organized by worker class and severity

## Architecture

The QA process has two distinct layers:

```
Worker completes
    ↓
Layer 1: Output Validation (automatic)
    validate_worker_output() — runs immediately after worker dispatch
    Binary: valid / invalid
    If invalid → ticket transitions to "failed" (never reaches review)
    ↓
Layer 2: QA Gate (manual, human-in-the-loop)
    create_qa_result() — recorded by Creative Director
    Binary: passed / failed (see qa-decision-model.md for extended states)
    If not passed → promotion blocked
    ↓
Review remains mandatory
Promotion remains manual
```

## Layer 1: Output Validation Rules

These rules are enforced automatically by `validate_worker_output()` in orchestrator.py.
Failure at this layer prevents the ticket from ever reaching review state.

### Universal Rules (all workers)

| ID | Rule | Severity | Effect on Failure |
|----|------|----------|-------------------|
| U1 | `files_written` non-empty OR `artifacts` non-empty | blocker | ticket → failed |
| U2 | If `changeset_dir` provided: `changeset.json` must exist | blocker | ticket → failed |
| U3 | If `changeset_dir` provided: `manifest.json` must exist | blocker | ticket → failed |
| U4 | Every artifact path must exist as file | blocker | ticket → failed |

### Mutation Worker Rules (code-worker)

Applied when `files_written` is non-empty:

| ID | Rule | Severity | Effect on Failure |
|----|------|----------|-------------------|
| M1 | `files_written` must be non-empty | blocker | ticket → failed |
| M2 | Each file in `files_written` must exist in test_repo | blocker | ticket → failed |
| M3 | Each file must have size > 0 bytes | blocker | ticket → failed |

### Validation Worker Rules (unity-worker)

Applied when `files_written` is empty but `artifacts` is non-empty:

| ID | Rule | Severity | Effect on Failure |
|----|------|----------|-------------------|
| V1 | `artifacts` must be non-empty | blocker | ticket → failed |
| V2 | Each artifact file must exist | blocker | ticket → failed |

### Rules NOT Currently Implemented

These are documented boundaries, not implemented checks:

| ID | Rule | Category | Status |
|----|------|----------|--------|
| N1 | `action` field matches actual filesystem state | advisory | not implemented |
| N2 | `files_added` / `files_modified` consistent with `action` | advisory | not implemented |
| N3 | Content is non-trivial (not just whitespace/empty markers) | advisory | not implemented |
| N4 | Validation Worker `files_written` is enforced empty | advisory | not implemented |
| N5 | Validation report contains interpretable pass/fail | advisory | not implemented |
| N6 | File type is within allowed scope | advisory | not implemented |

These are acceptable gaps for the current limited worker set. They should be revisited before adding new workers.

## Layer 2: QA Gate Rules

These rules are applied manually by the Creative Director using `qa-decide`, `qa-pass`, or `qa-fail` CLI commands.

### Before QA Can Be Recorded

| Precondition | Enforcement |
|--------------|-------------|
| Ticket must be in `review` state | ReviewPackage creation requires review state |
| ReviewPackage must exist | `create_qa_result()` requires ReviewPackage |
| QA must not already be recorded | Immutability enforced — RuntimeError on duplicate |

### QA Assessment Criteria

The Creative Director should evaluate based on worker class:

**For Mutation Worker outputs:**
- Does the output match what the ticket requested?
- Is the file content correct and complete?
- Is the changeset/manifest accurate?
- Are there any obvious errors in the output?
- Is the scope appropriate (no unexpected files)?

**For Validation Worker outputs:**
- Does the report accurately reflect project state?
- Are errors/warnings correctly identified?
- Is the validation type appropriate for the ticket?
- Is the report complete and interpretable?

### QA Gate Effect on Promotion

```
check_promotion_readiness() checks:
  1. ReviewPackage exists          → must pass
  2. ApprovalDecision = approved   → must pass
  3. QA gate passed                → must pass  ← THIS
  4. Repo separation enforced      → must pass
  5. test_repo exists              → must pass
  6. prod_repo exists              → must pass

All 6 must pass. Any failure blocks promotion.
create_promotion_request() raises ValueError if QA not passed.
```

## Severity Definitions

| Severity | Meaning | Consequence |
|----------|---------|-------------|
| **blocker** | Cannot proceed. Ticket must fail or be re-ticketed. | Automatic: ticket → failed. Manual: no promotion possible. |
| **fail** | Output is structurally deficient. Ticket should not pass QA. | QA should record `passed: false`. Review should not approve. |
| **advisory** | Potential issue noted but not enforced. | Logged or documented. Does not block pipeline. |

## Explicit Non-Rules

These things are explicitly NOT part of QA:

- QA does not verify creative quality or artistic direction
- QA does not run Unity builds or tests
- QA does not compare output to reference implementations
- QA does not auto-promote approved tickets
- QA does not replace human Review
- QA does not enforce code style or formatting
- QA does not assess whether a modify actually changed content (existence/non-emptiness only)

## Immutability

Both Output Validation results and QA Gate results are effectively immutable:
- Output Validation runs once, inline with pipeline execution
- QA Gate result (`qa.json`) cannot be overwritten (RuntimeError)
- If QA was recorded incorrectly, a new ticket must be created
