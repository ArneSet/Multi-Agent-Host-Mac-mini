# Promotion Preconditions

**Status**: Sprint 11B — Promotion Preconditions Hardening
**Date**: 2026-03-19
**Purpose**: Canonical definition of all preconditions that must be met before promotion

## Core Principle

Promotion is **always manual**. No amount of passing checks makes promotion automatic.
All preconditions must pass. Any single failure blocks promotion entirely.

## Precondition Checks

`check_promotion_readiness()` performs 6 checks. All must pass.

### Check 1: ReviewPackage exists

| Aspect | Value |
|--------|-------|
| **Name** | `review_package` |
| **What** | `reviews/{ticket_id}.review.json` must exist |
| **Why** | Ensures worker output has been formally packaged for review |
| **Failure** | `FileNotFoundError` — no ReviewPackage found |
| **Resolution** | Create ReviewPackage via `create_review_package()` |

### Check 2: ApprovalDecision == "approved"

| Aspect | Value |
|--------|-------|
| **Name** | `approval_decision` |
| **What** | `reviews/{ticket_id}.approval.json` must exist with `decision: "approved"` |
| **Why** | Creative Director must explicitly approve the work |
| **Failure** | Decision missing, or decision is `"rejected"` / `"reticketed"` |
| **Resolution** | Record approval via `approve`, `reject`, or `reticket` CLI commands |

### Check 3: QA Gate passed

| Aspect | Value |
|--------|-------|
| **Name** | `qa_gate` |
| **What** | `reviews/{ticket_id}.qa.json` must exist with `passed: true` |
| **Why** | Technical QA must confirm structural soundness |
| **Failure** | No QA record, or `passed: false` (regardless of `decision` value) |
| **Resolution** | Record QA via `qa-pass` or `qa-fail` CLI commands |

**Decision-to-gate mapping** (Sprint 11B):

| QA Decision | `passed` | Promotion |
|-------------|----------|-----------|
| `pass` | `true` | Allowed |
| `fail` | `false` | Blocked |
| `blocked` | `false` | Blocked |
| `inconclusive` | `false` | Blocked |

Only `decision == "pass"` allows promotion. This is enforced through the `passed: bool` field.

### Check 4: Repo separation enforced

| Aspect | Value |
|--------|-------|
| **Name** | `repo_separation` |
| **What** | test_repo and prod_repo must be physically distinct paths |
| **Why** | Prevents accidental cross-contamination |
| **Failure** | Paths resolve to same location |
| **Resolution** | Fix config — this is a setup error |

### Check 5: test_repo exists

| Aspect | Value |
|--------|-------|
| **Name** | `test_repo_exists` |
| **What** | test_repo path must exist as a directory |
| **Why** | Source of promotion content must be accessible |
| **Failure** | Directory missing |
| **Resolution** | Verify test_repo path in config |

### Check 6: prod_repo exists

| Aspect | Value |
|--------|-------|
| **Name** | `prod_repo_exists` |
| **What** | prod_repo path must exist as a directory |
| **Why** | Target for promotion must be accessible |
| **Failure** | Directory missing |
| **Resolution** | Verify prod_repo path in config |

## Hard Gates in `create_promotion_request()`

Beyond `check_promotion_readiness()`, `create_promotion_request()` enforces additional hard gates:

| Gate | Enforcement | Error |
|------|-------------|-------|
| Repo separation | `validate_repo_separation()` | ValueError |
| Approval == "approved" | `approval["decision"] != "approved"` | ValueError |
| QA passed | `not qa.get("passed")` | ValueError |
| No duplicate request | `existing.exists()` | RuntimeError |

These are not advisory — they raise exceptions and prevent the promotion request from being created.

## Promotion Flow

```
Ticket in review state
    ↓
1. create_review_package()     → ReviewPackage
2. create_approval_decision()  → ApprovalDecision (approved)
3. create_qa_result()          → QA Record (decision=pass, passed=true)
    ↓
4. check_promotion_readiness() → all 6 checks pass
    ↓
5. create_promotion_request()  → PromotionRequest (status=pending)
    ↓
6. execute_promotion()         → manual execution
```

Each step requires the previous step to be complete. No step can be skipped.

## What Promotion Does NOT Do

- Promotion does not auto-execute
- Promotion does not bypass QA
- Promotion does not bypass Review/Approval
- Promotion does not create or modify test_repo content
- Promotion does not assess creative quality
- Promotion does not make the system "production-ready"

## Relationship to QA Decision Model

The QA decision model (see `docs/qa-decision-model.md`) provides four states.
Promotion only cares about the binary gate: `passed == true`.

The distinction between `fail`, `blocked`, and `inconclusive` matters for the **operator's follow-up action** but not for the promotion gate. All three block promotion equally.

| QA State | Operator Action | Promotion |
|----------|-----------------|-----------|
| pass | Proceed with approval | Allowed |
| fail | Re-ticket with failure reason | Blocked |
| blocked | Resolve blocker, re-assess QA | Blocked |
| inconclusive | Investigate, then decide pass or fail | Blocked |
