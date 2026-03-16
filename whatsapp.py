#!/usr/bin/env python3
"""
HYBRIS WhatsApp Connector — Safe WhatsApp message boundary.

Receives authenticated WhatsApp webhooks, verifies sender identity,
normalizes messages into intake requests. External WhatsApp input
never executes commands, never touches repos, never triggers promotion.
Admitted input stops at the inbox boundary.
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# WhatsApp Domain Constants (Sprint 7)
# ---------------------------------------------------------------------------

WHATSAPP_MESSAGE_TYPES = frozenset([
    "text",
    # Future: "image", "document", "audio", "video", "location", "contact"
])

WHATSAPP_STATUSES = frozenset([
    "received",
    "verified",
    "authorized",
    "normalized",
    "admitted",
    "rejected",
    "duplicate",
    "rate_limited",
    "failed",
])

# WhatsApp Business API constants
WHATSAPP_API_VERSION = "v18.0"
WHATSAPP_BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"

# ---------------------------------------------------------------------------
# WhatsApp config helpers
# ---------------------------------------------------------------------------

def load_whatsapp_config(cfg: dict) -> dict:
    """Extract WhatsApp configuration from main config. Returns defaults if missing."""
    return cfg.get("whatsapp", {})


def is_whatsapp_enabled(cfg: dict) -> bool:
    """Check if WhatsApp connector is enabled."""
    return load_whatsapp_config(cfg).get("enabled", False)


def get_whatsapp_access_token(cfg: dict) -> str:
    """Get WhatsApp access token from config or environment."""
    config_token = load_whatsapp_config(cfg).get("access_token", "")
    if config_token and not config_token.startswith("EAAEXAMPLE"):
        return config_token
    # Fallback to environment
    return os.environ.get("WHATSAPP_ACCESS_TOKEN", "")


def get_whatsapp_verify_token(cfg: dict) -> str:
    """Get WhatsApp verify token from config or environment."""
    config_token = load_whatsapp_config(cfg).get("verify_token", "")
    if config_token and not config_token.endswith("_placeholder"):
        return config_token
    # Fallback to environment
    return os.environ.get("WHATSAPP_VERIFY_TOKEN", "")


def get_authorized_senders(cfg: dict) -> List[str]:
    """Get list of authorized WhatsApp sender numbers."""
    return load_whatsapp_config(cfg).get("authorized_senders", [])


def get_whatsapp_rate_limit(cfg: dict) -> int:
    """Get rate limit per sender per minute."""
    return load_whatsapp_config(cfg).get("rate_limit_per_sender", 5)


def get_whatsapp_dedup_window(cfg: dict) -> int:
    """Get deduplication window in seconds."""
    return load_whatsapp_config(cfg).get("dedup_window_seconds", 300)


# ---------------------------------------------------------------------------
# WhatsApp directories
# ---------------------------------------------------------------------------

def _whatsapp_dir(cfg: dict) -> Path:
    d = Path(cfg["management_root"]) / "whatsapp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _whatsapp_audit_dir(cfg: dict) -> Path:
    d = _whatsapp_dir(cfg) / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _whatsapp_state_dir(cfg: dict) -> Path:
    d = _whatsapp_dir(cfg) / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Provider verification
# ---------------------------------------------------------------------------

def verify_whatsapp_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify WhatsApp webhook signature using HMAC-SHA256."""
    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()

    provided_signature = signature[7:]  # Remove "sha256=" prefix
    return hmac.compare_digest(expected_signature, provided_signature)


def verify_webhook_request(cfg: dict, payload: bytes,
                          signature: Optional[str] = None) -> Tuple[bool, str]:
    """Verify incoming WhatsApp webhook request.

    Returns (is_valid, reason)
    """
    if not is_whatsapp_enabled(cfg):
        return False, "WhatsApp connector disabled"

    verify_token = get_whatsapp_verify_token(cfg)
    if not verify_token:
        return False, "No verify token configured"

    if signature:
        # Verify signature if provided
        if not verify_whatsapp_signature(payload, signature, verify_token):
            return False, "Invalid signature"
    else:
        # For development/testing, allow unsigned if explicitly configured
        if not load_whatsapp_config(cfg).get("allow_unsigned_webhooks", False):
            return False, "Signature required but not provided"

    return True, "Verified"


