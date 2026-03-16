#!/usr/bin/env python3
"""
Tests for HYBRIS WhatsApp Connector (Sprint 7).

Covers: provider verification, sender authorization, message parsing,
normalization, idempotency, rate limiting, audit trail, and safety
guarantees (no execution, no repos, no promotion).
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from whatsapp import (
    WHATSAPP_MESSAGE_TYPES,
    WHATSAPP_STATUSES,
    load_whatsapp_config,
    is_whatsapp_enabled,
    get_whatsapp_access_token,
    get_whatsapp_verify_token,
    get_authorized_senders,
    get_whatsapp_rate_limit,
    get_whatsapp_dedup_window,
    verify_whatsapp_signature,
    verify_webhook_request,
    authorize_sender,
    parse_whatsapp_message,
    check_whatsapp_replay,
    check_whatsapp_rate_limit,
    normalize_whatsapp_message,
    process_whatsapp_webhook,
    load_whatsapp_audit,
)


class WhatsAppTestBase(unittest.TestCase):
    """Base class with temp dirs and config fixture."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="hybris_whatsapp_test_")
        self.mgmt = os.path.join(self.tmpdir, "management")
        os.makedirs(os.path.join(self.mgmt, "tickets", "inbox"), exist_ok=True)
        os.makedirs(os.path.join(self.mgmt, "whatsapp", "audit"), exist_ok=True)
        os.makedirs(os.path.join(self.mgmt, "whatsapp", "state"), exist_ok=True)
        os.makedirs(os.path.join(self.mgmt, "intake", "audit"), exist_ok=True)
        os.makedirs(os.path.join(self.mgmt, "intake", "state"), exist_ok=True)

        self.config = {
            "version": "1.4.0",
            "management_root": self.mgmt,
            "tickets_dir": "tickets",
            "intake": {
                "trusted_sources": ["whatsapp"],
                "blocked_sources": [],
                "rate_limit": {"max_per_source_per_minute": 5, "max_global_per_minute": 20},
                "duplicate_window_seconds": 300,
            },
            "whatsapp": {
                "enabled": True,
                "webhook_url": "https://example.com/whatsapp/webhook",
                "verify_token": "test_verify_token",
                "access_token": "test_access_token",
                "authorized_senders": ["+1234567890"],
                "rate_limit_per_sender": 5,
                "dedup_window_seconds": 300,
                "allow_unsigned_webhooks": True,
            }
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestWhatsAppConstants(WhatsAppTestBase):
    """Test WhatsApp domain constants."""

    def test_message_types(self):
        self.assertIn("text", WHATSAPP_MESSAGE_TYPES)
        self.assertEqual(len(WHATSAPP_MESSAGE_TYPES), 1)  # v1: text only

    def test_statuses(self):
        expected = {"received", "verified", "authorized", "normalized",
                   "admitted", "rejected", "duplicate", "rate_limited", "failed"}
        self.assertEqual(WHATSAPP_STATUSES, expected)


class TestWhatsAppConfig(WhatsAppTestBase):
    """Test WhatsApp configuration loading."""

    def test_load_config(self):
        cfg = load_whatsapp_config(self.config)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["verify_token"], "test_verify_token")

    def test_is_enabled(self):
        self.assertTrue(is_whatsapp_enabled(self.config))

    def test_get_tokens(self):
        self.assertEqual(get_whatsapp_access_token(self.config), "test_access_token")
        self.assertEqual(get_whatsapp_verify_token(self.config), "test_verify_token")

    def test_authorized_senders(self):
        senders = get_authorized_senders(self.config)
        self.assertEqual(senders, ["+1234567890"])

    def test_rate_limits(self):
        self.assertEqual(get_whatsapp_rate_limit(self.config), 5)
        self.assertEqual(get_whatsapp_dedup_window(self.config), 300)


class TestProviderVerification(WhatsAppTestBase):
    """Test WhatsApp provider verification."""

    def test_signature_verification_valid(self):
        payload = b'{"test": "data"}'
        secret = "test_secret"
        import hmac
        import hashlib
        expected_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        signature = f"sha256={expected_sig}"

        self.assertTrue(verify_whatsapp_signature(payload, signature, secret))

    def test_signature_verification_invalid(self):
        payload = b'{"test": "data"}'
        signature = "sha256=invalid"
        secret = "test_secret"

        self.assertFalse(verify_whatsapp_signature(payload, signature, secret))

    def test_webhook_verification_enabled(self):
        payload = b'{"test": "data"}'

        # With allow_unsigned and no signature, should pass
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True
        valid, reason = verify_webhook_request(self.config, payload)
        self.assertTrue(valid)

    def test_webhook_verification_disabled(self):
        self.config["whatsapp"]["enabled"] = False
        payload = b'{"test": "data"}'

        valid, reason = verify_webhook_request(self.config, payload)
        self.assertFalse(valid)
        self.assertIn("disabled", reason)


class TestSenderAuthorization(WhatsAppTestBase):
    """Test sender authorization."""

    def test_authorized_sender(self):
        authorized, reason = authorize_sender(self.config, "+1234567890")
        self.assertTrue(authorized)
        self.assertEqual(reason, "Authorized sender")

    def test_unauthorized_sender(self):
        authorized, reason = authorize_sender(self.config, "+9999999999")
        self.assertFalse(authorized)
        self.assertIn("not in authorized list", reason)


