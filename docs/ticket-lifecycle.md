# HYBRIS Agent Host — Ticket Lifecycle

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-2-domain-model`  
> **Status:** Sprint 2 — Target Lifecycle modelliert, Implemented Lifecycle aktiv  

---

## Implementierter Lifecycle (Sprint 1)

Dies ist der aktuell im Code aktive Lebenszyklus.

```
inbox ──▶ ready ──▶ active ──▶ review ──▶ done
                       │         │
                       ▼         ▼
                     failed    active (rework)
                       │
                       ▼
                     ready (retry)
```

### Implementierte Zustände

| Zustand | Verzeichnis | Bedeutung |
|---------|-------------|-----------|
| `inbox` | `tickets/inbox/` | Neu eingegangen, noch nicht geprüft |
| `ready` | `tickets/ready/` | Validiert, Worker identifiziert, bereit zur Verarbeitung |
| `active` | `tickets/active/` | Worker arbeitet daran |
| `review` | `tickets/review/` | Worker fertig, wartet auf Abnahme |
| `done` | `tickets/done/` | Abgenommen und abgeschlossen |
| `failed` | `tickets/failed/` | Fehlgeschlagen |

### Implementierte Transitionen

| Von | Nach | Auslöser |
|-----|------|----------|
| `inbox` → `ready` | Ticket validiert, Worker identifiziert |
| `ready` → `active` | Orchestrator nimmt Ticket auf (Branch-Validierung, max_active geprüft) |
| `active` → `review` | Worker meldet Erfolg |
| `active` → `failed` | Worker meldet Fehler oder Abbruch |
| `review` → `done` | Creative Director gibt frei |
| `review` → `active` | Rework angefordert |
| `failed` → `ready` | Problem behoben, Retry freigegeben |

**Quelle:** `config.json` → `valid_transitions`, `orchestrator.py` → `transition_ticket()`

---

## Target Lifecycle (Sprint 2 Modell)

Dies ist der angestrebte, vollständige Lebenszyklus. Noch nicht im Code implementiert.

```
draft ──▶ triaged ──▶ ready ──▶ active ──▶ qa ──▶ review ──▶ approved ──▶ promoted
                        │         │                  │          │
                        │         ▼                  │          ▼
                        │       failed               │      rejected
                        │         │                  │          │
                        │         ▼                  │          ▼
                        │       ready (retry)        │      reticketed
                        │                            │
                        ▼                            ▼
                   ready (retry)              active (rework)
```

### Target Zustände

| Zustand | Bedeutung | Implementiert |
|---------|-----------|:-------------:|
| `draft` | Erstellt, noch nicht triagiert | — |
| `triaged` | Director GPT hat priorisiert und Worker zugewiesen | — |
| `ready` | Bereit zur Verarbeitung | ✓ (deckt `inbox`+`ready` ab) |
| `active` | Worker arbeitet | ✓ |
| `qa` | Automatische/manuelle Qualitätsprüfung | — |
| `review` | Wartet auf Creative-Director-Abnahme | ✓ |
| `approved` | Abgenommen, bereit zur Promotion | — |
| `rejected` | Abgelehnt, erfordert Neubewertung | — |
| `reticketed` | Aufgeteilt oder neu formuliert als neues Ticket | — |
| `promoted` | In Zielumgebung übernommen | — |
| `failed` | Technisch fehlgeschlagen | ✓ |

### Target Transitionen

| Von | Nach | Auslöser | Autorität |
|-----|------|----------|-----------|
| `draft` → `triaged` | Director GPT triagiert | Director GPT |
| `triaged` → `ready` | Orchestrator validiert Ticket | Orchestrator |
| `ready` → `active` | Orchestrator dispatcht Worker | Orchestrator |
| `active` → `qa` | Worker meldet Erfolg | Worker / Orchestrator |
| `active` → `failed` | Worker meldet Fehler | Worker / Orchestrator |
| `qa` → `review` | QA bestanden | QA / Orchestrator |
| `qa` → `failed` | QA fehlgeschlagen | QA / Orchestrator |
| `review` → `approved` | Creative Director gibt frei | Creative Director |
| `review` → `rejected` | Creative Director lehnt ab | Creative Director |
| `rejected` → `reticketed` | Wird als neues Ticket reformuliert | Director GPT |
| `approved` → `promoted` | In Zielumgebung übernommen | Orchestrator (nur nach CD-Approval) |
| `failed` → `ready` | Problem behoben, Retry | Director GPT / Orchestrator |

---

## Reconciliation: Implemented ↔ Target

| Implemented | Target-Äquivalent | Migration |
|-------------|-------------------|-----------|
| `inbox` | `draft` + `triaged` | `inbox` wird zu `draft`; `triaged` ist neu |
| `ready` | `ready` | Identisch |
| `active` | `active` | Identisch |
| — | `qa` | Neuer Zustand in Sprint 3+ |
| `review` | `review` | Identisch |
| — | `approved` | Neuer Zustand, aktuell in `review` → `done` zusammengefasst |
| — | `rejected` | Neuer Zustand, aktuell als `review` → `active` (rework) behandelt |
| — | `reticketed` | Neuer Zustand, manueller Prozess |
| `done` | `promoted` | `done` wird zu `promoted` |
| `failed` | `failed` | Identisch |

### Migrationsstrategie

**Konservativ:** Der implementierte Lifecycle bleibt in Sprint 2 unverändert. Die Target-States werden nur dokumentiert. Migration erfolgt schrittweise:

- **Sprint 3:** `qa` und `approved`/`rejected` einführen
- **Sprint 4:** `promoted` + PromotionTarget-Anbindung
- **Sprint 5:** `draft`/`triaged` mit externem Intake

Der Code bricht nicht, weil nur neue Zustände hinzukommen und bestehende Transitionen erhalten bleiben.

---

## Regeln

1. **Ein aktives Ticket pro Worker-Typ** (aktuell: ein aktives Ticket global via `max_active_tickets`)
2. **Branch-Validierung** vor Aktivierung: kein protected Branch, kein Traversal
3. **Ticket wird nie gelöscht** — nur zwischen Zustandsverzeichnissen verschoben
4. **Promotion ist nie automatisch** — Creative Director Approval ist mandatory
5. **Ticket-ID ist immutable** — wird bei Erstellung gesetzt, ändert sich nie
6. **Ticket-Dateien sind die Source of Truth** — kein externer State Store
