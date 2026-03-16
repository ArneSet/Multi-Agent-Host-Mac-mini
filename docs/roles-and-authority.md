# HYBRIS Agent Host — Roles & Authority

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-2-domain-model`  
> **Status:** Sprint 2 — definiert, teilweise im Code durchgesetzt  

---

## Rollenübersicht

```
Creative Director (Mensch)
       │
       ▼
Director GPT (KI-Berater)
       │
       ▼
Orchestrator (orchestrator.py)
       │
       ├──▶ Code Worker
       ├──▶ Unity Worker
       ├──▶ Blender Worker
       ├──▶ Tripo Worker
       └──▶ QA (zukünftig)
```

---

## 1. Creative Director

**Rolle:** Mensch. Letzte Entscheidungsinstanz für alle Inhalte und Architektur.

| Berechtigung | Beschreibung |
|-------------|--------------|
| Tickets erstellen | Direkt oder über Director GPT |
| Tickets freigeben | `review` → `done` / `approved` |
| Tickets ablehnen | `review` → `rejected` |
| Promotion autorisieren | Einzige Rolle mit Prod-Freigabe |
| Architektur entscheiden | Systemdesign, Priorisierung, Scope |
| Agenten stoppen | Jederzeit Abbruch möglich |

**Regel:** Keine Änderung erreicht Production ohne Creative-Director-Approval.

---

## 2. Director GPT

**Rolle:** KI-Berater. Übersetzt Creative-Director-Intentionen in strukturierte Tickets und bewertet Ergebnisse.

| Berechtigung | Beschreibung |
|-------------|--------------|
| Tickets formulieren | Aus Creative-Director-Anfragen |
| Tickets triagieren | Priorisierung und Worker-Zuweisung |
| Review-Feedback geben | Empfehlungen an Creative Director |
| Re-Ticketing vorschlagen | Abgelehnte Tickets neu formulieren |

**Einschränkungen:**
- Kann nicht eigenständig in Production promoten
- Kann keine Agenten direkt steuern — nur über Tickets
- Empfiehlt, entscheidet nicht

**Aktueller Status:** Rolle wird manuell vom Creative Director übernommen. Keine technische Integration in Sprint 2.

---

## 3. Orchestrator

**Rolle:** Automatisierter Ticket-Prozessor. `orchestrator.py` + `cli.py`.

| Berechtigung | Beschreibung |
|-------------|--------------|
| Tickets validieren | Frontmatter-Parsing, Schema-Check |
| Tickets zwischen Zuständen bewegen | Gemäß `valid_transitions` |
| Worker dispatchen | Gemäß Ticket-`worker`-Feld und Allowlist |
| Logs schreiben | Unter `logs/orchestrator/` und `logs/worker/` |
| Branches validieren | Protected-Branch-Check vor Aktivierung |
| Ticket-Locks verwalten | `fcntl.flock` für concurrent processing |

**Einschränkungen:**
- Kann kein Ticket freigeben (`review` → `done` erfordert CD)
- Kann keine Promotion auslösen
- Kann keine neuen Worker-Typen registrieren (hardcoded `_WORKER_MODULE_MAP`)
- Kann keine Shell-Befehle aus Ticket-Inhalten ausführen
- Kann keinen protected Branch beschreiben

**Implementiert in:** `orchestrator.py`, `cli.py`

---

## 4. Workers

**Rolle:** Spezialisierte Ausführungsagenten. Führen die eigentliche Arbeit durch.

### Worker-Katalog

| Worker | Modul | Domäne | Status |
|--------|-------|--------|--------|
| `code-worker` | `workers/code_worker.py` | C#, Python, Config-Dateien | Stub |
| `unity-worker` | `workers/unity_worker.py` | Unity Editor, Szenen, Prefabs | Stub |
| `blender-worker` | `workers/blender_worker.py` | 3D-Modellierung, FBX-Export | Stub |
| `tripo-worker` | `workers/tripo_worker.py` | Tripo API, 3D-Generierung | Stub |

### Worker-Berechtigungen

| Berechtigung | Beschreibung |
|-------------|--------------|
| Auf zugewiesenem Branch arbeiten | Nur der im Ticket definierte Branch |
| Artefakte erzeugen | Unter `artifacts/` |
| Logs schreiben | Über `write_log()` |
| Erfolg/Misserfolg melden | Return-Dict an Orchestrator |

### Worker-Einschränkungen

| Einschränkung | Begründung |
|---------------|------------|
| Kein Zugriff auf protected Branches | `validate_branch()` |
| Kein Zugriff auf andere Tickets | Ticket-Lock + ID-Sanitization |
| Keine Shell-Exec aus Ticket-Content | `allow_shell_exec_from_tickets: false` |
| Keine eigenständige Promotion | Nur Orchestrator kann Zustände verschieben |
| Kein Netzwerkzugriff (aktuell) | Stubs, kein externer I/O |

---

## 5. QA

**Rolle:** Qualitätssicherung. Prüft Worker-Ergebnisse vor der Director-Review.

| Berechtigung | Beschreibung |
|-------------|--------------|
| Artefakte prüfen | Compile-Check, Test-Run, visuelle Prüfung |
| `active` → `qa` bestätigen | Automatisch oder manuell |
| `qa` → `review` promoten | Bei bestandener QA |
| `qa` → `failed` zurückweisen | Bei fehlgeschlagener QA |

**Aktueller Status:** Noch nicht implementiert. In Sprint 1/2 wird der QA-Schritt implizit als Teil von `review` behandelt. Eigenständiger QA-Zustand in Sprint 3.

---

## 6. Promotion Authority

**Rolle:** Kontrolliert den Fluss von abgenommener Arbeit in Zielumgebungen.

| Aktion | Autorität | Automatisierbar |
|--------|-----------|:---------------:|
| `review` → `approved` | Creative Director | Nein |
| `approved` → `promoted` (staging) | Orchestrator (nach CD-Approval) | Ja (Sprint 4+) |
| staging → production (merge) | Creative Director | Nein |

**Harte Regel:** Kein Code erreicht `main` ohne explizite Creative-Director-Freigabe. Dies gilt auch dann, wenn alle automatisierten Prüfungen bestehen.

---

## Autoritätsmatrix

| Aktion | CD | Dir. GPT | Orch. | Worker | QA |
|--------|:--:|:--------:|:-----:|:------:|:--:|
| Ticket erstellen | ✓ | ✓ | — | — | — |
| Ticket triagieren | ✓ | ✓ | — | — | — |
| Ticket validieren | — | — | ✓ | — | — |
| Worker dispatchen | — | — | ✓ | — | — |
| Code auf Branch schreiben | — | — | — | ✓ | — |
| Artefakte erzeugen | — | — | — | ✓ | — |
| QA durchführen | ✓ | — | — | — | ✓ |
| Review-Entscheidung | ✓ | empfiehlt | — | — | — |
| Promotion autorisieren | ✓ | empfiehlt | führt aus | — | — |
| System stoppen | ✓ | — | — | — | — |
| Config ändern | ✓ | — | — | — | — |

**Legende:** ✓ = autorisiert, — = nicht autorisiert, empfiehlt = beratend
