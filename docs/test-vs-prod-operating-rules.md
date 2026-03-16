# Test vs. Prod Operating Rules

> Sprint 4 — Physical Repo Separation and Promotion Safety

## Grundprinzip

**Test Repo** und **Prod Repo** sind physisch getrennte lokale Git-Klone desselben Remotes.
Agenten arbeiten ausschließlich im Test Repo. Das Prod Repo ist durch Code und Validierung
vor direktem Agent-Zugriff geschützt.

## Was Agenten im test_repo dürfen

| Aktion | Erlaubt |
|--------|:-------:|
| Dateien lesen | ✓ |
| Dateien schreiben / erstellen | ✓ |
| Feature-Branches erstellen | ✓ |
| Commits erstellen | ✓ |
| Unity-Assets modifizieren | ✓ |
| Auf `main` mergen | ✗ (protected branch) |
| Auf `master` mergen | ✗ (protected branch) |
| Force-Push | ✗ (Konvention, nicht erzwungen) |

## Was im prod_repo verboten ist

| Aktion | Status |
|--------|:------:|
| Worker-Ausführung | ✗ Blockiert durch `validate_repo_target()` |
| Agent-Schreibzugriff | ✗ Blockiert durch `resolve_agent_repo()` |
| Direkte Dateiänderung durch Agenten | ✗ Pfad nie an Worker übergeben |
| Automatische Promotion | ✗ Nicht implementiert |

## Was nur der Creative Director autorisieren darf

1. **Approval-Entscheidung** (`approved` / `rejected` / `reticketed`)
2. **Promotion-Auslösung** (manuelles Git-Transfer von test → prod)
3. **Direkter Zugriff auf prod_repo** (git push, merge, cherry-pick)
4. **Konfigurationsänderungen** an `config.json`
5. **Stopp des Orchestrators** bei erkannten Problemen

## Was der Orchestrator darf und nicht darf

### Darf
- Tickets zwischen Zuständen bewegen (per konfigurierter State Machine)
- Worker dispatchen (nur gegen test_repo)
- ReviewPackages erstellen
- ApprovalDecisions aufzeichnen
- PromotionRequests erstellen (nur als Plan)
- Logs schreiben

### Darf nicht
- Auf prod_repo zugreifen (außer Path-Resolution für Promotion-Plan)
- Automatisch mergen oder pushen
- Approval-Entscheidungen selbst treffen
- Tickets ohne Genehmigung promovieren
- Im Hintergrund laufen (kein Daemon)

## Code-Enforcement

| Funktion | Schutz |
|----------|--------|
| `resolve_agent_repo(cfg)` | Gibt immer `test_repo` zurück |
| `validate_repo_target(cfg, target)` | Blockiert `prod_repo` als Agent-Ziel |
| `validate_repo_separation(cfg)` | Prüft physische Pfadtrennung |
| `dispatch_worker()` | Setzt `_agent_repo = test_repo` |
| `check_promotion_readiness()` | Prüft Approval + Repo-Trennung vor Promotion |
