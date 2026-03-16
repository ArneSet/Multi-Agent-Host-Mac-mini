#!/usr/bin/env python3
"""
Tests for HYBRIS Intake Adapter (Sprint 6).

Covers: source validation, payload validation, sanitization, normalization,
duplicate detection, rate limiting, admission, rejection, audit trail,
and safety guarantees (no execution, no repos, no promotion).
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

from intake import (
    INTAKE_SOURCES,
    SOURCE_TRUST_LEVELS,
    INTAKE_STATUSES,
    ALLOWED_WORKERS,
    REQUIRED_PAYLOAD_FIELDS,
    MAX_TITLE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    sanitize_intake_field,
    check_unsafe_content,
    validate_payload,
    validate_source,
    normalize_request,
    get_source_trust,
    get_rate_limit,
    check_duplicate,
    check_rate_limit,
    process_intake,
    load_intake_audit,
)


class IntakeTestBase(unittest.TestCase):
    """Base class with temp dirs and config fixture."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="hybris_intake_test_")
        self.mgmt = os.path.join(self.tmpdir, "management")
        os.makedirs(os.path.join(self.mgmt, "tickets", "inbox"), exist_ok=True)
        self.cfg = {
            "management_root": self.mgmt,
            "tickets_dir": "tickets",
            "intake": {
                "trusted_sources": ["local_simulated"],
                "blocked_sources": ["future_sms"],
                "rate_limit": {
                    "max_per_source_per_minute": 3,
                    "max_global_per_minute": 10,
                },
                "duplicate_window_seconds": 60,
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _valid_payload(self):
        return {"title": "Fix terrain rendering", "worker": "unity-worker"}


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

class TestIntakeConstants(unittest.TestCase):
    """Verify domain constant structure."""

    def test_intake_sources_are_frozenset(self):
        self.assertIsInstance(INTAKE_SOURCES, frozenset)
        self.assertIn("local_simulated", INTAKE_SOURCES)

    def test_trust_levels(self):
        self.assertEqual(SOURCE_TRUST_LEVELS,
                         frozenset(["trusted", "untrusted", "blocked"]))

    def test_intake_statuses(self):
        for s in ("received", "rejected", "normalized", "admitted",
                   "duplicate", "rate_limited", "failed"):
            self.assertIn(s, INTAKE_STATUSES)

    def test_allowed_workers_match_orchestrator(self):
        expected = {"code-worker", "unity-worker", "blender-worker",
                    "tripo-worker"}
        self.assertEqual(ALLOWED_WORKERS, expected)


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------

class TestSourceValidation(IntakeTestBase):
    """Test source identifier validation."""

    def test_valid_source(self):
        errors = validate_source("local_simulated")
        self.assertEqual(errors, [])

    def test_unknown_source(self):
        errors = validate_source("random_unknown")
        self.assertTrue(any("Unknown intake source" in e for e in errors))

    def test_empty_source(self):
        errors = validate_source("")
        self.assertTrue(len(errors) > 0)

    def test_none_source(self):
        errors = validate_source(None)
        self.assertTrue(len(errors) > 0)

    def test_source_with_path_traversal(self):
        errors = validate_source("../etc/passwd")
        self.assertTrue(len(errors) > 0)


# ---------------------------------------------------------------------------
# Source trust
# ---------------------------------------------------------------------------

class TestSourceTrust(IntakeTestBase):
    """Test source trust level resolution."""

    def test_trusted_source(self):
        trust = get_source_trust(self.cfg, "local_simulated")
        self.assertEqual(trust, "trusted")

    def test_blocked_source(self):
        trust = get_source_trust(self.cfg, "future_sms")
        self.assertEqual(trust, "blocked")

    def test_untrusted_source(self):
        trust = get_source_trust(self.cfg, "future_whatsapp")
        self.assertEqual(trust, "untrusted")

    def test_unknown_source_is_untrusted(self):
        trust = get_source_trust(self.cfg, "totally_new")
        self.assertEqual(trust, "untrusted")


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------

class TestPayloadValidation(IntakeTestBase):
    """Test payload structure validation."""

    def test_valid_payload(self):
        errors = validate_payload(self._valid_payload())
        self.assertEqual(errors, [])

    def test_missing_title(self):
        errors = validate_payload({"worker": "code-worker"})
        self.assertTrue(any("title" in e for e in errors))

    def test_missing_worker(self):
        errors = validate_payload({"title": "Fix thing"})
        self.assertTrue(any("worker" in e for e in errors))

    def test_invalid_worker(self):
        errors = validate_payload(
            {"title": "Fix thing", "worker": "hack-worker"}
        )
        self.assertTrue(any("Invalid worker" in e for e in errors))

    def test_title_too_long(self):
        errors = validate_payload(
            {"title": "A" * (MAX_TITLE_LENGTH + 1), "worker": "code-worker"}
        )
        self.assertTrue(any("Title too long" in e for e in errors))

    def test_description_too_long(self):
        errors = validate_payload(
            {"title": "Short", "worker": "code-worker",
             "description": "X" * (MAX_DESCRIPTION_LENGTH + 1)}
        )
        self.assertTrue(any("Description too long" in e for e in errors))

    def test_not_a_dict(self):
        errors = validate_payload("not a dict")
        self.assertTrue(any("dict" in e for e in errors))

    def test_forbidden_field_id(self):
        payload = self._valid_payload()
        payload["id"] = "injected-id"
        errors = validate_payload(payload)
        self.assertTrue(any("Forbidden" in e for e in errors))

    def test_forbidden_field_path(self):
        payload = self._valid_payload()
        payload["_path"] = "/etc/passwd"
        errors = validate_payload(payload)
        self.assertTrue(any("Forbidden" in e for e in errors))


# ---------------------------------------------------------------------------
# Unsafe content detection
# ---------------------------------------------------------------------------

class TestUnsafeContent(unittest.TestCase):
    """Test unsafe content pattern detection."""

    def test_path_traversal(self):
        violations = check_unsafe_content("../../../etc/passwd")
        self.assertTrue(len(violations) > 0)

    def test_shell_metachar_backtick(self):
        violations = check_unsafe_content("Run `rm -rf /`")
        self.assertTrue(len(violations) > 0)

    def test_shell_metachar_dollar(self):
        violations = check_unsafe_content("Use $HOME variable")
        self.assertTrue(len(violations) > 0)

    def test_script_injection(self):
        violations = check_unsafe_content("<script>alert(1)</script>")
        self.assertTrue(len(violations) > 0)

    def test_command_injection(self):
        violations = check_unsafe_content("; rm -rf /")
        self.assertTrue(len(violations) > 0)

    def test_safe_content(self):
        violations = check_unsafe_content("Fix terrain rendering bug")
        self.assertEqual(violations, [])

    def test_payload_with_unsafe_field(self):
        payload = {"title": "Fix ../traversal", "worker": "code-worker"}
        errors = validate_payload(payload)
        self.assertTrue(any("Unsafe" in e for e in errors))


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

class TestSanitization(unittest.TestCase):
    """Test field sanitization."""

    def test_truncation(self):
        result = sanitize_intake_field("A" * 1000, 100)
        self.assertEqual(len(result), 100)

    def test_null_byte_removal(self):
        result = sanitize_intake_field("hello\x00world")
        self.assertEqual(result, "helloworld")

    def test_control_char_removal(self):
        result = sanitize_intake_field("hello\x01\x02world")
        self.assertEqual(result, "helloworld")

    def test_newline_preserved(self):
        result = sanitize_intake_field("line1\nline2")
        self.assertIn("\n", result)

    def test_strips_whitespace(self):
        result = sanitize_intake_field("  hello  ")
        self.assertEqual(result, "hello")

    def test_non_string_returns_empty(self):
        result = sanitize_intake_field(12345)
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

class TestNormalization(IntakeTestBase):
    """Test intake request normalization."""

    def test_basic_normalization(self):
        result = normalize_request("local_simulated", self._valid_payload())
        self.assertEqual(result["title"], "Fix terrain rendering")
        self.assertEqual(result["worker"], "unity-worker")
        self.assertEqual(result["intake_source"], "local_simulated")
        self.assertIn("normalized_at", result)

    def test_priority_defaults_to_normal(self):
        result = normalize_request("local_simulated", self._valid_payload())
        self.assertEqual(result["priority"], "normal")

    def test_invalid_priority_normalized(self):
        payload = self._valid_payload()
        payload["priority"] = "super-urgent"
        result = normalize_request("local_simulated", payload)
        self.assertEqual(result["priority"], "normal")

    def test_valid_priority_preserved(self):
        payload = self._valid_payload()
        payload["priority"] = "critical"
        result = normalize_request("local_simulated", payload)
        self.assertEqual(result["priority"], "critical")

    def test_description_sanitized(self):
        payload = self._valid_payload()
        payload["description"] = "  hello\x00world  "
        result = normalize_request("local_simulated", payload)
        self.assertEqual(result["description"], "helloworld")


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection(IntakeTestBase):
    """Test duplicate/replay detection."""

    def test_first_request_is_not_duplicate(self):
        self.assertFalse(check_duplicate(self.cfg, self._valid_payload()))

    def test_same_payload_after_admit_is_duplicate(self):
        payload = self._valid_payload()
        # First: admit to register hash
        process_intake(self.cfg, "local_simulated", payload, admit=True)
        # Second: check duplicate
        self.assertTrue(check_duplicate(self.cfg, payload))

    def test_different_payload_is_not_duplicate(self):
        process_intake(self.cfg, "local_simulated", self._valid_payload(),
                       admit=True)
        other = {"title": "Different task", "worker": "code-worker"}
        self.assertFalse(check_duplicate(self.cfg, other))


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting(IntakeTestBase):
    """Test rate limit enforcement."""

    def test_under_limit_passes(self):
        self.assertFalse(check_rate_limit(self.cfg, "local_simulated"))

    def test_exceeding_per_source_limit(self):
        # Submit 3 requests (the limit) then check
        payload = {"title": "Task", "worker": "code-worker"}
        for i in range(3):
            p = {"title": f"Task {i}", "worker": "code-worker"}
            process_intake(self.cfg, "local_simulated", p, admit=True)
        self.assertTrue(check_rate_limit(self.cfg, "local_simulated"))

    def test_rate_limit_config(self):
        limits = get_rate_limit(self.cfg)
        self.assertEqual(limits["max_per_source_per_minute"], 3)
        self.assertEqual(limits["max_global_per_minute"], 10)


# ---------------------------------------------------------------------------
# Full pipeline: admission
# ---------------------------------------------------------------------------

class TestIntakeAdmission(IntakeTestBase):
    """Test full intake pipeline — happy path and admission."""

    def test_admit_creates_ticket_in_inbox(self):
        result = process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=True
        )
        self.assertEqual(result["status"], "admitted")
        self.assertIsNotNone(result["ticket_path"])
        self.assertTrue(Path(result["ticket_path"]).exists())
        # Verify ticket is in inbox
        self.assertIn("inbox", result["ticket_path"])

    def test_admitted_ticket_contains_metadata(self):
        result = process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=True
        )
        content = Path(result["ticket_path"]).read_text()
        self.assertIn("title: Fix terrain rendering", content)
        self.assertIn("worker: unity-worker", content)
        self.assertIn("intake_source: local_simulated", content)

    def test_simulate_does_not_create_ticket(self):
        result = process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=False
        )
        self.assertEqual(result["status"], "normalized")
        self.assertIsNone(result["ticket_path"])


