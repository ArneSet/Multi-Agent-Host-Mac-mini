# Multi-Agent Host — Mac mini

Local, file-based ticket orchestrator for HYBRIS multiagent development on Mac mini (Apple Silicon).

**This is the host/infra repo.** The game itself lives in a separate repo (`HYBRIS - Mortal Realm`).

## Architecture

```
~/Workspace/HYBRIS/
├── repos/
│   ├── hybris-game/  → symlink to HYBRIS game repo (Unity project)
│   └── hybris-host/  → THIS REPO (orchestrator, workers, CLI)
└── management/       → NOT versioned (runtime data only)
    ├── tickets/{inbox,ready,active,review,done,failed}/
    ├── sessions/
    ├── logs/{agent-runs,orchestrator,worker}/
    └── artifacts/
```

## Setup

```bash
# 1. Clone this repo
cd ~/Workspace/HYBRIS/repos
git clone git@github.com:ArneSet/Multi-Agent-Host-Mac-mini.git hybris-host

# 2. Create runtime directories
mkdir -p ~/Workspace/HYBRIS/management/tickets/{inbox,ready,active,review,done,failed}
mkdir -p ~/Workspace/HYBRIS/management/sessions
mkdir -p ~/Workspace/HYBRIS/management/logs/{agent-runs,orchestrator,worker}
mkdir -p ~/Workspace/HYBRIS/management/artifacts

# 3. Symlink game repo (adjust path if needed)
ln -sfn "/Users/$USER/Desktop/HYBRIS - Mortal Realm" ~/Workspace/HYBRIS/repos/hybris-game

# 4. Create local config from template
cp config.example.json config.json
# Edit config.json with your actual absolute paths
```

## Quick Start

```bash
cd ~/Workspace/HYBRIS/management/automation/hybris_host

# Validate setup
python3 cli.py validate

# List all tickets
python3 cli.py list

# Show ticket details
python3 cli.py show host-bootstrap-validation

# Dry-run a ticket (no file moves)
python3 cli.py process host-bootstrap-validation --dry-run

# Process a ticket for real
python3 cli.py process host-bootstrap-validation
```

## Repo Structure

```
hybris-host/                    # THIS REPO
├── cli.py                      # CLI entrypoint
├── orchestrator.py             # State machine + ticket processing
├── config.example.json         # Template (copy to config.json)
├── ticket_schema.md            # Ticket format documentation
├── README.md                   # This file
└── workers/
    ├── base_worker.py          # Worker interface
    ├── code_worker.py          # General code tasks (stub)
    ├── unity_worker.py         # Unity Editor tasks (stub)
    ├── blender_worker.py       # 3D asset tasks (stub)
    └── tripo_worker.py         # AI 3D generation (stub)
```

Runtime data (NOT in this repo):
```
~/Workspace/HYBRIS/management/
├── tickets/{inbox,ready,active,review,done,failed}/
├── sessions/
├── logs/{agent-runs,orchestrator,worker}/
└── artifacts/
```

## Operator Flow (Director's Guide)

### Creating a Ticket

1. Create a `.md` file in `tickets/inbox/` following the schema in `ticket_schema.md`
2. Use the naming convention: `YYYY-MM-DD_<short-id>.md`
3. Include YAML frontmatter with required fields: `id`, `title`, `worker`, `branch`

### Processing a Ticket

```bash
# 1. Check what's in the queue
python3 cli.py list

# 2. Preview what will happen
python3 cli.py process <ticket-id> --dry-run

# 3. Execute
python3 cli.py process <ticket-id>

# 4. Check result — ticket should be in 'review' or 'failed'
python3 cli.py list

# 5. If in review, approve it manually:
python3 cli.py transition <ticket-id> done

# Or send back for rework:
python3 cli.py transition <ticket-id> active
```

### Manual Transitions

```bash
python3 cli.py transition <ticket-id> <target-state>
```

Valid transitions:
- inbox → ready
- ready → active
- active → review | failed
- review → done | active
- failed → ready

## State Machine

```
inbox → ready → active → review → done
                  ↓
                failed → ready (retry)
```

## Safety Rules

| Rule | Enforcement |
|------|------------|
| Max 1 active ticket | Orchestrator blocks activation if another is active |
| No work on protected branches | Ticket `branch` field validated against config.safety.protected_branches |
| No shell exec from tickets | Workers never eval/exec ticket body content |
| No auto-commit | config.safety.auto_commit = false |
| No auto-merge | config.safety.auto_merge = false |
| Deterministic logging | Every transition and worker action logged with timestamp |

## Requirements

- Python 3.9+ (macOS system Python is fine)
- No external packages (stdlib only)
- No Docker, no daemons, no background processes

## Separation of Concerns

| Layer | Location | Versioned? |
|-------|----------|-----------|
| Game code | `hybris-game` repo | Yes (Git) |
| Host automation | `hybris-host` repo (this) | Yes (Git) |
| Runtime state | `~/Workspace/HYBRIS/management/` | No |

The game repo has `.claude/rules.md` for agent behavior within that repo.
This repo references the game repo via `config.json → game_repo_root`.
