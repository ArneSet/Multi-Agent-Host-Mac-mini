# Output Validation Rules

> **Sprint:** 10C — Worker Output Model Hardening  
> **Date:** 2026-03-19  
> **Status:** Canonical — binding for `validate_worker_output()` in orchestrator  

---

## Purpose

This document defines the exact rules that `validate_worker_output()` enforces after a worker reports success. These rules prevent silent success — a worker claiming completion without producing verifiable output.

The validation runs in `_process_ticket_inner()` between worker dispatch and state transition. If validation fails, `result["success"]` is flipped to `False`, and the ticket transitions to `failed` instead of `review`.

---

## Implementation Reference

Function: `validate_worker_output()` in `orchestrator.py`  
Called from: `_process_ticket_inner()`, after `dispatch_worker()`, before `transition_ticket()`  
Condition: Only runs when `result["success"] == True` and `dry_run == False`  

---

## Universal Rules (All Workers)

These apply regardless of worker class:

| # | Rule | Failure Behavior |
|---|------|-----------------|
| 1 | Worker must produce at least one of: `files_written` (non-empty) or `artifacts` (non-empty) | Immediate fail |
| 2 | If `changeset_dir` is provided, `changeset.json` must exist at `{changeset_dir}/metadata/changeset.json` | Immediate fail |
| 3 | If `changeset_dir` is provided, `manifest.json` must exist at `{changeset_dir}/metadata/manifest.json` | Immediate fail |
| 4 | Every path in `artifacts` must exist as a real file under `management/` | Immediate fail |

---

## Mutation Worker Rules (e.g. code-worker)

In addition to Universal Rules:

| # | Rule | Failure Behavior |
|---|------|-----------------|
| M1 | `files_written` must be non-empty | Immediate fail |
| M2 | Each file in `files_written` must exist in test_repo (`_agent_repo`) | Immediate fail |
| M3 | Each file in `files_written` must have size > 0 bytes | Immediate fail |
| M4 | `changeset_dir` should contain changeset metadata | Required |
| M5 | At least one artifact must exist | Required via Universal Rule 1 |

**Why `files_written` is mandatory for Mutation Workers:**  
A mutation worker's purpose is to produce repo changes. Success without repo changes is a lie. The validation catches this.

---

## Validation Worker Rules (e.g. unity-worker)

In addition to Universal Rules:

| # | Rule | Failure Behavior |
|---|------|-----------------|
| V1 | `files_written` may be empty — this is expected | No fail |
| V2 | `artifacts` must be non-empty (at least one report/log) | Immediate fail (via Universal Rule 1) |
| V3 | Artifact file must have meaningful content (non-zero size) | Checked via filesystem existence |
| V4 | `changeset_dir` should contain changeset metadata | Required |

**Why `files_written` is allowed to be empty for Validation Workers:**  
A validation worker's purpose is to inspect, not to write. Its proof is the validation report, not a repo diff. But it must still produce a verifiable artifact — empty output is never acceptable.

---

## Decision Logic in validate_worker_output()

```
Worker reports success
│
├─ files_written non-empty?
│   ├─ YES → Check each file exists + non-empty in test_repo
│   └─ NO  → Check artifacts non-empty
│               ├─ YES → Continue
│               └─ NO  → FAIL (no output at all)
│
├─ changeset_dir provided?
│   ├─ YES → Check changeset.json + manifest.json exist
│   └─ NO  → Skip (some workers may not produce changeset)
│
├─ artifacts listed?
│   ├─ YES → Check each artifact file exists
│   └─ NO  → Already handled by first check
│
└─ All checks pass → VALID
```

---

## Why This Validation Exists

Before Sprint 10A, workers could report `{"success": True}` with no proof. The orchestrator blindly transitioned the ticket to `review`. This meant:

- A stub worker that did nothing would pass
- A worker that crashed silently could still claim success
- No verifiable audit trail

The validation closes this gap: **no real output = no success**.

---

## What This Validation Does NOT Check

| Not Checked | Reason |
|-------------|--------|
| Content correctness | That's QA's job, not validation |
| Compile status | Unity worker includes this in its report, but the orchestrator doesn't parse it |
| Semantic relevance | Whether the change actually addresses the ticket |
| Diff quality | Whether the modification is meaningful vs. trivial |
| Code style | Out of scope for output validation |

These are downstream concerns for QA and Review, not for `validate_worker_output()`.

---

## Failure Modes That Reach This Validation

| Scenario | Result |
|----------|--------|
| Worker crashes before writing files | `success=False` from worker, validation never runs |
| Worker writes files but forgets changeset | Validation fails on changeset check |
| Worker writes changeset but file is empty | Validation fails on size check |
| Worker returns `success=True` with empty `files_written` and empty `artifacts` | Validation fails immediately |
| Worker returns `success=True` with artifact path that doesn't exist | Validation fails on artifact existence |

---

## Adding New Worker Types

When a new worker is added (e.g. blender-worker, tripo-worker):

1. Classify it as Mutation Worker or Validation Worker (see `docs/worker-output-classes.md`)
2. Ensure its `execute()` function returns the standard result dict including `files_written` and `artifacts`
3. The existing `validate_worker_output()` handles both classes — no code change needed
4. Document the classification in the worker's contract and in `worker-capability-matrix.md`
