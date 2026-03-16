# HYBRIS Agent Host — System Reference (Source of Truth)

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-7-whatsapp-connector` (Sprint 7)  
> **Repo:** `ArneSet/Multi-Agent-Host-Mac-mini`  
> **Host Role:** Lokaler Agent-Orchestrator für HYBRIS-Entwicklung  
> **Status:** Sprint 7 — Real WhatsApp Connector Boundary  

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
14. [External Intake Adapter](#14-external-intake-adapter)
15. [WhatsApp Connector Boundary](#15-whatsapp-connector-boundary)
16. [Bekannte Einschränkungen](#16-bekannte-einschränkungen)
17. [Git-Changelog](#17-git-changelog)
18. [Aktualisierungsprotokoll](#18-aktualisierungsprotokoll)

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

## 9. Dual Repo Architecture — Physical Separation

> Vollständige Definition: [docs/dual-repo-architecture.md](docs/dual-repo-architecture.md)  
> Physische Trennung: [docs/physical-repo-separation.md](docs/physical-repo-separation.md)  
> Betriebsregeln: [docs/test-vs-prod-operating-rules.md](docs/test-vs-prod-operating-rules.md)

### Prinzip

Agenten arbeiten **ausschließlich** im **Test Repo**. Das **Prod Repo** ist nur über eine genehmigte Promotion erreichbar. Kein Agent hat jemals direkten Schreibzugriff auf Prod.

**Ab Sprint 4** sind test_repo und prod_repo **physisch getrennte Git-Clones** mit eigenen `.git`-Verzeichnissen. `validate_repo_separation()` erzwingt, dass beide via `Path.resolve()` auf unterschiedliche Pfade zeigen. Symlinks, relative Pfade und Duplikate werden erkannt und blockiert.

### Physisches Layout

```
~/Workspace/HYBRIS/repos/
├── hybris-host/    ← Host-Repo (Orchestrator, CLI, Config)
├── hybris-test/    ← Agent-Arbeitsrepo (frischer Clone)
└── hybris-prod/    ← Produktionsrepo (nur Promotion)
```

Beide Game-Repos sind Clones von `agentavis-ai/HYBRIS---Mortal-Realm.git`.

### Repo Targets in Config

```json
"repo_targets": {
  "test_repo": "~/Workspace/HYBRIS/repos/hybris-test",
  "prod_repo": "~/Workspace/HYBRIS/repos/hybris-prod"
}
```

### Code-Enforcement

| Funktion | Zweck |
|----------|-------|
| `resolve_agent_repo(cfg)` | Gibt immer `test_repo` zurück — einziger Repo-Pfad für Worker |
| `resolve_prod_repo(cfg)` | Gibt `prod_repo` zurück — nur für Promotion |
| `validate_repo_target(cfg, target, allow_prod)` | Blockiert `prod_repo` als Agent-Ziel |
| `validate_repo_separation(cfg)` | Prüft physische Trennung via `Path.resolve()` — **Sprint 4** |
| `check_promotion_readiness(cfg, ticket_id)` | 6-Punkt-Readiness-Check vor Promotion — **Sprint 5** |
| `create_qa_result(cfg, ticket_id, passed, notes)` | QA-Ergebnis aufzeichnen (immutabel) — **Sprint 5** |
| `execute_promotion(cfg, ticket_id, dry_run)` | Git fetch von test_repo → prod_repo — **Sprint 5** |
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
6. **Repo-Separation** wird vor jeder Promotion geprüft (`validate_repo_separation`) — **Sprint 4**
7. **Readiness-Check** prüft 6 Bedingungen vor Promotion-Erstellung — **Sprint 5** (inkl. QA)
8. **QA-Gate** muss bestanden sein, bevor Promotion erstellt wird — **Sprint 5**
9. **Execution** nur mit explizitem `--execute` Flag — **Sprint 5**
10. **Audit-Record** für jeden Promotion-Versuch (Preview + Execute) — **Sprint 5**

> Promotion Safety: [docs/promotion-safety.md](docs/promotion-safety.md)  
> QA Gate: [docs/qa-gate.md](docs/qa-gate.md)  
> Manual Promotion: [docs/manual-promotion-execution.md](docs/manual-promotion-execution.md)  
> Audit Trail: [docs/promotion-audit-trail.md](docs/promotion-audit-trail.md)

### CLI-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `review-show TICKET_ID` | ReviewPackage anzeigen (erstellt es bei Bedarf) |
| `approve TICKET_ID` | Ticket genehmigen |
| `reject TICKET_ID` | Ticket ablehnen |
| `reticket TICKET_ID` | Ticket zurückgeben (neuer Scope) |
| `promote TICKET_ID` | Promotion-Request erstellen |
| `promote TICKET_ID --preview` | Promotion-Execution Vorschau — **Sprint 5** |
| `promote TICKET_ID --execute` | Promotion ausführen (git fetch) — **Sprint 5** |
| `promotion-check TICKET_ID` | Readiness-Check vor Promotion |
| `qa-pass TICKET_ID` | QA als bestanden markieren — **Sprint 5** |
| `qa-fail TICKET_ID` | QA als fehlgeschlagen markieren — **Sprint 5** |
| `qa-check TICKET_ID` | QA-Status anzeigen — **Sprint 5** |
| `promotion-status TICKET_ID` | Promotion-Status anzeigen — **Sprint 5** |
| `audit-show TICKET_ID` | Audit-Trail anzeigen — **Sprint 5** |
| `repo-targets` | Konfigurierte Repo-Targets anzeigen (mit Separation-Status) |

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
├── test_orchestrator.py               ← Unit Tests (86 Tests)
├── ticket_schema.md                   ← Ticket-Format-Referenz
├── docs/
│   ├── domain-model.md                ← Domain Model
│   ├── ticket-lifecycle.md            ← Lifecycle-Definition
│   ├── roles-and-authority.md         ← Rollen & Autoritätsmatrix
│   ├── dual-repo-architecture.md      ← Dual Repo (Sprint 3)
│   ├── promotion-flow.md              ← Promotion Flow (Sprint 3)
│   ├── repo-authority-boundaries.md   ← Repo Authority (Sprint 3)
│   ├── physical-repo-separation.md    ← Physische Trennung (Sprint 4)
│   ├── promotion-safety.md            ← Promotion Safety (Sprint 4)
│   ├── test-vs-prod-operating-rules.md ← Betriebsregeln (Sprint 4)
│   ├── qa-gate.md                     ← QA Gate (Sprint 5)
│   ├── manual-promotion-execution.md  ← Manuelle Promotion (Sprint 5)
│   ├── promotion-audit-trail.md       ← Audit Trail (Sprint 5)
│   └── external-intake-readiness.md   ← Intake-Readiness (Sprint 5)
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
│   └── audit/          ← Promotion Audit Trail (JSONL)
├── sessions/           ← (zukünftig)
└── locks/              ← fcntl Lock-Files pro Ticket
```

