# QA Record Schema

**Status**: Sprint 11B — QA Record Formalization
**Date**: 2026-03-19
**Purpose**: Define the canonical schema for persisted QA records

## Overview

A QA record is a JSON file stored at `reviews/{ticket_id}.qa.json`.
It represents the outcome of a manual QA assessment by the Creative Director.
QA records are **immutable** — once written, they cannot be changed.

QA is a **technical gate**. It verifies structural soundness. It does not replace Review.

## Schema (v2 — Sprint 11B)

```json
{
  "schema_version": 2,
  "ticket_id": "sprint-10c-ref-001",
  "decision": "pass",
  "passed": true,
  "worker_class": "mutation",
  "checked_artifacts": [
    "artifacts/sprint-10c-ref-001_code_result.md",
    "changeset/ticket-sprint-10c-ref-001/metadata/changeset.json",
    "changeset/ticket-sprint-10c-ref-001/metadata/manifest.json"
  ],
  "notes": "All structural checks passed. File exists, non-empty, changeset complete.",
  "validated_at": "2026-03-19T16:30:00Z",
  "validator": "creative-director"
}
```

## Field Definitions

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `ticket_id` | string | The ticket this QA record belongs to. Must match filename. |
| `decision` | string | One of: `pass`, `fail`, `blocked`, `inconclusive`. The formal QA decision. |
| `passed` | bool | Gate-relevant boolean. `true` only when `decision == "pass"`. Preserved for backward compatibility and promotion gating. |
| `notes` | string | Operator-provided context. May be empty. |
| `validated_at` | string | ISO 8601 timestamp of QA assessment. |
| `validator` | string | Who performed QA. Currently always `"creative-director"`. |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Schema version. `2` for Sprint 11B format. Absent in legacy records (treated as v1). |
| `worker_class` | string | `"mutation"` or `"validation"`. Documents which class of worker produced the output. |
| `checked_artifacts` | list[string] | Paths (relative to management root) of artifacts examined during QA. |

## Decision Values

| Decision | `passed` | Promotion Allowed | Meaning |
|----------|----------|-------------------|---------|
| `pass` | `true` | Yes (with approval) | Output is structurally sound and complete |
| `fail` | `false` | No | Clear structural defect found |
| `blocked` | `false` | No | QA cannot be performed (precondition missing) |
| `inconclusive` | `false` | No | Output exists but QA cannot determine pass or fail |

**Invariant**: `passed == (decision == "pass")`. This is enforced at creation time.

## Relationship to Promotion

Promotion checks `qa.get("passed")`. This means:
- Only `decision == "pass"` allows promotion
- `fail`, `blocked`, `inconclusive` all block promotion equally
- The `decision` field provides operator context for **why** promotion is blocked
- The `passed` field provides the gate-relevant boolean

See `docs/promotion-preconditions.md` for full promotion gate rules.

## Immutability

Once a QA record is written, it cannot be changed. `create_qa_result()` raises `RuntimeError` if a record already exists.

If a decision was recorded incorrectly:
- The original decision stands
- A new ticket must be created if rework is needed
- The `notes` field should document the rationale

## Preconditions

Before a QA record can be created:
- Ticket must be in `review` state
- `ReviewPackage` must exist (enforced by `create_qa_result()`)

## What QA Records Do NOT Contain

- No creative quality assessment
- No automated test results
- No build output
- No diff or content hash
- No approval decision (that's a separate record)
- No promotion status (that's a separate record)
