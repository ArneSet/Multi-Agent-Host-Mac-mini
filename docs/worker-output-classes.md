# Worker Output Classes

> **Sprint:** 10C — Worker Output Model Hardening  
> **Date:** 2026-03-19  
> **Status:** Canonical — binding for all workers and orchestrator logic  

---

## Why This Document Exists

After Sprint 10A (code-worker) and 10B (unity-worker), the system has two fundamentally different worker types with different output models. The orchestrator's `validate_worker_output()` must handle both correctly without becoming permissive. This document defines the boundary.

---

## Mutation Worker

**Definition:** A worker that creates or modifies files in test_repo as its primary output.

**Current Example:** `code-worker`

### Characteristics

| Property | Rule |
|----------|------|
| Writes to test_repo | Yes — primary purpose |
| `files_written` in result | **Required, non-empty** |
| Changeset metadata | Required (`changeset.json` + `manifest.json`) |
| Artifact summary | Required |
| `_agent_repo` usage | Must use exclusively, never `game_repo_root` |
| Repo-diff verifiable | Yes — files exist and are non-empty in test_repo |

### Minimum Proof Requirements

For `validate_worker_output()` to pass:

1. `files_written` must be non-empty
2. Each file in `files_written` must exist in test_repo and have size > 0
3. `changeset_dir` must be provided and contain `changeset.json` + `manifest.json`
4. At least one artifact file must exist

### Failure Conditions

- `files_written` empty → **immediate fail**
- Any listed file missing from test_repo → **immediate fail**
- Any listed file is 0 bytes → **immediate fail**
- Changeset metadata missing → **immediate fail**

### What a Mutation Worker Is NOT

- Not a "free repo author" — writes are scoped to ticket, path-contained, single-file (Sprint 10A scope)
- Not autonomous — receives work from ticket, does not self-assign
- Not trusted to be correct — output must pass validation, QA, and review before promotion
- Not capable of deletion (create/modify only in current scope)

---

## Validation Worker

**Definition:** A worker that inspects or validates the state of test_repo without writing to it. Its output is reports, logs, and artifacts under `management/`.

**Current Example:** `unity-worker`

### Characteristics

| Property | Rule |
|----------|------|
| Writes to test_repo | **No** — read-only inspection |
| `files_written` in result | Empty list (`[]`) — this is correct and expected |
| Changeset metadata | Required (`changeset.json` + `manifest.json`) |
| Artifact/Report | **Required, non-empty** — this is the primary output |
| `_agent_repo` usage | Must use exclusively for project path |
| Repo-diff verifiable | No — but report content is verifiable |

### Minimum Proof Requirements

For `validate_worker_output()` to pass:

1. `artifacts` must be non-empty (at least one report file)
2. Each artifact file must exist under `management/`
3. `changeset_dir` should be provided and contain `changeset.json` + `manifest.json`
4. `files_written` may be empty — this is the expected case

### Failure Conditions

- Both `files_written` and `artifacts` empty → **immediate fail**
- Artifact file listed but not on disk → **immediate fail**
- Changeset metadata declared but missing → **immediate fail**

### What a Validation Worker Is NOT

- Not a "free read-only agent" — executes specific validation types from ticket, not arbitrary inspection
- Not autonomous — does not self-assign work or decide scope
- Not a mutation worker in disguise — if a future validation worker needs to write to test_repo, it must be reclassified as a Mutation Worker and meet those stricter requirements
- Not trusted to be correct — validation results must still pass QA and review

---

## Classification Rule

The distinction is based on **whether the worker writes to test_repo**:

| Question | Answer → Class |
|----------|---------------|
| Does the worker create/modify files in test_repo? | Yes → **Mutation Worker** |
| Does the worker only read test_repo and produce reports? | Yes → **Validation Worker** |
| Does the worker do both? | → **Mutation Worker** (stricter rules apply) |

A worker that writes even one file to test_repo is a Mutation Worker and must meet all Mutation Worker requirements.

---

## Current Worker Classification

| Worker | Class | Status |
|--------|-------|--------|
| `code-worker` | Mutation Worker | limited real output in test_repo |
| `unity-worker` | Validation Worker | limited validation output, read-only |
| `blender-worker` | — | Stub (not classified yet) |
| `tripo-worker` | — | Stub (not classified yet) |

---

## No-Go Interpretations

These interpretations are explicitly forbidden:

- "Validation Workers can skip output validation" — **No.** They must still produce verifiable artifacts.
- "Mutation Workers can report success without files_written" — **No.** Empty `files_written` is an immediate validation failure.
- "A worker can be both classes depending on the ticket" — **No.** A worker has one class. If it needs to do both, it follows Mutation Worker rules.
- "Validation Workers have lower audit standards" — **No.** Same changeset/artifact requirements, different content type.
- "Workers can self-select their class at runtime" — **No.** Class is a design-time property documented in the worker contract.
