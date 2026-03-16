# HYBRIS Agent Host — Promotion Flow

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-3-dual-repo-promotion`  
> **Status:** Sprint 3 — modeled in code, manual execution  

---

## Übersicht

Der Promotion-Flow steuert, wie abgenommene Agent-Arbeit vom Test Repo ins Prod Repo gelangt.

```
Worker fertig
  └─▶ ReviewPackage erstellen
        └─▶ Creative Director prüft
              ├─▶ ApprovalDecision: approved
              │     └─▶ PromotionRequest erstellen
              │           └─▶ Orchestrator führt Promotion aus (manuell bestätigt)
              │                 └─▶ Ticket → promoted
              ├─▶ ApprovalDecision: rejected
              │     └─▶ Ticket → rejected (Begründung)
              └─▶ ApprovalDecision: reticketed
                    └─▶ Neues Ticket → inbox
```

---

## Konzepte

### 1. ReviewPackage

Bündelt alle Informationen für eine Abnahme-Entscheidung.

```json
{
    "ticket_id": "creature-hydra-model",
    "created_at": "2026-03-16T14:00:00Z",
    "worker": "blender-worker",
    "branch": "feature/creature-hydra",
    "repo_target": "test_repo",
    "artifacts": [
        "artifacts/creature-hydra-model_blender_result.md"
    ],
    "worker_log": "logs/worker/creature-hydra-model.log",
    "summary": "Hydra-Modell erstellt, FBX exportiert, 12k Tris"
}
```

**Speicherort:** `management/reviews/<ticket_id>.review.json`  
**Erstellt durch:** Orchestrator, wenn Ticket `review` erreicht  
**Konsumiert durch:** Creative Director (manuell), CLI (`review-show`)

### 2. ApprovalDecision

Die Entscheidung des Creative Directors.

```json
{
    "ticket_id": "creature-hydra-model",
    "decision": "approved",
    "reviewer": "creative-director",
    "reason": "Modell passt, Textur fehlt noch — separates Ticket",
    "decided_at": "2026-03-16T15:00:00Z"
}
```

**Gültige Entscheidungen:**

| Decision | Wirkung | Nächster Zustand |
|----------|---------|:----------------:|
| `approved` | Promotion freigegeben | `done` (→ promotion-ready) |
| `rejected` | Arbeit abgelehnt | `failed` |
| `reticketed` | Neues Ticket erforderlich | `failed` + neues Ticket |

**Speicherort:** `management/reviews/<ticket_id>.approval.json`  
**Erstellt durch:** CLI (`approve`, `reject`, `reticket`)

### 3. PromotionRequest

Ein Antrag auf kontrollierte Übernahme in das Prod Repo.

```json
{
    "ticket_id": "creature-hydra-model",
    "approval_ref": "reviews/creature-hydra-model.approval.json",
    "source_repo": "test_repo",
    "target_repo": "prod_repo",
    "branch": "feature/creature-hydra",
    "requested_at": "2026-03-16T15:30:00Z",
    "status": "pending"
}
```

**Speicherort:** `management/promotions/<ticket_id>.promotion.json`  
**Erstellt durch:** CLI (`promote`)  
**Status-Werte:** `pending` | `executed` | `failed` | `cancelled`

### 4. PromotionTarget

| Target | Config-Key | Beschreibung |
|--------|-----------|--------------|
| `test_repo` | `repo_targets.test_repo` | Agent-Arbeitsumgebung |
| `prod_repo` | `repo_targets.prod_repo` | Geschützte Production |

---

## CLI-Befehle

| Befehl | Aktion |
|--------|--------|
| `cli.py review-show <ticket_id>` | ReviewPackage anzeigen |
| `cli.py approve <ticket_id> [--reason TEXT]` | Ticket freigeben |
| `cli.py reject <ticket_id> --reason TEXT` | Ticket ablehnen |
| `cli.py reticket <ticket_id> --reason TEXT` | Ticket zur Neuformulierung zurückgeben |
| `cli.py promote <ticket_id> [--dry-run]` | Promotion planen / ausführen |
| `cli.py repo-targets` | Konfigurierte Repo-Targets anzeigen |

---

## Regeln

1. **Promotion erfordert Approval** — ohne `approved`-Entscheidung keine Promotion
2. **Promotion ist nie automatisch** — CLI-Befehl mit expliziter Bestätigung
3. **Dry-Run zuerst** — `promote --dry-run` zeigt Plan ohne Ausführung
4. **Nur Test→Prod** — Umgekehrte Richtung existiert nicht
5. **Ein ReviewPackage pro Ticket** — wird bei jedem Review-Eintritt neu erstellt
6. **ApprovalDecision ist immutable** — einmal getroffen, nicht überschreibbar
7. **PromotionRequest mit Audit-Trail** — Zeitstempel, Quelle, Ziel

---

## Noch NICHT implementiert (Sprint 3 Scope)

| Feature | Status | Geplant |
|---------|--------|---------|
| Automatischer Git-Merge bei Promotion | Nur Plan/Dry-Run | Sprint 4 |
| QA-Gate vor Review | Modell, kein Code | Sprint 4 |
| Externer Intake → Ticket | Dokumentiert, nicht live | Sprint 5 |
| Multi-Ticket-Promotion (Batch) | Nicht modelliert | Sprint 5+ |
