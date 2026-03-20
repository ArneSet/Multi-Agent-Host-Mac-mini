# Worker Output Format

> **Sprint:** 12A — Worker Contract Hardening  
> **Date:** 2026-03-20  
> **Status:** Active — verified against code  

---

## Canonical Return Format

Every worker's `execute(cfg, ticket, dry_run)` must return a dict with exactly these fields:

```python
{
    "success": bool,            # True if the worker completed its task
    "message": str,             # Human-readable result summary
    "artifacts": list[str],     # Artifact file paths (relative to management_root)
    "changeset_dir": str|None,  # Changeset directory (relative to management_root), or None
    "files_written": list[str], # Files created/modified in test_repo (relative paths), or []
}
```

All five fields are **required** in every return — success, failure, and dry-run paths.

---

## Field Semantics

### `success`

- `True`: worker completed its intended task (mutation or validation)
- `False`: worker failed — reason in `message`
- Must never be `True` if no real work was done (enforced by `validate_worker_output()`)

### `message`

- Prefixed with worker name: `"code-worker created 'path' in test_repo for ticket 'X'"`
- On failure, prefixed: `"code-worker FAILED: reason"`
- On dry-run, prefixed: `"[DRY-RUN] code-worker would ..."`

### `artifacts`

- List of artifact file paths relative to `management_root`
- Typically: `["artifacts/{ticket_id}_{worker_type}_result.md"]`
- Empty list `[]` on failure or dry-run

### `changeset_dir`

- Path to `changeset/ticket-{id}/` relative to `management_root`
- Contains `metadata/changeset.json` and `metadata/manifest.json`
- `None` on failure, dry-run, or stub workers

### `files_written`

- List of files created/modified in `test_repo`, relative to repo root
- Empty `[]` for validation-only workers (e.g. unity-worker)
- Empty `[]` on failure, dry-run, or stub workers
- Used by `validate_worker_output()` to determine `worker_class` (mutation vs validation)

---

## Worker Class Determination

`validate_worker_output()` classifies workers based on their output:

| Condition | Class | Example |
|-----------|-------|---------|
| `files_written` is non-empty | `mutation` | code-worker |
| `files_written` is empty, `artifacts` non-empty | `validation` | unity-worker |
| Both empty | **invalid** — validation fails | — |

---

## Consumers

| Consumer | Fields Used |
|----------|-------------|
| `process_ticket()` | `success`, `message`, `artifacts` |
| `validate_worker_output()` | `files_written`, `artifacts`, `changeset_dir` |
| `create_review_package()` | artifacts (from disk, not from return) |
| `create_qa_result()` | indirectly — QA is per-ticket, not per-result |

---

## Failure Returns

Workers must return `{"success": False, ...}` with the full 5-field format.
Workers must **never raise exceptions** — all errors are captured in the return dict.

`dispatch_worker()` error returns (allowlist failure, import failure, missing execute)
also use the same 5-field format with `changeset_dir=None` and `files_written=[]`.

---

## Stub Workers

Stub workers (blender-worker, tripo-worker) return the full 5-field format with:
- `changeset_dir: None`
- `files_written: []`
- `artifacts`: non-empty (they write a stub artifact file)

This means stub workers pass `validate_worker_output()` as `validation` class.

---

## Base Interface

See `workers/base_worker.py` for the interface declaration.
See individual worker contracts for full per-worker specifications:
- `docs/code-worker-contract.md`
- `docs/unity-worker-contract.md`
