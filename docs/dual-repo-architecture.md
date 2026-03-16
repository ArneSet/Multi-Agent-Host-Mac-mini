# HYBRIS Agent Host — Dual Repo Architecture

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-3-dual-repo-promotion`  
> **Status:** Sprint 3 — implemented in code and enforced  

---

## Warum ein Dual-Repo-Modell?

HYBRIS verwendet zwei getrennte Git-Repositories:

| Repository | Rolle | Agenten-Zugriff |
|-----------|-------|:----------------:|
| **Test Repo** | Arbeitsumgebung für KI-Agenten | ✓ Schreibzugriff |
| **Prod Repo** | Geschützte Produktionsumgebung | ✗ Kein direkter Zugriff |

### Grundprinzip

```
Agents arbeiten NUR gegen das Test Repo.
Promotion zum Prod Repo ist NIEMALS automatisch.
Creative-Director-Approval ist IMMER erforderlich.
```

Die Trennung existiert, um:

1. **Schadensrisiko zu begrenzen** — fehlerhafte Agent-Arbeit bleibt im Test Repo isoliert
2. **Review-Pflicht durchzusetzen** — nichts erreicht Production ohne menschliche Abnahme
3. **Rollback zu vereinfachen** — Test Repo kann jederzeit zurückgesetzt werden, ohne Prod zu berühren
4. **Qualitätsstufen zu modellieren** — Test = „wird gearbeitet", Prod = „abgenommen"

---

## Repo-Rollen

### Test Repo

Das Test Repo ist ein vollständiger Klon des Game-Repos, auf dem Agenten ihre Branches bearbeiten.

| Eigenschaft | Wert |
|-------------|------|
| Config-Key | `repo_targets.test_repo` |
| Agenten-Zugriff | Lesen + Schreiben (nur eigener Branch) |
| Branch-Schutz | `main`/`master`/`develop` protected |
| Zweck | Agent-Ausführung, QA, Integration |
| Risikostufe | Mittel — isoliert von Production |

**Was Agenten im Test Repo dürfen:**
- Auf ihrem zugewiesenen Feature-Branch arbeiten
- Code schreiben, Dateien erstellen/ändern
- Commits anlegen
- Artefakte erzeugen

**Was Agenten im Test Repo NICHT dürfen:**
- Protected Branches beschreiben
- Direkt auf `main` mergen
- Andere Ticket-Branches modifizieren
- Shell-Befehle aus Ticket-Content ausführen

### Prod Repo

Das Prod Repo ist das kanonische HYBRIS-Game-Repository. Es wird ausschließlich durch kontrollierte Promotion beschrieben.

| Eigenschaft | Wert |
|-------------|------|
| Config-Key | `repo_targets.prod_repo` |
| Agenten-Zugriff | ✗ Kein direkter Zugriff |
| Beschrieben durch | Nur Promotion-Flow nach CD-Approval |
| Zweck | Production-Stand, Release-Basis |
| Risikostufe | Kritisch — geschützt |

**Was im Prod Repo erlaubt ist:**
- Kontrollierte Promotion nach Creative-Director-Freigabe
- Manueller Merge durch Orchestrator (nach Approval)

**Was im Prod Repo VERBOTEN ist:**
- Direkter Agent-Schreibzugriff
- Automatische Promotion
- Ungeprüfte Merges
- Jede Form von unkontrolliertem Zugriff

---

## Flow-Übersicht

```
                    ┌──────────────┐
                    │ Creative Dir │
                    │  + Dir GPT   │
                    └──────┬───────┘
                           │ Ticket erstellen
                           ▼
                    ┌──────────────┐
                    │   Ticket     │
                    │   (inbox)    │
                    └──────┬───────┘
                           │ Orchestrator validiert
                           ▼
                    ┌──────────────┐
                    │  TEST REPO   │◄─── Agenten arbeiten hier
                    │  (active)    │
                    └──────┬───────┘
                           │ Worker fertig
                           ▼
                    ┌──────────────┐
                    │  Review-     │
                    │  Package     │
                    └──────┬───────┘
                           │ Creative Director prüft
                           ▼
                    ┌──────────────┐
                    │  Approval    │
                    │  Decision    │
                    └──────┬───────┘
                      ╱         ╲
                approved     rejected
                  │              │
                  ▼              ▼
           ┌────────────┐  ┌──────────┐
           │ Promotion   │  │ Reticket │
           │ Request     │  │ / Rework │
           └──────┬──────┘  └──────────┘
                  │
                  ▼
           ┌──────────────┐
           │  PROD REPO   │◄─── Nur nach CD-Approval
           │  (promoted)  │
           └──────────────┘
```

---

## Konfiguration

### config.json

```json
{
    "repo_targets": {
        "test_repo": "/path/to/hybris-game-test",
        "prod_repo": "/path/to/hybris-game-prod"
    }
}
```

### Enforcement im Code

1. `resolve_agent_repo(cfg)` → gibt **immer** `test_repo` zurück
2. `dispatch_worker()` übergibt immer `test_repo` als Arbeitsverzeichnis
3. `validate_repo_target()` prüft, dass Worker nie `prod_repo` erhalten
4. Promotion ist ein separater, expliziter CLI-Befehl mit Approval-Prüfung

---

## Rejection / Rollback

| Szenario | Aktion |
|----------|--------|
| CD lehnt Review ab | Ticket → `rejected` → kann als neues Ticket reformuliert werden |
| QA schlägt fehl | Ticket → `failed` → Branch im Test Repo bleibt, kann repariert werden |
| Promotion scheitert | Ticket bleibt in `approved`, Promotion kann wiederholt werden |
| Fehler in Production entdeckt | Manueller Hotfix im Prod Repo, neues Ticket für Test Repo |

---

## Zukünftige Erweiterung: Externer Intake

Wenn WhatsApp oder ein anderer Messaging-Gateway angebunden wird, ändert sich die Repo-Architektur **nicht**:

- Externe Messages werden zu Tickets in `inbox/`
- Director GPT triagiert
- Agenten arbeiten im Test Repo
- Promotion bleibt manuell und geschützt

Der Intake-Kanal ist austauschbar. Die Repo-Authority-Grenzen sind fix.
