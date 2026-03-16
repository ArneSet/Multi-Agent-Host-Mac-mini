#!/usr/bin/env python3
"""
HYBRIS Host Orchestrator — File-based ticket state machine.

Moves tickets through states, invokes worker stubs, writes logs.
No network, no shell exec from ticket content, deterministic.
"""

import fcntl
import json
import os
import re
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Domain Constants (Sprint 2 — see docs/domain-model.md)
# ---------------------------------------------------------------------------

# Canonical worker types — must match _WORKER_MODULE_MAP keys and config allowlist
WORKER_TYPES = frozenset(["code-worker", "unity-worker", "blender-worker", "tripo-worker"])

# Implemented ticket states (Sprint 1)
TICKET_STATES = frozenset(["inbox", "ready", "active", "review", "done", "failed"])

# Target ticket states (Sprint 2 model — not yet active in state machine)
TARGET_TICKET_STATES = frozenset([
    "draft", "triaged", "ready", "active", "qa",
    "review", "approved", "rejected", "reticketed", "promoted", "failed",
])

# Priority levels
PRIORITIES = frozenset(["low", "normal", "high", "critical"])

# Approval decisions (Sprint 2 model — not yet active)
APPROVAL_DECISIONS = frozenset(["approved", "rejected", "reticketed"])

