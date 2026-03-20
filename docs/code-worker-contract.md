# Code Worker Contract

> **Sprint:** 10A (created), 12A (verified against code)  
> **Date:** 2026-03-20  
> **Status:** Active — verified against code  
> **Worker Classification:** limited real output in test_repo  

---

## Purpose

The code-worker is the first HYBRIS worker to produce **real, verifiable output** in the test_repo. This contract defines all inputs, outputs, permissions, and constraints.

---

## Inputs

### Config (passed via `cfg`)

| Key | Type | Description |
|-----|------|-------------|
| `cfg["_agent_repo"]` | `str` | Absolute path to test_repo. **Only writable repo.** Set by `dispatch_worker()`. |
| `cfg["management_root"]` | `str` | Absolute path to `management/` directory. |
| `cfg["artifacts_dir"]` | `str` | Relative dir under management_root for artifact files. |

### Ticket (passed via `ticket`)

| Key | Type | Required | Description |
|-----|------|:--------:|-------------|
| `ticket["id"]` | `str` | ✓ | Sanitized ticket ID. |
| `ticket["title"]` | `str` | ✓ | Short title. |
| `ticket["_body"]` | `str` | ✓ | **Primary specification.** Content after YAML frontmatter `---`. Contains `target_file:` directive and file content. |
| `ticket["description"]` | `str` | ○ | **Legacy fallback only.** Single-line frontmatter value. Used only if `_body` is empty (unit-test compat). |
| `ticket["branch"]` | `str` | ✓ | Target branch in test_repo. |
| `ticket["worker"]` | `str` | ✓ | Must be `code-worker`. |

### Flags

| Flag | Type | Description |
|------|------|-------------|
| `dry_run` | `bool` | If `True`: validate inputs, report what would happen, write nothing. |

---

## Allowed Actions

1. **Read** files anywhere in `cfg["_agent_repo"]`
2. **Create or modify** files in `cfg["_agent_repo"]` — only within ticket scope
3. **Create** changeset structure under `management/changeset/ticket-{id}/`
4. **Write** artifact summary to `management/artifacts/{id}_code_result.md`
5. **Return** standardized result dict

---

## Forbidden Actions

| Action | Reason |
|--------|--------|
| Access `prod_repo` in any way | Agent boundary violation |
| Access protected branches (`main`, `master`, `develop`) | Branch safety |
| Write outside `cfg["_agent_repo"]` and `cfg["management_root"]` | Path containment |
| Import or call `dispatch_worker`, `execute_promotion`, `process_ticket` | Execution boundary |
| Execute shell commands (`subprocess`, `os.system`, `os.popen`) | No shell exec from worker |
| Network access (`urllib`, `http`, `socket`) | No network from worker |
| Delete existing files in test_repo | Preservation rule (create/modify only) |
| Write to paths containing `..` or absolute paths outside containment | Path traversal prevention |

---

## Expected Outputs

### Return Value

```python
{
    "success": bool,       # True if real output was produced
    "message": str,        # Human-readable result summary
    "artifacts": list,     # List of artifact file paths (relative to management_root)
    "changeset_dir": str,  # Path to changeset/ticket-{id}/ (relative to management_root)
    "files_written": list, # List of files created/modified in test_repo (relative paths)
}
```

### File Outputs

1. **test_repo file(s):** At least one file created or modified in `cfg["_agent_repo"]`
2. **Changeset metadata:** `management/changeset/ticket-{id}/metadata/changeset.json`
3. **Changeset manifest:** `management/changeset/ticket-{id}/metadata/manifest.json`
4. **Artifact summary:** `management/artifacts/{id}_code_result.md`

### Changeset JSON Schema

**changeset.json:**
```json
{
  "ticket_id": "TICKET-ID",
  "worker_type": "code-worker",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "status": "completed|failed",
  "files_written": [
    {"path": "relative/to/test_repo", "action": "created|modified", "size_bytes": 123}
  ]
}
```

**manifest.json:**
```json
{
  "ticket_id": "TICKET-ID",
  "worker_type": "code-worker",
  "timestamp": "ISO-8601",
  "files_added": ["relative/path"],
  "files_modified": [],
  "files_deleted": [],
  "artifact_summary": "artifacts/TICKET-ID_code_result.md"
}
```

---

## Path Containment Rules

1. `cfg["_agent_repo"]` must resolve to a real path via `Path.resolve()`
2. Every file written must resolve to a path **under** the resolved `_agent_repo`
3. Validation: `written_path.resolve().relative_to(agent_repo_resolved)` must not raise
4. No symlink following outside containment
5. No `..` components in any constructed path

---

## Failure Modes

The worker must return `{"success": False, ...}` (never crash) for:

| Failure | Behavior |
|---------|----------|
| `_agent_repo` missing or not a directory | Fail with clear message |
| `_agent_repo` resolves to prod_repo | Fail immediately |
| `ticket["branch"]` is a protected branch | Fail immediately |
| `ticket["id"]` missing or invalid | Fail immediately |
| Target file path escapes containment | Fail immediately |
| File write fails (permission, disk) | Fail with OS error detail |
| Empty output (no files written) | Fail — never report success with zero output |

---

## Ticket Format Rules

The ticket parser (`parse_ticket`) is **not a real YAML parser**. It uses regex key-value matching.

**Binding rules:**
- Frontmatter: simple `key: value` pairs only
- No YAML block scalars (`description: |`, `description: >`)
- `---` strictly separates frontmatter from body
- Worker reads task specification from `_body` (after frontmatter)
- `description` in frontmatter is a short single-line only
- See `docs/ticket-format-rules.md` for full format specification

---

## Audit Expectations

- All actions are logged via the existing `write_log()` mechanism
- Changeset metadata provides a machine-readable audit of all file operations
- Artifact summary provides a human-readable record

---

## What This Contract Does NOT Cover

- Git operations (commit, push, branch creation) — deferred
- Multi-file complex changes — single-file reference changes only
- C# compilation or syntax checking — deferred to later sprint
- Interaction with Unity Editor — out of scope
- Network or API calls — forbidden
