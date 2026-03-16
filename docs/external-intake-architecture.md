# External Intake Architecture

> Sprint 6 — Safe message-to-ticket intake adapter layer.

## Purpose

The intake adapter receives external requests and admits them into the ticket system **without granting execution authority**. External input never directly executes commands, never touches repos, never triggers promotion.

## Architecture Overview

```
External Source
       │
       ▼
┌──────────────┐
│  intake.py   │  ← Standalone module, no execution imports
├──────────────┤
│ 1. Validate source
│ 2. Check trust level
│ 3. Validate payload
│ 4. Check duplicate/replay
│ 5. Check rate limit
│ 6. Normalize
│ 7. Admit → inbox ticket
│ 8. Audit trail
└──────┬───────┘
       │
       ▼
  tickets/inbox/   ← Ticket file ONLY. No execution.
```

## Module Separation

| Module | Responsibility | Imports from orchestrator? |
|---|---|---|
| `intake.py` | External intake pipeline | Only `sanitize_ticket_id`, `sanitize_path_within` (at ticket creation time) |
| `orchestrator.py` | Ticket state machine, execution | N/A (does not import intake) |
| `cli.py` | User interface | Imports both |

This separation ensures intake code **cannot** call `dispatch_worker`, `execute_promotion`, or `process_ticket`.

## Pipeline Stages

1. **Source validation**: Source identifier must be in `INTAKE_SOURCES` and match safe pattern
2. **Trust check**: Source must be in `cfg.intake.trusted_sources` (blocked/untrusted are rejected)
3. **Payload validation**: Required fields (`title`, `worker`), length limits, no unsafe content, no forbidden fields
4. **Duplicate detection**: SHA-256 content hash compared against dedup window
5. **Rate limiting**: Per-source and global limits enforced per minute
6. **Normalization**: Fields sanitized, priority validated, metadata attached
7. **Admission**: Ticket file created in `tickets/inbox/` (or dry-run)
8. **Audit**: Every request (admitted or rejected) logged to JSONL audit trail

## Data Flow

- Input: `(source: str, payload: dict)` from CLI or future connector
- Output: Intake result dict with status, detail, and optional ticket path
- State: `management/intake/state/` (hashes, rate counters)
- Audit: `management/intake/audit/intake.audit.jsonl`

## Safety Boundary

The intake module is designed with a hard safety boundary:

- **NO imports** of `dispatch_worker`, `execute_promotion`, `process_ticket`
- **NO references** to `test_repo` or `prod_repo` as functional code
- **NO git operations** — intake only creates files
- Admitted tickets land in `inbox` state — they must still be manually transitioned through the ticket lifecycle by an authorized operator

## Future Connectors

The `INTAKE_SOURCES` constant includes placeholder sources for future connectors:
- `future_whatsapp` — WhatsApp Business API
- `future_openclaw` — OpenClaw integration
- `future_sms` — SMS gateway
- `future_api` — REST API endpoint

These are currently defined but not trusted. Adding a connector requires:
1. Adding the source to `intake.trusted_sources` in config
2. Building a connector that calls `process_intake()` with the correct source and payload
