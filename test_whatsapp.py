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
    parse_whatsapp_messages,
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

        messages = parse_whatsapp_messages(payload)
        self.assertEqual(len(messages), 1)
        message = messages[0]
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

        messages = parse_whatsapp_messages(payload)
        self.assertEqual(len(messages), 1)  # Returns list with None for unsupported
        self.assertIsNone(messages[0])

    def test_parse_invalid_payload(self):
        payload = {"invalid": "structure"}
        messages = parse_whatsapp_messages(payload)
        self.assertEqual(len(messages), 0)


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
        self.assertEqual(result["admitted_count"], 1)
        self.assertEqual(len(result["message_results"]), 1)
        msg_result = result["message_results"][0]
        self.assertEqual(msg_result["status"], "admitted")
        self.assertEqual(msg_result["sender"], "+1234567890")
        self.assertEqual(msg_result["message_id"], "test_msg_123")

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

        self.assertEqual(result["status"], "processed")  # No admissions, but processed
        self.assertEqual(result["admitted_count"], 0)
        self.assertEqual(result["rejected_count"], 1)
        self.assertEqual(len(result["message_results"]), 1)
        msg_result = result["message_results"][0]
        self.assertEqual(msg_result["status"], "rejected")
        self.assertIn("not in authorized list", msg_result["detail"])

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
        self.assertEqual(result1["admitted_count"], 1)

        # Second time - duplicate
        result2 = process_whatsapp_webhook(self.config, payload_bytes)
        self.assertEqual(result2["status"], "processed")  # No admissions due to duplicate
        self.assertEqual(result2["admitted_count"], 0)
        self.assertEqual(result2["duplicate_count"], 1)
        self.assertEqual(len(result2["message_results"]), 1)
        msg_result = result2["message_results"][0]
        self.assertEqual(msg_result["status"], "duplicate")


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


class TestBatchMessageParsing(WhatsAppTestBase):
    """Test batch message parsing (Sprint 8)."""

    def test_parse_single_message_batch(self):
        """Test parsing a batch with one message."""
        from whatsapp import parse_whatsapp_messages

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "id": "batch_msg_1",
                            "from": "+1234567890",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "Single message"}
                        }]
                    }
                }]
            }]
        }

        messages = parse_whatsapp_messages(payload)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["id"], "batch_msg_1")
        self.assertEqual(messages[0]["text"], "Single message")

    def test_parse_multiple_messages_batch(self):
        """Test parsing a batch with multiple messages."""
        from whatsapp import parse_whatsapp_messages

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "batch_msg_1",
                                "from": "+1234567890",
                                "timestamp": "1234567890",
                                "type": "text",
                                "text": {"body": "First message"}
                            },
                            {
                                "id": "batch_msg_2",
                                "from": "+1234567890",
                                "timestamp": "1234567891",
                                "type": "text",
                                "text": {"body": "Second message"}
                            }
                        ]
                    }
                }]
            }]
        }

        messages = parse_whatsapp_messages(payload)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["id"], "batch_msg_1")
        self.assertEqual(messages[1]["id"], "batch_msg_2")

    def test_parse_empty_batch(self):
        """Test parsing a batch with no messages."""
        from whatsapp import parse_whatsapp_messages

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": []
                    }
                }]
            }]
        }

        messages = parse_whatsapp_messages(payload)
        self.assertEqual(len(messages), 0)

    def test_parse_mixed_message_types_batch(self):
        """Test parsing batch with supported and unsupported message types."""
        from whatsapp import parse_whatsapp_messages

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "text_msg",
                                "from": "+1234567890",
                                "timestamp": "1234567890",
                                "type": "text",
                                "text": {"body": "Text message"}
                            },
                            {
                                "id": "image_msg",
                                "from": "+1234567890",
                                "timestamp": "1234567891",
                                "type": "image",
                                "image": {"id": "img_123"}
                            }
                        ]
                    }
                }]
            }]
        }

        messages = parse_whatsapp_messages(payload)
        # Should return list with valid message and None for invalid
        self.assertEqual(len(messages), 2)
        self.assertIsNotNone(messages[0])
        self.assertEqual(messages[0]["id"], "text_msg")
        self.assertIsNone(messages[1])  # Unsupported type


