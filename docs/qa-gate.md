# QA Gate

> Sprint 5 — HYBRIS Agent Host

## Why a QA Gate Is Required

Without an explicit QA gate, a ticket can appear "promotion-ready" based solely on:
- ReviewPackage exists (formal)
- Approval = approved (formal)

This means a formally correct but **functionally unvalidated** ticket could reach production. The QA gate closes this gap by requiring an explicit validation result before any promotion can proceed.

## What Is Implemented Now

A minimal, immutable **QA validation artifact** stored as JSON alongside the review artifacts.

### QA Result Record

```json
{
  "ticket_id": "TICKET-001",
  "passed": true,
  "notes": "All acceptance criteria met, tested on feature branch",
  "validated_at": "2026-03-16T12:00:00Z",
  "validator": "creative-director"
}
```

**File:** `reviews/<ticket_id>.qa.json`

### Functions

| Function | Purpose |
|----------|---------|
| `create_qa_result(cfg, ticket_id, passed, notes)` | Record QA passed/failed. Requires ReviewPackage. Immutable. |
| `load_qa_result(cfg, ticket_id)` | Load existing QA result |

### CLI Commands

| Command | Purpose |
|---------|---------|
| `qa-pass TICKET_ID [--notes TEXT]` | Mark QA as passed |
| `qa-fail TICKET_ID [--notes TEXT]` | Mark QA as failed |
| `qa-check TICKET_ID` | Show current QA status |

## What Constitutes "QA Passed"

The Creative Director explicitly marks a ticket as QA-passed after:
1. Reviewing the ReviewPackage (artifacts, worker log, branch)
2. Verifying acceptance criteria are met
3. Confirming the work is ready for production

This is a **manual, human-in-the-loop** decision — not automated testing.

## How QA Affects Promotion Readiness

`check_promotion_readiness()` includes a `qa_gate` check (6 checks total):

1. ✓ ReviewPackage exists
2. ✓ ApprovalDecision = approved
3. ✓ **QA gate passed** ← Sprint 5
4. ✓ Repo separation enforced
5. ✓ test_repo exists
6. ✓ prod_repo exists

`create_promotion_request()` will **raise an error** if QA has not passed.

## Immutability

QA results are immutable — once recorded, they cannot be changed. If a QA failed result was recorded in error, a new ticket must be created (same as approval decisions).

## What Remains Deferred

- Automated test execution as part of QA
- QA as a distinct ticket lifecycle state (currently enforced as a promotion precondition)
- Multi-reviewer QA workflows
- QA checklists or structured validation criteria