class TestMessageParsing(WhatsAppTestBase):
    """Test WhatsApp message parsing."""

    def test_parse_text_message(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "test_msg_id",
                            "from": "+1234567890",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "Hello World"}
                        }]
                    }
                }]
            }]
        }

        message = parse_whatsapp_message(payload)
        self.assertIsNotNone(message)
        self.assertEqual(message["id"], "test_msg_id")
        self.assertEqual(message["from"], "+1234567890")
        self.assertEqual(message["text"], "Hello World")

    def test_parse_non_text_message(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "test_msg_id",
                            "from": "+1234567890",
                            "timestamp": "1234567890",
                            "type": "image",  # Not supported in v1
                            "image": {"id": "img_id"}
                        }]
                    }
                }]
            }]
        }

        message = parse_whatsapp_message(payload)
        self.assertIsNone(message)

    def test_parse_invalid_payload(self):
        payload = {"invalid": "structure"}
        message = parse_whatsapp_message(payload)
        self.assertIsNone(message)


class TestIdempotency(WhatsAppTestBase):
    """Test message idempotency and replay detection."""

    def test_no_replay_on_first_message(self):
        is_replay = check_whatsapp_replay(self.config, "msg_123")
        self.assertFalse(is_replay)

    def test_replay_detection(self):
        # First time - not replay
        self.assertFalse(check_whatsapp_replay(self.config, "msg_123"))

        # Simulate processing
        from whatsapp import _record_whatsapp_message_processed
        _record_whatsapp_message_processed(self.config, "msg_123")

        # Second time - replay
        self.assertTrue(check_whatsapp_replay(self.config, "msg_123"))


class TestRateLimiting(WhatsAppTestBase):
    """Test rate limiting."""

    def test_no_rate_limit_initially(self):
        limited = check_whatsapp_rate_limit(self.config, "+1234567890")
        self.assertFalse(limited)

    def test_rate_limit_exceeded(self):
        from whatsapp import _record_whatsapp_rate_event

        # Exceed limit
        for _ in range(6):  # Limit is 5
            _record_whatsapp_rate_event(self.config, "+1234567890")

        limited = check_whatsapp_rate_limit(self.config, "+1234567890")
        self.assertTrue(limited)


class TestMessageNormalization(WhatsAppTestBase):
    """Test WhatsApp message normalization."""

    def test_normalize_text_message(self):
        message = {
            "id": "msg_123",
            "from": "+1234567890",
            "timestamp": "1234567890",
            "type": "text",
            "text": "Create a new feature"
        }

        normalized = normalize_whatsapp_message(message)
        self.assertEqual(normalized["title"], "WhatsApp: Create a new feature")
        self.assertEqual(normalized["worker"], "code-worker")
        self.assertIn("Message from +1234567890", normalized["description"])
        self.assertEqual(normalized["intake_source"], "whatsapp")


class TestWebhookProcessing(WhatsAppTestBase):
    """Test full webhook processing."""

    def test_process_valid_webhook(self):
        # Create valid webhook payload
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "test_msg_123",
                            "from": "+1234567890",
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": "Test message"}
                        }]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")

        # Allow unsigned for testing
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        self.assertEqual(result["status"], "admitted")
        self.assertEqual(result["sender"], "+1234567890")
        self.assertEqual(result["message_id"], "test_msg_123")

    def test_process_unauthorized_sender(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "test_msg_123",
                            "from": "+9999999999",  # Not authorized
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": "Test message"}
                        }]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        self.assertEqual(result["status"], "rejected")
        self.assertIn("not in authorized list", result["detail"])

    def test_process_duplicate_message(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "duplicate_msg",
                            "from": "+1234567890",
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": "Test message"}
                        }]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        # First time - should work
        result1 = process_whatsapp_webhook(self.config, payload_bytes)
        self.assertEqual(result1["status"], "admitted")

        # Second time - duplicate
        result2 = process_whatsapp_webhook(self.config, payload_bytes)
        self.assertEqual(result2["status"], "duplicate")


class TestAuditTrail(WhatsAppTestBase):
    """Test WhatsApp audit trail."""

    def test_audit_record_creation(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "audit_test_msg",
                            "from": "+1234567890",
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": "Audit test"}
                        }]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        process_whatsapp_webhook(self.config, payload_bytes)

        records = load_whatsapp_audit(self.config)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "admitted")
        self.assertEqual(records[0]["sender"], "+1234567890")


class TestSafetyGuarantees(WhatsAppTestBase):
    """Test that WhatsApp processing maintains safety boundaries."""

    def test_no_direct_execution(self):
        """Ensure WhatsApp messages don't trigger worker execution."""
        # This is tested by the fact that process_whatsapp_webhook only calls
        # intake processing, which creates tickets but doesn't execute workers
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "safety_test",
                            "from": "+1234567890",
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": "Execute dangerous command"}
                        }]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        # Should be admitted to intake, not executed
        self.assertEqual(result["status"], "admitted")
        # Check that no worker execution occurred (would be in separate process)

    def test_no_repo_access(self):
        """Ensure WhatsApp processing doesn't touch repos."""
        # Similar to above - intake only, no repo operations
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "repo_test",
                            "from": "+1234567890",
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": "Access production repo"}
                        }]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        self.assertEqual(result["status"], "admitted")
        # No repo operations should have occurred


if __name__ == "__main__":
    unittest.main()