# HYBRIS Agent Host — Ticket Lifecycle

> **Letzte Aktualisierung:** 2026-03-20
> **Status:** Sprint 11C — aktualisiert auf Code-Iststand

---

## Implementierter Lifecycle (Sprint 1–11)

Dies ist der aktuell im Code aktive Lebenszyklus, verifiziert gegen `config.json` und `orchestrator.py`.

```
inbox ──▶ ready ──▶ active ──▶ review ──▶ done
                       │         │
                       ▼         ▼
                     failed    active (rework → failed)
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
| `review` | `tickets/review/` | Worker fertig, wartet auf QA und Abnahme |
| `done` | `tickets/done/` | Abgenommen, bereit für Promotion-Pipeline |
| `failed` | `tickets/failed/` | Fehlgeschlagen |

**Quelle:** `config.json` → `ticket_states`

### Implementierte Transitionen

| Von | Nach | Auslöser | Autorität |
|-----|------|----------|-----------|
| `inbox` → `ready` | Ticket validiert, Worker identifiziert | Orchestrator / Operator |
| `ready` → `active` | Branch-Validierung + max_active geprüft | Orchestrator |
| `active` → `review` | Worker meldet Erfolg + Output Validation bestanden | Orchestrator |
| `active` → `failed` | Worker meldet Fehler oder Output Validation fehlgeschlagen | Orchestrator |
| `review` → `done` | `create_approval_decision()` mit `decision: "approved"` | Creative Director |
| `review` → `active` → `failed` | `create_approval_decision()` mit `decision: "rejected"` oder `"reticketed"` | Creative Director |
| `failed` → `ready` | Problem behoben, Retry freigegeben | Operator |

**Quelle:** `config.json` → `valid_transitions`, `orchestrator.py` → `transition_ticket()`, `create_approval_decision()`

### Sicherheits-Guards bei Transitionen

| Guard | Transition | Enforcement |
|-------|-----------|-------------|
| Branch-Validierung | ready → active | `validate_branch()` — kein protected Branch, kein Traversal |
| max_active_tickets | ready → active | Maximal 1 aktives Ticket (konfigurierbar) |
| Output Validation | active → review | `validate_worker_output()` muss bestehen |
| ReviewPackage Pflicht | review → done/failed (via approval) | `create_approval_decision()` ruft `load_review_package()` |

---

## Review-Phase im Detail (Sprint 5–11B)

Die `review`-Phase umfasst mehrere unabhängige, persistierte Records:

```
Ticket in review
    ↓
1. create_review_package()     → ReviewPackage   (reviews/{id}.review.json)
    ↓
2. create_qa_result()          → QA Record       (reviews/{id}.qa.json)
    ↓
3. create_approval_decision()  → Approval        (reviews/{id}.approval.json)
    ↓                            Ticket → done
4. check_promotion_readiness() → 6 Checks müssen bestehen
    ↓
5. create_promotion_request()  → PromotionRequest (promotions/{id}.promotion.json)
    ↓
6. execute_promotion()         → git fetch in prod_repo (manuell ausgelöst)
```

**Empfohlene Reihenfolge:** QA → Approval → PromotionRequest.
**Nicht hart erzwungen im Code:** Approval kann vor QA aufgezeichnet werden. Die Promotion-Gates prüfen beides unabhängig.

### Gate-Übersicht

| Gate | Typ | Wann | Blockiert was |
|------|-----|------|---------------|
| Output Validation | automatisch | nach Worker-Dispatch | Ticket → review (bei Fehler: → failed) |
| QA Gate | manuell | in review | Promotion (bei Fehler: blockiert PromotionRequest) |
| Approval | manuell | in review | Promotion (bei Fehler: blockiert PromotionRequest) |
| Promotion Readiness | automatisch | bei PromotionRequest | 6 Checks, alle müssen bestehen |

---

## Nicht implementierte Zielzustände (Sprint 2 Modell — historisch)

Die folgenden Zustände wurden in Sprint 2 als Zielmodell dokumentiert. Sie sind **nicht im Code implementiert** und werden hier nur als historische Referenz beibehalten.

| Zustand | Bedeutung | Status |
|---------|-----------|--------|
| `draft` | Erstellt, noch nicht triagiert | nicht implementiert |
| `triaged` | Director GPT hat priorisiert | nicht implementiert |
| `qa` | Eigenständiger QA-Zustand | nicht implementiert (QA läuft innerhalb `review`) |
| `approved` | Eigenständiger Approved-Zustand | nicht implementiert (via `done` + ApprovalDecision) |
| `rejected` | Eigenständiger Rejected-Zustand | nicht implementiert (via `failed` + ApprovalDecision) |
| `reticketed` | Eigenständiger Reticketed-Zustand | nicht implementiert (via `failed` + ApprovalDecision) |
| `promoted` | Eigenständiger Promoted-Zustand | nicht implementiert (via `done` + PromotionRequest) |

**Bewertung (Sprint 11C):** Die meisten Zielzustände werden aktuell durch die Kombination aus bestehenden Zuständen (`review`, `done`, `failed`) und persistierten Records (QA, Approval, PromotionRequest) abgedeckt. Eine Einführung separater Ticket-States für diese Phasen ist operativ aktuell nicht erforderlich.

---

## Regeln

1. **Ein aktives Ticket global** via `max_active_tickets` (default: 1)
2. **Branch-Validierung** vor Aktivierung: kein protected Branch, kein Traversal
3. **Ticket wird nie gelöscht** — nur zwischen Zustandsverzeichnissen verschoben
4. **Promotion ist nie automatisch** — erfordert QA + Approval + manuelle Ausführung
5. **Ticket-ID ist immutable** — wird bei Erstellung gesetzt, ändert sich nie
6. **Ticket-Dateien sind die Source of Truth** — kein externer State Store
7. **Kein Agent darf direkt auf prod_repo arbeiten** — Workers arbeiten nur auf test_repo
8. **Records (QA, Approval, PromotionRequest) sind immutable** — einmal geschrieben, nicht änderbar
