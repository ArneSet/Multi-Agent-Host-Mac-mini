# WhatsApp Connector Architecture

## Overview

The WhatsApp connector provides a safe boundary for authenticated WhatsApp messages to enter the HYBRIS ticket system. It terminates at the intake layer, ensuring external messages never directly execute commands, touch repositories, or trigger promotions.

## Why WhatsApp Ends at Intake

WhatsApp messages are external, untrusted input that must be strictly controlled:

1. **No Direct Execution**: WhatsApp messages cannot trigger worker execution
2. **No Repo Access**: WhatsApp messages cannot directly target test_repo or prod_repo
3. **No Promotion**: WhatsApp messages cannot trigger promotion flows
4. **Ticket Boundary**: WhatsApp input becomes ticket candidates in inbox only
5. **Human Oversight**: All admitted WhatsApp tickets require human review before processing

## Connector Boundary Design

```
WhatsApp Webhook
    ↓
WhatsApp Provider Verification
    ↓
Sender Identity Mapping
    ↓
Message Normalization
    ↓
Intake Pipeline (validate, dedupe, rate-limit)
    ↓
Ticket Creation in Inbox
    ↓
Human Review Required
    ↓
Normal Orchestrator Flow
```

## Inbound Message Flow

1. **Webhook Reception**: HTTP endpoint receives WhatsApp webhook payload
2. **Provider Auth**: Verify webhook signature/authenticity
3. **Sender Check**: Map WhatsApp sender to authorized identity
4. **Content Extract**: Extract text content (media rejected in v1)
5. **Normalize**: Convert to intake request format
6. **Intake Process**: Validate, dedupe, rate-limit, admit to inbox
7. **Audit**: Record all events in connector audit trail

## How Inbound Messages Are Verified

- **Provider Verification**: HMAC signature validation or API key
- **Sender Authorization**: Whitelist of allowed WhatsApp numbers
- **Content Safety**: Reject unsafe patterns, scripts, commands
- **Structure Validation**: Required fields, length limits

## How They Are Normalized

WhatsApp messages are normalized into standard intake requests:

```json
{
  "title": "WhatsApp: Hello World",
  "worker": "code-worker",
  "description": "Message from +1234567890: Hello World",
  "branch": "feature/whatsapp-request",
  "priority": "normal",
  "intake_source": "whatsapp"
}
```

## How They Become Ticket Candidates

Normalized requests pass through the intake pipeline:

1. Source trust check (must be "trusted")
2. Payload validation
3. Duplicate detection
4. Rate limiting
5. Ticket creation in inbox with intake_source metadata

## Why No Direct Execution Is Allowed

- **Security**: External input could contain malicious commands
- **Control**: Human review ensures quality and intent
- **Boundaries**: Maintains separation between external intake and internal execution
- **Auditability**: Every action traceable through ticket lifecycle

## Current Limitations

- Text-only messages (no media/attachments in v1)
- Single authorized sender per connector instance
- No automatic worker dispatch from WhatsApp
- Manual review required for all admitted tickets
- Rate limited to prevent abuse</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/whatsapp-connector-architecture.md