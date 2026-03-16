# HYBRIS Agent Host — Domain Model

> **Letzte Aktualisierung:** 2026-03-16  
> **Branch:** `feature/sprint-2-domain-model`  
> **Status:** Sprint 2 — modeled, not fully automated  

---

## Zentrales Aggregate: Ticket

Das **Ticket** ist das Aggregate Root des gesamten Host-Systems.  
Alle anderen Konzepte hängen am Ticket oder existieren in Bezug auf eines.

```
DirectorRequest
  └─▶ Ticket (Aggregate Root)
        ├── AgentRun[]
        │     └── Artifact[]
        ├── ChangeSet
        ├── ReviewPackage
        ├── ApprovalDecision
        └── PromotionRequest
              └── PromotionTarget
```

---

## Domain Concepts

### 1. DirectorRequest

Ein Auftrag des Creative Directors, der über den Director GPT in das System eingespeist wird.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `source` | `creative-director` \| `director-gpt` | Wer den Request formuliert hat |
| `intent` | string | Freitextziel (z. B. „Neues Creature-Modell: Hydra") |
| `constraints` | string[] | Einschränkungen (z. B. „Kein neues Package", „Max 2 Tage") |
| `priority` | `low` \| `normal` \| `high` \| `critical` | Dringlichkeit |

**Noch nicht im Code implementiert.** In Sprint 1/2 wird der Director Request manuell als Ticket-Datei in `inbox/` angelegt. Automatisierter Intake ist explizit nicht Teil von Sprint 2.

---

### 2. Ticket

Die zentrale Arbeitseinheit. Eine Markdown-Datei mit YAML-Frontmatter, physisch im Zustandsverzeichnis abgelegt.

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `id` | string | ✓ | Eindeutiger Bezeichner (`^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$`) |
| `title` | string | ✓ | Kurztitel |
| `worker` | WorkerType | ✓ | Zuständiger Worker |
| `branch` | string | ✓ | Git-Branch (niemals `main`/`master`/`develop`) |
| `priority` | Priority | ✓ | `low` \| `normal` \| `high` \| `critical` |
| `created` | ISO-8601 | ○ | Erstellungszeitpunkt |
| `description` | string | ○ | Ausführliche Beschreibung |
| `tags` | string[] | ○ | Kategorisierung |
| `depends_on` | string[] | ○ | Ticket-IDs, von denen dieses abhängt |
| `artifacts` | string[] | ○ | Ausgabeartefakte nach Abschluss |

**Implementiert in:** `orchestrator.py` → `parse_ticket()`, `ticket_schema.md`

---

### 3. AgentRun

Eine einzelne Ausführung eines Workers im Kontext eines Tickets.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ticket_id` | string | Referenz auf das Ticket |
| `worker` | WorkerType | Welcher Worker ausgeführt wurde |
| `started_at` | ISO-8601 | Startzeitpunkt |
| `finished_at` | ISO-8601 | Endzeitpunkt |
| `success` | bool | Ob der Lauf erfolgreich war |
| `message` | string | Ergebnismeldung |
| `artifacts` | string[] | Erzeugte Artefakte |

**Noch nicht als eigene Struktur im Code.** Wird derzeit implizit durch `dispatch_worker()` Return-Dict und Log-Einträge abgebildet. Formalisierung in Sprint 3.

---

### 4. WorkerType

Typisierung der verfügbaren Worker.

| Name | Modul | Beschreibung | Status |
|------|-------|--------------|--------|
| `code-worker` | `code_worker` | C#/Python-Codeänderungen | Stub |
| `unity-worker` | `unity_worker` | Unity-Editor-Operationen | Stub |
| `blender-worker` | `blender_worker` | 3D-Modellierung, Export | Stub |
| `tripo-worker` | `tripo_worker` | Tripo-API 3D-Generierung | Stub |

**Implementiert in:** `orchestrator.py` → `_WORKER_MODULE_MAP`, `config.json` → `allowed_workers`

Doppeltes Gate: Worker muss sowohl in `_WORKER_MODULE_MAP` (hardcoded) als auch in `config.allowed_workers` stehen.

---

### 5. Artifact

Ein Arbeitsergebnis, das ein Worker erzeugt.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `path` | string | Dateipfad relativ zu `management_root/artifacts/` |
| `ticket_id` | string | Zugehöriges Ticket |
| `worker` | WorkerType | Erzeugender Worker |
| `type` | string | Art des Artefakts (z. B. `code_result`, `model_fbx`, `screenshot`) |

**Implementiert als:** Datei in `artifacts/`, Pfad im Worker-Log. Noch kein formales Schema.

---

### 6. ChangeSet

Die Menge aller Git-Änderungen, die ein Ticket auf seinem Branch erzeugt hat.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ticket_id` | string | Zugehöriges Ticket |
| `branch` | string | Git-Branch |
| `commits` | string[] | Commit-Hashes |
| `files_changed` | string[] | Geänderte Dateien |

**Noch nicht implementiert.** In Sprint 1/2 wird der Branch manuell geprüft. Automatisierte ChangeSet-Erfassung in Sprint 3+.

---

### 7. ReviewPackage

Bündelt alle Informationen, die für eine Abnahme-Entscheidung nötig sind.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ticket_id` | string | Zugehöriges Ticket |
| `artifacts` | Artifact[] | Erzeugte Artefakte |
| `change_set` | ChangeSet | Git-Änderungen |
| `worker_logs` | string[] | Relevante Log-Dateien |
| `qa_result` | string | QA-Ergebnis (wenn vorhanden) |

**Noch nicht implementiert.** Konzeptuelles Modell für Sprint 3. Im aktuellen Sprint wird eine Ticket-Datei im `review/`-Verzeichnis als implizites ReviewPackage behandelt.

---

### 8. ApprovalDecision

Die Entscheidung des Creative Directors über ein ReviewPackage.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ticket_id` | string | Zugehöriges Ticket |
| `decision` | `approved` \| `rejected` \| `reticketed` | Entscheidung |
| `reviewer` | string | Wer entschieden hat (Creative Director) |
| `reason` | string | Begründung |
| `timestamp` | ISO-8601 | Zeitpunkt |

**Noch nicht implementiert.** Aktuell erfolgt die Abnahme manuell per `cli.py transition <id> done`. Formalisierung in Sprint 3.

**Regel:** Promotion zu Production ist niemals automatisch. Creative-Director-Approval bleibt mandatory.

---

### 9. PromotionRequest

Ein Antrag auf Übernahme eines abgenommenen Tickets in ein Zielrepository.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ticket_id` | string | Zugehöriges Ticket |
| `approval_decision` | ApprovalDecision | Vorausgehende Freigabe |
| `target` | PromotionTarget | Wohin promotet werden soll |
| `requested_by` | string | Director GPT oder Creative Director |

**Noch nicht implementiert.** Reines Domänenkonzept in Sprint 2. Technische Umsetzung frühestens Sprint 4.

---

### 10. PromotionTarget

Modelliert die verschiedenen Zielumgebungen, in die Arbeit übernommen werden kann.

| Name | Beschreibung | Status |
|------|--------------|--------|
| `staging_target` | Test-/Integrationsumgebung (Game-Repo Feature-Branch) | Konzept |
| `promotion_target` | Abgenommener, merge-bereiter Stand | Konzept |
| `prod_target` | Production (Game-Repo `main`) | Konzept |

**Bewusst nur als Modell definiert**, nicht als Code implementiert. Sprint 2 vermeidet, dass eine falsche Repo-Topologie vorschnell gebaut wird. Technische Anbindung in Sprint 4+.

---

## Beziehungsübersicht

```
Creative Director ──request──▶ Director GPT ──creates──▶ Ticket
                                                           │
                                     ┌─────────────────────┤
                                     ▼                     ▼
                                 AgentRun              ChangeSet
                                     │
                                     ▼
                                 Artifact[]
                                     │
                                     ▼
                               ReviewPackage
                                     │
                                     ▼
                             ApprovalDecision
                              ╱            ╲
                        approved          rejected / reticketed
                           │                    │
                           ▼                    ▼
                    PromotionRequest       neues Ticket / Rework
                           │
                           ▼
                     PromotionTarget
                    (staging → prod)
```

---

## Abgrenzung Sprint 2

| Konzept | Modelliert | Im Code | Vollautomatisiert |
|---------|:----------:|:-------:|:-----------------:|
| DirectorRequest | ✓ | — | — |
| Ticket | ✓ | ✓ | ✓ |
| AgentRun | ✓ | teilweise | — |
| WorkerType | ✓ | ✓ | ✓ |
| Artifact | ✓ | teilweise | — |
| ChangeSet | ✓ | — | — |
| ReviewPackage | ✓ | — | — |
| ApprovalDecision | ✓ | — | — |
| PromotionRequest | ✓ | — | — |
| PromotionTarget | ✓ | — | — |
