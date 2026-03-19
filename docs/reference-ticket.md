# Reference Ticket Definition

**Ticket ID**: `REF-001`
**Title**: Add logging utility function to code-worker
**Type**: Code Enhancement
**Priority**: Low
**Status**: Draft

## Description
Add a simple logging utility function to the code-worker module to standardize debug output formatting.

## Requirements
- Add `log_debug()` function to `code_worker/utils.py`
- Function should accept message string and optional context dict
- Output format: `[DEBUG] timestamp - message (context)`
- No external dependencies
- Include basic unit test

## Acceptance Criteria
- Function exists and is importable
- Output format matches specification
- Unit test passes
- No breaking changes to existing code
- Function is used in at least one existing code path

## Technical Details
- **Worker**: code-worker
- **Files to modify**: `code_worker/utils.py`, `tests/test_utils.py`
- **Test command**: `python -m pytest tests/test_utils.py::test_log_debug`
- **Expected artifact**: Modified `code_worker/utils.py` with new function

## Why This Reference Ticket?
- **Simple scope**: Single function addition, minimal risk
- **Code-only**: No asset dependencies, no external tools
- **Testable**: Clear pass/fail criteria
- **Audit trail**: Demonstrates full ticket lifecycle
- **Worker validation**: Proves code-worker operational capability</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/reference-ticket.md