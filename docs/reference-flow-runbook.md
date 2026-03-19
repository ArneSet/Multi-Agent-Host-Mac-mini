# Reference Flow Runbook

**Sprint**: 9A - Reference Flow Operationalization
**Ticket**: REF-001 (Add logging utility to code-worker)
**Date**: 2026-03-17
**Purpose**: Minimal operator guide for running one reference ticket end-to-end

## Prerequisites

### Environment Setup
- **Machine**: Mac mini (canonical reference machine)
- **User**: hybris-operator
- **Working Directory**: `/Users/arnesetkewitz/Workspace/HYBRIS/`
- **Shell**: zsh with proper PATH

### Repository State
- **Host Repo**: `feature/sprint-7-whatsapp-connector` branch
- **Test Repo**: `main` branch, clean state
- **No uncommitted changes** in either repo

### System State
- **WhatsApp Connector**: Daily-use ready (Sprint 8 complete)
- **Orchestrator**: Functional
- **code-worker**: Staging ready (confirmed in capability matrix)
- **All safety boundaries**: Intact (no auto-promotion, manual gates)

## Reference Flow Steps

### Phase 1: Ticket Creation
**Goal**: Create REF-001 ticket in the system

1. **Navigate to management directory**
   ```bash
   cd /Users/arnesetkewitz/Workspace/HYBRIS/management
   ```

2. **Create ticket via intake**
   ```bash
   python3 ../repos/hybris-host/cli.py intake-submit whatsapp \
     --title "Add logging utility function to code-worker" \
     --worker code-worker \
     --description "Add log_debug() function to code_worker/utils.py with standardized formatting"
   ```

3. **Verify ticket creation**
   ```bash
   ls -la tickets/inbox/
   # Should show: intake-{timestamp}-{hash}.md
   ```

### Phase 2: Orchestrator Processing
**Goal**: Process ticket through orchestrator to create work order

1. **Check ticket status**
   ```bash
   python3 ../repos/hybris-host/cli.py intake-status
   ```

2. **Process ticket**
   ```bash
   # Find ticket ID from inbox listing
   TICKET_ID=intake-{timestamp}-{hash}
   python3 ../repos/hybris-host/cli.py process $TICKET_ID
   ```

3. **Verify work order creation**
   ```bash
   ls -la tickets/active/
   # Should show work order file
   ```

### Phase 3: Worker Execution
**Goal**: Execute code-worker to produce artifact

1. **Check worker status** (should be idle)

2. **Execute worker**
   ```bash
   python3 ../repos/hybris-host/cli.py process $TICKET_ID --execute-worker
   ```

3. **Monitor execution**
   - Worker should complete within 30 seconds
   - Check for success/failure output
   - Verify artifact creation in changeset directory

4. **Verify artifact**
   ```bash
   ls -la changeset/ticket-REF-001/artifact/
   # Should contain: code_worker/utils.py, tests/test_log_debug.py
   ```

### Phase 4: QA Gate
**Goal**: Manual QA verification of artifact

1. **Review changes**
   ```bash
   cat changeset/ticket-REF-001/artifact/code_worker/utils.py
   # Verify log_debug() function exists and is correct
   ```

2. **Run tests**
   ```bash
   cd changeset/ticket-REF-001/artifact/
   python3 -m pytest tests/test_utils.py::test_log_debug -v
   # Should pass
   ```

3. **Create QA report**
   ```bash
   # Manual: Create qa-report.json
   cat > changeset/ticket-REF-001/metadata/qa-report.json << 'EOF'
   {
     "ticket_id": "REF-001",
     "qa_engineer": "hybris-operator",
     "timestamp": "2026-03-17T11:00:00Z",
     "status": "passed",
     "criteria_checked": [
       "Function exists and is importable",
       "Output format matches specification",
       "Unit test passes",
       "No breaking changes"
     ],
     "notes": "All acceptance criteria met. Function works as expected."
   }
   EOF
   ```

### Phase 5: Review Gate
**Goal**: Manual review decision

1. **Review artifact and QA report**

2. **Make review decision**
   - **APPROVE**: Proceed to promotion
   - **REJECT**: Create re-ticket with issues

3. **Create review report**
   ```bash
   cat > changeset/ticket-REF-001/metadata/review-report.json << 'EOF'
   {
     "ticket_id": "REF-001",
     "reviewer": "hybris-operator",
     "timestamp": "2026-03-17T11:15:00Z",
     "decision": "approved",
     "rationale": "Clean implementation, tests pass, meets requirements",
     "risk_assessment": "low",
     "approval_conditions": []
   }
   EOF
   ```

### Phase 6: Promotion (Manual)
**Goal**: Apply approved changes to production

1. **Verify promotion readiness**
   - QA: passed
   - Review: approved
   - All files present

2. **Execute promotion**
   ```bash
   python3 ../repos/hybris-host/cli.py promotion-check $TICKET_ID
   # Manual promotion command (to be implemented)
   ```

3. **Verify promotion success**
   - Changes applied to prod repo
   - Ticket moved to completed
   - Audit trail updated

## Expected Outcomes

### Success State
- Ticket: `completed` status
- Artifact: Present in `changeset/ticket-REF-001/`
- QA Report: `passed`
- Review Report: `approved`
- Promotion: Successful (if executed)

### File Structure After Completion
```
management/
├── tickets/
│   ├── completed/
│   │   └── intake-{timestamp}-{hash}.md
│   └── archive/
│       └── REF-001-{execution-id}/
├── changeset/
│   └── ticket-REF-001/
│       ├── artifact/
│       │   ├── code_worker/utils.py
│       │   └── tests/test_log_debug.py
│       └── metadata/
│           ├── changeset.json
│           ├── qa-report.json
│           └── review-report.json
└── audit/
    └── {audit logs}
```

## Failure Handling

### Worker Execution Fails
- Check worker logs
- Verify environment setup
- Re-run worker if transient failure
- Create re-ticket if code issue

### QA Fails
- Document specific issues
- Create re-ticket with fixes
- Do not proceed to review

### Review Rejects
- Document rejection reasons
- Create new ticket with fixes
- Archive rejected changeset

## Safety Checks

### Before Each Phase
- [ ] No uncommitted changes in repos
- [ ] Safety boundaries intact
- [ ] Previous phase completed successfully

### Emergency Stop
- [ ] Can abort at any point
- [ ] State remains clean
- [ ] No partial changes applied

## Timing Expectations

- **Ticket Creation**: 2 minutes
- **Orchestrator Processing**: 5 minutes
- **Worker Execution**: 30 seconds
- **QA**: 10 minutes
- **Review**: 5 minutes
- **Promotion**: 5 minutes
- **Total Reference Flow**: ~30 minutes

## Validation Commands

```bash
# Check system status
python3 ../repos/hybris-host/cli.py intake-status

# Verify artifact
ls -la changeset/ticket-REF-001/artifact/

# Run tests
cd changeset/ticket-REF-001/artifact/ && python3 -m pytest tests/test_utils.py -v

# Check audit trail
python3 ../repos/hybris-host/cli.py intake-audit-show
```</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/reference-flow-runbook.md