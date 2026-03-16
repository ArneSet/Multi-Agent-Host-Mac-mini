#!/usr/bin/env python3
"""
HYBRIS Host Orchestrator — File-based ticket state machine.

Moves tickets through states, invokes worker stubs, writes logs.
No network, no shell exec from ticket content, deterministic.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _HERE / "config.json"


def load_config(path: Path = _DEFAULT_CONFIG) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Ticket parsing (YAML-frontmatter-lite, no PyYAML dependency)
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^(\w[\w-]*):\s*(.+)$", re.MULTILINE)


def parse_ticket(path: Path) -> dict:
    """Return frontmatter fields + body from a ticket .md file."""
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        raise ValueError(f"Ticket has no valid YAML frontmatter: {path}")
    fm_block = m.group(1)
    body = text[m.end():]
    fields = {}
    for kv in _KV_RE.finditer(fm_block):
        key, val = kv.group(1), kv.group(2).strip().strip('"').strip("'")
        fields[key] = val
    fields["_body"] = body.strip()
    fields["_path"] = str(path)
    return fields


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def find_ticket(cfg: dict, ticket_id: str) -> tuple:
    """Return (state, Path) for a ticket id, or (None, None)."""
    mgmt = Path(cfg["management_root"])
    for state in cfg["ticket_states"]:
        state_dir = mgmt / cfg["tickets_dir"] / state
        for f in state_dir.glob("*.md"):
            try:
                t = parse_ticket(f)
                if t.get("id") == ticket_id:
                    return state, f
            except ValueError:
                continue
    return None, None


def list_tickets(cfg: dict, state_filter: str = None) -> list:
    """Return list of (state, id, title, path) tuples."""
    mgmt = Path(cfg["management_root"])
    results = []
    states = [state_filter] if state_filter else cfg["ticket_states"]
    for state in states:
        state_dir = mgmt / cfg["tickets_dir"] / state
        if not state_dir.exists():
            continue
        for f in sorted(state_dir.glob("*.md")):
            try:
                t = parse_ticket(f)
                results.append((state, t.get("id", "?"), t.get("title", "?"), str(f)))
            except ValueError:
                results.append((state, "?", "PARSE_ERROR", str(f)))
    return results


def transition_ticket(cfg: dict, ticket_id: str, target_state: str,
                      dry_run: bool = False, from_state_override: str = None) -> str:
    """Move ticket to target_state. Returns log message.
    from_state_override: use this instead of filesystem lookup (for dry-run chaining).
    """
    current_state, path = find_ticket(cfg, ticket_id)
    if current_state is None:
        raise FileNotFoundError(f"Ticket not found: {ticket_id}")

    # In dry-run chains, the file hasn't moved, so use the logical state
    effective_state = from_state_override if from_state_override else current_state

    valid = cfg["valid_transitions"]
    allowed = valid.get(effective_state, [])
    if target_state not in allowed:
        raise ValueError(
            f"Invalid transition: {effective_state} → {target_state}. "
            f"Allowed from {effective_state}: {allowed}"
        )

    # Safety: max active tickets
    if target_state == "active":
        mgmt = Path(cfg["management_root"])
        active_dir = mgmt / cfg["tickets_dir"] / "active"
        active_count = len(list(active_dir.glob("*.md")))
        max_active = cfg["safety"]["max_active_tickets"]
        if active_count >= max_active:
            raise RuntimeError(
                f"Cannot activate: {active_count} ticket(s) already active "
                f"(max {max_active})"
            )

    # Safety: branch validation for active
    if target_state == "active" and cfg["safety"]["require_branch_for_active"]:
        ticket = parse_ticket(path)
        branch = ticket.get("branch", "")
        protected = cfg["safety"]["protected_branches"]
        if branch in protected or not branch:
            raise ValueError(
                f"Ticket branch '{branch}' is protected or empty. "
                f"Protected branches: {protected}"
            )

    dest_dir = Path(cfg["management_root"]) / cfg["tickets_dir"] / target_state
    dest_path = dest_dir / path.name

    msg = f"[{_now()}] {ticket_id}: {effective_state} → {target_state}"
    if dry_run:
        return f"[DRY-RUN] {msg} (would move {path} → {dest_path})"

    shutil.move(str(path), str(dest_path))
    return msg


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_log(cfg: dict, category: str, ticket_id: str, message: str):
    """Append to per-ticket log file under logs/<category>/."""
    log_dir = Path(cfg["management_root"]) / cfg["logs_dir"] / category
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{ticket_id}.log"
    entry = f"[{_now()}] {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# Worker dispatch
# ---------------------------------------------------------------------------

def dispatch_worker(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    """
    Import and run the appropriate worker for the ticket.
    Returns dict with keys: success (bool), message (str), artifacts (list).
    """
    worker_name = ticket.get("worker", "")
    allowed = cfg["allowed_workers"]
    if worker_name not in allowed:
        return {
            "success": False,
            "message": f"Unknown or disallowed worker: {worker_name}. Allowed: {allowed}",
            "artifacts": [],
        }

    # Map worker name to module
    module_map = {
        "code-worker": "code_worker",
        "unity-worker": "unity_worker",
        "blender-worker": "blender_worker",
        "tripo-worker": "tripo_worker",
    }
    module_name = module_map.get(worker_name)
    if not module_name:
        return {"success": False, "message": f"No module mapping for {worker_name}", "artifacts": []}

    # Dynamic import from workers/ package
    workers_dir = _HERE / "workers"
    sys.path.insert(0, str(workers_dir.parent))
    try:
        mod = __import__(f"workers.{module_name}", fromlist=[module_name])
        worker_fn = getattr(mod, "execute", None)
        if not worker_fn:
            return {"success": False, "message": f"Worker {module_name} has no execute() function", "artifacts": []}
        return worker_fn(cfg, ticket, dry_run=dry_run)
    except ImportError as e:
        return {"success": False, "message": f"Failed to import worker {module_name}: {e}", "artifacts": []}
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# Process pipeline
# ---------------------------------------------------------------------------

def process_ticket(cfg: dict, ticket_id: str, dry_run: bool = False) -> int:
    """
    Full pipeline: ready → active → run worker → review/failed.
    Returns exit code: 0 = success, 1 = failure.
    """
    current_state, path = find_ticket(cfg, ticket_id)
    if current_state is None:
        print(f"ERROR: Ticket '{ticket_id}' not found.")
        return 1

    # Track logical state for dry-run (file doesn't move)
    logical_state = current_state

    # If in inbox, move to ready first
    if logical_state == "inbox":
        msg = transition_ticket(cfg, ticket_id, "ready", dry_run=dry_run,
                                from_state_override=logical_state)
        print(msg)
        write_log(cfg, "orchestrator", ticket_id, msg)
        logical_state = "ready"

    # Move to active
    if logical_state == "ready":
        msg = transition_ticket(cfg, ticket_id, "active", dry_run=dry_run,
                                from_state_override=logical_state)
        print(msg)
        write_log(cfg, "orchestrator", ticket_id, msg)
        logical_state = "active"

    if logical_state != "active":
        print(f"ERROR: Ticket is in state '{logical_state}', expected 'active'.")
        return 1

    # Re-read ticket from current location
    _, updated_path = find_ticket(cfg, ticket_id)
    if updated_path is None:
        print("ERROR: Lost ticket after transition.")
        return 1

    ticket = parse_ticket(updated_path)

    # Dispatch worker
    write_log(cfg, "worker", ticket_id, f"Worker dispatch: {ticket.get('worker', '?')}")
    result = dispatch_worker(cfg, ticket, dry_run=dry_run)
    write_log(cfg, "worker", ticket_id, f"Result: success={result['success']} — {result['message']}")
    print(f"Worker result: {result['message']}")

    if result.get("artifacts"):
        write_log(cfg, "worker", ticket_id, f"Artifacts: {result['artifacts']}")

    # Transition based on result
    if result["success"]:
        target = "review"
    else:
        target = "failed"

    msg = transition_ticket(cfg, ticket_id, target, dry_run=dry_run,
                            from_state_override=logical_state)
    print(msg)
    write_log(cfg, "orchestrator", ticket_id, msg)

    return 0 if result["success"] else 1
