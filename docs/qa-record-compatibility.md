# QA Record Compatibility

**Status**: Sprint 11B — QA Record Formalization
**Date**: 2026-03-19
**Purpose**: Define how legacy and current QA records coexist

## Problem

Before Sprint 11B, QA records used a simpler schema (v1):

```json
{
  "ticket_id": "t-001",
  "passed": true,
  "notes": "All good",
  "validated_at": "2026-03-16T12:00:00Z",
  "validator": "creative-director"
}
```

Sprint 11B introduces schema v2 with `decision`, `worker_class`, `checked_artifacts`, and `schema_version` fields.

Both must coexist without silent breaking changes.

## Current State

As of Sprint 11B, **no QA records exist on disk**. The `reviews/` directory has never been created because no ticket has been put through the manual QA gate (`qa-pass`/`qa-fail`). All reference tickets stopped at `review/` state.

This means there is technically no migration problem — yet. But the compatibility rules must be defined now because:
- Tests create v1-format records
- Future code may encounter records from either schema version
- The rules must be clear before records start accumulating

## Schema Versions

| Version | Source | Distinguishing Feature |
|---------|--------|----------------------|
| v1 | Pre-11B | No `schema_version` field. Only `passed: bool` and `notes`. |
| v2 | Sprint 11B | Has `schema_version: 2`, `decision` field, optional `worker_class` and `checked_artifacts`. |

## Reading Rules

### Rule 1: Detect Version by Presence of `schema_version`

```
if "schema_version" not in record:
    → treat as v1
else:
    → use schema_version value
```

### Rule 2: v1 → v2 Mapping

When reading a v1 record, interpret it as:

| v1 Field | v2 Equivalent | Mapping |
|----------|---------------|---------|
| `passed: true` | `decision: "pass"` | Direct |
| `passed: false` | `decision: "fail"` | Conservative: assume fail, not blocked/inconclusive |
| `notes` | `notes` | Preserved as-is |
| (absent) | `worker_class` | Unknown — treat as unclassified |
| (absent) | `checked_artifacts` | Unknown — treat as empty |

**Important**: `passed: false` in v1 maps to `decision: "fail"`, not `"blocked"` or `"inconclusive"`.
This is the conservative interpretation — if blocked/inconclusive was intended, the notes field should be consulted for context, but the system treats it as fail for gate purposes.

### Rule 3: v2 Reading

When reading a v2 record:
- `decision` is the authoritative decision
- `passed` is derived from `decision == "pass"` and must be consistent
- If `passed` and `decision` contradict each other, `decision` takes precedence
- `worker_class` and `checked_artifacts` are optional and may be absent

### Rule 4: Promotion Gate

Promotion uses `qa.get("passed")` as the gate-relevant check.
This works identically for both v1 and v2 records:
- v1: `passed: true` → allowed
- v2: `passed: true` (which implies `decision == "pass"`) → allowed
- All other states → blocked

No migration or version-specific logic needed in the promotion path.

## Writing Rules

### Rule 5: New Records Use v2

All new QA records created after Sprint 11B use v2 schema.
`create_qa_result()` always sets `schema_version: 2`.

### Rule 6: No v1 Records Can Be Created

The updated `create_qa_result()` always includes `decision` and `schema_version`.
Legacy `passed: bool` is preserved for backward compatibility but is derived from `decision`.

### Rule 7: No Retroactive Migration

Existing v1 records (if any) are never modified.
They are interpreted according to Rule 2 when read.
No migration script, no batch update, no silent rewriting.

## Edge Cases

### Notes-Prefix Convention (Sprint 11A)

Sprint 11A introduced `BLOCKED:`, `INCONCLUSIVE:`, `FAIL:` prefixes in the `notes` field as an operator convention.

In v2, these are superseded by the `decision` field:
- v2 records should use the `decision` field, not rely on notes prefixes
- v1 records with notes prefixes are still interpreted by Rule 2 (`passed: false` → `fail`)
- The notes prefix is informational context only — it does not override the `decision` or `passed` fields

### Contradictory `passed` and `decision`

Should not occur because `create_qa_result()` enforces the invariant.
If encountered in a manually edited file:
- `decision` takes precedence
- Log a warning
- `passed` is treated as unreliable

## Summary

| Scenario | Behavior |
|----------|----------|
| No QA record exists | Promotion blocked (FileNotFoundError) |
| v1 record with `passed: true` | Promotion allowed |
| v1 record with `passed: false` | Promotion blocked |
| v2 record with `decision: "pass"` | Promotion allowed |
| v2 record with `decision: "fail"` | Promotion blocked |
| v2 record with `decision: "blocked"` | Promotion blocked |
| v2 record with `decision: "inconclusive"` | Promotion blocked |
