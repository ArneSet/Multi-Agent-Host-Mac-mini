# WhatsApp Idempotency and Replay

## Provider Message ID Handling

WhatsApp provides unique message IDs for each message:

### Message ID Structure

```
wamid.HBgNNTkxNDI5Nzk2NzkVAgASGBQzRTE2ODU2NzY5Njg2NDYVAgA=
```

### Storage and Tracking

Message IDs are stored with processing state:

```json
{
  "message_id": "wamid.xxx",
  "processed_at": "2026-03-16T10:30:00Z",
  "intake_id": "intake-20260316103000-abc123",
  "status": "processed"
}
```

## Replay Detection

### Detection Logic

1. **Message ID Lookup**: Check if message_id already processed
2. **Time Window**: Reject replays outside dedup window
3. **Content Hash**: Fallback duplicate detection

### Implementation

```python
def check_whatsapp_replay(cfg: dict, message_id: str) -> bool:
    state = load_whatsapp_state(cfg)
    if message_id in state.get("processed_messages", {}):
        return True
    return False
```

## Duplicate Detection

### Content-Based Dedup

For messages without IDs or as fallback:

```python
def content_hash(message: str) -> str:
    return hashlib.sha256(message.encode()).hexdigest()
```

### Window Management

- **Default Window**: 5 minutes
- **Cleanup**: Remove old entries after 1 hour
- **Storage**: JSON file with timestamp pruning

## Failure Behavior

### Safe Rejection

- **Replay Detected**: Log and ignore, return 200 OK
- **Invalid ID**: Log warning, reject with 400
- **Processing Error**: Log error, reject with 500

### Audit Trail

All replay/duplicate events are audited:

```json
{
  "event": "whatsapp_replay_detected",
  "message_id": "wamid.xxx",
  "reason": "already_processed",
  "timestamp": "2026-03-16T10:30:00Z"
}
```

## Current Limitations

- No cross-connector dedup
- Time-based cleanup only
- No message content comparison
- Single instance state (no clustering)</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/whatsapp-idempotency-and-replay.md