# ---------------------------------------------------------------------------
# Sender authorization
# ---------------------------------------------------------------------------

def authorize_sender(cfg: dict, sender_number: str) -> Tuple[bool, str]:
    """Check if sender is authorized.

    Returns (is_authorized, reason)
    """
    authorized = get_authorized_senders(cfg)
    if sender_number in authorized:
        return True, "Authorized sender"
    return False, f"Sender {sender_number} not in authorized list"


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def parse_whatsapp_messages(payload: dict) -> List[Optional[Dict]]:
    """Parse WhatsApp webhook payload into list of message dicts.

    Returns list of message dicts, or empty list if no valid messages.
    Each message dict contains: id, from, timestamp, type, text
    Invalid messages in batch return None in their position.
    """
    messages = []
    try:
        # WhatsApp webhook structure
        if "object" not in payload or payload["object"] != "whatsapp_business_account":
            return []

        if "entry" not in payload:
            return []

        for entry in payload["entry"]:
            if "changes" not in entry:
                continue

            for change in entry["changes"]:
                if change.get("field") != "messages":
                    continue

                if "value" not in change:
                    continue

                value = change["value"]
                if "messages" not in value:
                    continue

                # Safety limit: max 10 messages per batch
                batch_messages = value["messages"][:10]

                for message in batch_messages:
                    try:
                        msg_type = message.get("type")
                        if msg_type not in WHATSAPP_MESSAGE_TYPES:
                            messages.append(None)  # Invalid type
                            continue

                        # Only handle text messages in v1
                        if msg_type != "text":
                            messages.append(None)  # Unsupported type
                            continue

                        parsed_message = {
                            "id": message["id"],
                            "from": message["from"],
                            "timestamp": message["timestamp"],
                            "type": msg_type,
                            "text": message.get("text", {}).get("body", ""),
                        }
                        messages.append(parsed_message)

                    except (KeyError, TypeError):
                        messages.append(None)  # Malformed message

        return messages

    except (KeyError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Idempotency / replay detection
# ---------------------------------------------------------------------------

def _load_whatsapp_processed_messages(cfg: dict) -> Dict:
    """Load processed message state."""
    state_file = _whatsapp_state_dir(cfg) / "processed_messages.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_whatsapp_processed_messages(cfg: dict, messages: Dict):
    """Save processed message state."""
    state_file = _whatsapp_state_dir(cfg) / "processed_messages.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def check_whatsapp_replay(cfg: dict, message_id: str) -> bool:
    """Check if message ID has been processed before."""
    processed = _load_whatsapp_processed_messages(cfg)
    return message_id in processed


def _record_whatsapp_message_processed(cfg: dict, message_id: str):
    """Record message as processed."""
    processed = _load_whatsapp_processed_messages(cfg)
    now = time.time()

    # Prune old entries (older than dedup window)
    window = get_whatsapp_dedup_window(cfg)
    cutoff = now - window
    processed = {k: v for k, v in processed.items() if v.get("processed_at", 0) > cutoff}

    processed[message_id] = {"processed_at": now}
    _save_whatsapp_processed_messages(cfg, processed)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _load_whatsapp_rate_state(cfg: dict) -> Dict:
    """Load rate limit state."""
    state_file = _whatsapp_state_dir(cfg) / "rate_state.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_whatsapp_rate_state(cfg: dict, state: Dict):
    """Save rate limit state."""
    state_file = _whatsapp_state_dir(cfg) / "rate_state.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_whatsapp_rate_limit(cfg: dict, sender: str) -> bool:
    """Check if sender has exceeded rate limit. Returns True if rate-limited."""
    limit = get_whatsapp_rate_limit(cfg)
    state = _load_whatsapp_rate_state(cfg)
    now = time.time()
    window = 60.0  # per minute

    # Prune old entries
    per_sender = state.get("per_sender", {})
    for s in list(per_sender.keys()):
        per_sender[s] = [t for t in per_sender[s] if now - t < window]
        if not per_sender[s]:
            del per_sender[s]

    sender_count = len(per_sender.get(sender, []))
    if sender_count >= limit:
        return True

    return False


def _record_whatsapp_rate_event(cfg: dict, sender: str):
    """Record a rate limit event."""
    state = _load_whatsapp_rate_state(cfg)
    now = time.time()
    window = 60.0

    per_sender = state.get("per_sender", {})
    for s in list(per_sender.keys()):
        per_sender[s] = [t for t in per_sender[s] if now - t < window]
        if not per_sender[s]:
            del per_sender[s]

    if sender not in per_sender:
        per_sender[sender] = []
    per_sender[sender].append(now)

    state["per_sender"] = per_sender
    _save_whatsapp_rate_state(cfg, state)


# ---------------------------------------------------------------------------
# Message normalization
# ---------------------------------------------------------------------------

def normalize_whatsapp_message(message: Dict) -> Dict:
    """Normalize WhatsApp message into intake request format."""
    sender = message["from"]
    text = message["text"].strip()

    # Create title from first line or truncate
    lines = text.split('\n', 1)
    title = lines[0][:80]  # Limit title length
    description = lines[1] if len(lines) > 1 else ""

    return {
        "title": f"WhatsApp: {title}",
        "worker": "code-worker",  # Default worker
        "description": f"Message from {sender}: {description}".strip(),
        "branch": "feature/whatsapp-request",
        "priority": "normal",
        "intake_source": "whatsapp",
    }


# ---------------------------------------------------------------------------
# WhatsApp audit trail
# ---------------------------------------------------------------------------

def _append_whatsapp_audit(cfg: dict, record: Dict):
    """Append WhatsApp audit record to JSONL file."""
    audit_file = _whatsapp_audit_dir(cfg) / "whatsapp.audit.jsonl"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_whatsapp_audit(cfg: dict) -> List[Dict]:
    """Load all WhatsApp audit records."""
    audit_file = _whatsapp_audit_dir(cfg) / "whatsapp.audit.jsonl"
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
# Main WhatsApp processing
# ---------------------------------------------------------------------------

def process_whatsapp_webhook(cfg: dict, payload: bytes,
                           signature: Optional[str] = None) -> Dict:
    """Process incoming WhatsApp webhook with batch support.

    Returns batch processing result dict with per-message outcomes.
    """
    batch_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    batch_result = {
        "timestamp": batch_timestamp,
        "batch_size": 0,
        "processed_messages": 0,
        "admitted_count": 0,
        "rejected_count": 0,
        "duplicate_count": 0,
        "rate_limited_count": 0,
        "message_results": [],
        "status": None,
        "detail": None,
    }

    try:
        # 1. Verify webhook authenticity (provider level)
        verified, reason = verify_webhook_request(cfg, payload, signature)
        if not verified:
            batch_result["status"] = "rejected"
            batch_result["detail"] = f"Provider verification failed: {reason}"
            # Create audit records for all messages in failed payload
            json_payload = json.loads(payload.decode("utf-8"))
            messages = parse_whatsapp_messages(json_payload)
            for i, message in enumerate(messages):
                if message:
                    msg_result = {
                        "timestamp": batch_timestamp,
                        "message_id": message["id"],
                        "sender": message["from"],
                        "status": "rejected",
                        "detail": f"Provider verification failed: {reason}",
                        "batch_position": i + 1,
                        "batch_size": len(messages),
                    }
                    _append_whatsapp_audit(cfg, msg_result)
                    batch_result["message_results"].append(msg_result)
                    batch_result["rejected_count"] += 1
            return batch_result

        # 2. Parse all messages in batch
        json_payload = json.loads(payload.decode("utf-8"))
        messages = parse_whatsapp_messages(json_payload)
        batch_result["batch_size"] = len(messages)

        if not messages:
            batch_result["status"] = "rejected"
            batch_result["detail"] = "No valid messages found in webhook"
            _append_whatsapp_audit(cfg, {
                "timestamp": batch_timestamp,
                "status": "rejected",
                "detail": "No valid messages found in webhook"
            })
            return batch_result

        # 3. Process each message individually
        for i, message in enumerate(messages):
            if message is None:
                # Malformed or unsupported message
                msg_result = {
                    "timestamp": batch_timestamp,
                    "status": "rejected",
                    "detail": "Malformed or unsupported message",
                    "batch_position": i + 1,
                    "batch_size": len(messages),
                }
                _append_whatsapp_audit(cfg, msg_result)
                batch_result["message_results"].append(msg_result)
                batch_result["rejected_count"] += 1
                continue

            # Process valid message
            msg_result = _process_single_whatsapp_message(cfg, message, batch_timestamp, i + 1, len(messages))
            batch_result["message_results"].append(msg_result)
            batch_result["processed_messages"] += 1

            # Update counters
            if msg_result["status"] == "admitted":
                batch_result["admitted_count"] += 1
            elif msg_result["status"] == "rejected":
                batch_result["rejected_count"] += 1
            elif msg_result["status"] == "duplicate":
                batch_result["duplicate_count"] += 1
            elif msg_result["status"] == "rate_limited":
                batch_result["rate_limited_count"] += 1

        # 4. Set overall batch status
        if batch_result["admitted_count"] > 0:
            batch_result["status"] = "admitted"
            batch_result["detail"] = f"Batch processed: {batch_result['admitted_count']} admitted, {batch_result['rejected_count']} rejected, {batch_result['duplicate_count']} duplicates, {batch_result['rate_limited_count']} rate limited"
        elif batch_result["processed_messages"] == 0:
            batch_result["status"] = "rejected"
            batch_result["detail"] = "No messages could be processed"
        else:
            batch_result["status"] = "processed"
            batch_result["detail"] = f"Batch processed with no admissions: {batch_result['rejected_count']} rejected, {batch_result['duplicate_count']} duplicates, {batch_result['rate_limited_count']} rate limited"

        return batch_result

    except Exception as e:
        batch_result["status"] = "failed"
        batch_result["detail"] = f"Batch processing error: {e}"
        return batch_result


def _process_single_whatsapp_message(cfg: dict, message: Dict, batch_timestamp: str,
                                   batch_position: int, batch_size: int) -> Dict:
    """Process a single WhatsApp message within a batch.

    Returns message processing result dict.
    """
    result = {
        "timestamp": batch_timestamp,
        "message_id": message["id"],
        "sender": message["from"],
        "batch_position": batch_position,
        "batch_size": batch_size,
        "status": None,
        "detail": None,
        "intake_result": None,
    }

    try:
        # 1. Check replay (idempotency)
        if check_whatsapp_replay(cfg, message["id"]):
            result["status"] = "duplicate"
            result["detail"] = "Message already processed"
            _append_whatsapp_audit(cfg, result)
            return result

        # 2. Authorize sender
        authorized, auth_reason = authorize_sender(cfg, message["from"])
        if not authorized:
            result["status"] = "rejected"
            result["detail"] = f"Unauthorized sender: {auth_reason}"
            _append_whatsapp_audit(cfg, result)
            return result

        # 3. Check rate limit
        if check_whatsapp_rate_limit(cfg, message["from"]):
            result["status"] = "rate_limited"
            result["detail"] = f"Rate limit exceeded for sender {message['from']}"
            _append_whatsapp_audit(cfg, result)
            return result

        # 4. Normalize message
        normalized = normalize_whatsapp_message(message)

        # 5. Submit to intake
        from intake import process_intake
        intake_result = process_intake(cfg, "whatsapp", normalized, admit=True)

        result["status"] = "admitted" if intake_result["status"] == "admitted" else "failed"
        result["detail"] = intake_result.get("detail", "Intake processing completed")
        result["intake_result"] = intake_result

        # 6. Record processing
        _record_whatsapp_message_processed(cfg, message["id"])
        _record_whatsapp_rate_event(cfg, message["from"])

    except Exception as e:
        result["status"] = "failed"
        result["detail"] = f"Message processing error: {e}"

    _append_whatsapp_audit(cfg, result)
    return result


# ---------------------------------------------------------------------------
# WhatsApp Business API helpers (for future use)
# ---------------------------------------------------------------------------

def send_whatsapp_message(access_token: str, to: str, message: str) -> bool:
    """Send a WhatsApp message via Business API.

    Placeholder for future outbound messaging.
    """
    # TODO: Implement when outbound messaging is needed
    return False


def verify_whatsapp_token(access_token: str) -> bool:
    """Verify WhatsApp access token is valid.

    Placeholder for token validation.
    """
    # TODO: Implement token verification
    return bool(access_token)
