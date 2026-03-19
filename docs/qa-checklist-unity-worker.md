# QA Checklist: unity-worker

**Worker Class**: Validation Worker
**Purpose**: Operator checklist for QA assessment of unity-worker outputs

## Pre-QA

- [ ] Ticket is in `review` state
- [ ] ReviewPackage exists (`reviews/{ticket_id}.review.json`)

## Structural Checks (blocker — must all pass)

- [ ] Artifact report exists (`artifacts/{ticket_id}_unity_result.md`)
- [ ] Artifact report is non-empty
- [ ] `changeset/ticket-{id}/metadata/changeset.json` exists
- [ ] `changeset/ticket-{id}/metadata/manifest.json` exists
- [ ] `files_written` is empty (Validation Workers must not write to test_repo)

## Report Content Checks (advisory — should be verified)

- [ ] Report contains clear pass/fail status
- [ ] Compile error count is stated (should be 0 for pass)
- [ ] Exit code is stated and plausible
- [ ] Unity Editor version is stated
- [ ] Report references the correct ticket ID

## Validation-Specific Checks (advisory — should be verified)

- [ ] `validation_type` matches ticket request (e.g., `project-health`)
- [ ] No unexpected warnings that indicate real problems
- [ ] Unity log was captured (referenced in changeset or artifact)
- [ ] Timeout was not hit (execution time < 120s)

## Security Checks (blocker — must all pass)

- [ ] No files were written to test_repo
- [ ] No files were written to prod_repo
- [ ] Unity was invoked against test_repo only

## QA Decision

| Check Result | Decision | Notes Prefix |
|-------------|----------|-------------|
| All structural + security pass, report clear | **pass** | (describe validation result) |
| Artifact missing or empty | **fail** | `FAIL: {what is missing}` |
| Cannot access artifacts or test_repo | **blocked** | `BLOCKED: {what is inaccessible}` |
| Report exists but status ambiguous | **inconclusive** | `INCONCLUSIVE: {what is unclear}` |

## CLI Command

```bash
# After assessment:
python3 cli.py qa-decide {ticket_id} pass --notes "Validation report present. project-health passed, 0 compile errors, exit code 0."
# OR
python3 cli.py qa-decide {ticket_id} fail --notes "Validation report shows 3 compile errors."
# OR use shortcuts:
python3 cli.py qa-pass {ticket_id} --notes "..."
python3 cli.py qa-fail {ticket_id} --notes "..."
```

## Quick Verification Commands

```bash
# Check artifact report
cat ~/Workspace/HYBRIS/management/artifacts/{ticket_id}_unity_result.md

# Check changeset
cat ~/Workspace/HYBRIS/management/changeset/ticket-{id}/metadata/changeset.json | python3 -m json.tool

# Check manifest (files_written should be empty array)
cat ~/Workspace/HYBRIS/management/changeset/ticket-{id}/metadata/manifest.json | python3 -m json.tool

# Check Unity log (if referenced)
ls -la ~/Workspace/HYBRIS/management/changeset/ticket-{id}/
```