# ---------------------------------------------------------------------------
# Full pipeline: rejection
# ---------------------------------------------------------------------------

class TestIntakeRejection(IntakeTestBase):
    """Test intake rejection scenarios."""

    def test_blocked_source_rejected(self):
        result = process_intake(
            self.cfg, "future_sms", self._valid_payload(), admit=True
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("blocked", result["detail"])

    def test_untrusted_source_rejected(self):
        result = process_intake(
            self.cfg, "future_whatsapp", self._valid_payload(), admit=True
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("untrusted", result["detail"])

    def test_invalid_payload_rejected(self):
        result = process_intake(
            self.cfg, "local_simulated", {"worker": "code-worker"}, admit=True
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("Missing required field", result["detail"])

    def test_unsafe_content_rejected(self):
        payload = {"title": "Fix ../traversal", "worker": "code-worker"}
        result = process_intake(
            self.cfg, "local_simulated", payload, admit=True
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("Unsafe", result["detail"])

    def test_unknown_source_rejected(self):
        result = process_intake(
            self.cfg, "totally_unknown_source",
            self._valid_payload(), admit=True
        )
        self.assertEqual(result["status"], "rejected")

    def test_duplicate_returns_duplicate_status(self):
        payload = self._valid_payload()
        process_intake(self.cfg, "local_simulated", payload, admit=True)
        result = process_intake(
            self.cfg, "local_simulated", payload, admit=True
        )
        self.assertEqual(result["status"], "duplicate")

    def test_rate_limited_returns_rate_limited(self):
        for i in range(3):
            p = {"title": f"Task {i}", "worker": "code-worker"}
            process_intake(self.cfg, "local_simulated", p, admit=True)
        result = process_intake(
            self.cfg, "local_simulated",
            {"title": "One more", "worker": "code-worker"}, admit=True
        )
        self.assertEqual(result["status"], "rate_limited")


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

class TestIntakeAudit(IntakeTestBase):
    """Test intake audit trail."""

    def test_admitted_request_has_audit(self):
        process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=True
        )
        records = load_intake_audit(self.cfg)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "admitted")

    def test_rejected_request_has_audit(self):
        process_intake(self.cfg, "future_sms", self._valid_payload())
        records = load_intake_audit(self.cfg)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "rejected")

    def test_multiple_requests_accumulate_audits(self):
        process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=True
        )
        process_intake(self.cfg, "future_sms", self._valid_payload())
        records = load_intake_audit(self.cfg)
        self.assertEqual(len(records), 2)

    def test_audit_contains_source_and_id(self):
        process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=True
        )
        records = load_intake_audit(self.cfg)
        self.assertEqual(records[0]["source"], "local_simulated")
        self.assertTrue(records[0]["intake_id"].startswith("intake-"))


