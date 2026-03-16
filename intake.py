#!/usr/bin/env python3
"""
HYBRIS Intake Adapter — Safe external message-to-ticket intake pipeline.

Receives, validates, normalizes, and admits external requests into
the ticket system. External input never executes commands, never
touches repos, never triggers promotion. Admitted input stops at
the inbox boundary.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Intake Domain Constants (Sprint 6)
# ---------------------------------------------------------------------------

INTAKE_SOURCES = frozenset([
    "local_simulated",
    "future_whatsapp",
    "future_openclaw",
    "future_sms",
    "future_api",
])

SOURCE_TRUST_LEVELS = frozenset(["trusted", "untrusted", "blocked"])

INTAKE_STATUSES = frozenset([
    "received",
    "rejected",
    "normalized",
    "admitted",
    "duplicate",
    "rate_limited",
    "failed",
])

# Required fields in an intake request payload
REQUIRED_PAYLOAD_FIELDS = frozenset(["title", "worker"])

# Allowed worker values (must match orchestrator WORKER_TYPES)
ALLOWED_WORKERS = frozenset([
    "code-worker", "unity-worker", "blender-worker", "tripo-worker",
])

# Max lengths for sanitization
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_FIELD_LENGTH = 500

# Content patterns that are never allowed in intake
_UNSAFE_PATTERNS = [
    re.compile(r"\.\./"),                     # path traversal
    re.compile(r"[`$]"),                      # shell metacharacters
    re.compile(r"<script", re.IGNORECASE),    # script injection
    re.compile(r";\s*(rm|del|drop|exec)\b", re.IGNORECASE),  # command injection
]

# Safe ticket ID characters
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")

# ---------------------------------------------------------------------------
# Intake config helpers
# ---------------------------------------------------------------------------

def load_intake_config(cfg: dict) -> dict:
    """Extract intake configuration from main config. Returns defaults if missing."""
    return cfg.get("intake", {})


def get_source_trust(cfg: dict, source: str) -> str:
    """Determine trust level for a source. Unknown sources are untrusted."""
    intake = load_intake_config(cfg)
    trusted = intake.get("trusted_sources", [])
    blocked = intake.get("blocked_sources", [])
    if source in blocked:
        return "blocked"
    if source in trusted:
        return "trusted"
    return "untrusted"


def get_rate_limit(cfg: dict) -> dict:
    """Return rate limit configuration."""
    intake = load_intake_config(cfg)
    return intake.get("rate_limit", {
        "max_per_source_per_minute": 5,
        "max_global_per_minute": 20,
    })


# ---------------------------------------------------------------------------
# Intake directories
# ---------------------------------------------------------------------------

def _intake_dir(cfg: dict) -> Path:
    d = Path(cfg["management_root"]) / "intake"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _intake_audit_dir(cfg: dict) -> Path:
    d = _intake_dir(cfg) / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _intake_state_dir(cfg: dict) -> Path:
    d = _intake_dir(cfg) / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Timestamps / IDs
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_intake_id(source: str, payload: dict) -> str:
    """Generate a deterministic intake ID from source + payload content."""
    content = json.dumps({"source": source, "payload": payload},
                         sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"intake-{ts}-{h}"


def _content_hash(payload: dict) -> str:
    """Deterministic hash of payload content for duplicate detection."""
    content = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

def sanitize_intake_field(value: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    """Sanitize a single intake field. Strips unsafe content."""
    if not isinstance(value, str):
        return ""
    # Truncate
    value = value[:max_length].strip()
    # Remove null bytes
    value = value.replace("\x00", "")
    # Remove control characters except newlines
    value = re.sub(r"[\x01-\x09\x0b-\x0c\x0e-\x1f]", "", value)
    return value


def check_unsafe_content(text: str) -> list:
    """Check text for unsafe patterns. Returns list of matched pattern descriptions."""
    violations = []
    for pattern in _UNSAFE_PATTERNS:
        if pattern.search(text):
            violations.append(f"Unsafe pattern: {pattern.pattern}")
    return violations


def validate_payload(payload: dict) -> list:
    """Validate intake payload structure. Returns list of error strings."""
    errors = []
    if not isinstance(payload, dict):
        return ["Payload must be a dict"]

    # Required fields
    for field in REQUIRED_PAYLOAD_FIELDS:
        if field not in payload or not payload[field]:
            errors.append(f"Missing required field: '{field}'")

    # Worker must be allowed
    worker = payload.get("worker", "")
    if worker and worker not in ALLOWED_WORKERS:
        errors.append(
            f"Invalid worker: '{worker}'. Allowed: {sorted(ALLOWED_WORKERS)}"
        )

    # Title length
    title = payload.get("title", "")
    if isinstance(title, str) and len(title) > MAX_TITLE_LENGTH:
        errors.append(f"Title too long: {len(title)} > {MAX_TITLE_LENGTH}")

    # Description length
    desc = payload.get("description", "")
    if isinstance(desc, str) and len(desc) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"Description too long: {len(desc)} > {MAX_DESCRIPTION_LENGTH}"
        )

    # Check all string fields for unsafe content
    for key, val in payload.items():
        if isinstance(val, str):
            unsafe = check_unsafe_content(val)
            if unsafe:
                errors.extend(
                    [f"Field '{key}': {u}" for u in unsafe]
                )

    # Reject fields that should never come from external intake
    forbidden_fields = {"_path", "_body", "id"}
    for ff in forbidden_fields:
        if ff in payload:
            errors.append(f"Forbidden field in intake: '{ff}'")

    return errors


def validate_source(source: str) -> list:
    """Validate source identifier. Returns list of error strings."""
    errors = []
    if not source or not isinstance(source, str):
        errors.append("Source must be a non-empty string")
        return errors
    if source not in INTAKE_SOURCES:
        errors.append(
            f"Unknown intake source: '{source}'. Known: {sorted(INTAKE_SOURCES)}"
        )
    if not _SAFE_ID_RE.match(source):
        errors.append(f"Invalid source identifier: '{source}'")
    return errors


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_request(source: str, payload: dict) -> dict:
    """Normalize an intake request into a ticket candidate.

    Returns a normalized dict suitable for ticket creation.
    Does NOT create the ticket — only normalizes the shape.
    """
    sanitized_title = sanitize_intake_field(
        payload.get("title", ""), MAX_TITLE_LENGTH
    )
    sanitized_desc = sanitize_intake_field(
        payload.get("description", ""), MAX_DESCRIPTION_LENGTH
    )
    worker = payload.get("worker", "")
    branch = sanitize_intake_field(payload.get("branch", ""), 256)
    priority = payload.get("priority", "normal")
    if priority not in ("low", "normal", "high", "critical"):
        priority = "normal"

    return {
        "title": sanitized_title,
        "worker": worker,
        "branch": branch,
        "priority": priority,
        "description": sanitized_desc,
        "intake_source": source,
        "normalized_at": _now(),
    }


# ---------------------------------------------------------------------------
# Duplicate / replay detection
# ---------------------------------------------------------------------------

def _load_seen_hashes(cfg: dict) -> dict:
    """Load the set of recently seen content hashes with timestamps."""
    state_file = _intake_state_dir(cfg) / "seen_hashes.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_seen_hashes(cfg: dict, hashes: dict):
    """Save seen hashes to state file."""
    state_file = _intake_state_dir(cfg) / "seen_hashes.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2, ensure_ascii=False)


def check_duplicate(cfg: dict, payload: dict) -> bool:
    """Check if this payload is a duplicate of a recently seen request.
    Returns True if duplicate.
    """
    h = _content_hash(payload)
    seen = _load_seen_hashes(cfg)

    intake = load_intake_config(cfg)
    window = intake.get("duplicate_window_seconds", 300)

    now = time.time()
    if h in seen:
        seen_at = seen[h].get("seen_at", 0)
        if now - seen_at < window:
            return True

    return False


def _record_hash(cfg: dict, payload: dict):
    """Record a payload hash as seen."""
    h = _content_hash(payload)
    seen = _load_seen_hashes(cfg)
    now = time.time()

    # Prune old entries (older than 1 hour)
    cutoff = now - 3600
    seen = {k: v for k, v in seen.items() if v.get("seen_at", 0) > cutoff}

    seen[h] = {"seen_at": now}
    _save_seen_hashes(cfg, seen)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _load_rate_state(cfg: dict) -> dict:
    """Load rate limit state."""
    state_file = _intake_state_dir(cfg) / "rate_state.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_rate_state(cfg: dict, state: dict):
    """Save rate limit state."""
    state_file = _intake_state_dir(cfg) / "rate_state.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_rate_limit(cfg: dict, source: str) -> bool:
    """Check if source has exceeded rate limit. Returns True if rate-limited."""
    limits = get_rate_limit(cfg)
    max_per_source = limits.get("max_per_source_per_minute", 5)
    max_global = limits.get("max_global_per_minute", 20)

    state = _load_rate_state(cfg)
    now = time.time()
    window = 60.0

    # Prune old entries
    per_source = state.get("per_source", {})
    for s in list(per_source.keys()):
        per_source[s] = [t for t in per_source[s] if now - t < window]
        if not per_source[s]:
            del per_source[s]

    global_ts = [t for t in state.get("global", []) if now - t < window]

    # Check limits
    source_count = len(per_source.get(source, []))
    global_count = len(global_ts)

    if source_count >= max_per_source:
        return True
    if global_count >= max_global:
        return True

    return False


def _record_rate(cfg: dict, source: str):
    """Record a rate limit event."""
    state = _load_rate_state(cfg)
    now = time.time()
    window = 60.0

    per_source = state.get("per_source", {})
    for s in list(per_source.keys()):
        per_source[s] = [t for t in per_source[s] if now - t < window]
        if not per_source[s]:
            del per_source[s]

    if source not in per_source:
        per_source[source] = []
    per_source[source].append(now)

    global_ts = [t for t in state.get("global", []) if now - t < window]
    global_ts.append(now)

    state["per_source"] = per_source
    state["global"] = global_ts
    _save_rate_state(cfg, state)


# ---------------------------------------------------------------------------
# Intake audit trail
# ---------------------------------------------------------------------------

def _append_intake_audit(cfg: dict, record: dict):
    """Append an intake audit record to JSONL file."""
    audit_file = _intake_audit_dir(cfg) / "intake.audit.jsonl"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_intake_audit(cfg: dict) -> list:
    """Load all intake audit records. Returns list of dicts."""
    audit_file = _intake_audit_dir(cfg) / "intake.audit.jsonl"
    if not audit_file.exists():
        return []
    records = []
    with open(audit_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Ticket candidate creation
# ---------------------------------------------------------------------------

_TICKET_CANDIDATE_TEMPLATE = """\
---
id: {id}
title: {title}
worker: {worker}
branch: {branch}
priority: {priority}
intake_source: {intake_source}
---