### Pfade in Config

| Config-Key | Beschreibung | Beispiel |
|-----------|--------------|---------|
| `game_repo_root` | Pfad zum HYBRIS Game Repo (Legacy) | `~/Workspace/HYBRIS/repos/hybris-game` |
| `host_repo_root` | Pfad zum Host Repo | `~/Workspace/HYBRIS/repos/hybris-host` |
| `management_root` | Runtime-Daten (nicht versioniert) | `~/Workspace/HYBRIS/management` |
| `repo_targets.test_repo` | Agent-Arbeitsrepo (physisch getrennt) | `~/Workspace/HYBRIS/repos/hybris-test` |
| `repo_targets.prod_repo` | Produktionsrepo (nur Promotion) | `~/Workspace/HYBRIS/repos/hybris-prod` |

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
- **Status:** `pending → previewed → executed` (oder `failed`)
- **Status-History:** Array von Statusübergängen mit Timestamps
- **Erfordert:** Approved ApprovalDecision + QA passed

### QA Results

- **QA-Ergebnis:** `reviews/<ticket_id>.qa.json` — Immutables QA-Validierungsergebnis
- **Erzeugt durch:** `create_qa_result()` (via `qa-pass` / `qa-fail` CLI)
- **Immutabel:** Einmal gesetzt, nicht änderbar

### Promotion Audit Trail

- **Audit-Datei:** `promotions/audit/<ticket_id>.audit.jsonl` — JSONL-Format
- **Erzeugt durch:** `execute_promotion()` (Preview + Execute)
- **Append-only:** Neue Records werden angehängt, nie geändert
- **Inhalt:** ticket_id, source/target repo, branch, commit, action, result, timestamp

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
| Repo Separation | `validate_repo_separation()` — test≠prod via Path.resolve() | ✓ |
| Promotion | Requires approved ApprovalDecision, immutable records | ✓ |
| Promotion Readiness | `check_promotion_readiness()` — 6-point check before promotion | ✓ |
| QA Gate | `create_qa_result()` — immutable QA validation before promotion | ✓ |
| Promotion Execution | `execute_promotion()` — explicit `--execute` flag required | ✓ |
| Promotion Audit | `_append_audit_record()` — every attempt recorded in JSONL | ✓ |

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

