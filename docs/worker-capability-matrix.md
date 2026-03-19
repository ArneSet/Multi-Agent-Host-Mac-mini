# Worker Capability Matrix

**Status**: Sprint 10C — Worker Output Model Hardened
**Date**: 2026-03-19
**Purpose**: Honest assessment of worker operational readiness

## Worker Classes

Workers are classified into two formal classes (see `docs/worker-output-classes.md`):
- **Mutation Workers**: Write files to test_repo. Changeset must contain `files_written` with `action` and non-empty `files_added` or `files_modified`.
- **Validation Workers**: Read-only. No test_repo writes. Changeset must contain `artifacts` with validation reports.

## Capability Levels

| Level | Description | Operational Status |
|-------|-------------|-------------------|
| **PRODUCTION** | Fully operational, tested, monitored | None |
| **OPERATIONAL** | Real output in test_repo, validated, changeset produced | code-worker |
| **VALIDATION** | Read-only validation via CLI, report output, no repo writes | unity-worker |
| **DEVELOPMENT** | Basic functionality exists | — |
| **STUBBED** | Interface exists, no real implementation | blender-worker, tripo-worker |
| **MISSING** | Not implemented | - |

## Worker Assessment

### code-worker
**Status**: OPERATIONAL ✅ (Sprint 10A+10C — Create + Modify Verified)
**Class**: Mutation Worker
**Capabilities**:
- ✅ Creates files in test_repo from ticket body
- ✅ Modifies existing files in test_repo (verified Sprint 10C)
- ✅ Path containment enforcement (no escape from agent_repo)
- ✅ Changeset metadata production (changeset.json + manifest.json)
- ✅ Correct `action` field: "created" vs "modified"
- ✅ Correct manifest: `files_added` vs `files_modified`
- ✅ Artifact summary output
- ✅ Output validation by orchestrator post-execution
- ✅ Failure handling with standardized error returns
- ✅ Protected branch rejection
- ✅ prod_repo access rejection
- ✅ Content size cap (64KB)
**Limitations**:
- No shell/command execution from ticket content
- No network access
- No file deletion (create/modify only)
- Single file per ticket
- Content must be specified in ticket body (`_body` field)
**Security Boundaries**:
- Never writes to prod_repo
- Never targets protected branches (main/master/develop)
- Path containment via Path.relative_to()
- Ticket ID format validation
- No dynamic code execution
**Reference Flows**:
- sprint-10a-ref-001: create path (BuildVersionInfo.cs created)
- sprint-10c-ref-001: modify path (BuildVersionInfo.cs modified to v0.2.0-alpha)

### unity-worker
**Status**: VALIDATION ✅ (Sprint 10B — Limited Validation Output)
**Class**: Validation Worker
**Capabilities**:
- ✅ Unity batchmode invocation against test_repo
- ✅ Project health validation (open, compile, exit)
- ✅ Compile error detection from Unity log
- ✅ Validation report artifact output
- ✅ Changeset metadata production
- ✅ Path containment to test_repo only
- ✅ Unity Editor version auto-resolution from ProjectVersion.txt
- ✅ Timeout protection (120s)
- ✅ prod_repo rejection
- ✅ Protected branch rejection
**Limitations**:
- No test_repo writes (read-only validation)
- No scene/prefab mutation
- No asset generation
- No -executeMethod (no custom C# execution)
- No build execution
- Single validation type: project-health
**Security Boundaries**:
- Never writes to test_repo (validation-only in 10B)
- Never accesses prod_repo
- CLI argument whitelist (deny-by-default)
- No arbitrary shell commands
**Reference Flows**:
- unity-10b-ref-001: project-health validation (initial)
- unity-10c-followup-001: project-health validation after code-worker modify (confirmed zero compile errors)

### blender-worker
**Status**: STUBBED ❌ (Not Reference Flow Ready)
**Capabilities**:
- ❌ Blender file processing
- ❌ 3D model manipulation
- ❌ Rendering
**Limitations**:
- No Blender installation
- No processing pipeline
**Reference Flow Ready**: No

### tripo-worker
**Status**: STUBBED ❌ (Not Reference Flow Ready)
**Capabilities**:
- ❌ Tripo API integration
- ❌ 3D generation
- ❌ Model processing
**Limitations**:
- No API credentials
- No processing pipeline
**Reference Flow Ready**: No

## Reference Flow Decision

**Operational Workers**: code-worker (Mutation), unity-worker (Validation)
**Rationale**:
- code-worker: Mutation Worker with real file output in test_repo — both create and modify verified
- unity-worker: Validation Worker with real Unity CLI invocation — read-only, report output only
**Cross-validation**: Unity follow-up after code-worker modify confirms no compilation breakage
- Both produce verifiable changeset metadata and artifact reports
- Output validation by orchestrator prevents silent success

## Sprint 10A Reference Run

**Ticket**: sprint-10a-ref-001
**File Created**: `Assets/Scripts/Utilities/BuildVersionInfo.cs` (1565 bytes)
**Pipeline**: inbox → ready → active → code-worker → validation PASSED → review
**Changeset**: `changeset/ticket-sprint-10a-ref-001/metadata/`
**Artifact**: `artifacts/sprint-10a-ref-001_code_result.md`
**Security**: No prod_repo access, no protected branches, path contained

## Sprint 10B Reference Run

**Ticket**: unity-10b-ref-001
**Validation**: project-health (batchmode open, compile check, clean exit)
**Pipeline**: inbox → ready → active → unity-worker → validation PASSED → review
**Unity Exit Code**: 0
**Compile Errors**: 0
**Execution Time**: ~6 seconds
**Changeset**: `changeset/ticket-unity-10b-ref-001/metadata/`
**Artifact**: `artifacts/unity-10b-ref-001_unity_result.md`
**Unity Log**: `changeset/ticket-unity-10b-ref-001/metadata/unity_log.txt` (413 lines)
**Security**: No prod_repo access, no test_repo writes, no protected branches

## Future Worker Readiness

### Next Priorities
1. **blender-worker**: Blender installation, basic processing pipeline
2. **tripo-worker**: API integration, model generation workflow
3. **unity-worker expansion**: -executeMethod for targeted validation scripts
4. **code-worker expansion**: multi-file output, safe modify path

### Infrastructure Requirements
- Blender installation and Python API
- Tripo API credentials and rate limiting
- Cross-worker testing environment</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/worker-capability-matrix.md