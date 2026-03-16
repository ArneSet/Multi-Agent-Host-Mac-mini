# HYBRIS Ticket Schema

## Ticket Format

Each ticket is a single Markdown file placed in a ticket state directory.

### Filename Convention
```
YYYY-MM-DD_<short-id>.md
```
Example: `2026-03-16_host-bootstrap-validation.md`

### Required Frontmatter (YAML)
```yaml
---
id: host-bootstrap-validation
title: "Host Bootstrap Validation"
created: 2026-03-16T12:00:00
priority: normal          # low | normal | high | critical
worker: code-worker       # code-worker | unity-worker | blender-worker | tripo-worker
branch: feature/xyz       # git branch (never main)
description: |
  Short description of work to be done.
tags: [infrastructure, sprint-1]
---
```

### Optional Fields
```yaml
assignee: claude           # agent identity
depends_on: []             # list of ticket IDs that must be done first
artifacts: []              # list of output file paths
notes: |
  Additional context.
```

### Body
Free-form Markdown below the frontmatter. Contains:
- Acceptance criteria
- Implementation notes
- Constraints

## State Machine

```
inbox → ready → active → review → done
                  ↓                  
                failed              
```

### State Transitions
| From    | To      | Trigger                        |
|---------|---------|--------------------------------|
| inbox   | ready   | Ticket validated, worker identified |
| ready   | active  | Orchestrator picks up ticket   |
| active  | review  | Worker completes successfully   |
| active  | failed  | Worker fails or error detected  |
| review  | done    | Director (human) approves      |
| review  | active  | Director requests rework       |
| failed  | ready   | Issue resolved, retry approved  |

### Rules
- **One active ticket at a time** per worker type
- Moving to `active` creates a log file in `logs/worker/`
- Moving to `review` or `failed` closes the log
- Tickets are moved by physically relocating the .md file between directories
- The orchestrator never deletes tickets