# Promotion targets (Sprint 2 model — not yet active)
PROMOTION_TARGETS = frozenset(["staging_target", "promotion_target", "prod_target"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _HERE / "config.json"


def load_config(path: Path = _DEFAULT_CONFIG) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def sanitize_ticket_id(ticket_id: str) -> str:
    """Validate and return ticket_id, or raise ValueError.

    Rejects path traversal, shell metacharacters, and empty/overly long IDs.
    """
    if not ticket_id or not isinstance(ticket_id, str):
        raise ValueError("Ticket ID must be a non-empty string.")
    if not _SAFE_ID_RE.match(ticket_id):
        raise ValueError(
            f"Invalid ticket ID: '{ticket_id}'. "
            "Must be 1-128 chars, alphanumeric start, only [a-zA-Z0-9._-]."
        )
    # Reject any path traversal attempts
    if ".." in ticket_id or "/" in ticket_id or "\\" in ticket_id:
        raise ValueError(f"Ticket ID contains path traversal characters: '{ticket_id}'")
    return ticket_id


def sanitize_path_within(base: Path, target: Path) -> Path:
    """Ensure target is strictly within base. Raises ValueError otherwise."""
    try:
        resolved_base = base.resolve()
        resolved_target = target.resolve()
        resolved_target.relative_to(resolved_base)
        return resolved_target
    except ValueError:
        raise ValueError(
            f"Path escape detected: {target} is not within {base}"
        )


# ---------------------------------------------------------------------------
# Ticket locking
# ---------------------------------------------------------------------------

@contextmanager
def ticket_lock(cfg: dict, ticket_id: str):
    """Acquire an exclusive file lock for a ticket. Prevents concurrent processing."""
    ticket_id = sanitize_ticket_id(ticket_id)
    lock_dir = Path(cfg["management_root"]) / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / f"{ticket_id}.lock"
    sanitize_path_within(lock_dir, lock_file)

    fd = open(lock_file, "w", encoding="utf-8")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(f"{os.getpid()}\n")
        fd.flush()
        yield
    except BlockingIOError:
        fd.close()
        raise RuntimeError(
            f"Ticket '{ticket_id}' is locked by another process. "
            f"Lock file: {lock_file}"
        )
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Atomic file move
# ---------------------------------------------------------------------------

def atomic_move(src: Path, dest_dir: Path) -> Path:
    """Move a file atomically within the same filesystem.

    Writes to a temp file in dest_dir, then renames (which is atomic on POSIX).
    Falls back to shutil.move if os.rename fails (cross-device).
    """
    dest_path = dest_dir / src.name
    tmp_path = dest_dir / f".tmp_{src.name}"

    # Copy to temp location in target dir
    shutil.copy2(str(src), str(tmp_path))

    try:
        # Atomic rename within same directory
        os.rename(str(tmp_path), str(dest_path))
        # Only remove source after successful rename
        src.unlink()
    except OSError:
        # Cross-device fallback: tmp is already in place, rename it
        tmp_path.unlink(missing_ok=True)
        shutil.move(str(src), str(dest_path))

    return dest_path


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
    ticket_id = sanitize_ticket_id(ticket_id)
    mgmt = Path(cfg["management_root"])
    for state in cfg["ticket_states"]:
        state_dir = mgmt / cfg["tickets_dir"] / state
        for f in state_dir.glob("*.md"):
            # Skip temp files from atomic moves
            if f.name.startswith(".tmp_"):
                continue
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
            if f.name.startswith(".tmp_"):
                continue
            try:
                t = parse_ticket(f)
                results.append((state, t.get("id", "?"), t.get("title", "?"), str(f)))
            except ValueError:
                results.append((state, "?", "PARSE_ERROR", str(f)))
    return results


_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9./_-]{0,255}$")


def validate_branch(cfg: dict, branch: str):
    """Validate branch name: must exist, not protected, no traversal."""
    protected = cfg["safety"]["protected_branches"]
    if not branch:
        raise ValueError("Ticket branch is empty. A non-protected branch is required.")
    if branch in protected:
        raise ValueError(
            f"Ticket branch '{branch}' is protected. "
            f"Protected branches: {protected}"
        )
    if not _SAFE_BRANCH_RE.match(branch):
        raise ValueError(
            f"Invalid branch name: '{branch}'. "
            "Must be alphanumeric start, only [a-zA-Z0-9./_-]."
        )
    if ".." in branch:
        raise ValueError(f"Branch name contains path traversal: '{branch}'")


def transition_ticket(cfg: dict, ticket_id: str, target_state: str,
                      dry_run: bool = False, from_state_override: str = None) -> str:
    """Move ticket to target_state. Returns log message.
    from_state_override: use this instead of filesystem lookup (for dry-run chaining).
    """
    ticket_id = sanitize_ticket_id(ticket_id)

    # Validate target_state is a known state
    if target_state not in cfg["ticket_states"]:
        raise ValueError(f"Unknown target state: '{target_state}'")

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
        active_count = sum(1 for f in active_dir.glob("*.md") if not f.name.startswith(".tmp_"))
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
        validate_branch(cfg, branch)

    dest_dir = Path(cfg["management_root"]) / cfg["tickets_dir"] / target_state
    sanitize_path_within(Path(cfg["management_root"]), dest_dir)
    dest_path = dest_dir / path.name

    msg = f"[{_now()}] {ticket_id}: {effective_state} → {target_state}"
    if dry_run:
        return f"[DRY-RUN] {msg} (would move {path} → {dest_path})"

    atomic_move(path, dest_dir)
    return msg


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_log(cfg: dict, category: str, ticket_id: str, message: str):
    """Append to per-ticket log file under logs/<category>/."""
    ticket_id = sanitize_ticket_id(ticket_id)
    # Sanitize category to prevent path traversal
    if not re.match(r"^[a-zA-Z0-9_-]+$", category):
        raise ValueError(f"Invalid log category: '{category}'")
    log_dir = Path(cfg["management_root"]) / cfg["logs_dir"] / category
    sanitize_path_within(Path(cfg["management_root"]), log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{ticket_id}.log"
    entry = f"[{_now()}] {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# Worker dispatch
# ---------------------------------------------------------------------------

_WORKER_MODULE_MAP = {
    "code-worker": "code_worker",
    "unity-worker": "unity_worker",
    "blender-worker": "blender_worker",
    "tripo-worker": "tripo_worker",
}


def dispatch_worker(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    """
    Import and run the appropriate worker for the ticket.
    Returns dict with keys: success (bool), message (str), artifacts (list).
    """
    worker_name = ticket.get("worker", "")
    allowed = cfg.get("allowed_workers", [])

    # Strict allowlist: worker must be both in config AND in our hardcoded map
    if worker_name not in allowed:
        return {
            "success": False,
            "message": f"Unknown or disallowed worker: {worker_name}. Allowed: {allowed}",
            "artifacts": [],
        }

    module_name = _WORKER_MODULE_MAP.get(worker_name)
    if not module_name:
        return {
            "success": False,
            "message": f"No module mapping for worker '{worker_name}' — check _WORKER_MODULE_MAP",
            "artifacts": [],
        }

    # Validate module_name is a simple identifier (no dots, slashes, traversal)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", module_name):
        return {
            "success": False,
            "message": f"Invalid module name: '{module_name}'",
            "artifacts": [],
        }

    # Dynamic import from workers/ package
    workers_dir = _HERE / "workers"
    sys.path.insert(0, str(workers_dir.parent))
    try:
        mod = __import__(f"workers.{module_name}", fromlist=[module_name])
        worker_fn = getattr(mod, "execute", None)
        if not worker_fn or not callable(worker_fn):
            return {"success": False, "message": f"Worker {module_name} has no callable execute()", "artifacts": []}
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
    ticket_id = sanitize_ticket_id(ticket_id)

    with ticket_lock(cfg, ticket_id):
        return _process_ticket_inner(cfg, ticket_id, dry_run)


def _process_ticket_inner(cfg: dict, ticket_id: str, dry_run: bool) -> int:
    """Inner pipeline, called under ticket_lock."""
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
