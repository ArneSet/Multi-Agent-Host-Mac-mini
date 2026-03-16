# Intake Safety Rules

> Sprint 6 — Non-negotiable safety guarantees for external intake.

## Core Safety Principle

**External messages must never directly execute commands, bypass ticket creation, touch repos, or trigger promotion.**

Intake is a **one-way valve**: external input enters the ticket system as an inbox ticket file. That's it. Everything else requires human/operator action through the existing ticket lifecycle.

## Non-Negotiable Rules

### 1. No Execution from Intake

The `intake.py` module does NOT import and CANNOT call:
- `dispatch_worker()` — No worker execution
- `process_ticket()` — No ticket processing pipeline
- `execute_promotion()` — No promotion

This is verified by automated tests that inspect the module source.

### 2. No Repo Access from Intake

Intake code does NOT reference or access:
- `test_repo` — Agent working repository
- `prod_repo` — Production repository
- Any git operations

Admitted tickets are plain Markdown files in the management directory.

### 3. Deny by Default

- Unknown sources → rejected
- Untrusted sources → rejected  
- Only explicitly trusted sources can submit requests
- Empty trust config = no intake possible

### 4. Content Sanitization Required

All string fields are:
- Truncated to maximum lengths
- Stripped of null bytes and control characters
- Checked against unsafe patterns (path traversal, injection, shell metacharacters)
- Rejected if any unsafe content is detected

### 5. Rate Limiting Enforced

Even trusted sources:
- Per-source rate limit (default: 5/min)
- Global rate limit (default: 20/min)
- Rate state persisted to prevent bypass via restart

### 6. Duplicate/Replay Protection

- Content hash deduplication with configurable window
- Prevents replay attacks and accidental double-submission

### 7. Audit Everything

Every intake request — admitted or rejected — is logged to an append-only JSONL audit trail:
- `management/intake/audit/intake.audit.jsonl`
- Records: intake_id, source, timestamp, status, detail

### 8. Admitted Tickets Stop at Inbox

An admitted intake request creates a ticket in `inbox` state. To proceed:
1. Operator transitions `inbox` → `ready` (manual)
2. Operator transitions `ready` → `active` (requires branch)
3. Worker processes ticket (dispatched by operator)
4. Review → Approval → QA → Promotion (existing lifecycle)

No step in this chain is automated from intake.

## Test Coverage

Safety guarantees are verified by the `TestIntakeSafety` test class:
- `test_intake_does_not_import_dispatch_worker`
- `test_intake_does_not_import_execute_promotion`
- `test_intake_does_not_import_process_ticket`
- `test_admitted_ticket_is_only_a_file`
- `test_intake_never_touches_repos`

These tests inspect the actual module source code to ensure prohibited imports/references never appear.

## Threat Model

| Threat | Mitigation |
|---|---|
| Attacker submits malicious ticket | Payload validated, content sanitized, unsafe patterns rejected |
| Attacker floods with requests | Rate limiting (per-source + global) |
| Replay attack | Content hash dedup with time window |
| Path traversal via payload | Path sanitization + `sanitize_path_within()` check |
| Source spoofing | Only configured trusted sources accepted |
| Direct execution attempt | Module boundary prevents import of execution functions |
| Privilege escalation | Admitted tickets land in inbox; no automatic transitions |
