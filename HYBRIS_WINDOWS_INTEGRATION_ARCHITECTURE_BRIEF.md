# HYBRIS Agent Operations — Windows Integration Architecture Brief

**Status:** Mac-first / Windows not yet available  
**Purpose:** Vorbereitung der finalen Dual-Host-Architektur für HYBRIS, ohne den aktuellen Mac-first-Betrieb zu verkomplizieren  
**Audience:** Claude / GPT / technischer Implementierer, sobald die Windows-Maschine vorhanden ist  
**Current Date Context:** 2026-03-16  
**Owner:** Creative Director / Director GPT  
**Scope:** Architektur, Rollen, Schnittstellen, Repo-Strategie, Validierungsplan, späterer Windows-Onboarding-Sprint

---

## 1. Zweck dieses Dokuments

Dieses Dokument ist **kein sofortiger Implementierungsauftrag für Windows**.

Es ist ein **präziser Architektur- und Übergabebrief** für den Zeitpunkt, an dem eine Windows-Maschine verfügbar ist und die aktuelle Mac-first-Architektur von HYBRIS zu einem **Dual-Host-Setup** erweitert werden soll.

Bis dahin gilt:

- der **Mac mini** bleibt der einzige aktive Host
- die aktuelle Host-Automation bleibt **Mac-first**
- es werden **keine spekulativen Windows-spezifischen Änderungen** im laufenden Betrieb eingebaut
- alle Architekturentscheidungen werden so vorbereitet, dass die spätere Windows-Integration **sauber ergänzt**, aber **nicht vorzeitig erzwungen** wird

---

## 2. Aktueller Ist-Zustand

### 2.1 Aktive Host-Landschaft
Derzeit existiert:

- **Mac mini** als lokaler Agenten-Host
- separates **HYBRIS Game Repo**
- separates **hybris-host Repo**
- lokale, nicht versionierte Runtime-Struktur für:
  - Tickets
  - Sessions
  - Logs
  - Artifacts

### 2.2 Bereits etablierte Grundlagen
Bereits vorhanden bzw. beschlossen:

- Ticket-basierter Agentenbetrieb
- gehärteter lokaler Orchestrator
- getrenntes Host-Repo
- dokumentiertes Domänenmodell
- Ticket als zentrales Aggregate Root
- Promotion nach Production **nie automatisch**
- Creative Director bleibt finale Freigabeinstanz

### 2.3 Noch nicht vorhanden
Noch **nicht** vorhanden:

- Windows-Host
- Cross-host Agent-Orchestrierung
- echter Staging-/Promotion-Lane über zwei Maschinen
- produktive Heavy-Execution-Lane für große Unity-Welten auf Windows
- externer Intake (OpenClaw / SMS / WhatsApp)

---

## 3. Zielbild

## 3.1 Strategisches Ziel
Das Ziel ist ein **Dual-Host-Modell**:

- **Mac mini = Control Plane / Authoring Host**
- **Windows Workstation = Heavy Execution / Integration Host**

Das System soll so geschnitten werden, dass:

- der Mac mini weiterhin Tickets, Orchestrierung, Review und leichte Validierung steuert
- die Windows-Maschine schwere Unity-Aufgaben übernimmt
- später große prozedurale Weltzustände, schwere Imports, größere Testumgebungen und finale Integrationsläufe auf Windows stattfinden
- Production-Freigaben weiterhin bewusst und kontrolliert erfolgen

---

## 4. Architekturprinzipien

### 4.1 Klare Host-Rollen
Die Hosts dürfen **nicht dieselbe Rolle unscharf parallel** ausführen.

#### Mac mini
Rolle:
- Creative-Director-naher Steuerhost
- Ticket Intake / Ticket Management
- Director GPT Ausführung
- lokaler Orchestrator
- Code-Agentenkoordination
- kleinere Unity-Validierungen
- QA-Zusammenfassung
- ReviewPackage-Erzeugung
- Promotion-Vorbereitung

#### Windows Workstation
Rolle:
- Heavy Integration Host
- größere Unity-Szenen / größere Weltsegmente
- prozedurale Welt-Läufe
- schwere Imports
- heavy test builds
- ggf. Blender-/Asset-nahe Verarbeitung, wenn die Hardware dafür besser geeignet ist

### 4.2 Keine Frühmigration in Windows-Logik
Solange keine Windows-Maschine existiert:

