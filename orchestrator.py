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

# Approval decisions
APPROVAL_DECISIONS = frozenset(["approved", "rejected", "reticketed"])

# Repo targets (Sprint 3 — dual repo architecture)
REPO_TARGETS = frozenset(["test_repo", "prod_repo"])

# Promotion targets
PROMOTION_TARGETS = frozenset(["test", "prod"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _HERE / "config.json"


def load_config(path: Path = _DEFAULT_CONFIG) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Repo targeting (Sprint 3 — dual repo)
# ---------------------------------------------------------------------------

def resolve_agent_repo(cfg: dict) -> str:
    """Return the repo path agents are allowed to work in. Always test_repo."""
    targets = cfg.get("repo_targets", {})
    test_repo = targets.get("test_repo", "")
    if not test_repo:
        raise ValueError("repo_targets.test_repo is not configured.")
    return test_repo


def resolve_prod_repo(cfg: dict) -> str:
    """Return the prod repo path. Used only for promotion, never for agents."""
    targets = cfg.get("repo_targets", {})
    prod_repo = targets.get("prod_repo", "")
    if not prod_repo:
        raise ValueError("repo_targets.prod_repo is not configured.")
    return prod_repo


def validate_repo_target(cfg: dict, target: str, allow_prod: bool = False):
    """Validate that a repo target is known. Blocks prod_repo unless allow_prod=True."""
    if target not in REPO_TARGETS:
        raise ValueError(f"Unknown repo target: '{target}'. Valid: {sorted(REPO_TARGETS)}")
    if target == "prod_repo" and not allow_prod:
        raise ValueError(
            "prod_repo cannot be used as an agent execution target. "
            "Agents may only work against test_repo."
        )


def validate_repo_separation(cfg: dict) -> bool:
    """Validate that test_repo and prod_repo resolve to different physical paths.
    Raises ValueError if they are the same or missing.
    Returns True if separation is valid.
    """
    test_path = resolve_agent_repo(cfg)
    prod_path = resolve_prod_repo(cfg)

    test_real = Path(test_path).resolve()
    prod_real = Path(prod_path).resolve()

    if test_real == prod_real:
        raise ValueError(
            f"REPO SEPARATION VIOLATION: test_repo and prod_repo resolve to the "
            f"same physical path: {test_real}\n"
            f"  test_repo config: {test_path}\n"
            f"  prod_repo config: {prod_path}\n"
            f"Physical separation is required for safe operation."
        )
    return True


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

    # Enforce: workers always target test_repo, never prod_repo
    agent_repo = resolve_agent_repo(cfg)
    worker_cfg = dict(cfg)
    worker_cfg["_agent_repo"] = agent_repo

    # Dynamic import from workers/ package
    workers_dir = _HERE / "workers"
    sys.path.insert(0, str(workers_dir.parent))
    try:
        mod = __import__(f"workers.{module_name}", fromlist=[module_name])
        worker_fn = getattr(mod, "execute", None)
        if not worker_fn or not callable(worker_fn):
            return {"success": False, "message": f"Worker {module_name} has no callable execute()", "artifacts": []}
        return worker_fn(worker_cfg, ticket, dry_run=dry_run)
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


# ---------------------------------------------------------------------------
# Review / Approval / Promotion (Sprint 3)
# ---------------------------------------------------------------------------

def _reviews_dir(cfg: dict) -> Path:
    d = Path(cfg["management_root"]) / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _promotions_dir(cfg: dict) -> Path:
    d = Path(cfg["management_root"]) / "promotions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_review_package(cfg: dict, ticket_id: str) -> dict:
    """Create a ReviewPackage for a ticket in review state. Returns the package dict."""
    ticket_id = sanitize_ticket_id(ticket_id)
    state, path = find_ticket(cfg, ticket_id)
    if state is None:
        raise FileNotFoundError(f"Ticket not found: {ticket_id}")
    if state != "review":
        raise ValueError(f"Ticket '{ticket_id}' is in state '{state}', expected 'review'.")

    ticket = parse_ticket(path)
    mgmt = Path(cfg["management_root"])

    # Gather artifacts
    artifacts_dir = mgmt / cfg["artifacts_dir"]
    artifacts = []
    if artifacts_dir.exists():
        for f in artifacts_dir.glob(f"{ticket_id}*"):
            artifacts.append(str(f.relative_to(mgmt)))

    # Gather worker log
    worker_log = mgmt / cfg["logs_dir"] / "worker" / f"{ticket_id}.log"
    worker_log_rel = str(worker_log.relative_to(mgmt)) if worker_log.exists() else None

    package = {
        "ticket_id": ticket_id,
        "created_at": _now(),
        "worker": ticket.get("worker", "?"),
        "branch": ticket.get("branch", "?"),
        "repo_target": "test_repo",
        "artifacts": artifacts,
        "worker_log": worker_log_rel,
        "summary": ticket.get("title", ""),
    }

    out = _reviews_dir(cfg) / f"{ticket_id}.review.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(package, f, indent=2, ensure_ascii=False)

    write_log(cfg, "orchestrator", ticket_id, f"ReviewPackage created: {out.name}")
    return package


def load_review_package(cfg: dict, ticket_id: str) -> dict:
    """Load existing ReviewPackage for a ticket."""
    ticket_id = sanitize_ticket_id(ticket_id)
    p = _reviews_dir(cfg) / f"{ticket_id}.review.json"
    if not p.exists():
        raise FileNotFoundError(f"No ReviewPackage for ticket '{ticket_id}'.")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def create_approval_decision(cfg: dict, ticket_id: str, decision: str,
                             reason: str = "") -> dict:
    """Record an approval decision for a ticket. Requires existing ReviewPackage."""
    ticket_id = sanitize_ticket_id(ticket_id)
    if decision not in APPROVAL_DECISIONS:
        raise ValueError(f"Invalid decision: '{decision}'. Valid: {sorted(APPROVAL_DECISIONS)}")

    # Ensure ReviewPackage exists
    load_review_package(cfg, ticket_id)

    # Check approval doesn't already exist
    approval_path = _reviews_dir(cfg) / f"{ticket_id}.approval.json"
    if approval_path.exists():
        raise RuntimeError(
            f"ApprovalDecision already exists for '{ticket_id}'. "
            "Decisions are immutable."
        )

    record = {
        "ticket_id": ticket_id,
        "decision": decision,
        "reviewer": "creative-director",
        "reason": reason,
        "decided_at": _now(),
    }

    with open(approval_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    write_log(cfg, "orchestrator", ticket_id,
              f"ApprovalDecision: {decision} — {reason or '(no reason)'}")

    # Transition ticket based on decision
    state, _ = find_ticket(cfg, ticket_id)
    if state == "review":
        if decision == "approved":
            transition_ticket(cfg, ticket_id, "done")
        elif decision in ("rejected", "reticketed"):
            transition_ticket(cfg, ticket_id, "active")
            transition_ticket(cfg, ticket_id, "failed")

    return record


def load_approval_decision(cfg: dict, ticket_id: str) -> dict:
    """Load existing ApprovalDecision for a ticket."""
    ticket_id = sanitize_ticket_id(ticket_id)
    p = _reviews_dir(cfg) / f"{ticket_id}.approval.json"
    if not p.exists():
        raise FileNotFoundError(f"No ApprovalDecision for ticket '{ticket_id}'.")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def check_promotion_readiness(cfg: dict, ticket_id: str) -> dict:
    """Check all preconditions for promotion. Returns structured result.

    Result: {
        "ready": bool,
        "ticket_id": str,
        "checks": [{"name": str, "passed": bool, "detail": str}, ...]
    }
    """
    ticket_id = sanitize_ticket_id(ticket_id)
    checks = []

    # 1. ReviewPackage exists
    try:
        review = load_review_package(cfg, ticket_id)
        checks.append({"name": "review_package", "passed": True,
                        "detail": f"ReviewPackage exists (created {review.get('created_at', '?')})"})
    except FileNotFoundError:
        checks.append({"name": "review_package", "passed": False,
                        "detail": "No ReviewPackage found"})

    # 2. ApprovalDecision exists and is 'approved'
    try:
        approval = load_approval_decision(cfg, ticket_id)
        decision = approval.get("decision", "?")
        if decision == "approved":
            checks.append({"name": "approval_decision", "passed": True,
                            "detail": f"Decision: approved by {approval.get('reviewer', '?')}"})
        else:
            checks.append({"name": "approval_decision", "passed": False,
                            "detail": f"Decision is '{decision}', not 'approved'"})
    except FileNotFoundError:
        checks.append({"name": "approval_decision", "passed": False,
                        "detail": "No ApprovalDecision found"})

    # 3. Repo separation is enforced
    try:
        validate_repo_separation(cfg)
        checks.append({"name": "repo_separation", "passed": True,
                        "detail": "test_repo and prod_repo are physically distinct"})
    except ValueError as e:
        checks.append({"name": "repo_separation", "passed": False,
                        "detail": str(e)})

    # 4. Both repo paths exist as directories
    try:
        test_path = resolve_agent_repo(cfg)
        if Path(test_path).is_dir():
            checks.append({"name": "test_repo_exists", "passed": True,
                            "detail": f"test_repo exists: {test_path}"})
        else:
            checks.append({"name": "test_repo_exists", "passed": False,
                            "detail": f"test_repo not found: {test_path}"})
    except ValueError as e:
        checks.append({"name": "test_repo_exists", "passed": False, "detail": str(e)})

    try:
        prod_path = resolve_prod_repo(cfg)
        if Path(prod_path).is_dir():
            checks.append({"name": "prod_repo_exists", "passed": True,
                            "detail": f"prod_repo exists: {prod_path}"})
        else:
            checks.append({"name": "prod_repo_exists", "passed": False,
                            "detail": f"prod_repo not found: {prod_path}"})
    except ValueError as e:
        checks.append({"name": "prod_repo_exists", "passed": False, "detail": str(e)})

    ready = all(c["passed"] for c in checks)
    return {"ready": ready, "ticket_id": ticket_id, "checks": checks}


def create_promotion_request(cfg: dict, ticket_id: str,
                             dry_run: bool = False) -> dict:
    """Create a PromotionRequest. Requires approved ApprovalDecision and repo separation."""
    ticket_id = sanitize_ticket_id(ticket_id)

    # Enforce physical repo separation
    validate_repo_separation(cfg)

    # Load and verify approval
    approval = load_approval_decision(cfg, ticket_id)
    if approval["decision"] != "approved":
        raise ValueError(
            f"Cannot promote: ticket '{ticket_id}' decision is "
            f"'{approval['decision']}', not 'approved'."
        )

    # Load review for branch info
    review = load_review_package(cfg, ticket_id)

    request = {
        "ticket_id": ticket_id,
        "approval_ref": f"reviews/{ticket_id}.approval.json",
        "source_repo": "test_repo",
        "source_path": resolve_agent_repo(cfg),
        "target_repo": "prod_repo",
        "target_path": resolve_prod_repo(cfg),
        "branch": review.get("branch", "?"),
        "requested_at": _now(),
        "status": "pending",
    }

    if dry_run:
        request["status"] = "dry_run"
        return request

    out = _promotions_dir(cfg) / f"{ticket_id}.promotion.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(request, f, indent=2, ensure_ascii=False)

    write_log(cfg, "orchestrator", ticket_id,
              f"PromotionRequest created: {review.get('branch', '?')} "
              f"test_repo → prod_repo (status: pending)")
    return request