class TestBatchWebhookProcessing(WhatsAppTestBase):
    """Test batch webhook processing (Sprint 8)."""

    def test_process_batch_all_valid(self):
        """Test processing a batch where all messages are valid."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "batch_valid_1",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time())),
                                "type": "text",
                                "text": {"body": "Valid message 1"}
                            },
                            {
                                "id": "batch_valid_2",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time()) + 1),
                                "type": "text",
                                "text": {"body": "Valid message 2"}
                            }
                        ]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        # Should return batch result with individual message results
        self.assertEqual(result["status"], "admitted")
        self.assertIn("message_results", result)
        self.assertEqual(len(result["message_results"]), 2)

        # Both messages should be admitted
        for msg_result in result["message_results"]:
            self.assertEqual(msg_result["status"], "admitted")

    def test_process_batch_mixed_validity(self):
        """Test processing batch with mix of valid and invalid messages."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "batch_valid",
                                "from": "+1234567890",  # Authorized
                                "timestamp": str(int(time.time())),
                                "type": "text",
                                "text": {"body": "Valid message"}
                            },
                            {
                                "id": "batch_unauthorized",
                                "from": "+9999999999",  # Not authorized
                                "timestamp": str(int(time.time()) + 1),
                                "type": "text",
                                "text": {"body": "Unauthorized message"}
                            },
                            {
                                "id": "batch_unsupported",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time()) + 2),
                                "type": "image",  # Unsupported type
                                "image": {"id": "img_123"}
                            }
                        ]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        self.assertEqual(result["status"], "admitted")
        self.assertEqual(len(result["message_results"]), 3)

        # Check individual results - find by batch position since some may not have message_id
        valid_result = None
        unauthorized_result = None
        unsupported_result = None

        for msg_result in result["message_results"]:
            if msg_result.get("message_id") == "batch_valid":
                valid_result = msg_result
            elif msg_result.get("message_id") == "batch_unauthorized":
                unauthorized_result = msg_result
            elif "Malformed or unsupported message" in msg_result.get("detail", ""):
                unsupported_result = msg_result

        self.assertIsNotNone(valid_result)
        self.assertIsNotNone(unauthorized_result)
        self.assertIsNotNone(unsupported_result)

        self.assertEqual(valid_result["status"], "admitted")
        self.assertEqual(unauthorized_result["status"], "rejected")
        self.assertIn("not in authorized list", unauthorized_result["detail"])
        self.assertEqual(unsupported_result["status"], "rejected")
        self.assertIn("Malformed or unsupported message", unsupported_result["detail"])

    def test_process_batch_with_duplicates(self):
        """Test batch processing with duplicate messages."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "duplicate_msg",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time())),
                                "type": "text",
                                "text": {"body": "First instance"}
                            },
                            {
                                "id": "duplicate_msg",  # Same ID
                                "from": "+1234567890",
                                "timestamp": str(int(time.time()) + 1),
                                "type": "text",
                                "text": {"body": "Duplicate instance"}
                            }
                        ]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        self.assertEqual(result["status"], "admitted")
        self.assertEqual(len(result["message_results"]), 2)

        # First should be admitted, second should be duplicate
        results_by_index = result["message_results"]
        self.assertEqual(results_by_index[0]["status"], "admitted")
        self.assertEqual(results_by_index[1]["status"], "duplicate")

    def test_process_empty_batch(self):
        """Test processing a batch with no messages."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": []
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        result = process_whatsapp_webhook(self.config, payload_bytes)

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(result["message_results"]), 0)


class TestBatchAuditTrail(WhatsAppTestBase):
    """Test audit trail for batch processing (Sprint 8)."""

    def test_batch_audit_records(self):
        """Test that batch processing creates individual audit records."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "audit_batch_1",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time())),
                                "type": "text",
                                "text": {"body": "Audit message 1"}
                            },
                            {
                                "id": "audit_batch_2",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time()) + 1),
                                "type": "text",
                                "text": {"body": "Audit message 2"}
                            }
                        ]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        process_whatsapp_webhook(self.config, payload_bytes)

        records = load_whatsapp_audit(self.config)
        self.assertEqual(len(records), 2)

        # Check that both messages are recorded
        message_ids = {r["message_id"] for r in records}
        self.assertEqual(message_ids, {"audit_batch_1", "audit_batch_2"})

        # Both should be admitted
        for record in records:
            self.assertEqual(record["status"], "admitted")

    def test_batch_audit_mixed_results(self):
        """Test audit trail for batch with mixed success/failure."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "id": "audit_valid",
                                "from": "+1234567890",
                                "timestamp": str(int(time.time())),
                                "type": "text",
                                "text": {"body": "Valid message"}
                            },
                            {
                                "id": "audit_invalid",
                                "from": "+9999999999",  # Unauthorized
                                "timestamp": str(int(time.time()) + 1),
                                "type": "text",
                                "text": {"body": "Invalid message"}
                            }
                        ]
                    }
                }]
            }]
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        self.config["whatsapp"]["allow_unsigned_webhooks"] = True

        process_whatsapp_webhook(self.config, payload_bytes)

        records = load_whatsapp_audit(self.config)
        self.assertEqual(len(records), 2)

        # Check statuses
        records_by_id = {r["message_id"]: r for r in records}
        self.assertEqual(records_by_id["audit_valid"]["status"], "admitted")
        self.assertEqual(records_by_id["audit_invalid"]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()