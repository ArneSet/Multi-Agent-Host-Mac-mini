# QA Worker Classes

**Status**: Sprint 11A — QA Gate Hardening
**Date**: 2026-03-19
**Purpose**: Define how QA treats Mutation Workers and Validation Workers differently

## Core Principle

QA is a **technical gate**. It does not replace creative Review.
QA checks whether worker output is **structurally sound and complete**.
Review checks whether worker output is **correct and acceptable**.

QA ergänzt Review, ersetzt es nicht.

## Two QA Classes

Workers fall into exactly two classes. QA must treat them differently because their output models are fundamentally different.

### Mutation Worker QA

**Applies to**: code-worker (and any future worker that writes to test_repo)

A Mutation Worker's purpose is to produce **real file changes** in test_repo.
If a Mutation Worker reports success but no file was changed, that is a false positive.

**QA must verify**:

| # | Check | Severity | Current Implementation |
|---|-------|----------|----------------------|
| MQ1 | `files_written` non-empty | blocker | `validate_worker_output()` — U1 |
| MQ2 | Each file in `files_written` exists in test_repo | blocker | `validate_worker_output()` — M2 |
| MQ3 | Each file has size > 0 bytes | blocker | `validate_worker_output()` — M3 |
| MQ4 | `changeset.json` exists | blocker | `validate_worker_output()` — U2 |
| MQ5 | `manifest.json` exists | blocker | `validate_worker_output()` — U3 |
| MQ6 | Artifact report exists | blocker | `validate_worker_output()` — U4 |
| MQ7 | File path is within test_repo | blocker | code-worker path containment |
| MQ8 | `action` field plausible ("created" or "modified") | advisory | NOT checked by QA today |
| MQ9 | `files_added` / `files_modified` consistent with `action` | advisory | NOT checked by QA today |
| MQ10 | Content is non-trivial (not just whitespace) | advisory | NOT checked by QA today |

**Known limitation**: QA does not verify whether a modify actually changed content. It verifies the file exists and is non-empty. This is acceptable for now but must remain documented as a boundary.

### Validation Worker QA

**Applies to**: unity-worker (and any future worker that produces reports without repo writes)

A Validation Worker's purpose is to produce a **validation report** without modifying test_repo.
If a Validation Worker writes to test_repo, that is a boundary violation.

**QA must verify**:

| # | Check | Severity | Current Implementation |
|---|-------|----------|----------------------|
| VQ1 | `artifacts` non-empty | blocker | `validate_worker_output()` — U1 |
| VQ2 | Each artifact file exists | blocker | `validate_worker_output()` — U4 |
| VQ3 | `changeset.json` exists | blocker | `validate_worker_output()` — U2 |
| VQ4 | `manifest.json` exists | blocker | `validate_worker_output()` — U3 |
| VQ5 | `files_written` is empty | advisory | NOT enforced by QA today |
| VQ6 | Validation result interpretable (pass/fail status in report) | advisory | NOT checked by QA today |
| VQ7 | No test_repo modifications detected | advisory | NOT checked by QA today |

**Known limitation**: QA does not enforce that a Validation Worker actually left test_repo untouched. The worker itself enforces this (`files_written: []`), but QA does not independently verify it. This is acceptable because the worker is trusted internal code, but the boundary must remain documented.

## Classification Rule

The worker class is determined by the worker type, not by the output.

| Worker Type | Class | Rationale |
|-------------|-------|-----------|
| code-worker | Mutation | Writes files to test_repo |
| unity-worker | Validation | Reads test_repo, produces reports only |
| blender-worker | (stubbed) | Expected: Mutation |
| tripo-worker | (stubbed) | Expected: Mutation |

**Important**: A worker's class is set by its contract, not inferred at runtime.
`validate_worker_output()` currently handles this implicitly through OR logic (`files_written OR artifacts`).
There is no explicit worker class field in the ticket or result.

## Current Implementation State

**What exists today** (verified against orchestrator.py lines 562–615):
- Single `validate_worker_output()` function handles both classes
- Checks `files_written OR artifacts` non-empty (U1)
- If `files_written` present: checks file existence and non-emptiness in test_repo (M2, M3)
- Checks changeset metadata existence (U2, U3)
- Checks artifact file existence (U4)
- Returns `{"valid": bool, "reason": str|None, "detail": str}`

**What does NOT exist today**:
- No explicit worker class parameter in validation
- No `blocked` or `inconclusive` return states
- No content plausibility checks
- No enforcement that Validation Workers have empty `files_written`
- No check that `action` field matches actual filesystem state

**Gap assessment**: The implicit handling works correctly for both current workers. Explicit class-awareness in `validate_worker_output()` is desirable but not blocking. The OR logic is structurally equivalent to class-aware checking for the two current workers.

## What QA Does NOT Do

- QA does not assess creative quality
- QA does not decide whether output is "good enough"
- QA does not replace human Review
- QA does not auto-promote
- QA does not read or parse file content for semantic correctness
- QA does not run tests or build processes

Review remains mandatory. Promotion remains manual.