{description}
"""


def _create_ticket_candidate(cfg: dict, normalized: dict,
                             intake_id: str) -> Path:
    """Create a ticket file in inbox from a normalized intake request.

    Returns path to created ticket file.
    """
    from orchestrator import sanitize_ticket_id, sanitize_path_within

    ticket_id = intake_id
    sanitize_ticket_id(ticket_id)

    mgmt = Path(cfg["management_root"])
    inbox_dir = mgmt / cfg["tickets_dir"] / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    ticket_path = inbox_dir / f"{ticket_id}.md"
    sanitize_path_within(mgmt, ticket_path)

    content = _TICKET_CANDIDATE_TEMPLATE.format(
        id=ticket_id,
        title=normalized["title"],
        worker=normalized["worker"],
        branch=normalized.get("branch", ""),
        priority=normalized.get("priority", "normal"),
        intake_source=normalized.get("intake_source", "unknown"),
        description=normalized.get("description", ""),
    )

    ticket_path.write_text(content, encoding="utf-8")
    return ticket_path


# ---------------------------------------------------------------------------
# Main intake pipeline
# ---------------------------------------------------------------------------

def process_intake(cfg: dict, source: str, payload: dict,
                   admit: bool = True) -> dict:
    """Process an external intake request through the full pipeline.

    Stages:
    1. Validate source
    2. Check source trust
    3. Validate payload
    4. Check duplicate/replay
    5. Check rate limit
    6. Normalize
    7. Admit (create ticket in inbox) — only if admit=True
    8. Write audit record

    Returns intake result dict with status and details.

    IMPORTANT: Admitted intake ONLY creates a ticket in inbox.
    It does NOT execute workers, does NOT trigger promotion,
    does NOT touch test_repo or prod_repo.
    """
    intake_id = _generate_intake_id(source, payload)
    timestamp = _now()

    result = {
        "intake_id": intake_id,
        "source": source,
        "timestamp": timestamp,
        "status": None,
        "detail": None,
        "ticket_path": None,
        "normalized": None,
    }

    # 1. Validate source identifier
    source_errors = validate_source(source)
    if source_errors:
        result["status"] = "rejected"
        result["detail"] = f"Invalid source: {'; '.join(source_errors)}"
        _append_intake_audit(cfg, result)
        return result

    # 2. Check source trust
    trust = get_source_trust(cfg, source)
    if trust == "blocked":
        result["status"] = "rejected"
        result["detail"] = f"Source '{source}' is blocked"
        _append_intake_audit(cfg, result)
        return result

    if trust == "untrusted":
        result["status"] = "rejected"
        result["detail"] = (
            f"Source '{source}' is untrusted. "
            "Add to intake.trusted_sources in config to allow."
        )
        _append_intake_audit(cfg, result)
        return result

    # 3. Validate payload
    payload_errors = validate_payload(payload)
    if payload_errors:
        result["status"] = "rejected"
        result["detail"] = f"Invalid payload: {'; '.join(payload_errors)}"
        _append_intake_audit(cfg, result)
        return result

    # 4. Check duplicate
    if check_duplicate(cfg, payload):
        result["status"] = "duplicate"
        result["detail"] = "Duplicate request detected within dedup window"
        _append_intake_audit(cfg, result)
        return result

    # 5. Check rate limit
    if check_rate_limit(cfg, source):
        result["status"] = "rate_limited"
        result["detail"] = f"Rate limit exceeded for source '{source}'"
        _append_intake_audit(cfg, result)
        return result

    # 6. Normalize
    normalized = normalize_request(source, payload)
    result["normalized"] = normalized

    # 7. Record rate + hash tracking
    _record_rate(cfg, source)
    _record_hash(cfg, payload)

    # 8. Admit or normalize-only
    if admit:
        try:
            ticket_path = _create_ticket_candidate(cfg, normalized, intake_id)
            result["status"] = "admitted"
            result["detail"] = f"Ticket created in inbox: {ticket_path.name}"
            result["ticket_path"] = str(ticket_path)
        except (ValueError, OSError) as e:
            result["status"] = "failed"
            result["detail"] = f"Failed to create ticket: {e}"
    else:
        result["status"] = "normalized"
        result["detail"] = "Request normalized but not admitted (dry-run)"

    _append_intake_audit(cfg, result)
    return result
