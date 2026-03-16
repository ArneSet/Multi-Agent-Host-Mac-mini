# WhatsApp Operating Rules

## Connector Startup/Shutdown Behavior

### Startup Sequence

1. **Config Validation**: Verify all required settings present
2. **Token Verification**: Test WhatsApp API connectivity (optional)
3. **State Initialization**: Load previous message state
4. **Webhook Registration**: Confirm webhook URL configured

### Shutdown Sequence

1. **Graceful Stop**: Complete processing current messages
2. **State Persistence**: Save all state to disk
3. **Audit Flush**: Ensure all events written to audit trail
4. **Clean Exit**: No hanging connections

## Operator Flow

### Daily Operation

1. **Check Status**: `python3 cli.py whatsapp-status`
2. **Monitor Audit**: `python3 cli.py whatsapp-audit-show`
3. **Review Tickets**: Check inbox for new WhatsApp tickets
4. **Process Normally**: Use standard ticket commands

### Incident Response

1. **Disable Connector**: Set `enabled: false` in config
2. **Check Audit**: Review recent events for anomalies
3. **Rate Limit Check**: Verify not under attack
4. **Re-enable**: After investigation

## Failure Handling

### Provider Authentication Failure

- **Action**: Reject webhook with 401
- **Log**: Authentication failure with IP/timestamp
- **Alert**: Log warning for monitoring

### Invalid Message Format

- **Action**: Reject with 400, log details
- **Audit**: Record malformed message attempt
- **No Retry**: Single rejection

### Rate Limit Exceeded

- **Action**: Reject with 429, log sender
- **Audit**: Record rate limit violation
- **Cooldown**: Automatic based on config

### Intake Pipeline Failure

- **Action**: Reject with 500, log error
- **Audit**: Record processing failure
- **Retry**: Manual review may be needed

## Attachment/Media Policy

### Current Policy (v1)

- **Text Only**: Accept text messages only
- **Media Rejected**: All attachments/media return 400
- **Future**: Media handling in future sprint

### Rejection Response

```json
{
  "error": "Media attachments not supported",
  "supported_types": ["text"]
}
```

## Current Non-Goals

### Not Implemented in Sprint 7

- Media/file processing
- Group chat support
- Rich message formatting
- Automatic responses
- Message threading
- Delivery receipts
- Typing indicators
- Message reactions

### Future Considerations

- Media analysis for safe content
- Group admin controls
- Message templates
- Interactive buttons
- Location sharing

## Security Monitoring

### Key Metrics to Monitor

- Authentication failure rate
- Rate limit hit rate
- Invalid message rate
- Processing error rate
- New sender attempts

### Alert Thresholds

- Auth failures > 5/minute
- Rate limits > 10/hour
- Invalid messages > 20/hour
- Processing errors > 1/hour

### Log Analysis

```bash
# Check recent auth failures
grep "auth_failed" ~/Workspace/HYBRIS/management/logs/whatsapp.log

# Check rate limit hits
grep "rate_limited" ~/Workspace/HYBRIS/management/logs/whatsapp.log
```

## Backup and Recovery

### State Backup

- Message processing state backed up with main system
- Audit trail is append-only, recoverable
- Config changes versioned (secrets excluded)

### Recovery Procedure

1. **Stop Connector**: Disable webhook processing
2. **Restore State**: Copy state files from backup
3. **Validate**: Run `whatsapp-validate`
4. **Restart**: Re-enable connector

## Performance Guidelines

### Expected Load

- **Messages/Hour**: 10-50 typical
- **Peak**: 100/hour acceptable
- **Response Time**: < 2 seconds
- **Uptime**: 99% (manual operation)

### Scaling Limits

- Single-threaded processing
- Memory: < 100MB
- Disk: < 1GB for logs/state
- Network: Minimal outbound to WhatsApp API</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/whatsapp-operating-rules.md