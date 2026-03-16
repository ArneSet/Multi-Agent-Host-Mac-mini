# WhatsApp Auth and Identity

## Provider Authenticity Verification Model

WhatsApp webhooks must prove they originate from the official WhatsApp Business API:

### Verification Methods

1. **HMAC Signature**: Webhook payload signed with shared secret
2. **API Key**: Bearer token in Authorization header
3. **IP Whitelist**: Restrict to known WhatsApp IP ranges

### Implementation

```python
def verify_whatsapp_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Sender Identity Model

### Identity Mapping

WhatsApp phone numbers are mapped to internal identities:

```json
{
  "whatsapp": {
    "authorized_senders": {
      "+1234567890": {
        "identity": "arne",
        "permissions": ["create_tickets"],
        "rate_limit": 10
      }
    }
  }
}
```

### Authorization Rules

- **Default Deny**: Unknown senders rejected
- **Explicit Allow**: Only whitelisted numbers can send
- **Identity Context**: Sender mapped to internal user/role
- **Permission Scope**: Limited to ticket creation only

## What a Valid Sender May Request

Authorized WhatsApp senders can request:

- **Ticket Creation**: Create new work tickets in inbox
- **Status Queries**: Check ticket status (future)
- **Basic Commands**: Limited safe operations

### Forbidden Actions

Authorized senders still cannot:

- Execute workers directly
- Access repositories
- Trigger promotions
- Modify existing tickets
- Access sensitive data

## What Remains Forbidden Even for Valid Senders

All direct system access is forbidden:

- File system access
- Command execution
- Database queries
- Network calls
- Repository operations
- Promotion triggers

## Current Limitations

- Single sender per connector instance
- No group chat support
- No media/file uploads
- No rich formatting preservation
- Manual identity mapping required</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/whatsapp-auth-and-identity.md