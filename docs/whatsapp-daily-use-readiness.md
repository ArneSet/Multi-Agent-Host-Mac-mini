# WhatsApp Daily-Use Readiness

## Was bedeutet "Daily-Use Ready"?

**Definition:** Der WhatsApp Connector kann als kontrollierter täglicher Intake-Kanal verwendet werden, ohne ständige manuelle Überwachung zu erfordern, aber mit klaren Betriebsregeln und Grenzen.

**Nicht Ready bedeutet:**
- Pilot-Only: Nur für kontrollierte Tests
- Blocker vorhanden: Kritische Funktionalität fehlt
- High Risk: Zuverlässigkeit nicht gegeben

**Ready bedeutet:**
- Reliable: Verarbeitet alle validen Nachrichten korrekt
- Auditable: Vollständige Nachverfolgung möglich
- Safe: Keine Boundary-Verletzungen
- Monitored: Operator kann Status prüfen

## Approved Operating Mode

### Zulässige Nutzung
- **Secondary Intake Channel**: Nicht der primäre Weg für Tickets
- **Text-Only**: Nur Text-Nachrichten
- **Single Sender**: Nur ein autorisierter Absender
- **Controlled Volume**: Rate-Limiting aktiv
- **Manual Review**: Alle Tickets werden manuell reviewed

### Betriebsregeln
1. **Sender Limit**: Nur konfigurierter autorisierter Sender
2. **Message Types**: Nur Text, keine Medien/Anhänge
3. **Volume Control**: Max 5 Nachrichten/Minute pro Sender
4. **Review Required**: Keine automatische Worker-Dispatch
5. **Audit Checks**: Regelmäßige `whatsapp-audit-show` Prüfung
6. **Fallback Available**: Alternativer Intake-Weg verfügbar

### Nicht-Zulässige Nutzung
- Kritische Produktions-Tickets ausschließlich über WhatsApp
- Hohes Volumen ohne Monitoring
- Multi-Sender Szenarien
- Media/Attachment Versand
- Automatisierte Prozesse abhängig von WhatsApp

## Sender Limits

### Aktuelle Konfiguration
- **Authorized Senders**: 1 (konfigurierbar, aber für Daily-Use auf 1 begrenzt)
- **Rate Limit**: 5 Nachrichten/Minute pro Sender
- **Dedup Window**: 5 Minuten

### Warum Single Sender?
- **Safety First**: Minimale Angriffsfläche
- **Auditability**: Klare Verantwortlichkeit
- **Testing**: Einfachere Validierung
- **Operational Control**: Direkter Kontakt zum Sender

### Erweiterung zu Multi-Sender
- Erfordert zusätzliche Sicherheitsprüfungen
- Separate Sprint (Sprint 9+)
- Zusätzliche Audit-Anforderungen

## Text-Only Rule

### Unterstützt
- Reine Text-Nachrichten
- Emojis und Sonderzeichen
- Mehrzeiliger Text
- Lange Nachrichten (bis 4096 Zeichen)

### Nicht Unterstützt (Rejected)
- Bilder, Videos, Audio
- Dokumente, PDFs
- Kontakte, Standorte
- Interaktive Elemente (Buttons, etc.)

### Warum Text-Only?
- **Safety**: Keine komplexen Payloads
- **Simplicity**: Einfache Parsing/Validation
- **Auditability**: Klare Inhaltsprüfung
- **Boundary Control**: Keine externen Ressourcen

## Operator Monitoring Expectations

### Regelmäßige Checks
- **Tägliche Status-Prüfung**: `whatsapp-status`
- **Audit Review**: `whatsapp-audit-show --last 24h`
- **Inbox Monitoring**: Neue Tickets aus WhatsApp identifizieren
- **Error Detection**: Failed Messages prüfen

### Alarmbedingungen
- **Rate Limit Hits**: Mehr als 10/Minute
- **Reject Rate**: Mehr als 20% rejected Messages
- **Duplicate Rate**: Mehr als 5% duplicates
- **Processing Errors**: Mehr als 0 in 24h

### Monitoring Commands
```bash
# Status Overview
whatsapp-status

# Recent Activity
whatsapp-audit-show --tail 50

# Specific Sender
whatsapp-audit-show --filter sender=+1234567890

# Error Summary
whatsapp-audit-show --filter status=rejected --since 1d
```

## Bekannte Limitations (noch vorhanden)

### Funktionale Grenzen
- **Batch Size**: Max 10 Messages/Payload
- **Message Size**: 4096 Zeichen
- **Sender Count**: 1 autorisiert
- **Message Types**: Text only

### Operationale Grenzen
- **Latency**: Webhook-Verarbeitung kann 1-5 Sekunden dauern
- **Reliability**: Abhängig von WhatsApp API Verfügbarkeit
- **Error Recovery**: Kein automatischer Retry
- **Monitoring**: Manueller Check erforderlich

### Sicherheitsgrenzen
- **No Direct Execution**: Immer manuelle Review
- **No Repo Access**: Nur Inbox
- **No Promotion**: Keine automatische Promotion
- **Audit Only**: Vollständige Nachverfolgung

## Risk Assessment

### Low Risk
- Single Sender: Minimale Angriffsfläche
- Text-Only: Keine komplexen Payloads
- Rate Limited: DOS-Schutz
- Audited: Vollständige Nachverfolgung

### Medium Risk
- Provider Dependency: WhatsApp API Ausfälle
- Manual Monitoring: Menschlicher Fehler möglich
- Batch Processing: Komplexität erhöht

### Mitigation Strategies
- **Fallback Channels**: Alternative Intake-Wege
- **Monitoring Alerts**: Automatische Benachrichtigungen
- **Regular Audits**: Wöchentliche Review
- **Sender Training**: Klare Nutzungsregeln

## Operational Rules for Daily Use

### Do's
- ✅ Verwende für nicht-kritische Requests
- ✅ Prüfe Inbox täglich
- ✅ Monitor Status wöchentlich
- ✅ Dokumentiere Issues
- ✅ Halte Sender informiert

### Don'ts
- ❌ Kritische Produktion über WhatsApp
- ❌ Hohes Volumen ohne Review
- ❌ Media-Versand
- ❌ Automatisierte Prozesse
- ❌ Mehrere Sender gleichzeitig

### Emergency Procedures
1. **Bei Ausfall**: Fallback zu manuellem Ticket-Erstellung
2. **Bei Fehlern**: `whatsapp-status` prüfen, Logs analysieren
3. **Bei Spam**: Sender blockieren, Audit review
4. **Bei Sicherheitsbedenken**: Connector deaktivieren

## Future Roadmap

### Sprint 9: Multi-Sender Support
- Mehrere autorisierte Sender
- Per-Sender Rate Limits
- Enhanced Audit per Sender

### Sprint 10: Media Support
- Bild-Verarbeitung
- Dokument-Handling
- Sicherheitsprüfungen

### Sprint 11: Advanced Features
- Gruppenchat-Unterstützung
- Interactive Messages
- Two-Way Communication