## 14. External Intake Adapter

> Sprint 6 — Safe message-to-ticket intake pipeline.

### Intake Module (`intake.py`)

Standalone module that receives, validates, normalizes, and admits external requests into the ticket system. Strictly separated from execution code.

### Intake Constants

| Constant | Values |
|----------|--------|
| `INTAKE_SOURCES` | `local_simulated`, `future_whatsapp`, `future_openclaw`, `future_sms`, `future_api` |
| `SOURCE_TRUST_LEVELS` | `trusted`, `untrusted`, `blocked` |
| `INTAKE_STATUSES` | `received`, `rejected`, `normalized`, `admitted`, `duplicate`, `rate_limited`, `failed` |

### Pipeline Stages

1. Validate source → 2. Check trust → 3. Validate payload → 4. Check duplicate → 5. Check rate limit → 6. Normalize → 7. Admit (inbox) → 8. Audit

### Safety Boundary

- `intake.py` does NOT import `dispatch_worker`, `execute_promotion`, or `process_ticket`
- No git operations, no repo access
- Admitted tickets land in inbox only — manual lifecycle continues

### CLI Commands (Sprint 6)

| Command | Beschreibung |
|---------|-------------|
| `intake-config` | Show intake configuration |
| `intake-validate SOURCE --title --worker` | Validate intake request |
| `intake-simulate SOURCE --title --worker` | Simulate pipeline (dry-run) |
| `intake-submit SOURCE --title --worker` | Submit and admit to inbox |
| `intake-normalize SOURCE --title --worker` | Show normalization result |
| `intake-audit-show` | Show intake audit trail |
| `intake-status` | Show intake system status |

### Config Section (v1.3.0)

```json
"intake": {
    "trusted_sources": ["local_simulated"],
    "blocked_sources": [],
    "rate_limit": { "max_per_source_per_minute": 5, "max_global_per_minute": 20 },
    "duplicate_window_seconds": 300
}
```

### Intake State Files

| Pfad | Funktion |
|------|----------|
| `management/intake/state/seen_hashes.json` | Duplicate detection state |
| `management/intake/state/rate_state.json` | Rate limit counters |
| `management/intake/audit/intake.audit.jsonl` | Append-only audit trail |

### Tests

65 tests in `test_intake.py` covering: source validation, trust levels, payload validation, unsafe content, sanitization, normalization, duplicates, rate limiting, admission, rejection, audit, and safety guarantees.

---

## 15. WhatsApp Connector Boundary

### Architektur

Der WhatsApp Connector stellt die erste reale Messaging-Grenze dar. Er terminiert an der Intake-Schicht und stellt sicher, dass WhatsApp-Nachrichten niemals direkt ausführen, Repositories berühren oder Promotion auslösen.

```
WhatsApp Webhook
    ↓
Provider Verification (HMAC/API Key)
    ↓
Sender Identity Mapping
    ↓
Message Normalization
    ↓
Intake Pipeline (validate, dedupe, rate-limit)
    ↓
Ticket Creation in Inbox Only
    ↓
Human Review Required
```

### Sicherheit

- **Provider Auth**: HMAC-Signatur oder API-Key-Verifikation
- **Sender Auth**: Whitelist autorisierter WhatsApp-Nummern
- **Boundary Enforcement**: Nur Ticket-Erstellung in Inbox
- **No Direct Execution**: Keine Worker-Ausführung aus WhatsApp
- **No Repo Access**: Kein Zugriff auf test_repo oder prod_repo
- **No Promotion**: Keine Promotion-Auslösung

### Konfiguration

```json
{
  "whatsapp": {
    "enabled": false,
    "webhook_url": "https://domain.com/whatsapp/webhook",
    "verify_token": "verify_token",
    "access_token": "EAA...",
    "authorized_senders": ["+1234567890"],
    "rate_limit_per_sender": 5,
    "dedup_window_seconds": 300
  }
}
```

### Betrieb

- **CLI Commands**: `whatsapp-config`, `whatsapp-validate`, `whatsapp-simulate`, `whatsapp-status`, `whatsapp-audit-show`
- **Audit Trail**: Vollständige Nachverfolgung aller Events
- **Idempotency**: Message-ID-basierte Replay-Schutz
- **Rate Limiting**: Pro-Sender und global
- **Safe-by-Default**: Deaktiviert bis konfiguriert

### Einschränkungen (v1)

