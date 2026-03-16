# HYBRIS Agent Host — System Reference (Source of Truth)

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `main` (Sprint 3)  
> **Repo:** `ArneSet/Multi-Agent-Host-Mac-mini`  
> **Host Role:** Lokaler Agent-Orchestrator für HYBRIS-Entwicklung  
> **Status:** Sprint 3 — Dual Repo Promotion Architecture  

---

## Inhaltsverzeichnis

1. [Projektidentität](#1-projektidentität)
2. [Betriebsziel / Purpose](#2-betriebsziel--purpose)
3. [Architektur-Übersicht](#3-architektur-übersicht)
4. [Tech Stack & Konventionen](#4-tech-stack--konventionen)
5. [Domain Model](#5-domain-model)
6. [Rollen & Autorität](#6-rollen--autorität)
7. [Ticket Lifecycle](#7-ticket-lifecycle)
8. [Worker-Katalog](#8-worker-katalog)
9. [Dual Repo Architecture](#9-dual-repo-architecture)
10. [Promotion Flow](#10-promotion-flow)
11. [Verzeichnis- und Pfadstruktur](#11-verzeichnis--und-pfadstruktur)
12. [Runtime State](#12-runtime-state)
13. [Sicherheits- und Freigaberegeln](#13-sicherheits--und-freigaberegeln)
14. [Bekannte Einschränkungen](#14-bekannte-einschränkungen)
15. [Git-Changelog](#15-git-changelog)
16. [Aktualisierungsprotokoll](#16-aktualisierungsprotokoll)

---

## 1. Projektidentität

**HYBRIS Agent Host** ist das lokale Orchestrierungssystem für die KI-gestützte Entwicklung des Spiels HYBRIS.

Es verwaltet den Fluss von Arbeitsaufträgen (Tickets) zwischen einem menschlichen Creative Director, einem beratenden Director GPT und spezialisierten KI-Agenten (Workers).

| Eigenschaft | Wert |
|-------------|------|
| **Projektname** | HYBRIS Agent Host |
| **Elternprojekt** | HYBRIS — Mythologisches Survival-RPG (2027) |
| **Repo** | `git@github.com:ArneSet/Multi-Agent-Host-Mac-mini.git` |
| **Game Repo** | `git@github.com:agentavis-ai/HYBRIS---Mortal-Realm.git` |
| **Host-Maschine** | Mac mini M4, macOS, Apple Silicon |
| **Betriebsart** | Lokaler kontrollierter Betrieb, kein Dauerbetrieb |

---

## 2. Betriebsziel / Purpose

### Ziel-Flow

```
Creative Director
  └──▶ Director GPT
         └──▶ Ticket (inbox)
                └──▶ Orchestrator
                       ├──▶ Code Worker
                       ├──▶ Unity Worker
                       ├──▶ Blender Worker
                       └──▶ Tripo Worker
                              └──▶ Artifacts + ChangeSet
                                     └──▶ QA
                                            └──▶ Review (Creative Director)
                                                   ├──▶ Approved → Promotion
                                                   └──▶ Rejected → Re-Ticket
```

### Nicht-Ziele (explizit ausgeschlossen)

- Kein Dauerbetrieb / Daemon
- Kein externer Intake (OpenClaw, SMS, WhatsApp)
- Keine automatische Promotion zu Production
- Keine GUI
- Kein Netzwerk-Listener
- Keine Parallelverarbeitung schwerer Worker

---

## 3. Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI LAYER (cli.py)                        │
│  Commands: list, show, process, transition, validate,       │
│           repo-targets, review-show, approve, reject,       │
│           reticket, promote                                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              ORCHESTRATOR (orchestrator.py)                  │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │ Sanitization │  │ Ticket Lock  │  │ Branch Validate │    │
│  │ ticket_id    │  │ fcntl.flock  │  │ protected list  │    │
│  │ path_within  │  │ per-ticket   │  │ regex + guard   │    │
│  └─────────────┘  └──────────────┘  └─────────────────┘    │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │ Parse Ticket│  │ Atomic Move  │  │ State Machine   │    │
│  │ YAML front  │  │ copy+rename  │  │ config-driven   │    │
│  │ matter lite │  │ POSIX atomic │  │ valid_transitions│    │
│  └─────────────┘  └──────────────┘  └─────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Worker Dispatch                         │    │
│  │  _WORKER_MODULE_MAP (hardcoded) ∩ config allowlist   │    │
│  │  → resolve_agent_repo() enforces test_repo only      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Review / Approval / Promotion                │    │
│  │  create_review_package → create_approval_decision    │    │
│  │  → create_promotion_request (approved only)          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   WORKER LAYER (workers/)                    │
│                                                             │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────┐ ┌────────┐  │
│  │ code_worker │ │ unity_worker │ │ blender  │ │ tripo  │  │
│  │    (stub)   │ │    (stub)    │ │  (stub)  │ │ (stub) │  │
│  └─────────────┘ └──────────────┘ └──────────┘ └────────┘  │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              FILE SYSTEM STATE (management/)                 │
│                                                             │
│  tickets/           logs/              artifacts/            │
│  ├── inbox/         ├── orchestrator/  └── *.md             │
│  ├── ready/         └── worker/                             │
│  ├── active/                           sessions/            │
│  ├── review/        locks/             └── (future)         │
│  ├── done/          └── *.lock                              │
│  └── failed/                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Tech Stack & Konventionen

### Runtime

| Komponente | Version / Details |
|------------|------------------|
| **Python** | 3.9+ (System Python, macOS) |
| **Dependencies** | stdlib only — kein `pip install`, kein venv |
| **OS** | macOS Apple Silicon (Mac mini M4) |
| **Locking** | `fcntl.flock` (POSIX, lokal) |
| **State Storage** | Dateisystem — Markdown-Dateien in Verzeichnissen |

### Konventionen

| Konvention | Regel |
|-----------|-------|
| **Commits** | Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) |
| **Branches** | Nie auf `main`/`master`/`develop` — immer Feature-Branch |
| **Merge-Art** | Squash Merge bevorzugt |
| **Ticket-IDs** | `^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$` |
| **Branch-Namen** | `^[a-zA-Z0-9][a-zA-Z0-9./_-]{0,255}$` |
| **Config** | `config.json` (lokal, gitignored) / `config.example.json` (Template) |
| **Sprache** | Code + Commit Messages auf Englisch, Dokumentation Deutsch oder Englisch |

---

## 5. Domain Model

> Vollständige Definition: [docs/domain-model.md](docs/domain-model.md)

### Kernkonzepte

| Konzept | Aggregate | Implementiert |
|---------|:---------:|:-------------:|
| **Ticket** | Root | ✓ |
| DirectorRequest | — | Modell |
| AgentRun | Ticket | teilweise |
| WorkerType | Ticket | ✓ |
| Artifact | Ticket | teilweise |
| ChangeSet | Ticket | Modell |
| ReviewPackage | Ticket | Modell |
| ApprovalDecision | Ticket | Modell |
| PromotionRequest | Ticket | Modell |
| PromotionTarget | — | Modell |

**Zentrales Aggregate:** Das **Ticket** ist das Aggregate Root. Alle anderen Konzepte existieren in Bezug auf ein Ticket.

---

## 6. Rollen & Autorität

> Vollständige Definition: [docs/roles-and-authority.md](docs/roles-and-authority.md)

| Rolle | Typ | Kernberechtigung |
|-------|-----|-----------------|
| **Creative Director** | Mensch | Letzte Entscheidung, Promotion, Stopp |
| **Director GPT** | KI-Berater | Tickets formulieren, triagieren, empfehlen |
| **Orchestrator** | Automation | Tickets validieren, dispatchen, bewegen |
| **Workers** | KI-Agenten | Code/Assets auf zugewiesenem Branch produzieren |
| **QA** | Automation (Sprint 3+) | Artefakte prüfen, qa-Gate |

**Harte Regel:** Promotion zu Production ist niemals automatisch. Creative-Director-Approval bleibt mandatory.

---

## 7. Ticket Lifecycle

> Vollständige Definition: [docs/ticket-lifecycle.md](docs/ticket-lifecycle.md)

### Implementierter Lifecycle (Sprint 1)

```
inbox → ready → active → review → done
                  ↓         ↓
                failed    active (rework)
                  ↓
                ready (retry)
```

### Target Lifecycle (Sprint 2 Modell)

```
draft → triaged → ready → active → qa → review → approved → promoted
                    ↓        ↓              ↓         ↓
                  (retry)  failed       (rework)   rejected → reticketed
```

Migration erfolgt konservativ über mehrere Sprints. Der implementierte Lifecycle bleibt in Sprint 2 aktiv.

---

## 8. Worker-Katalog

| Worker | Modul | Domäne | Status |
|--------|-------|--------|--------|
| `code-worker` | `workers/code_worker.py` | C#, Python, Config | Stub |
| `unity-worker` | `workers/unity_worker.py` | Unity Editor, Szenen, Prefabs | Stub |
| `blender-worker` | `workers/blender_worker.py` | 3D-Modellierung, FBX-Export | Stub |
| `tripo-worker` | `workers/tripo_worker.py` | Tripo API, 3D-Generierung | Stub |

### Dispatch-Mechanismus

1. Ticket enthält `worker: <name>`
2. Orchestrator prüft `config.allowed_workers` (Config Gate)
3. Orchestrator prüft `_WORKER_MODULE_MAP` (Code Gate)
4. Nur wenn beide Gates passieren → `workers/<module>.execute()` wird aufgerufen
5. Worker gibt zurück: `{success: bool, message: str, artifacts: list}`

### Worker-Interface

```python
def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    """
    Returns: {"success": bool, "message": str, "artifacts": list}
    """
```

---

## 9. Dual Repo Architecture

> Vollständige Definition: [docs/dual-repo-architecture.md](docs/dual-repo-architecture.md)

### Prinzip

Agenten arbeiten **ausschließlich** im **Test Repo**. Das **Prod Repo** ist nur über eine genehmigte Promotion erreichbar. Kein Agent hat jemals direkten Schreibzugriff auf Prod.

### Repo Targets in Config

```json
"repo_targets": {
  "test_repo": "/path/to/test/game-repo",
  "prod_repo": "/path/to/prod/game-repo"
}
```

### Code-Enforcement

| Funktion | Zweck |
|----------|-------|
| `resolve_agent_repo(cfg)` | Gibt immer `test_repo` zurück — einziger Repo-Pfad für Worker |
| `resolve_prod_repo(cfg)` | Gibt `prod_repo` zurück — nur für Promotion |
| `validate_repo_target(cfg, target, allow_prod)` | Blockiert `prod_repo` als Agent-Ziel |
| `dispatch_worker()` | Setzt `_agent_repo` im Worker-Config auf `test_repo` |

### Autoritätsmatrix

| Aktor | test_repo | prod_repo |
|-------|:---------:|:---------:|
| Worker (Agent) | Lesen + Schreiben | ✗ Kein Zugriff |
| Orchestrator | Verwalten | Nur Promotion-Pfad |
| Creative Director | Voll | Voll |

---

## 10. Promotion Flow

> Vollständige Definition: [docs/promotion-flow.md](docs/promotion-flow.md)

### Ablauf

```
Ticket in review
  └──▶ create_review_package()
         └──▶ Creative Director prüft
                ├──▶ approve → create_approval_decision("approved")
                │       └──▶ create_promotion_request()
                │               └──▶ test_repo → prod_repo (manuell/skript)
                ├──▶ reject → create_approval_decision("rejected")
                │       └──▶ Ticket → failed
                └──▶ reticket → create_approval_decision("reticketed")
                        └──▶ Ticket → failed (neues Ticket erforderlich)
```

### Regeln

1. **ReviewPackage** muss existieren, bevor eine Entscheidung getroffen wird
2. **ApprovalDecision** ist immutabel — einmal gesetzt, nicht änderbar
3. **PromotionRequest** erfordert `decision == "approved"`
4. Promotion ist **nie automatisch** — Creative Director muss genehmigen
5. `--dry-run` bei Promotion schreibt keine Datei

### CLI-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `review-show TICKET_ID` | ReviewPackage anzeigen (erstellt es bei Bedarf) |
| `approve TICKET_ID` | Ticket genehmigen |
| `reject TICKET_ID` | Ticket ablehnen |
| `reticket TICKET_ID` | Ticket zurückgeben (neuer Scope) |
| `promote TICKET_ID` | Promotion-Request erstellen |
| `repo-targets` | Konfigurierte Repo-Targets anzeigen |

---

## 11. Verzeichnis- und Pfadstruktur

### Host Repo (`hybris-host/`)

```
hybris-host/
├── AGENT_HOST_SYSTEM_REFERENCE.md    ← dieses Dokument
├── README.md                          ← Operator-Anleitung
├── orchestrator.py                    ← Kern-State-Machine
├── cli.py                             ← CLI-Entrypoint
├── config.json                        ← Lokale Config (gitignored)
├── config.example.json                ← Config-Template
├── test_orchestrator.py               ← Unit Tests (34 Tests)
├── ticket_schema.md                   ← Ticket-Format-Referenz
├── docs/
│   ├── domain-model.md                ← Domain Model
│   ├── ticket-lifecycle.md            ← Lifecycle-Definition
│   ├── roles-and-authority.md         ← Rollen & Autoritätsmatrix
│   ├── dual-repo-architecture.md      ← Dual Repo (Sprint 3)
│   ├── promotion-flow.md              ← Promotion Flow (Sprint 3)
│   └── repo-authority-boundaries.md   ← Repo Authority (Sprint 3)
└── workers/
    ├── __init__.py
    ├── base_worker.py
    ├── code_worker.py
    ├── unity_worker.py
    ├── blender_worker.py
    └── tripo_worker.py
```

### Runtime / Management (`management/`)

```
~/Workspace/HYBRIS/management/
├── tickets/
│   ├── inbox/          ← Neue Tickets
│   ├── ready/          ← Validiert, bereit
│   ├── active/         ← In Bearbeitung
│   ├── review/         ← Wartet auf Abnahme
│   ├── done/           ← Abgeschlossen
│   └── failed/         ← Fehlgeschlagen
├── logs/
│   ├── orchestrator/   ← Orchestrator-Logs pro Ticket
│   └── worker/         ← Worker-Logs pro Ticket
├── artifacts/          ← Worker-Ausgaben
├── reviews/            ← ReviewPackages + ApprovalDecisions
├── promotions/         ← PromotionRequests
├── sessions/           ← (zukünftig)
└── locks/              ← fcntl Lock-Files pro Ticket
```

### Pfade in Config

| Config-Key | Beschreibung | Beispiel |
|-----------|--------------|---------|
| `game_repo_root` | Pfad zum HYBRIS Game Repo (Legacy) | `~/Workspace/HYBRIS/repos/hybris-game` |
| `host_repo_root` | Pfad zum Host Repo | `~/Workspace/HYBRIS/repos/hybris-host` |
| `management_root` | Runtime-Daten (nicht versioniert) | `~/Workspace/HYBRIS/management` |
| `repo_targets.test_repo` | Agent-Arbeitsrepo (nur Lesen+Schreiben) | `~/Desktop/HYBRIS - Mortal Realm` |
| `repo_targets.prod_repo` | Produktionsrepo (nur Promotion) | `~/Desktop/HYBRIS - Mortal Realm` |

---

## 12. Runtime State

### Tickets

- **Format:** Markdown mit YAML-Frontmatter
- **Speicherung:** Physisch im Zustandsverzeichnis unter `tickets/<state>/`
- **Zustandswechsel:** Datei wird atomar zwischen Verzeichnissen verschoben
- **Keine Datenbank:** Dateisystem ist die Source of Truth

### Logs

- **Orchestrator-Logs:** `logs/orchestrator/<ticket_id>.log`
- **Worker-Logs:** `logs/worker/<ticket_id>.log`
- **Format:** `[ISO-8601] Nachricht\n`
- **Pfad-Sanitization:** Category und Ticket-ID werden gegen Traversal geprüft

### Artifacts

- **Pfad:** `artifacts/<ticket_id>_<worker>_result.md`
- **Erzeugt von:** Workers
- **Kein formales Schema** — Freiformat, wird in Sprint 3 strukturiert

### Locks

- **Pfad:** `locks/<ticket_id>.lock`
- **Mechanismus:** `fcntl.flock(LOCK_EX | LOCK_NB)`
- **Inhalt:** PID des haltenden Prozesses
- **Cleanup:** Automatisch bei Prozessende

---

### Reviews

- **ReviewPackage:** `reviews/<ticket_id>.review.json` — Prüfpaket mit Artefakten, Branch, Worker
- **ApprovalDecision:** `reviews/<ticket_id>.approval.json` — Immutable Entscheidung (approved/rejected/reticketed)
- **Erzeugt durch:** `create_review_package()`, `create_approval_decision()`

### Promotions

- **PromotionRequest:** `promotions/<ticket_id>.promotion.json` — Promotion von test_repo → prod_repo
- **Erfordert:** Approved ApprovalDecision
- **Status:** `pending` (erstellt), `dry_run` (Simulation)

---

## 13. Sicherheits- und Freigaberegeln

### Eingabe-Sanitization

| Vektor | Schutz | Implementiert |
|--------|--------|:-------------:|
| Ticket-ID Traversal | `sanitize_ticket_id()` — Regex + Traversal-Check | ✓ |
| Pfad-Escape | `sanitize_path_within()` — resolve + relative_to | ✓ |
| Branch Injection | `validate_branch()` — Regex + Protected-List | ✓ |
| Log-Pfad Traversal | `write_log()` — Category-Regex + path_within | ✓ |
| Worker Injection | Doppeltes Gate: hardcoded Map ∩ Config Allowlist | ✓ |
| Repo Access | `validate_repo_target()` — Agents blocked from prod_repo | ✓ |
| Promotion | Requires approved ApprovalDecision, immutable records | ✓ |

### Concurrency

| Schutz | Mechanismus | Implementiert |
|--------|-------------|:-------------:|
| Doppelverarbeitung | `ticket_lock()` → `fcntl.flock` | ✓ |
| Atomare Zustandswechsel | `atomic_move()` → copy + rename | ✓ |
| Temp-File Isolation | `.tmp_`-Prefix, übersprungen bei Listing | ✓ |

### Branch-Schutz

| Regel | Details |
|-------|---------|
| Protected Branches | `main`, `master`, `develop` — konfigurierbar |
| Validierung | Vor jeder Aktivierung (`ready` → `active`) |
| Traversal-Block | `..` in Branch-Namen wird abgelehnt |

### Freigabe-Regeln

| Aktion | Erlaubt für |
|--------|------------|
| Lokaler kontrollierter Betrieb | ✓ Ja |
| Sprint-2-Vorbereitung | ✓ Ja |
| Externer Intake | ✗ Nein |
| Unbeaufsichtigter Dauerbetrieb | ✗ Nein |
| Parallele schwere Worker | ✗ Nein |
| Automatische Prod-Promotion | ✗ Nein |

---

## 14. Bekannte Einschränkungen

| # | Einschränkung | Risiko | Geplant für |
|---|--------------|--------|-------------|
| 1 | `atomic_move()` nur innerhalb gleichen Filesystems sauber | Niedrig (lokal) | Sprint 3: Temp-Strategie |
| 2 | Kein Subprocess-Timeout / Resource Caps für Worker | Mittel (bei echten Workern) | Sprint 3 |
| 3 | Kein `status.json` pro Ticket | Niedrig | Sprint 3 |
| 4 | Kein Audit-Record für `review` → `done` | Mittel | Sprint 3 |
| 5 | Worker sind Stubs — keine echte Ausführung | Erwartungsgemäß | Sprint 3+ |
| 6 | QA-Zustand nicht implementiert | Erwartungsgemäß | Sprint 3 |
| 7 | DirectorRequest nur als manuelles Ticket | Erwartungsgemäß | Sprint 5 |
| 8 | `fcntl.flock` nur lokal (kein NFS/Multi-Host) | Niedrig (einzelner Host) | — |
| 9 | Kein Retry-Counter / Max-Retries | Niedrig | Sprint 3 |
| 10 | Desktop-Pfad im Game Repo noch nicht migriert | Betriebsrisiko | Sprint 4 |
| 11 | test_repo und prod_repo zeigen aktuell auf gleichen Pfad | Betriebsrisiko | Sprint 4: Repo-Split |
| 12 | Promotion führt noch keine Git-Operationen aus | Erwartungsgemäß | Sprint 4 |
| 13 | Kein QA-Gate zwischen active und review | Erwartungsgemäß | Sprint 4 |

---

## 15. Git-Changelog

| Datum | Commit | Beschreibung |
|-------|--------|--------------|
| 2026-03-16 | `d16d0bf` | Sprint 1: Hardened Host Orchestrator Baseline (squash merge) |
| 2026-03-16 | `v0.1.0` | Tag: Sprint 1 Release |
| 2026-03-16 | `a3f2f5d` | Sprint 2: Domain Model + System Reference (squash merge) |
| 2026-03-16 | `v0.2.0` | Tag: Sprint 2 Release |
| 2026-03-16 | — | Sprint 3: Dual Repo Promotion Architecture (this branch) |

---

## 16. Aktualisierungsprotokoll

| Datum | Autor | Änderung |
|-------|-------|----------|
| 2026-03-16 | Sprint 2 Agent | Erstversion: System Reference, Domain Model, Ticket Lifecycle, Roles & Authority |
| 2026-03-16 | Sprint 3 Agent | Dual Repo Architecture, Promotion Flow, Repo Authority, CLI-Erweiterung, 22 neue Tests |
