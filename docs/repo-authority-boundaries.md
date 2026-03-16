# HYBRIS Agent Host — Repo Authority Boundaries

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-3-dual-repo-promotion`  
> **Status:** Sprint 3 — enforced in code  

---

## Grundregel

```
Agenten haben NUR Schreibzugriff auf das Test Repo.
Das Prod Repo ist NUR durch explizite Promotion erreichbar.
Promotion erfordert IMMER Creative-Director-Approval.
```

---

## Autoritätsmatrix: Repo-Zugriff

| Rolle | Test Repo Lesen | Test Repo Schreiben | Prod Repo Lesen | Prod Repo Schreiben |
|-------|:---------------:|:-------------------:|:---------------:|:-------------------:|
| Creative Director | ✓ | ✓ | ✓ | ✓ (manuell) |
| Director GPT | ✓ | — | ✓ | — |
| Orchestrator | ✓ | — (dispatcht Worker) | ✓ | nur via Promotion |
| Workers / Agenten | ✓ | ✓ (eigener Branch) | — | — |
| QA | ✓ | — | ✓ | — |

---

## Was darf das Test Repo berühren?

| Aktor | Aktion | Erlaubt |
|-------|--------|:-------:|
| Worker | Code auf Feature-Branch schreiben | ✓ |
| Worker | Commits erstellen | ✓ |
| Worker | Artefakte erzeugen | ✓ |
| Worker | Protected Branch beschreiben | ✗ |
| Worker | Branch eines anderen Tickets modifizieren | ✗ |
| Orchestrator | Worker dispatchen | ✓ |
| Orchestrator | Ticket-Zustand ändern | ✓ |
| Director GPT | Code schreiben | ✗ |
| Creative Director | Manuell eingreifen | ✓ |

---

## Was darf das Prod Repo berühren?

| Aktor | Aktion | Erlaubt |
|-------|--------|:-------:|
| Worker / Agent | Direkt schreiben | ✗ |
| Worker / Agent | Branch erstellen | ✗ |
| Orchestrator | Automatisch mergen | ✗ |
| Orchestrator | Promotion nach Approval ausführen | ✓ |
| Creative Director | Manuell mergen / eingreifen | ✓ |
| Automatische Prozesse | Push auf main | ✗ |

---

## Code-Enforcement

### `resolve_agent_repo(cfg)`

Gibt **immer** den Pfad zum Test Repo zurück.

```python
def resolve_agent_repo(cfg: dict) -> str:
    return cfg["repo_targets"]["test_repo"]
```

### `validate_repo_target(cfg, target)`

Prüft, dass ein Repo-Target gültig und nicht `prod_repo` im Agent-Kontext ist.

### `dispatch_worker()` 

Übergibt `resolve_agent_repo(cfg)` als `repo_root` an Worker — niemals `prod_repo`.

### Promotion-Pfad

1. CLI `promote` prüft: ApprovalDecision vorhanden und `approved`?
2. CLI `promote --dry-run` zeigt Plan
3. CLI `promote` (ohne dry-run) erfordert Bestätigung
4. Promotion schreibt PromotionRequest mit Audit-Trail

---

## Zukünftiger Intake-Punkt

Wenn externer Intake (WhatsApp, OpenClaw o.Ä.) angebunden wird:

```
Externe Message
  └─▶ Intake Gateway (Sprint 5)
        └─▶ Ticket in inbox/
              └─▶ normaler Flow ─▶ Test Repo ─▶ Review ─▶ Prod Repo
```

Die Repo-Authority-Grenzen ändern sich **nicht** durch einen neuen Intake-Kanal. Der Intake ist austauschbar; die Repo-Architektur ist fix.

---

## Enforcement-Checkliste

| Prüfpunkt | Methode | Implementiert |
|-----------|---------|:-------------:|
| Agent-Repo resolves zu test_repo | `resolve_agent_repo()` | ✓ |
| Worker erhält nie prod_repo | `dispatch_worker()` Enforcement | ✓ |
| Promotion nur nach Approval | `create_promotion_request()` prüft | ✓ |
| Prod-Repo in Config geschützt | `repo_targets.prod_repo` separat | ✓ |
| Protected Branches blockiert | `validate_branch()` | ✓ |
| Tests validieren Enforcement | `test_orchestrator.py` | ✓ |