# ---------------------------------------------------------------------------
# Safety guarantees
# ---------------------------------------------------------------------------

class TestIntakeSafety(IntakeTestBase):
    """Critical: intake must NEVER trigger execution, repo access, or promotion."""

    def test_intake_does_not_import_dispatch_worker(self):
        """Intake module must not import dispatch_worker."""
        import intake as m
        source = Path(m.__file__).read_text()
        self.assertNotIn("dispatch_worker", source)

    def test_intake_does_not_import_execute_promotion(self):
        """Intake module must not import execute_promotion."""
        import intake as m
        source = Path(m.__file__).read_text()
        self.assertNotIn("execute_promotion", source)

    def test_intake_does_not_import_process_ticket(self):
        """Intake module must not import process_ticket."""
        import intake as m
        source = Path(m.__file__).read_text()
        self.assertNotIn("process_ticket", source)

    def test_admitted_ticket_is_only_a_file(self):
        """An admitted intake request creates only a file. Nothing else."""
        result = process_intake(
            self.cfg, "local_simulated", self._valid_payload(), admit=True
        )
        # The result only has a ticket_path — no repo, no worker log
        self.assertIsNotNone(result["ticket_path"])
        self.assertTrue(result["ticket_path"].endswith(".md"))
        # Verify no execution happened by checking the result dict
        self.assertNotIn("worker_log", result)
        self.assertNotIn("repo_commit", result)

    def test_intake_never_touches_repos(self):
        """Intake code must not call or import repo-related functions."""
        import intake as m
        source = Path(m.__file__).read_text()
        self.assertNotIn("resolve_agent_repo", source)
        self.assertNotIn("resolve_prod_repo", source)
        # No functional references to repo config keys (ignore comments/docstrings)
        import ast
        tree = ast.parse(source)
        names = {
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        attrs = {
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        all_symbols = names | attrs
        self.assertNotIn("test_repo", all_symbols)
        self.assertNotIn("prod_repo", all_symbols)


if __name__ == "__main__":
    unittest.main()
