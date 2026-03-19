# Ticket Format Rules

> **Status:** Canonical — binding for all workers and intake systems  
> **Date:** 2026-03-19  
> **Reason:** `parse_ticket()` uses regex KV matching, not a real YAML parser  

---

## Why This Matters

The orchestrator's `parse_ticket()` reads ticket files with a regex:

```python
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)$", re.MULTILINE)
```

This means:
- The first `---` opens frontmatter
- The second `---` **closes** frontmatter
- Only simple `key: value` lines are extracted
- Multi-line YAML constructs are **not supported**
- Any `---` inside a multi-line value would prematurely close frontmatter

---

## Allowed Ticket Format

```markdown
---
id: my-ticket-001
title: Short descriptive title
worker: code-worker
branch: feature/my-change
priority: normal
created: 2026-03-19T12:00:00Z
---

Task specification goes here in the body.
This can be multiple lines, any format the worker understands.
```

### Frontmatter Rules

| Rule | Detail |
|------|--------|
| Format | Simple `key: value` pairs, one per line |
| Keys | ASCII alphanumeric + underscore, starting with letter/underscore |
| Values | Single-line strings. Quotes are stripped. |
| Separator | `---` on its own line opens and closes the frontmatter block |
| No block scalars | `description: \|` or `description: >` are **forbidden** |
| No nested YAML | No lists, no maps, no anchors, no aliases |
| No `---` in values | Would prematurely close frontmatter |

### Required Frontmatter Keys

| Key | Purpose |
|-----|---------|
| `id` | Unique ticket identifier (alphanumeric, dots, hyphens, max 128 chars) |
| `title` | Short human-readable title |
| `worker` | Worker to dispatch (must be in `allowed_workers`) |
| `branch` | Target branch in test_repo (must not be protected) |

### Optional Frontmatter Keys

| Key | Purpose |
|-----|---------|
| `priority` | `normal`, `high`, `low` |
| `created` | ISO-8601 timestamp |
| `description` | **Legacy only.** Short single-line. Workers should read `_body`. |
| `intake_source` | Origin channel (`whatsapp`, `cli`, `api`) |

---

## Body Convention

Everything after the closing `---` is the **body** (`_body` in parsed ticket dict).

- Workers read their primary task specification from `_body`
- Format of `_body` is worker-specific (see each worker contract)
- `_body` can contain `---` separators, multi-line content, any text

### Code Worker Body Format

```
target_file: relative/path/to/file.ext
---
(file content follows)
```

### Unity Worker Body Format

```
validation_type: project-health | compile-check | asset-validation
target_path: optional/relative/path
```

---

## Forbidden Patterns

These will cause parse failures or incorrect behavior:

```yaml
# FORBIDDEN: block scalar
description: |
  This is multi-line
  content that won't parse

# FORBIDDEN: nested list in frontmatter
tags:
  - sprint-10a
  - reference

# FORBIDDEN: --- inside a value
title: My --- Ticket

# FORBIDDEN: multi-line value
description: This is a
  continued value
```

---

## Valid Ticket Examples

### Code Worker Ticket

```markdown
---
id: code-ref-001
title: Add utility file
worker: code-worker
branch: feature/code-ref-001
priority: normal
---

target_file: Assets/Scripts/Utilities/MyUtility.cs
---
using UnityEngine;

public static class MyUtility
{
    public static void DoSomething() { }
}
```

### Unity Worker Ticket

```markdown
---
id: unity-val-001
title: Validate test_repo project health
worker: unity-worker
branch: feature/unity-val-001
priority: normal
---

validation_type: project-health
```

---

## Parser Implementation Reference

Location: `orchestrator.py`, function `parse_ticket()`

The parser returns a dict with:
- All frontmatter KV pairs as string values
- `_body`: stripped content after frontmatter
- `_path`: file path of the ticket
