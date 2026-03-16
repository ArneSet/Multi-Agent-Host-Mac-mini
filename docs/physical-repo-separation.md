# Physical Repo Separation

> Sprint 4 — Physical Repo Separation and Promotion Safety

## Warum logische Trennung nicht ausreicht

Sprint 3 führte `test_repo` und `prod_repo` als Konzept ein. Beide Targets zeigten jedoch
auf denselben physischen Pfad (`~/Desktop/HYBRIS - Mortal Realm`). Ein Agent, der auf
`test_repo` schreibt, schreibt damit automatisch auch in `prod_repo`.

**Das ist der größte verbleibende Architekturfehler vor externem Ticket-Intake.**

## Gewählte Strategie: Separate Clones

Zwei unabhängige `git clone`-Instanzen desselben Remotes:

```
~/Workspace/HYBRIS/repos/hybris-test    ← Agent-Arbeitsrepo (test_repo)
~/Workspace/HYBRIS/repos/hybris-prod    ← Produktionsrepo (prod_repo)
```

### Warum Clones statt Worktrees?

| Kriterium | Separate Clones | Git Worktrees |
|-----------|:--------------:|:-------------:|
| Unabhängiges `.git` | ✓ | ✗ (geteilt) |
| Kein versehentlicher Cross-Zugriff | ✓ | Riskant |
| Einfach zu verstehen | ✓ | Mittel |
| Einfach rückgängig zu machen | ✓ | ✓ |
| Speicherplatz | ~2×.git | Spart .git |

Speicherplatz ist bei 153MB .git irrelevant auf dem Mac mini.

## Lokale Pfadstruktur nach Sprint 4

```
~/Workspace/HYBRIS/
├── repos/
│   ├── hybris-host/        ← Host-Orchestrator (dieses Repo)
│   ├── hybris-test/        ← Agent-Arbeitsrepo (test_repo) ← NEU
│   ├── hybris-prod/        ← Produktionsrepo (prod_repo)   ← NEU
│   └── hybris-game -> …    ← Legacy-Symlink (wird nicht mehr verwendet)
└── management/             ← Runtime-Daten (unverändert)
```

### Desktop-Pfad

`~/Desktop/HYBRIS - Mortal Realm` bleibt als Unity-Editor-Verzeichnis bestehen.
Es ist **keine** der beiden Repo-Targets mehr. Die Config verweist nur noch auf
die Workspace-Pfade.

## Betriebsregeln

### test_repo (`hybris-test/`)
- Agenten dürfen lesen und schreiben
- Feature-Branches werden hier erstellt
- Worker-Ausführung passiert ausschließlich hier
- Kann jederzeit auf `main` zurückgesetzt werden

### prod_repo (`hybris-prod/`)
- Agenten haben **keinen** Zugriff
- Nur über genehmigte Promotion erreichbar
- Bleibt auf `main` (oder einem geschützten Release-Branch)
- Creative Director hat vollen Zugriff

## Rollback / Recovery

| Szenario | Aktion |
|----------|--------|
| test_repo beschädigt | `git reset --hard origin/main` oder neu klonen |
| prod_repo versehentlich geändert | `git reset --hard origin/main` — Promotion-Dateien in management/ prüfen |
| Zurück zu Single-Repo | Config auf gleichen Pfad setzen — logisch äquivalent zu Sprint 3 |

## Config nach Sprint 4

```json
{
  "repo_targets": {
    "test_repo": "/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-test",
    "prod_repo": "/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-prod"
  }
}
```

## Validierung

Die Config-Validierung erzwingt ab Sprint 4:
1. `test_repo` und `prod_repo` müssen konfiguriert sein
2. Beide Pfade müssen als Verzeichnisse existieren
3. Beide Pfade müssen zu **unterschiedlichen** realen Pfaden auflösen
4. `test_repo` muss ein `Assets/`-Verzeichnis enthalten (Unity-Repo)
5. `prod_repo` muss ein `Assets/`-Verzeichnis enthalten (Unity-Repo)
