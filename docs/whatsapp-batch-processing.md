# WhatsApp Batch Processing

## Warum Batch-Verarbeitung wichtig ist

WhatsApp Business API sendet eingehende Nachrichten häufig in Batches/Webhook-Payloads, die mehrere Nachrichten enthalten können. Dies geschieht aus Effizienzgründen und bei hohem Nachrichtenaufkommen.

**Risiko ohne korrekte Batch-Verarbeitung:**
- Nur die erste Nachricht wird verarbeitet
- Gültige Nachrichten werden stillschweigend ignoriert
- System erscheint nicht-deterministisch
- Verlust von Arbeitsaufträgen

**Sicherheitsanforderung:**
- Alle validen Nachrichten müssen verarbeitet werden
- Keine stillen Drops aufgrund von Array-Struktur
- Jede Nachricht erhält individuelle Entscheidung

## Provider Payload Structure Assumptions

WhatsApp Webhook-Payloads folgen dieser Struktur:

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "business_account_id",
      "changes": [
        {
          "field": "messages",
          "value": {
            "messages": [
              {
                "id": "wamid.msg1",
                "from": "+1234567890",
                "timestamp": "1640995200",
                "type": "text",
                "text": {"body": "Message 1"}
              },
              {
                "id": "wamid.msg2",
                "from": "+1234567890",
                "timestamp": "1640995201",
                "type": "text",
                "text": {"body": "Message 2"}
              }
            ]
          }
        }
      ]
    }
  ]
}
```

**Annahmen:**
- `entry` ist Array (normalerweise 1 Element)
- `changes` ist Array von Change-Objekten
- `value.messages` ist Array von Message-Objekten
- Jede Message hat eindeutige `id` (WAMID)

## Message Iteration Implementation

### Provider-Level Verification
1. HMAC-Signatur wird gegen gesamten Payload verifiziert
2. Bei Signatur-Fehler: Gesamter Payload rejected
3. Bei Erfolg: Iteration über Messages beginnt

### Per-Message Processing Loop
```python
for message in payload_messages:
    # 1. Parse message
    parsed = parse_single_message(message)

    # 2. Authorize sender
    if not authorize_sender(parsed['from']):
        audit_reject(message_id, 'unauthorized_sender')
        continue

    # 3. Check replay
    if check_replay(message_id):
        audit_duplicate(message_id, 'replay_detected')
        continue

    # 4. Check rate limit
    if check_rate_limit(sender):
        audit_rate_limited(message_id, 'rate_limit_exceeded')
        continue

    # 5. Normalize & admit
    normalized = normalize_message(parsed)
    intake_result = process_intake(normalized)
    audit_admit(message_id, intake_result)
```

### Safety Guarantees
- Provider-Verifikation zuerst (fail-closed)
- Jede Message unabhängig verarbeitet
- Fehler in einer Message blockiert nicht andere
- Alle Entscheidungen auditiert

## Per-Message Audit Recording

Jeder Message-Status wird separat auditiert:

```json
{
  "timestamp": "2026-03-16T20:44:26Z",
  "event": "message_processed",
  "message_id": "wamid.HBgNNTUyNzkwNjU5NzkVAgRGGCYzRjZGRkJFNzM3ODcA",
  "sender": "+1234567890",
  "status": "admitted",
  "detail": "Ticket created: intake-20260316204426-fcffbb1f3881b717.md",
  "batch_context": {
    "batch_size": 2,
    "batch_position": 1,
    "payload_hash": "abc123..."
  }
}
```

**Audit-Fields:**
- `message_id`: WhatsApp Message ID (WAMID)
- `sender`: Absender-Nummer
- `status`: admitted/rejected/duplicate/rate_limited
- `detail`: Spezifische Begründung
- `batch_context`: Metadaten über Batch

## Partial Success/Failure Handling

### Erfolgreich verarbeitete Messages
- Erhalten Ticket in Inbox
- Audit-Record mit `status: "admitted"`

### Fehlgeschlagene Messages
- Kein Ticket erstellt
- Audit-Record mit entsprechendem Status
- Keine Auswirkung auf andere Messages

### Provider-Level Failures
- Gesamter Payload rejected
- Einzelne Audit-Records für jede Message mit `status: "rejected"`
- Grund: "provider_verification_failed"

## What Remains Intentionally Unsupported

### Batch-Level Limits
- Max 10 Messages pro Payload (DOS-Schutz)
- Überschreitung: Payload rejected mit Audit

### Complex Payloads
- Nur `messages` Changes verarbeitet
- Andere Change-Types ignoriert (sicher)

### Message Types
- Nur `text` Messages (v1)
- Andere Types: `rejected` mit "unsupported_message_type"

### Error Recovery
- Kein Retry-Mechanismus (Provider übernimmt)
- Fehlgeschlagene Messages bleiben failed