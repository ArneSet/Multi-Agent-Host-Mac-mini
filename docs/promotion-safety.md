# Promotion Safety

> Sprint 4 — Physical Repo Separation and Promotion Safety

## Was Promotion bedeutet

Promotion ist der kontrollierte Transfer von Arbeitsergebnissen aus dem Test Repo
in das Prod Repo. Es ist **keine** automatische Operation und erfordert immer die
explizite Genehmigung des Creative Directors.

## Voraussetzungen für Promotion

Eine Promotion kann nur stattfinden, wenn alle folgenden Bedingungen erfüllt sind:

1. **Ticket existiert** und ist identifizierbar
2. **ReviewPackage existiert** (`reviews/<ticket_id>.review.json`)
3. **ApprovalDecision existiert** (`reviews/<ticket_id>.approval.json`)
4. **Entscheidung = `approved`** (nicht `rejected`, nicht `reticketed`)
5. **test_repo und prod_repo sind physisch getrennt** (Validierung)

## Was implementiert ist (Sprint 4)

### Promotion-Readiness-Check
- `check_promotion_readiness(cfg, ticket_id)` prüft alle Voraussetzungen
- Gibt strukturiertes Ergebnis mit `ready: bool` und `checks: [...]`
- Wird von CLI `promotion-check` und `promote` verwendet

### Promotion-Preview
- `create_promotion_request(cfg, ticket_id, dry_run=True)` erzeugt Plan ohne Schreibvorgang
- Zeigt: Source-Repo, Target-Repo, Branch, Approval-Status

### Promotion-Request
- `create_promotion_request(cfg, ticket_id)` schreibt `promotions/<ticket_id>.promotion.json`
- Status: `pending` — erfordert manuelle Ausführung

### Repo-Trennung-Validierung
- `validate_repo_separation(cfg)` prüft, dass test_repo ≠ prod_repo (real path)
- In `cmd_validate` und `promote` integriert

## Was bewusst manuell bleibt

| Aktion | Status | Grund |
|--------|--------|-------|
| Git merge/cherry-pick | Manuell | Zu riskant für automatische Ausführung |
| Git push | Manuell | Creative Director muss kontrollieren |
| Branch-Wahl in prod_repo | Manuell | Abhängig von Release-Strategie |
| Rollback bei fehlerhafter Promotion | Manuell | `git reset` in prod_repo |

## Was für Sprint 5+ aufgeschoben ist

- **Automatisierte Promotion-Ausführung** (git cherry-pick / merge mit Bestätigung)
- **Promotion-Status-Tracking** (pending → executing → completed / failed)
- **Promotion-History** pro Ticket
- **Diff-Summary** zwischen test und prod vor Promotion

## Ablaufdiagramm

```
Ticket in review
  └──▶ create_review_package()
         └──▶ Creative Director prüft
                ├──▶ approve → create_approval_decision("approved")
                │       └──▶ check_promotion_readiness()
                │               ├── ✓ all checks pass
                │               │       └──▶ create_promotion_request()
                │               │               └──▶ manueller Git-Transfer
                │               └── ✗ check fails → Fehler melden
                ├──▶ reject → create_approval_decision("rejected")
                │       └──▶ Ticket → failed
                └──▶ reticket → create_approval_decision("reticketed")
                        └──▶ Ticket → failed (neues Ticket erforderlich)
```