- keine echten Windows-spezifischen Pfade
- keine Windows-only Skripte im Kernpfad
- keine impliziten Tool-Entscheidungen zugunsten von Windows
- keine Host-Logik, die den Mac-first-Betrieb destabilisiert

### 4.3 Ticket bleibt das zentrale Aggregate
Nicht der Host.  
Nicht der Agent.  
Nicht das Repo.

Das Ticket bleibt der zentrale Container für:

- Ziel
- Constraints
- Zustände
- AgentRuns
- Artifacts
- Review
- Approval / Reticket / Promotion-Vorbereitung

### 4.4 Promotion bleibt manuell
Production-Freigabe bleibt immer an den Creative Director gebunden.

---

## 5. Ziel-Workflow

```text
Creative Director
-> Director GPT
-> Ticket
-> Orchestrator
-> Agenten
   -> Code
   -> Unity
   -> Blender
   -> Tripo
   -> QA
-> Staging / Test Integration
-> Creative Director Abnahme
-> Director GPT
   -> Promotion vorbereiten
   ODER
   -> neue / abgeleitete Tickets erzeugen
```

### 5.1 Mit künftigem Windows-Host
```text
Creative Director
-> Director GPT auf Mac mini
-> Ticket
-> Orchestrator auf Mac mini
-> passende Worker-Zuweisung
   -> Mac Worker
   -> Windows Integration Worker
-> Test / Staging Ergebnis
-> ReviewPackage
-> Creative Director Abnahme
-> PromotionRequest
-> Production Freigabe oder Reticket
```

---

## 6. Repo- und Branch-Strategie

### 6.1 Empfohlene Struktur
Es soll **kein chaotisches Doppel-Repo-System** für denselben Game-Stand entstehen.

Empfohlene technische Struktur:

- **Prod Repo**
  - `main`
- **Staging / Integration Lane**
  - z. B. `integration/windows`
  - oder ein klar definierter staging branch
- **Ticket-/Feature-Branches**
  - unter Kontrolle des Host-Orchestrators

### 6.2 Was vermieden werden soll
Nicht empfehlenswert:

- dauerhaft divergierendes Test-Repo als zweites kanonisches Spiel-Repo
- nicht synchronisierte Windows-Sonderbranches ohne Governance
- manuell gepflegte „final-final-test“-Repos
- hostabhängige Projektkopien

### 6.3 Wann ein echtes Test-Repo sinnvoll wäre
Nur falls bewusst nötig für:

- Quarantäne für riskante AI-generierte Assets
- Build-/Experiment-Sandbox
- isolierte Evaluierung

Dann muss es explizit als **nicht-kanonisch** dokumentiert sein.

---

## 7. Domänenmodell-Erweiterung für Dual-Host

Folgende Konzepte sollen im Host-System für die spätere Windows-Integration ergänzt oder explizit modelliert werden:

- `HostType`
  - `authoring_host`
  - `integration_host`

- `ExecutionTarget`
  - `mac_local`
  - `windows_integration`

- `StagingTarget`
  - branch / remote / controlled repo lane

- `PromotionTarget`
  - production target / main branch / protected release lane

- `EnvironmentProfile`
  - `mac_dev`
  - `windows_integration`
  - später optional `build_host`

- `CapabilitySet`
  - z. B. `unity_small_scene`
  - `unity_heavy_world`
  - `blender_heavy`
  - `qa_only`

Diese Konzepte sollen zuerst **modelliert und dokumentiert**, aber erst mit realer Hardware produktiv aktiviert werden.

---

## 8. Was der Mac mini dauerhaft bleiben soll

Der Mac mini soll **nicht** zu einem überforderten Alleskönner mutieren.

Er bleibt:

- Director-Host
- Orchestrator
- leichte Validierungsinstanz
- Ticket-/Review-/Approval-Steuerung
- Mac-first Entwicklungsumgebung
- sichere lokale Kontrollstation

Der Mac mini soll **nicht** langfristig Hauptplattform sein für:

- schwere Open-World-Authoring-Läufe
- große prozedurale Welt-Integration
- maximale heavy editor sessions
- parallele High-RAM-Unity/Blender-Last

---

## 9. Was die Windows-Maschine später leisten soll

Die Windows-Maschine soll später die Heavy-Lane übernehmen.

Geplante Aufgaben:

