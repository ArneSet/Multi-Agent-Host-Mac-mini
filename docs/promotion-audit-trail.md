# Promotion Audit Trail

> Sprint 5 — HYBRIS Agent Host

## Purpose

Every promotion attempt — whether preview or execute — produces a structured audit record. This creates an immutable, inspectable history of all promotion activity per ticket.

## Audit Record Structure

Each record is a single JSON object stored as one line in a JSONL file:

```json
{
  "ticket_id": "TICKET-001",
  "promotion_request": "promotions/TICKET-001.promotion.json",
  "source_repo": "/path/to/hybris-test",
  "target_repo": "/path/to/hybris-prod",
  "review_package": "reviews/TICKET-001.review.json",
  "approval_decision": "reviews/TICKET-001.approval.json",
  "qa_result": "reviews/TICKET-001.qa.json",
  "branch": "feature/test",
  "source_commit": "abc12345",
  "action": "execute",
  "dry_run": false,
  "timestamp": "2026-03-16T12:00:00Z",
  "result": "executed",
  "detail": "Branch 'feature/test' (abc12345) fetched into /path/to/hybris-prod"
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `ticket_id` | The ticket being promoted |
| `promotion_request` | Path to the promotion request file |
| `source_repo` | Resolved absolute path to test_repo |
| `target_repo` | Resolved absolute path to prod_repo |
| `review_package` | Reference to the ReviewPackage |
| `approval_decision` | Reference to the ApprovalDecision |
| `qa_result` | Reference to the QA validation result |
| `branch` | The branch being promoted |
| `source_commit` | Git commit hash at the time of promotion |
| `action` | `preview` or `execute` |
| `dry_run` | Boolean — true for preview, false for execution |
| `timestamp` | ISO-8601 UTC timestamp |
| `result` | `preview_ok`, `executed`, or `failed` |
| `detail` | Human-readable description of what happened |
| `git_output` | (Optional) Raw git stderr output |

## Storage Location

```
~/Workspace/HYBRIS/management/promotions/audit/<ticket_id>.audit.jsonl
```

- One file per ticket
- JSONL format (one JSON record per line)
- Append-only — records are never modified or deleted
- Multiple records per ticket if previewed and then executed

## CLI Access

```bash
python3 cli.py audit-show TICKET_ID
```

Shows all audit records for a ticket with timestamps, actions, results, and details.

## How Records Are Used

1. **Operator verification**: After executing a promotion, check audit-show to confirm the operation completed correctly
2. **Debugging failures**: Failed promotions include error details in the audit record
3. **Accountability**: Every promotion attempt is timestamped and traceable back to the ticket, review, approval, and QA
4. **Dry-run tracking**: Previews are also recorded, showing that the operator verified before executing

## Limitations and Future Evolution

### Current Limitations
- No operator identity in audit records (single-operator system)
- No cryptographic signing of audit records
- Audit files are local plain-text, not tamper-proof
- No aggregated audit dashboard

### Future Evolution
- Add operator/agent identity when multi-user support arrives
- Consider structured log aggregation for monitoring
- Add promotion diff summary to audit records
- Add remote backup of audit trail
