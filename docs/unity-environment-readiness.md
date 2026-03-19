# Unity Environment Readiness

> **Sprint:** 10B  
> **Date:** 2026-03-19  
> **Status:** Verified — batchmode functional  

---

## System

| Item | Value |
|------|-------|
| Host | Mac mini M4 |
| OS | macOS (Apple Silicon) |
| Unity Hub | Installed at `/Applications/Unity Hub.app/` |

## Installed Unity Editors

| Version | Path | Project Match |
|---------|------|:------------:|
| 6000.3.10f1 | `/Applications/Unity/Hub/Editor/6000.3.10f1/Unity.app/Contents/MacOS/Unity` | ✅ matches test_repo |
| 6000.3.11f1 | `/Applications/Unity/Hub/Editor/6000.3.11f1/Unity.app/Contents/MacOS/Unity` | — |

## Project Version

- File: `repos/hybris-test/ProjectSettings/ProjectVersion.txt`
- Content: `m_EditorVersion: 6000.3.10f1`
- Match: Editor 6000.3.10f1 is installed and callable

## Batchmode Test

| Check | Result |
|-------|--------|
| Binary exists and is executable | ✅ |
| `-version` returns clean output | ✅ `6000.3.10f1` |
| `-batchmode -nographics -quit` | ✅ Clean exit |
| License check | ✅ No license blockers |
| "Exiting batchmode successfully now!" | ✅ Present in log |
| Compile errors | ✅ None |
| Execution time | ~6 seconds |

## Unity CLI: Not in PATH

`unity` is not in the system PATH. The worker resolves the binary from `ProjectVersion.txt` and the Hub Editor install path. This is by design — no PATH dependency.

## Known Constraints

- Unity Editor must be installed via Unity Hub at the standard macOS path
- The editor version must match `ProjectVersion.txt` in the project
- No custom editor scripts are invoked in Sprint 10B (no `-executeMethod`)
- Batchmode timeout is 120 seconds

## Risks Assessed

| Risk | Status | Mitigation |
|------|--------|------------|
| Editor not installed | ✅ Mitigated | Worker checks binary existence before invocation |
| Version mismatch | ✅ Mitigated | Worker reads `ProjectVersion.txt` and resolves matching editor |
| License blockade | ✅ Verified clear | Batchmode connects/disconnects licensing cleanly |
| Timeout | ✅ Mitigated | `subprocess.run(timeout=120)` with `TimeoutExpired` handling |
| Wrong project path | ✅ Mitigated | Worker uses `_agent_repo` (set by `dispatch_worker()`) only |