- größere prozedurale Weltsegmente öffnen
- schwere Unity-Szenen testen
- größere Integrationstests fahren
- Asset-Import- und Validierungsläufe ausführen
- ggf. Blender-/Tripo-nahe Pipeline-Schritte übernehmen
- finalere „realistischere“ Testumgebung für die spätere Produktionswelt liefern

Wichtig:
Diese Maschine ist **kein zweiter Director**, sondern ein **Execution Host**.

---

## 10. Voraussetzungen für die spätere Windows-Integration

Sobald die Windows-Maschine vorhanden ist, müssen vor der eigentlichen Integration mindestens diese Punkte geprüft werden:

### 10.1 Unity-Konsistenz
- exakt passende Unity-Version
- gleiche Projektkonventionen
- keine stillen Versionssprünge

### 10.2 Git-/Repo-Hygiene
- sauberer Pull des vorgesehenen Staging-Ziels
- keine lokalen Sonderstände
- kein Windows-only Fork-Drift

### 10.3 Dateisystem-/Pfad-Disziplin
- keine hardcodierten Mac-Pfade im laufenden System
- Pfade durch Konfiguration / EnvironmentProfile steuerbar

### 10.4 Tool-Kompatibilität
- Unity
- Git
- ggf. Blender
- ggf. Tripo-nahe Tooling
- Host-Lokalregeln auf Windows klar begrenzen

### 10.5 Sicherheitsrahmen
- Windows erhält nicht automatisch Vollzugriff
- nur freigegebene Worker und definierte Skriptpfade
- keine freie Shell aus Tickettexten
- Promotion weiterhin nur nach Director-Freigabe

---

## 11. Geplanter Windows-Onboarding-Sprint

Sobald die Windows-Maschine existiert, soll **kein unstrukturierter Setup-Marathon** stattfinden.

Stattdessen ein eigener Implementierungssprint mit diesem Scope:

### Sprint-Ziel
Ergänze die bestehende Mac-first-Agentenarchitektur um einen Windows-Integration-Host, ohne die Mac-Kontrollarchitektur zu destabilisieren.

### Muss enthalten
1. Windows-Maschine als `integration_host` modellieren
2. ExecutionTargets für `mac_local` und `windows_integration`
3. Staging-/Integration-Lane definieren
4. Windows-Validierungspfad dokumentieren
5. definierte Windows-Worker-Adapter oder Runner-Stubs anlegen
6. ReviewPackage um Host-Herkunft und Testumgebung erweitern
7. Promotion-Vorbereitung auf Basis Windows-validierter Ergebnisse ermöglichen
8. keine automatische Prod-Promotion

### Darf nicht enthalten
- keine spontane Vollautomatisierung
- kein Remote-Desktop-Hack als Kernarchitektur
- kein zweites kanonisches Game-Repo ohne Begründung
- keine hostabhängige Chaos-Konfiguration
- keine Prod-Freigabe ohne Creative Director

---

## 12. Empfohlene Windows-Sprint-Deliverables

Sobald die Windows-Maschine da ist, soll der nächste Implementierer mindestens diese Deliverables erzeugen:

### Dokumentation
- `docs/dual-host-architecture.md`
- `docs/windows-integration-lane.md`
- Update der `AGENT_HOST_SYSTEM_REFERENCE.md`

### Modell / Konfiguration
- Host-Konfigurationen für:
  - `mac-mini`
  - `windows-integration`
- Capability-Zuordnung pro Host
- ExecutionTarget-Regeln

### Code / Host-Layer
- minimaler Windows Runner / Adapter
- sichere Dispatch-Regeln
- Host-aware ReviewPackage-Felder
- Windows-spezifische Validierung ohne Vollautonomie

### Validierung
- Test-Pull auf Windows
- Unity-Projekt erfolgreich öffnen
- definierter Staging-Stand validierbar
- ReviewPackage zurück an Mac/Director
- kein Schreiben auf Production ohne Freigabe

---

## 13. Offene Architekturentscheidungen

Diese Entscheidungen sollen **nicht jetzt auf dem Mac erzwungen**, sondern erst mit echter Windows-Hardware sauber getroffen werden:

1. **Branch vs. separates Test-Repo**
   - Default-Empfehlung: Branch/Lane statt zweites kanonisches Repo

2. **Welche Worker laufen wirklich auf Windows?**
   - nur Unity?
   - zusätzlich Blender?
   - zusätzlich Build/QA?

