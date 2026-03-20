# Approval Decision Schema

**Status**: Sprint 11C — Review Record Formalization
**Date**: 2026-03-20
**Purpose**: Define the canonical schema for persisted ApprovalDecision records

## Overview

An ApprovalDecision is a JSON file stored at `reviews/{ticket_id}.approval.json`.
It represents the Creative Director's decision on a ticket in review state.
ApprovalDecision records are **immutable** — once written, they cannot be changed.

Approval is a **creative gate**. It assesses whether the work meets creative intent.
It does not replace QA (technical gate) and does not itself authorize promotion.

## Schema (v1 — Sprint 11C)

```json
{
  "schema_version": 1,
  "ticket_id": "sprint-10c-ref-001",
  "decision": "approved",
  "reviewer": "creative-director",
  "reason": "Output meets creative intent, file structure correct.",
  "decided_at": "2026-03-19T19:25:45Z"
}
```

## Field Definitions

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `ticket_id` | string | The ticket this decision belongs to. Must match filename. |
| `decision` | string | One of: `approved`, `rejected`, `reticketed`. |
| `reviewer` | string | Who made the decision. Currently always `"creative-director"`. |
| `reason` | string | Operator-provided rationale. May be empty. |
| `decided_at` | string | ISO 8601 timestamp of the decision. |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Schema version. `1` for Sprint 11C format. Absent in pre-11C records (treated as v0). |

## Decision Values

| Decision | Meaning | Ticket Transition | Promotion |
|----------|---------|-------------------|-----------|
| `approved` | Work meets creative intent | review → done | Allowed (with QA pass) |
| `rejected` | Work does not meet creative intent | review → active → failed | Blocked |
| `reticketed` | Work needs different scope or approach | review → active → failed | Blocked |

**Invariant**: Only `decision == "approved"` can lead to promotion. This is enforced by `create_promotion_request()` checking `approval["decision"] != "approved"`.

## Relationship to QA

Approval and QA are independent gates. Both must pass for promotion.

| Scenario | Promotion |
|----------|-----------|
| QA pass + Approval approved | Allowed |
| QA pass + Approval rejected | Blocked |
| QA fail + Approval approved | Blocked |
| QA fail + Approval rejected | Blocked |

**Recommended order**: QA → Approval → PromotionRequest.
**Not enforced in code**: The Creative Director may approve before QA is recorded. This does not bypass the promotion gate — `create_promotion_request()` independently checks both QA and Approval.

## Ticket State Side Effects

`create_approval_decision()` triggers automatic ticket state transitions:

| Decision | Transition | Rationale |
|----------|------------|-----------|
| `approved` | review → done | Work accepted, ready for promotion pipeline |
| `rejected` | review → active → failed | Sent back for rework |
| `reticketed` | review → active → failed | Needs new ticket with different scope |

These transitions only fire when the ticket is in `review` state at the time of the decision.

## Preconditions

Before an ApprovalDecision can be created:
- `ReviewPackage` must exist (enforced by `create_approval_decision()`)
- Decision must be one of `APPROVAL_DECISIONS` (enforced)

**Not required before approval:**
- QA result (not checked — see "Relationship to QA" above)

## Immutability

Once an ApprovalDecision is written, it cannot be changed. `create_approval_decision()` raises `RuntimeError` if a record already exists.

If a decision was recorded incorrectly:
- The original decision stands
- A new ticket must be created if the work needs re-evaluation
- The `reason` field should document the rationale

## Compatibility

### Pre-11C Records

Records created before Sprint 11C lack the `schema_version` field. These are treated as v0 and remain fully compatible — all consumers read the same fields.

### Reading Rules

| Condition | Interpretation |
|-----------|---------------|
| `schema_version` absent | v0 (pre-11C), valid |
| `schema_version: 1` | v1 (Sprint 11C+), valid |
| `decision` not in {approved, rejected, reticketed} | Invalid — should not exist |

No migration needed. Pre-11C records are read identically.

## What ApprovalDecision Records Do NOT Contain

- No QA assessment (that's `qa.json`)
- No technical validation (that's `validate_worker_output()`)
- No promotion status (that's `promotion.json`)
- No content hash or diff
- No worker output details (that's the `ReviewPackage`)

## CLI Commands

| Command | Effect |
|---------|--------|
| `approve TICKET_ID [--reason TEXT]` | Creates ApprovalDecision with `decision: "approved"` |
| `reject TICKET_ID [--reason TEXT]` | Creates ApprovalDecision with `decision: "rejected"` |
| `reticket TICKET_ID [--reason TEXT]` | Creates ApprovalDecision with `decision: "reticketed"` |
| `review-show TICKET_ID` | Shows ReviewPackage (not ApprovalDecision) |
