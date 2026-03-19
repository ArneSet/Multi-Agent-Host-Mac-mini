# QA Decision Model

**Status**: Sprint 11A — QA Gate Hardening
**Date**: 2026-03-19
**Purpose**: Formalize QA decision states beyond binary pass/fail

## Problem Statement

The current QA Gate implementation supports only two states: `passed: true` and `passed: false`.
This is operationally too coarse. Not every issue is a clear pass or fail:

- A worker output may be structurally valid but missing context → not clearly fail, not clearly pass
- A validation run may timeout without producing errors → unclear whether this is a real failure
- A changeset may be present but incomplete → not pass, but also not necessarily a re-ticket situation

## Decision States

QA decisions should use four states:

| State | Meaning | Promotion Allowed | Review Continues | Follow-up Required |
|-------|---------|-------------------|------------------|-------------------|
| **pass** | Output is structurally sound and complete. All technical checks satisfied. | Yes (after approval) | Yes | No |
| **fail** | Output is structurally deficient. Clear technical defect found. | No | No — re-ticket required | Re-ticket with failure reason |
| **blocked** | QA cannot be performed. Missing preconditions or infrastructure issue. | No | No — resolve blocker first | Investigate and unblock |
| **inconclusive** | Output exists but QA cannot determine pass or fail. Edge case or ambiguity. | No | Yes — manual investigation needed | Operator must investigate before re-assessment |

### State Definitions

**pass**
- All blocker-severity checks passed
- Output exists and is non-empty
- Changeset/manifest present
- No structural defects found
- Operator confidence: output is technically sound
- Next step: proceed to approval/review

**fail**
- At least one blocker-severity check failed
- OR output is clearly deficient (empty, missing, corrupted)
- OR security boundary violated
- Next step: re-ticket with clear failure reason
- Cannot be overridden — immutable

**blocked**
- QA cannot run because preconditions are not met
- Examples:
  - ReviewPackage missing
  - Artifacts referenced but not found on disk
  - test_repo not accessible
  - Worker produced no result at all (crash before output)
- Next step: resolve blocker, then re-assess
- This is NOT a quality judgment — it's an infrastructure/precondition issue

**inconclusive**
- Output exists and appears structurally present
- But QA cannot confidently determine whether it meets requirements
- Examples:
  - Modify run succeeded but change is semantically trivial
  - Unity validation exited with code 0 but log contains warnings
  - Artifact report exists but content is ambiguous
  - Changeset says "modified" but no visible content difference
- Next step: operator investigates manually before making pass/fail decision
- This prevents premature pass for edge cases

## Mapping to Current Implementation

### Current State (pre-11A)

```
create_qa_result(cfg, ticket_id, passed=True|False, notes="...")
```

Only two values: `True` or `False`. No blocked/inconclusive.

### Target State (post-11A)

The `notes` field in the QA result should carry the decision context.
The `passed` field remains the gate-relevant boolean.

Mapping:

| Decision | `passed` | `notes` prefix | Promotion |
|----------|----------|---------------|-----------|
| pass | `True` | (any) | allowed |
| fail | `False` | `FAIL: ...` | blocked |
| blocked | `False` | `BLOCKED: ...` | blocked |
| inconclusive | `False` | `INCONCLUSIVE: ...` | blocked |

**Rationale**: The promotion system only checks `passed: bool`. Adding a new field would require changes across CLI, orchestrator, and tests. Using `notes` prefix preserves backward compatibility while adding operational clarity.

This means:
- `fail`, `blocked`, and `inconclusive` all result in `passed: False`
- The distinction is in the `notes` field for operator visibility
- Promotion is blocked for all three non-pass states
- The difference matters for the **operator's follow-up action**, not for the gate logic

## Decision Flow

```
Ticket in review state
    ↓
Operator examines ReviewPackage
    ↓
Can QA be performed?
    ├── No → BLOCKED (precondition missing)
    │       qa-decide {id} blocked --notes "{reason}"
    │       action: resolve blocker, re-assess
    │
    └── Yes → Evaluate output
            ↓
        Is output clearly deficient?
            ├── Yes → FAIL
            │       qa-decide {id} fail --notes "{reason}"
            │       action: re-ticket
            │
            └── No → Is output clearly sound?
                    ├── Yes → PASS
                    │       qa-decide {id} pass --notes "{details}"
                    │       action: proceed to approval
                    │
                    └── No → INCONCLUSIVE
                            qa-decide {id} inconclusive --notes "{what is unclear}"
                            action: investigate, then re-assess
```

## Operational Guidelines

### When to use each state

**Use PASS when:**
- All structural checks pass
- File(s) exist and are non-empty
- Changeset/manifest present and plausible
- Artifact report present
- No security boundary violation
- You are confident the output is technically correct

**Use FAIL when:**
- Output is missing or empty
- Changeset is corrupt or missing
- Security boundary was violated
- File was written to wrong location
- Worker reported success but produced nothing useful
- Clear, unambiguous structural defect

**Use BLOCKED when:**
- You cannot access the artifacts
- test_repo is in an inconsistent state
- ReviewPackage was not created
- Infrastructure issue prevents assessment
- NOT when output quality is questionable — that's inconclusive

**Use INCONCLUSIVE when:**
- Output exists but you're unsure about correctness
- Modify run succeeded but diff is unclear
- Validation passed but with warnings you don't understand
- You need more information before deciding
- NOT when there's a clear defect — that's fail

### Anti-patterns

- Do not use PASS for "probably okay" — investigate or mark inconclusive
- Do not use FAIL for "I'm not sure" — that's inconclusive
- Do not use BLOCKED when the output is just bad — that's fail
- Do not use INCONCLUSIVE to avoid making a decision — investigate first
- Do not pass Mutation Worker output without verifying file existence
- Do not pass Validation Worker output without checking report content

## Immutability

Once a QA decision is recorded, it cannot be changed. This is enforced by `create_qa_result()`.

If a decision was recorded incorrectly:
- The original decision stands
- A new ticket must be created if rework is needed
- The notes field should document why the decision was made
