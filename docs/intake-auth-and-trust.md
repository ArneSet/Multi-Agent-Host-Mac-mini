# Intake Auth and Trust

> Sprint 6 — Source authentication and authorization model.

## Trust Model

Every intake source is assigned a trust level:

| Trust Level | Behavior |
|---|---|
| `trusted` | Requests proceed through the full pipeline |
| `untrusted` | Requests are immediately rejected |
| `blocked` | Requests are immediately rejected (explicit deny) |

### Trust Resolution

1. If source is in `cfg.intake.blocked_sources` → **blocked**
2. If source is in `cfg.intake.trusted_sources` → **trusted**
3. Otherwise → **untrusted** (deny by default)

This is a **deny-by-default** model. Unknown sources are never admitted.

## Configuration

```json
{
    "intake": {
        "trusted_sources": ["local_simulated"],
        "blocked_sources": [],
        "rate_limit": {
            "max_per_source_per_minute": 5,
            "max_global_per_minute": 20
        },
        "duplicate_window_seconds": 300
    }
}
```

## Source Identifiers

Known intake sources are defined in `INTAKE_SOURCES`:

- `local_simulated` — CLI-based local testing (default trusted)
- `future_whatsapp` — WhatsApp Business API (future)
- `future_openclaw` — OpenClaw integration (future)
- `future_sms` — SMS gateway (future)
- `future_api` — REST API endpoint (future)

Source identifiers must:
- Be non-empty strings
- Match `^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$`
- Exist in `INTAKE_SOURCES`

## Authorization Boundaries

Intake authorization only controls **admission to inbox**. It does NOT grant:
- Worker execution authority
- Repo access (test or prod)
- State transition rights
- Promotion privileges

These are governed by the existing ticket lifecycle (Sprints 1-5).

## Rate Limiting

Even trusted sources are rate-limited:
- **Per-source**: Max requests per minute (default: 5)
- **Global**: Max total requests per minute (default: 20)

Rate state is stored in `management/intake/state/rate_state.json`.

## Duplicate Protection

Content-hash-based duplicate detection prevents replay attacks:
- SHA-256 hash of payload content
- Configurable dedup window (default: 300 seconds)
- Hash state stored in `management/intake/state/seen_hashes.json`
- Old entries pruned after 1 hour
