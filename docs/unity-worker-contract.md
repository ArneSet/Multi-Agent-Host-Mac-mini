# Unity Worker Contract

> **Sprint:** 10B (created), 12A (verified against code)  
> **Date:** 2026-03-20  
> **Status:** Active — verified against code  
> **Worker Classification:** limited validation output in test_repo  

---

## Purpose

The unity-worker performs **read-only validation and inspection** of the Unity project in test_repo. It invokes Unity CLI in batchmode to run health checks, compile verification, and structural validation. It does **not** mutate project content in Sprint 10B.

---

## Inputs

### Config (passed via `cfg`)

| Key | Type | Description |
|-----|------|-------------|
| `cfg["_agent_repo"]` | `str` | Absolute path to test_repo. Set by `dispatch_worker()`. **Only repo the worker may access.** |
| `cfg["management_root"]` | `str` | Absolute path to `management/` directory. |
| `cfg["artifacts_dir"]` | `str` | Relative dir under management_root for artifact files. |

### Ticket (passed via `ticket`)

| Key | Type | Required | Description |
|-----|------|:--------:|-------------|
| `ticket["id"]` | `str` | ✓ | Sanitized ticket ID. |
| `ticket["title"]` | `str` | ✓ | Short title. |
| `ticket["_body"]` | `str` | ✓ | **Primary specification.** Contains `validation_type:` directive. |
| `ticket["description"]` | `str` | ○ | Legacy fallback only. |
| `ticket["branch"]` | `str` | ✓ | Target branch in test_repo. |
| `ticket["worker"]` | `str` | ✓ | Must be `unity-worker`. |

### Flags

| Flag | Type | Description |
|------|------|-------------|
| `dry_run` | `bool` | If `True`: validate inputs, report what would happen, run nothing. |

---

## Validation Types (Sprint 10B)

| Type | Description |
|------|-------------|
| `project-health` | Open project in batchmode, verify clean exit. Reports compile status. |

Future validation types (not Sprint 10B):
- `compile-check` — targeted C# compilation verification
- `asset-validation` — asset database integrity check

---

## Allowed Actions

1. **Read** files in `cfg["_agent_repo"]` (test_repo)
2. **Invoke** Unity CLI in batchmode with a strict argument whitelist
3. **Parse** Unity log output for compile errors, warnings, project health
4. **Create** changeset structure under `management/changeset/ticket-{id}/`
5. **Write** validation report as artifact to `management/artifacts/`
6. **Return** standardized result dict

---

## Forbidden Actions

| Action | Reason |
|--------|--------|
| Access `prod_repo` in any way | Agent boundary violation |
| Access protected branches (`main`, `master`, `develop`) | Branch safety |
| Write to `cfg["_agent_repo"]` (test_repo) | Read-only validation in Sprint 10B |
| Execute arbitrary shell commands | No free shell autonomy |
| Pass unsanitized arguments to Unity CLI | Injection prevention |
| Network access | No network from worker |
| Modify Unity project files, scenes, prefabs | Not a mutation worker in 10B |
| Side effects outside test_repo and management/ | Containment rule |

---

## Unity CLI Invocation Rules

### Binary Path Resolution

The worker resolves the Unity Editor binary from `ProjectSettings/ProjectVersion.txt` in test_repo:
```
/Applications/Unity/Hub/Editor/{version}/Unity.app/Contents/MacOS/Unity
```

### Allowed CLI Arguments (Whitelist)

| Argument | Purpose |
|----------|---------|
| `-batchmode` | Required for headless execution |
| `-nographics` | No GPU rendering |
| `-projectPath <path>` | Must be `_agent_repo` (test_repo) |
| `-quit` | Exit after execution |
| `-logFile <path>` | Capture output to management/ log |

### Forbidden CLI Arguments

| Argument | Reason |
|----------|--------|
| `-executeMethod` | No arbitrary C# execution in Sprint 10B |
| `-buildTarget` | No build execution |
| `-importPackage` | No package modification |
| `-createProject` | No project creation |
| Any argument not in whitelist | Deny-by-default |

---

## Expected Outputs

### Return Value

```python
{
    "success": bool,        # True if validation completed without errors
    "message": str,         # Human-readable result summary
    "artifacts": list,      # List of artifact file paths (relative to management_root)
    "changeset_dir": str,   # Path to changeset/ticket-{id}/ (relative to management_root)
    "files_written": list,  # Empty for validation-only (no test_repo writes in 10B)
}
```

### File Outputs

1. **Validation report:** `management/artifacts/{id}_unity_result.md`
2. **Unity log:** `management/changeset/ticket-{id}/metadata/unity_log.txt`
3. **Changeset metadata:** `management/changeset/ticket-{id}/metadata/changeset.json`
4. **Changeset manifest:** `management/changeset/ticket-{id}/metadata/manifest.json`

---

## Project Structure Validation

Before any Unity CLI invocation, the worker validates:
1. `Assets/` directory must exist under `_agent_repo`
2. `ProjectSettings/` directory must exist under `_agent_repo`

If either is missing, the worker fails immediately with a clear error message.

---

## Path Containment Rules

1. `cfg["_agent_repo"]` must resolve to a real path via `Path.resolve()`
2. `cfg["_agent_repo"]` must NOT resolve to `prod_repo`
3. Unity `-projectPath` must be exactly the resolved `_agent_repo`
4. Log files must be written under `management/` only
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
| Unity Editor binary not found | Fail with path detail |
| `ProjectVersion.txt` missing or unparseable | Fail with detail |
| Unity batchmode exit code != 0 | Report as validation failure |
| Unity batchmode timeout (>120s) | Kill process, fail with timeout |
| Unity log contains compile errors | Report as validation failure with error detail |
| Unknown `validation_type` | Fail with supported types list |

---

## Timeout Rules

| Operation | Timeout | Action on Timeout |
|-----------|---------|-------------------|
| Unity batchmode | 120 seconds | Kill process, return failure |

---

## Ticket Format Rules

See `docs/ticket-format-rules.md` for general format.

Worker reads `_body` for:
```
validation_type: project-health
```

---

## Audit Expectations

- All actions logged via `write_log()`
- Changeset metadata provides machine-readable audit
- Unity log captured in full under changeset metadata
- Artifact summary provides human-readable validation report