- Text-only Nachrichten (keine Medien)
- Einzelner autorisierter Sender
- Manuelle Review für alle Tickets erforderlich
- Keine automatische Worker-Dispatch
- Keine Gruppenchat-Unterstützung

---

## 16. Bekannte Einschränkungen

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
| 10 | ~~Desktop-Pfad im Game Repo noch nicht migriert~~ | ~~Betriebsrisiko~~ | ✅ Sprint 4: Config zeigt auf physische Clones |
| 11 | ~~test_repo und prod_repo zeigen auf gleichen Pfad~~ | ~~Betriebsrisiko~~ | ✅ Sprint 4: Physisch getrennt + validate_repo_separation() |
| 12 | ~~Promotion führt noch keine Git-Operationen aus~~ | ~~Erwartungsgemäß~~ | ✅ Sprint 5: execute_promotion() mit git fetch |
| 13 | ~~Kein QA-Gate zwischen active und review~~ | ~~Erwartungsgemäß~~ | ✅ Sprint 5: QA-Gate als Promotion-Vorbedingung |
| 14 | ~~Promotion Readiness prüft, führt aber nicht aus~~ | ~~Erwartungsgemäß~~ | ✅ Sprint 5: --preview und --execute implementiert |
| 15 | Legacy hybris-game Symlink noch vorhanden | Niedrig | Manuelles Cleanup |
| 16 | Promotion führt kein git merge/push aus | Erwartungsgemäß | CD manuell |
| 17 | Kein Operator-Identity in Audit Records | Niedrig | Multi-User Sprint |
| 18 | Audit Trail nicht kryptographisch signiert | Niedrig | — |
| 19 | ~~Kein External Intake Adapter~~ | ~~Erwartungsgemäß~~ | ✅ Sprint 6: intake.py mit Pipeline, CLI, Audit |
| 20 | ~~Future Intake Connectors nur als Placeholder~~ | ~~Erwartungsgemäß~~ | ✅ Sprint 7: WhatsApp Connector Boundary implementiert |
| 21 | Intake hat kein Authentication Token System | Niedrig | Connector Sprint |
| 22 | WhatsApp Connector nur Text-Nachrichten | Erwartungsgemäß | Future Sprint: Media Support |

---

## 16. Git-Changelog

| Datum | Commit | Beschreibung |
|-------|--------|--------------|
| 2026-03-16 | `d16d0bf` | Sprint 1: Hardened Host Orchestrator Baseline (squash merge) |
| 2026-03-16 | `v0.1.0` | Tag: Sprint 1 Release |
| 2026-03-16 | `a3f2f5d` | Sprint 2: Domain Model + System Reference (squash merge) |
| 2026-03-16 | `v0.2.0` | Tag: Sprint 2 Release |
| 2026-03-16 | `fb8f959` | Sprint 3: Dual Repo Promotion Architecture (squash merge) |
| 2026-03-16 | `v0.3.0` | Tag: Sprint 3 Release |
| 2026-03-16 | — | Sprint 4: Physical Repo Separation & Promotion Safety (this branch) |
| 2026-03-16 | — | Sprint 5: QA Gate, Manual Promotion Execution, Audit Trail (this branch) |
| 2026-03-16 | — | Sprint 6: External Intake Adapter Layer (this branch) |
| 2026-03-16 | — | Sprint 7: Real WhatsApp Connector Boundary (this branch) |

---

## 17. Aktualisierungsprotokoll

| Datum | Autor | Änderung |
|-------|-------|----------|
| 2026-03-16 | Sprint 2 Agent | Erstversion: System Reference, Domain Model, Ticket Lifecycle, Roles & Authority |
| 2026-03-16 | Sprint 3 Agent | Dual Repo Architecture, Promotion Flow, Repo Authority, CLI-Erweiterung, 22 neue Tests |
| 2026-03-16 | Sprint 4 Agent | Physical Repo Separation, Promotion Safety, Readiness Check, 3 neue Docs, 10 neue Tests (66 total) |
| 2026-03-16 | Sprint 5 Agent | QA Gate, Manual Promotion Execution, Promotion Status Tracking, Audit Trail, 4 neue Docs, 20 neue Tests (86 total) |
| 2026-03-16 | Sprint 6 Agent | External Intake Adapter: intake.py, 7 CLI Commands, intake auth/trust, normalization, dedup, rate limiting, audit, 4 neue Docs, 65 neue Tests (151 total) |
| 2026-03-16 | Sprint 7 Agent | WhatsApp Connector Boundary: whatsapp.py, 5 CLI Commands, provider auth, sender identity, idempotency, audit, 5 neue Docs, config updates, 50 neue Tests (201 total) |
