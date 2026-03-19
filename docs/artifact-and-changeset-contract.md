# Artifact and ChangeSet Contract

**Version**: 1.0
**Date**: 2026-03-17
**Purpose**: Define what artifacts are produced by workers and how changesets are structured

## Artifact Definition

### What is an Artifact?
An **artifact** is the tangible output produced by a worker when processing a ticket. Artifacts must be:
- **Identifiable**: Clearly linked to the originating ticket
- **Verifiable**: QA can confirm correctness
- **Promotable**: Can be moved between environments
- **Auditable**: Changes are traceable

### Artifact Types

#### Code Artifact
**Produced by**: code-worker
**Content**: Modified source code files
**Format**: Standard file system files (.py, .cs, .md, etc.)
**Location**: Within worker workspace
**Identification**: Ticket ID in commit message + file paths

#### Asset Artifact
**Produced by**: unity-worker, blender-worker, tripo-worker
**Content**: Modified or generated assets (models, textures, scenes)
**Format**: Unity assets, Blender files, FBX, etc.
**Location**: Within worker workspace Assets/ directory
**Identification**: Ticket ID in metadata + file paths

## ChangeSet Definition

### What is a ChangeSet?
A **changeset** is the complete set of changes made to produce an artifact, including:
- Modified files
- New files
- Deleted files
- Metadata about the changes

### ChangeSet Structure
```
changeset/
├── ticket-{TICKET_ID}/
│   ├── artifact/
│   │   ├── {files produced by worker}
│   │   └── manifest.json
│   ├── metadata/
│   │   ├── changeset.json
│   │   ├── qa-report.json (after QA)
│   │   └── review-report.json (after review)
│   └── audit/
│       └── {audit logs}
```

### ChangeSet Metadata Files

#### manifest.json
```json
{
  "ticket_id": "REF-001",
  "worker_type": "code-worker",
  "timestamp": "2026-03-17T10:30:00Z",
  "files_modified": ["code_worker/utils.py"],
  "files_added": ["tests/test_log_debug.py"],
  "files_deleted": [],
  "artifact_root": "changeset/ticket-REF-001/artifact/"
}
```

#### changeset.json
```json
{
  "ticket_id": "REF-001",
  "worker_type": "code-worker",
  "worker_version": "1.0.0",
  "execution_id": "exec-20260317103000-abc123",
  "start_time": "2026-03-17T10:30:00Z",
  "end_time": "2026-03-17T10:30:05Z",
  "status": "completed",
  "exit_code": 0,
  "changes": {
    "modified": [
      {
        "path": "code_worker/utils.py",
        "checksum_before": "abc123...",
        "checksum_after": "def456...",
        "diff_summary": "+15 lines, -0 lines"
      }
    ],
    "added": [
      {
        "path": "tests/test_log_debug.py",
        "checksum": "ghi789...",
        "size_bytes": 1024
      }
    ],
    "deleted": []
  }
}
```

## Identification and Linking

### Ticket-to-Artifact Linking
- **Primary Key**: Ticket ID (e.g., "REF-001")
- **Secondary Key**: Execution ID (timestamp-based UUID)
- **File Path**: `changeset/ticket-{TICKET_ID}/`
- **Commit Message**: Always includes ticket ID

### Artifact Verification
QA must verify:
- All required files are present
- File contents match expected changes
- No unexpected files modified
- Checksums match (if provided)

### Promotion Readiness
An artifact is promotion-ready when:
- QA report exists with status "passed"
- Review report exists with decision "approved"
- All files are present and verified
- ChangeSet metadata is complete

## Reference Flow Contract

For Sprint 9A Reference Flow (REF-001):

### Expected Artifact
- **Type**: Code Artifact
- **Files**: `code_worker/utils.py` (modified), `tests/test_log_debug.py` (new)
- **Location**: `changeset/ticket-REF-001/artifact/`
- **Verification**: Unit test passes, function exists and works

### ChangeSet Requirements
- Exactly 1 file modified
- Exactly 1 file added
- 0 files deleted
- QA and Review reports generated
- All metadata files present

### Success Criteria
- Artifact directory exists and contains expected files
- Unit tests pass: `python -m pytest tests/test_utils.py::test_log_debug`
- Function importable: `from code_worker.utils import log_debug`
- No breaking changes to existing functionality</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/artifact-and-changeset-contract.md