# Code Worker Modify Reference Ticket — Sprint 10C

> **Date:** 2026-03-19  
> **Purpose:** Define and document the second reference proof: modify instead of create  

---

## Context

Sprint 10A proved `create` — the code-worker produced a new file (`BuildVersionInfo.cs`) in test_repo.

Sprint 10C proves `modify` — the code-worker changes an existing file and the pipeline correctly identifies this as a modification.

---

## Target File

**File:** `Assets/Scripts/Utilities/BuildVersionInfo.cs`  
**Created by:** Sprint 10A ticket `sprint-10a-ref-001`  
**Current content:** Static build metadata class with Version `0.1.0-alpha`, BuildDate `2026-03-18`

---

## Modification

Update the version constants to reflect the Sprint 10C milestone:

| Field | Before | After |
|-------|--------|-------|
| `Version` | `"0.1.0-alpha"` | `"0.2.0-alpha"` |
| `BuildDate` | `"2026-03-18"` | `"2026-03-19"` |
| `TicketId` | `"sprint-10a-ref-001"` | `"sprint-10c-ref-001"` |
| Header comment | `Ticket: sprint-10a-ref-001` | `Ticket: sprint-10c-ref-001` |

---

## Why This Is a Good Modify Target

- Small, reversible change (version bump)
- Same file structure — no structural refactoring
- Clearly verifiable diff
- Cannot break Unity project (static constants only)
- File already exists and is known-good
- Within the safe `Assets/Scripts/Utilities/` boundary

---

## Expected Changeset Behavior

| Field | Expected Value |
|-------|---------------|
| `changeset.json → files_written[0].action` | `"modified"` |
| `manifest.json → files_added` | `[]` (empty) |
| `manifest.json → files_modified` | `["Assets/Scripts/Utilities/BuildVersionInfo.cs"]` |
| Artifact summary | `File modified:` (not `File created:`) |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| File doesn't exist at run time | Worker checks `target_path.exists()` before deciding action |
| Overwrite destroys good content | Full content specified in ticket body — atomic replacement, not patch |
| Content identical to existing | Acceptable — validation checks existence/non-empty, not diff content. Content correctness is QA. |
| Path escape | Same containment rules as create path |
