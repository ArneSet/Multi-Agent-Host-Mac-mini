# QA Checklist: code-worker

**Worker Class**: Mutation Worker
**Purpose**: Operator checklist for QA assessment of code-worker outputs

## Pre-QA

- [ ] Ticket is in `review` state
- [ ] ReviewPackage exists (`reviews/{ticket_id}.review.json`)

## Structural Checks (blocker — must all pass)

- [ ] File in `files_written` exists in test_repo
- [ ] File is non-empty (size > 0 bytes)
- [ ] `changeset/ticket-{id}/metadata/changeset.json` exists
- [ ] `changeset/ticket-{id}/metadata/manifest.json` exists
- [ ] Artifact report exists (`artifacts/{ticket_id}_code_result.md`)

## Plausibility Checks (advisory — should be verified)

- [ ] `action` field is plausible ("created" for new files, "modified" for existing)
- [ ] `manifest.json` → `files_added` or `files_modified` matches `action`
- [ ] File path is within expected scope (no unexpected directories)
- [ ] File content is non-trivial (not just whitespace or placeholder)
- [ ] File type is expected for the ticket's purpose

## Security Checks (blocker — must all pass)

- [ ] File is within test_repo (not prod_repo, not outside repo)
- [ ] No protected branch was targeted
- [ ] No unexpected files were created outside the ticket scope

## QA Decision

| Check Result | Decision | Notes Prefix |
|-------------|----------|-------------|
| All structural + security pass, plausibility reasonable | **pass** | (describe what was verified) |
| Structural check failed | **fail** | `FAIL: {which check failed}` |
| Cannot access artifacts or test_repo | **blocked** | `BLOCKED: {what is inaccessible}` |
| Structural pass but plausibility unclear | **inconclusive** | `INCONCLUSIVE: {what is unclear}` |

## CLI Command

```bash
# After assessment:
python3 cli.py qa-decide {ticket_id} pass --notes "All structural checks passed. File exists, non-empty, changeset complete."
# OR
python3 cli.py qa-decide {ticket_id} fail --notes "File exists but is empty."
# OR use shortcuts:
python3 cli.py qa-pass {ticket_id} --notes "..."
python3 cli.py qa-fail {ticket_id} --notes "..."
```

## Quick Verification Commands

```bash
# Check file exists and size
ls -la ~/Workspace/HYBRIS/repos/hybris-test/{file_path}

# Check changeset
cat ~/Workspace/HYBRIS/management/changeset/ticket-{id}/metadata/changeset.json | python3 -m json.tool

# Check manifest
cat ~/Workspace/HYBRIS/management/changeset/ticket-{id}/metadata/manifest.json | python3 -m json.tool

# Check artifact
head -20 ~/Workspace/HYBRIS/management/artifacts/{ticket_id}_code_result.md
```