3. **Wie wird der Windows-Host ausgelöst?**
   - Pull-basiert
   - orchestrierter Job
   - späterer Remote Trigger

4. **Wie groß ist der reale Scope der Heavy World Lane?**
   - nur Testen?
   - auch Authoring?
   - auch finale Integration?

5. **Wie stark wird der Mac mini später entlastet?**
   - nur Unity heavy?
   - auch Asset- und Build-Lane?

---

## 14. Was bis zur Windows-Maschine NICHT getan werden soll

Bis reale Windows-Hardware vorhanden ist, soll der laufende Mac-first-Stack **bewusst schlank** bleiben.

Nicht tun:

- Windows-spezifische Pfadlogik einbauen
- künstliche Dual-Host-Komplexität erzeugen
- Cross-host Features ohne Testbarkeit erfinden
- echte Heavy-World-Strategie simulieren
- Architektur auf hypothetische Hardware optimieren

---

## 15. Definition of Ready für die spätere Windows-Integration

Wenn die Windows-Maschine vorhanden ist, gilt der nächste Sprint erst dann als startklar, wenn:

- die Windows-Hardware einsatzbereit ist
- Unity-Version definiert ist
- Git-Zugang sauber funktioniert
- Staging-Ziel festgelegt ist
- Mac-first-Host stabil bleibt
- Sprint-Ziel auf Windows klar begrenzt ist
- klar ist, welche Tests auf Windows real laufen sollen

---

## 16. Definition of Done für die spätere Windows-Integration

Der Windows-Integrationssprint gilt erst als abgeschlossen, wenn:

- das definierte Staging-Ziel auf Windows sauber gezogen werden kann
- das Unity-Projekt dort erfolgreich geöffnet werden kann
- mindestens ein definierter Heavy-Testlauf oder Integrationslauf erfolgreich durchläuft
- das Ergebnis als ReviewPackage zurück in den Director-Flow kommt
- keine Production-Freigabe automatisiert wurde
- keine chaotische Doppel-Repo-Struktur entstanden ist
- die System Reference aktualisiert wurde

---

## 17. Konkreter Auftragstext für den späteren Implementierer

Diesen Block kann der Creative Director später direkt an Claude oder einen anderen Implementierer geben:

```text
You are working in the hybris-host repository.

Context:
- HYBRIS currently runs in a Mac-first agent-host setup.
- A Windows machine is now available and should be added as an integration host.
- The Mac mini remains the control plane / authoring host.
- The Windows machine is intended for heavier Unity integration and larger world validation.
- Do not destabilize the existing Mac-first setup.

Goal:
Extend the current host architecture into a controlled dual-host model.

Requirements:
1. Keep the Mac mini as control plane.
2. Add the Windows machine as integration_host, not as a second uncontrolled primary host.
3. Model and implement execution target routing:
   - mac_local
   - windows_integration
4. Define a clear staging / integration lane.
5. Do not implement automatic production promotion.
6. Do not create a second canonical game repo unless explicitly justified.
7. Update AGENT_HOST_SYSTEM_REFERENCE.md.
8. Add dual-host architecture docs.
9. Keep changes minimal, production-minded, and reversible.
10. Validate with a real pull/open/test cycle on the Windows machine.

Deliverables:
- dual-host architecture documentation
- windows integration lane documentation
- minimal host config updates
- minimal execution target routing
- validation report
- updated system reference

Non-goals:
- no GUI automation
- no remote desktop driven architecture
- no WhatsApp/OpenClaw integration in this sprint
- no speculative overengineering
- no automatic promotion to production
```

---

## 18. Maintenance-Regel

Sobald die Windows-Maschine integriert wurde, müssen folgende Dokumente synchron gepflegt werden:

- `AGENT_HOST_SYSTEM_REFERENCE.md`
- `docs/domain-model.md`
- `docs/ticket-lifecycle.md`
- `docs/roles-and-authority.md`
- dieses Dokument oder sein Nachfolger (`docs/dual-host-architecture.md`)

---

## 19. Klare Abschlussformel

Bis zur realen Windows-Maschine gilt:

- **Mac-first bleibt kanonisch**
- **Windows wird vorbereitet, aber nicht vorweggenommen**
- **Architektur zuerst, Heavy-Execution später**
- **Creative Director bleibt Freigabeinstanz**
- **Production bleibt geschützt**
