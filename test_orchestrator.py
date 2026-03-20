#!/usr/bin/env python3
"""
Tests for HYBRIS Host Orchestrator hardening.

Run with: python3 -m pytest test_orchestrator.py -v
Or:       python3 test_orchestrator.py
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import orchestrator as orc

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_cfg(tmp: str) -> dict:
    """Build a minimal config pointing at a temp directory."""
    mgmt = os.path.join(tmp, "management")
    os.makedirs(mgmt, exist_ok=True)
    cfg = {
        "version": "1.0.0",
        "project_name": "TEST",
        "game_repo_root": tmp,
        "host_repo_root": tmp,
        "management_root": mgmt,
        "tickets_dir": "tickets",
        "logs_dir": "logs",
        "artifacts_dir": "artifacts",
        "sessions_dir": "sessions",
        "ticket_states": ["inbox", "ready", "active", "review", "done", "failed"],
        "valid_transitions": {
            "inbox": ["ready"],
            "ready": ["active"],
            "active": ["review", "failed"],
            "review": ["done", "active"],
            "failed": ["ready"],
        },
        "allowed_workers": ["code-worker", "unity-worker"],
        "repo_targets": {
            "test_repo": tmp,
            "prod_repo": os.path.join(tmp, "prod_repo"),
        },
        "safety": {
            "max_active_tickets": 1,
            "protected_branches": ["main", "master", "develop"],
            "allow_shell_exec_from_tickets": False,
            "require_branch_for_active": True,
            "auto_commit": False,
            "auto_merge": False,
        },
    }
    # Create state directories
    for state in cfg["ticket_states"]:
        os.makedirs(os.path.join(mgmt, "tickets", state), exist_ok=True)
    return cfg


_TICKET_TEMPLATE = """\
---
id: {id}
title: {title}
worker: {worker}
branch: {branch}
---

{body}
"""


def _create_ticket(cfg, state, ticket_id, title="Test",
                   worker="code-worker", branch="feature/test", body="..."):
    """Write a ticket file into the given state directory."""
    mgmt = cfg["management_root"]
    path = Path(mgmt) / cfg["tickets_dir"] / state / f"{ticket_id}.md"
    path.write_text(
        _TICKET_TEMPLATE.format(id=ticket_id, title=title,
                                worker=worker, branch=branch, body=body),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# sanitize_ticket_id
# ---------------------------------------------------------------------------

class TestSanitizeTicketId(unittest.TestCase):

    def test_valid_ids(self):
        for tid in ["fix-123", "ABC.def", "a", "x" * 128, "v1.0.0-rc1"]:
            self.assertEqual(orc.sanitize_ticket_id(tid), tid)

    def test_empty(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id("")

    def test_none(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id(None)

    def test_path_traversal_dots(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id("../../etc/passwd")

    def test_path_traversal_slash(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id("foo/bar")

    def test_shell_metachar(self):
        for bad in ["$(cmd)", "; rm -rf", "tick`et"]:
            with self.assertRaises(ValueError, msg=f"Should reject: {bad}"):
                orc.sanitize_ticket_id(bad)

    def test_too_long(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id("a" * 200)

    def test_starts_with_dot(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id(".hidden")

    def test_starts_with_dash(self):
        with self.assertRaises(ValueError):
            orc.sanitize_ticket_id("-flag")


# ---------------------------------------------------------------------------
# validate_branch
# ---------------------------------------------------------------------------

class TestValidateBranch(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_branch(self):
        orc.validate_branch(self.cfg, "feature/my-thing")  # should not raise

    def test_protected_main(self):
        with self.assertRaises(ValueError):
            orc.validate_branch(self.cfg, "main")

    def test_protected_master(self):
        with self.assertRaises(ValueError):
            orc.validate_branch(self.cfg, "master")

    def test_empty_branch(self):
        with self.assertRaises(ValueError):
            orc.validate_branch(self.cfg, "")

    def test_traversal(self):
        with self.assertRaises(ValueError):
            orc.validate_branch(self.cfg, "feature/../../../etc/passwd")


# ---------------------------------------------------------------------------
# sanitize_path_within
# ---------------------------------------------------------------------------

class TestSanitizePathWithin(unittest.TestCase):

    def test_valid_subpath(self):
        base = Path("/tmp/test_base")
        target = Path("/tmp/test_base/sub/dir")
        result = orc.sanitize_path_within(base, target)
        self.assertTrue(str(result).startswith(str(base.resolve())))

    def test_escape_rejected(self):
        base = Path("/tmp/test_base")
        target = Path("/tmp/test_base/../../../etc/passwd")
        with self.assertRaises(ValueError):
            orc.sanitize_path_within(base, target)


# ---------------------------------------------------------------------------
# transition_ticket
# ---------------------------------------------------------------------------

class TestTransitionTicket(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inbox_to_ready(self):
        _create_ticket(self.cfg, "inbox", "t-001")
        msg = orc.transition_ticket(self.cfg, "t-001", "ready")
        self.assertIn("t-001", msg)
        self.assertIn("inbox → ready", msg)
        # File should now be in ready/
        state, path = orc.find_ticket(self.cfg, "t-001")
        self.assertEqual(state, "ready")

    def test_invalid_transition(self):
        _create_ticket(self.cfg, "inbox", "t-002")
        with self.assertRaises(ValueError):
            orc.transition_ticket(self.cfg, "t-002", "active")

    def test_unknown_target_state(self):
        _create_ticket(self.cfg, "inbox", "t-003")
        with self.assertRaises(ValueError):
            orc.transition_ticket(self.cfg, "t-003", "nonexistent")

    def test_max_active_enforced(self):
        # Create an already active ticket
        _create_ticket(self.cfg, "active", "t-existing", branch="feature/a")
        # Try to activate another
        _create_ticket(self.cfg, "ready", "t-new", branch="feature/b")
        with self.assertRaises(RuntimeError):
            orc.transition_ticket(self.cfg, "t-new", "active")

    def test_protected_branch_rejected(self):
        _create_ticket(self.cfg, "ready", "t-prot", branch="main")
        with self.assertRaises(ValueError):
            orc.transition_ticket(self.cfg, "t-prot", "active")

    def test_dry_run_no_move(self):
        _create_ticket(self.cfg, "inbox", "t-dry")
        msg = orc.transition_ticket(self.cfg, "t-dry", "ready", dry_run=True)
        self.assertIn("DRY-RUN", msg)
        # File should still be in inbox
        state, _ = orc.find_ticket(self.cfg, "t-dry")
        self.assertEqual(state, "inbox")


# ---------------------------------------------------------------------------
# dispatch_worker
# ---------------------------------------------------------------------------

class TestDispatchWorker(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_disallowed_worker(self):
        ticket = {"worker": "evil-worker"}
        result = orc.dispatch_worker(self.cfg, ticket)
        self.assertFalse(result["success"])
        self.assertIn("disallowed", result["message"])

    def test_empty_worker(self):
        ticket = {"worker": ""}
        result = orc.dispatch_worker(self.cfg, ticket)
        self.assertFalse(result["success"])

    def test_no_module_mapping(self):
        # Add a worker to allowed but not to _WORKER_MODULE_MAP
        self.cfg["allowed_workers"].append("phantom-worker")
        ticket = {"worker": "phantom-worker"}
        result = orc.dispatch_worker(self.cfg, ticket)
        self.assertFalse(result["success"])
        self.assertIn("No module mapping", result["message"])

    def test_stub_worker_returns_relative_artifact_path(self):
        """Stub workers must return artifact paths relative to management_root."""
        mgmt = Path(self.cfg["management_root"])
        for sub in ["orchestrator", "worker", "agent-runs"]:
            (mgmt / "logs" / sub).mkdir(parents=True, exist_ok=True)
        self.cfg["allowed_workers"].append("blender-worker")
        ticket = {"id": "t-stub1", "title": "stub test", "worker": "blender-worker",
                  "branch": "feature/test", "description": "test"}
        result = orc.dispatch_worker(self.cfg, ticket)
        self.assertTrue(result["success"], f"Worker failed: {result['message']}")
        self.assertEqual(len(result["artifacts"]), 1)
        art = result["artifacts"][0]
        # Must be relative (not absolute), and must resolve under management_root
        self.assertFalse(art.startswith("/"), f"Artifact path is absolute: {art}")
        self.assertTrue((mgmt / art).exists(), f"Artifact not found: {mgmt / art}")


# ---------------------------------------------------------------------------
# write_log
# ---------------------------------------------------------------------------

class TestWriteLog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_log(self):
        orc.write_log(self.cfg, "orchestrator", "t-log1", "hello")
        log_file = Path(self.cfg["management_root"]) / "logs" / "orchestrator" / "t-log1.log"
        self.assertTrue(log_file.exists())
        content = log_file.read_text()
        self.assertIn("hello", content)

    def test_invalid_category_traversal(self):
        with self.assertRaises(ValueError):
            orc.write_log(self.cfg, "../../../etc", "t-log2", "bad")

    def test_invalid_category_slash(self):
        with self.assertRaises(ValueError):
            orc.write_log(self.cfg, "foo/bar", "t-log3", "bad")

    def test_invalid_ticket_id(self):
        with self.assertRaises(ValueError):
            orc.write_log(self.cfg, "test", "../../etc/passwd", "bad")


# ---------------------------------------------------------------------------
# atomic_move
# ---------------------------------------------------------------------------

class TestAtomicMove(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_move_success(self):
        src_dir = Path(self.tmp) / "src"
        dst_dir = Path(self.tmp) / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        src_file = src_dir / "test.md"
        src_file.write_text("content")

        result = orc.atomic_move(src_file, dst_dir)
        self.assertEqual(result, dst_dir / "test.md")
        self.assertTrue(result.exists())
        self.assertFalse(src_file.exists())
        self.assertEqual(result.read_text(), "content")


# ---------------------------------------------------------------------------
# ticket_lock
# ---------------------------------------------------------------------------

class TestTicketLock(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_and_release(self):
        with orc.ticket_lock(self.cfg, "t-lock1"):
            lock_file = Path(self.cfg["management_root"]) / "locks" / "t-lock1.lock"
            self.assertTrue(lock_file.exists())
        # Lock file should be cleaned up
        self.assertFalse(lock_file.exists())

    def test_invalid_ticket_id_rejected(self):
        with self.assertRaises(ValueError):
            with orc.ticket_lock(self.cfg, "../escape"):
                pass


# ---------------------------------------------------------------------------
# Full pipeline (process_ticket)
# ---------------------------------------------------------------------------

class TestProcessTicket(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_not_found(self):
        rc = orc.process_ticket(self.cfg, "nonexistent")
        self.assertEqual(rc, 1)

    def test_inbox_to_review_dry_run(self):
        _create_ticket(self.cfg, "inbox", "t-pipe1", branch="feature/pipe")
        rc = orc.process_ticket(self.cfg, "t-pipe1", dry_run=True)
        # dry-run: file stays in inbox
        state, _ = orc.find_ticket(self.cfg, "t-pipe1")
        self.assertEqual(state, "inbox")


# ---------------------------------------------------------------------------
# Repo targeting (Sprint 3)
# ---------------------------------------------------------------------------

class TestRepoTargeting(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolve_agent_repo_returns_test_repo(self):
        result = orc.resolve_agent_repo(self.cfg)
        self.assertEqual(result, self.tmp)

    def test_resolve_agent_repo_missing_raises(self):
        cfg = dict(self.cfg)
        cfg["repo_targets"] = {}
        with self.assertRaises(ValueError):
            orc.resolve_agent_repo(cfg)

    def test_resolve_prod_repo(self):
        result = orc.resolve_prod_repo(self.cfg)
        self.assertEqual(result, os.path.join(self.tmp, "prod_repo"))

    def test_validate_repo_target_test_ok(self):
        orc.validate_repo_target(self.cfg, "test_repo")  # should not raise

    def test_validate_repo_target_prod_blocked(self):
        with self.assertRaises(ValueError) as ctx:
            orc.validate_repo_target(self.cfg, "prod_repo")
        self.assertIn("cannot be used as an agent", str(ctx.exception))

    def test_validate_repo_target_prod_allowed_explicit(self):
        orc.validate_repo_target(self.cfg, "prod_repo", allow_prod=True)

    def test_validate_repo_target_unknown_rejected(self):
        with self.assertRaises(ValueError):
            orc.validate_repo_target(self.cfg, "mystery_repo")

    def test_dispatch_worker_injects_agent_repo(self):
        """dispatch_worker should resolve test_repo and pass _agent_repo to worker."""
        ticket = {
            "id": "test-dispatch-001",
            "title": "Test dispatch",
            "worker": "code-worker",
            "branch": "feature/test",
            "description": "target_file: test.txt\n---\ntest content",
        }
        result = orc.dispatch_worker(self.cfg, ticket, dry_run=True)
        # code_worker succeeds in dry-run with valid inputs
        self.assertTrue(result["success"])


# ---------------------------------------------------------------------------
# Review / Approval / Promotion (Sprint 3)
# ---------------------------------------------------------------------------

class TestReviewApprovalPromotion(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)
        # Create logs dirs needed by write_log
        mgmt = Path(self.cfg["management_root"])
        for sub in ["orchestrator", "worker", "agent-runs"]:
            (mgmt / "logs" / sub).mkdir(parents=True, exist_ok=True)
        # Create prod_repo dir (for promotion path resolution)
        os.makedirs(self.cfg["repo_targets"]["prod_repo"], exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put_ticket_in_review(self, ticket_id="t-rev1"):
        """Helper: create a ticket directly in review state."""
        _create_ticket(self.cfg, "review", ticket_id, branch="feature/test")
        return ticket_id

    def test_create_review_package(self):
        tid = self._put_ticket_in_review()
        pkg = orc.create_review_package(self.cfg, tid)
        self.assertEqual(pkg["ticket_id"], tid)
        self.assertEqual(pkg["repo_target"], "test_repo")
        self.assertIn("created_at", pkg)
        # File written
        review_file = Path(self.cfg["management_root"]) / "reviews" / f"{tid}.review.json"
        self.assertTrue(review_file.exists())

    def test_review_package_requires_review_state(self):
        _create_ticket(self.cfg, "inbox", "t-wrong-state")
        with self.assertRaises(ValueError):
            orc.create_review_package(self.cfg, "t-wrong-state")

    def test_load_review_package(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        loaded = orc.load_review_package(self.cfg, tid)
        self.assertEqual(loaded["ticket_id"], tid)

    def test_load_review_package_missing(self):
        with self.assertRaises(FileNotFoundError):
            orc.load_review_package(self.cfg, "nonexistent")

    def test_approve_ticket(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        record = orc.create_approval_decision(self.cfg, tid, "approved", "Looks good")
        self.assertEqual(record["decision"], "approved")
        self.assertEqual(record["reason"], "Looks good")
        # Ticket should transition to done
        state, _ = orc.find_ticket(self.cfg, tid)
        self.assertEqual(state, "done")

    def test_reject_ticket(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        record = orc.create_approval_decision(self.cfg, tid, "rejected", "Needs rework")
        self.assertEqual(record["decision"], "rejected")
        # Ticket should transition review → active → failed
        state, _ = orc.find_ticket(self.cfg, tid)
        self.assertEqual(state, "failed")

    def test_reticket(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        record = orc.create_approval_decision(self.cfg, tid, "reticketed", "Different scope")
        self.assertEqual(record["decision"], "reticketed")
        state, _ = orc.find_ticket(self.cfg, tid)
        self.assertEqual(state, "failed")

    def test_approval_is_immutable(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        with self.assertRaises(RuntimeError) as ctx:
            orc.create_approval_decision(self.cfg, tid, "rejected")
        self.assertIn("immutable", str(ctx.exception))

    def test_invalid_decision_rejected(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        with self.assertRaises(ValueError):
            orc.create_approval_decision(self.cfg, tid, "maybe")

    def test_approval_requires_review_package(self):
        _create_ticket(self.cfg, "review", "t-no-review")
        with self.assertRaises(FileNotFoundError):
            orc.create_approval_decision(self.cfg, "t-no-review", "approved")

    # --- Sprint 11C: ApprovalDecision schema_version ---

    def test_approval_has_schema_version(self):
        """New ApprovalDecision records include schema_version."""
        tid = self._put_ticket_in_review("t-schema-v")
        orc.create_review_package(self.cfg, "t-schema-v")
        record = orc.create_approval_decision(self.cfg, "t-schema-v", "approved")
        self.assertEqual(record["schema_version"], 1)
        # Verify persisted
        loaded = orc.load_approval_decision(self.cfg, "t-schema-v")
        self.assertEqual(loaded["schema_version"], 1)

    def test_legacy_approval_without_schema_version_loads(self):
        """Pre-11C ApprovalDecision without schema_version still loads fine."""
        tid = self._put_ticket_in_review("t-legacy-appr")
        orc.create_review_package(self.cfg, "t-legacy-appr")
        # Write a legacy record directly (no schema_version)
        reviews = Path(self.cfg["management_root"]) / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        approval_path = reviews / "t-legacy-appr.approval.json"
        with open(approval_path, "w", encoding="utf-8") as f:
            json.dump({"ticket_id": "t-legacy-appr", "decision": "approved",
                        "reviewer": "creative-director", "reason": "",
                        "decided_at": "2026-01-01T00:00:00Z"}, f)
        loaded = orc.load_approval_decision(self.cfg, "t-legacy-appr")
        self.assertEqual(loaded["decision"], "approved")
        self.assertNotIn("schema_version", loaded)

    def test_promotion_works_with_legacy_approval(self):
        """Promotion succeeds with pre-11C approval (no schema_version)."""
        tid = self._put_ticket_in_review("t-promo-legacy")
        orc.create_review_package(self.cfg, "t-promo-legacy")
        # Write legacy approval directly
        reviews = Path(self.cfg["management_root"]) / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        with open(reviews / "t-promo-legacy.approval.json", "w") as f:
            json.dump({"ticket_id": "t-promo-legacy", "decision": "approved",
                        "reviewer": "creative-director", "reason": "",
                        "decided_at": "2026-01-01T00:00:00Z"}, f)
        orc.create_qa_result(self.cfg, "t-promo-legacy", True)
        request = orc.create_promotion_request(self.cfg, "t-promo-legacy")
        self.assertEqual(request["status"], "pending")

    def test_promotion_requires_approval(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        # No approval yet → should fail
        with self.assertRaises(FileNotFoundError):
            orc.create_promotion_request(self.cfg, tid)

    def test_promotion_requires_approved_decision(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "rejected", "Bad")
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, tid)
        self.assertIn("not 'approved'", str(ctx.exception))

    def test_promotion_success(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, True)
        request = orc.create_promotion_request(self.cfg, tid)
        self.assertEqual(request["ticket_id"], tid)
        self.assertEqual(request["source_repo"], "test_repo")
        self.assertEqual(request["target_repo"], "prod_repo")
        self.assertEqual(request["status"], "pending")
        # File written
        promo_file = Path(self.cfg["management_root"]) / "promotions" / f"{tid}.promotion.json"
        self.assertTrue(promo_file.exists())

    def test_promotion_dry_run(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, True)
        request = orc.create_promotion_request(self.cfg, tid, dry_run=True)
        self.assertEqual(request["status"], "dry_run")
        # No file written in dry-run
        promo_file = Path(self.cfg["management_root"]) / "promotions" / f"{tid}.promotion.json"
        self.assertFalse(promo_file.exists())


# ---------------------------------------------------------------------------
# Physical repo separation (Sprint 4)
# ---------------------------------------------------------------------------

class TestRepoSeparation(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)
        # Ensure prod_repo dir exists
        os.makedirs(self.cfg["repo_targets"]["prod_repo"], exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_separation_valid_different_paths(self):
        """test_repo and prod_repo are different paths → passes."""
        self.assertTrue(orc.validate_repo_separation(self.cfg))

    def test_separation_fails_same_path(self):
        """If both point to same path, validation must fail."""
        self.cfg["repo_targets"]["prod_repo"] = self.tmp
        with self.assertRaises(ValueError) as ctx:
            orc.validate_repo_separation(self.cfg)
        self.assertIn("REPO SEPARATION VIOLATION", str(ctx.exception))

    def test_separation_fails_same_via_symlink(self):
        """Symlink to same path must be detected as same physical path."""
        link_path = os.path.join(self.tmp, "symlink_to_tmp")
        os.symlink(self.tmp, link_path)
        self.cfg["repo_targets"]["test_repo"] = self.tmp
        self.cfg["repo_targets"]["prod_repo"] = link_path
        with self.assertRaises(ValueError):
            orc.validate_repo_separation(self.cfg)

    def test_separation_detects_relative_same(self):
        """Relative paths that resolve to same real path must fail."""
        self.cfg["repo_targets"]["prod_repo"] = os.path.join(self.tmp, "sub", "..")
        with self.assertRaises(ValueError):
            orc.validate_repo_separation(self.cfg)


# ---------------------------------------------------------------------------
# Promotion readiness (Sprint 4)
# ---------------------------------------------------------------------------

class TestPromotionReadiness(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)
        mgmt = Path(self.cfg["management_root"])
        for sub in ["orchestrator", "worker", "agent-runs"]:
            (mgmt / "logs" / sub).mkdir(parents=True, exist_ok=True)
        os.makedirs(self.cfg["repo_targets"]["prod_repo"], exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put_ticket_in_review(self, ticket_id="t-ready1"):
        _create_ticket(self.cfg, "review", ticket_id, branch="feature/test")
        return ticket_id

    def test_readiness_all_pass(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, True)
        result = orc.check_promotion_readiness(self.cfg, tid)
        self.assertTrue(result["ready"])
        self.assertTrue(all(c["passed"] for c in result["checks"]))

    def test_readiness_no_review(self):
        _create_ticket(self.cfg, "review", "t-norev")
        result = orc.check_promotion_readiness(self.cfg, "t-norev")
        self.assertFalse(result["ready"])
        names = {c["name"] for c in result["checks"] if not c["passed"]}
        self.assertIn("review_package", names)

    def test_readiness_no_approval(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        result = orc.check_promotion_readiness(self.cfg, tid)
        self.assertFalse(result["ready"])
        names = {c["name"] for c in result["checks"] if not c["passed"]}
        self.assertIn("approval_decision", names)

    def test_readiness_rejected_not_ready(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "rejected")
        result = orc.check_promotion_readiness(self.cfg, tid)
        self.assertFalse(result["ready"])

    def test_readiness_fails_same_repo_path(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        # Force same path
        self.cfg["repo_targets"]["prod_repo"] = self.tmp
        result = orc.check_promotion_readiness(self.cfg, tid)
        self.assertFalse(result["ready"])
        names = {c["name"] for c in result["checks"] if not c["passed"]}
        self.assertIn("repo_separation", names)

    def test_promotion_blocked_same_path(self):
        """create_promotion_request must fail if repos are not separated."""
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, True)
        self.cfg["repo_targets"]["prod_repo"] = self.tmp
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, tid)
        self.assertIn("REPO SEPARATION VIOLATION", str(ctx.exception))

    def test_readiness_artifacts_exist(self):
        """Promotion readiness passes when referenced artifacts exist on disk."""
        tid = self._put_ticket_in_review()
        # Create a real artifact file so ReviewPackage picks it up
        mgmt = Path(self.cfg["management_root"])
        artifacts_dir = mgmt / self.cfg["artifacts_dir"]
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / f"{tid}_code_result.md").write_text("test artifact")
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, True)
        result = orc.check_promotion_readiness(self.cfg, tid)
        self.assertTrue(result["ready"])
        art_check = [c for c in result["checks"] if c["name"] == "artifacts_exist"]
        self.assertEqual(len(art_check), 1)
        self.assertTrue(art_check[0]["passed"])

    def test_readiness_fails_missing_artifact(self):
        """Promotion readiness fails when a referenced artifact is deleted."""
        tid = self._put_ticket_in_review()
        mgmt = Path(self.cfg["management_root"])
        artifacts_dir = mgmt / self.cfg["artifacts_dir"]
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        art_file = artifacts_dir / f"{tid}_code_result.md"
        art_file.write_text("test artifact")
        orc.create_review_package(self.cfg, tid)
        # Delete artifact after ReviewPackage references it
        art_file.unlink()
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, True)
        result = orc.check_promotion_readiness(self.cfg, tid)
        self.assertFalse(result["ready"])
        names = {c["name"] for c in result["checks"] if not c["passed"]}
        self.assertIn("artifacts_exist", names)

    def test_readiness_no_review_skips_artifact_check(self):
        """If ReviewPackage is missing, artifact check is skipped (not crashed)."""
        _create_ticket(self.cfg, "review", "t-norev2")
        result = orc.check_promotion_readiness(self.cfg, "t-norev2")
        self.assertFalse(result["ready"])
        art_checks = [c for c in result["checks"] if c["name"] == "artifacts_exist"]
        self.assertEqual(len(art_checks), 0)  # skipped, not failed

    def test_review_package_artifacts_no_prefix_collision(self):
        """ReviewPackage glob must not pick up artifacts from prefix-colliding ticket IDs."""
        mgmt = Path(self.cfg["management_root"])
        artifacts_dir = mgmt / self.cfg["artifacts_dir"]
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact for our ticket
        (artifacts_dir / "t-glob_code_result.md").write_text("real", encoding="utf-8")
        # Create artifact for a prefix-colliding ticket
        (artifacts_dir / "t-glob-extra_code_result.md").write_text("collider", encoding="utf-8")

        _create_ticket(self.cfg, "review", "t-glob")
        pkg = orc.create_review_package(self.cfg, "t-glob")

        # Only the exact ticket's artifact should be included
        self.assertEqual(len(pkg["artifacts"]), 1)
        self.assertIn("t-glob_code_result.md", pkg["artifacts"][0])
        for a in pkg["artifacts"]:
            self.assertNotIn("t-glob-extra", a)


# ---------------------------------------------------------------------------
# QA Gate (Sprint 5)
# ---------------------------------------------------------------------------

class TestQAGate(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)
        mgmt = Path(self.cfg["management_root"])
        for sub in ["orchestrator", "worker", "agent-runs"]:
            (mgmt / "logs" / sub).mkdir(parents=True, exist_ok=True)
        os.makedirs(self.cfg["repo_targets"]["prod_repo"], exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put_ticket_in_review(self, ticket_id="t-qa1"):
        _create_ticket(self.cfg, "review", ticket_id, branch="feature/test")
        return ticket_id

    def test_create_qa_passed(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        result = orc.create_qa_result(self.cfg, tid, True, "All good")
        self.assertTrue(result["passed"])
        self.assertEqual(result["notes"], "All good")
        qa_file = Path(self.cfg["management_root"]) / "reviews" / f"{tid}.qa.json"
        self.assertTrue(qa_file.exists())

    def test_create_qa_failed(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        result = orc.create_qa_result(self.cfg, tid, False, "Bugs found")
        self.assertFalse(result["passed"])

    def test_qa_requires_review_package(self):
        _create_ticket(self.cfg, "review", "t-qa-norev")
        with self.assertRaises(FileNotFoundError):
            orc.create_qa_result(self.cfg, "t-qa-norev", True)

    def test_qa_is_immutable(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_qa_result(self.cfg, tid, True)
        with self.assertRaises(RuntimeError) as ctx:
            orc.create_qa_result(self.cfg, tid, False)
        self.assertIn("immutable", str(ctx.exception))

    def test_promotion_blocked_without_qa(self):
        """Promotion request requires QA passed."""
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        with self.assertRaises(FileNotFoundError):
            orc.create_promotion_request(self.cfg, tid)

    def test_promotion_blocked_qa_failed(self):
        """Promotion request blocked if QA failed."""
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        orc.create_approval_decision(self.cfg, tid, "approved")
        orc.create_qa_result(self.cfg, tid, False, "Bugs found")
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, tid)
        self.assertIn("QA has not passed", str(ctx.exception))

    def test_readiness_includes_qa_check(self):
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        result = orc.check_promotion_readiness(self.cfg, tid)
        names = [c["name"] for c in result["checks"]]
        self.assertIn("qa_gate", names)

    # --- Sprint 11B: QA decision field tests ---

    def test_qa_decision_pass(self):
        """QA with decision=pass sets passed=True and includes schema_version."""
        tid = self._put_ticket_in_review()
        orc.create_review_package(self.cfg, tid)
        result = orc.create_qa_result(self.cfg, tid, False, decision="pass")
        self.assertTrue(result["passed"])
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["schema_version"], 2)

    def test_qa_decision_blocked(self):
        """QA with decision=blocked sets passed=False."""
        tid = self._put_ticket_in_review("t-qa-blocked")
        orc.create_review_package(self.cfg, "t-qa-blocked")
        result = orc.create_qa_result(self.cfg, "t-qa-blocked", True,
                                       decision="blocked", notes="BLOCKED: missing artifacts")
        self.assertFalse(result["passed"])
        self.assertEqual(result["decision"], "blocked")

    def test_qa_decision_inconclusive(self):
        """QA with decision=inconclusive sets passed=False."""
        tid = self._put_ticket_in_review("t-qa-inc")
        orc.create_review_package(self.cfg, "t-qa-inc")
        result = orc.create_qa_result(self.cfg, "t-qa-inc", True,
                                       decision="inconclusive")
        self.assertFalse(result["passed"])
        self.assertEqual(result["decision"], "inconclusive")

    def test_qa_invalid_decision(self):
        """Invalid QA decision raises ValueError."""
        tid = self._put_ticket_in_review("t-qa-invalid")
        orc.create_review_package(self.cfg, "t-qa-invalid")
        with self.assertRaises(ValueError):
            orc.create_qa_result(self.cfg, "t-qa-invalid", True, decision="maybe")

    def test_qa_legacy_compat(self):
        """Legacy call without decision still works, infers decision from passed."""
        tid = self._put_ticket_in_review("t-qa-legacy")
        orc.create_review_package(self.cfg, "t-qa-legacy")
        result = orc.create_qa_result(self.cfg, "t-qa-legacy", True, "old style")
        self.assertTrue(result["passed"])
        self.assertEqual(result["decision"], "pass")

    def test_promotion_blocked_qa_blocked(self):
        """Promotion blocked when QA decision is 'blocked'."""
        tid = self._put_ticket_in_review("t-qa-promo-blk")
        orc.create_review_package(self.cfg, "t-qa-promo-blk")
        orc.create_approval_decision(self.cfg, "t-qa-promo-blk", "approved")
        orc.create_qa_result(self.cfg, "t-qa-promo-blk", False, decision="blocked")
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, "t-qa-promo-blk")
        self.assertIn("QA has not passed", str(ctx.exception))

    # --- Sprint 11B: QA record consistency hardening ---

    def _write_tampered_qa(self, ticket_id, decision, passed):
        """Write a QA record directly to disk, bypassing create_qa_result().
        Simulates manual file tampering."""
        reviews = Path(self.cfg["management_root"]) / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        qa_path = reviews / f"{ticket_id}.qa.json"
        record = {
            "schema_version": 2,
            "ticket_id": ticket_id,
            "decision": decision,
            "passed": passed,
            "notes": "tampered record for testing",
            "validated_at": "2026-03-20T00:00:00Z",
            "validator": "test-tamper",
        }
        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump(record, f)

    def test_tampered_qa_fail_passed_true_blocks_promotion(self):
        """Tampered QA: decision=fail but passed=true must block promotion."""
        tid = self._put_ticket_in_review("t-tamper-fail")
        orc.create_review_package(self.cfg, "t-tamper-fail")
        orc.create_approval_decision(self.cfg, "t-tamper-fail", "approved")
        self._write_tampered_qa("t-tamper-fail", decision="fail", passed=True)
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, "t-tamper-fail")
        self.assertIn("integrity error", str(ctx.exception))

    def test_tampered_qa_blocked_passed_true_blocks_promotion(self):
        """Tampered QA: decision=blocked but passed=true must block promotion."""
        tid = self._put_ticket_in_review("t-tamper-blk")
        orc.create_review_package(self.cfg, "t-tamper-blk")
        orc.create_approval_decision(self.cfg, "t-tamper-blk", "approved")
        self._write_tampered_qa("t-tamper-blk", decision="blocked", passed=True)
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, "t-tamper-blk")
        self.assertIn("integrity error", str(ctx.exception))

    def test_tampered_qa_inconclusive_passed_true_blocks_promotion(self):
        """Tampered QA: decision=inconclusive but passed=true must block promotion."""
        tid = self._put_ticket_in_review("t-tamper-inc")
        orc.create_review_package(self.cfg, "t-tamper-inc")
        orc.create_approval_decision(self.cfg, "t-tamper-inc", "approved")
        self._write_tampered_qa("t-tamper-inc", decision="inconclusive", passed=True)
        with self.assertRaises(ValueError) as ctx:
            orc.create_promotion_request(self.cfg, "t-tamper-inc")
        self.assertIn("integrity error", str(ctx.exception))

    def test_tampered_qa_readiness_check_detects_inconsistency(self):
        """check_promotion_readiness() detects tampered QA record."""
        tid = self._put_ticket_in_review("t-tamper-rdy")
        orc.create_review_package(self.cfg, "t-tamper-rdy")
        orc.create_approval_decision(self.cfg, "t-tamper-rdy", "approved")
        self._write_tampered_qa("t-tamper-rdy", decision="fail", passed=True)
        result = orc.check_promotion_readiness(self.cfg, "t-tamper-rdy")
        qa_check = [c for c in result["checks"] if c["name"] == "qa_gate"][0]
        self.assertFalse(qa_check["passed"])
        self.assertIn("integrity error", qa_check["detail"])
        self.assertFalse(result["ready"])

    def test_legacy_qa_no_decision_field_still_works(self):
        """Legacy v1 QA record without decision field: passed=true allows promotion."""
        tid = self._put_ticket_in_review("t-legacy-v1")
        orc.create_review_package(self.cfg, "t-legacy-v1")
        orc.create_approval_decision(self.cfg, "t-legacy-v1", "approved")
        # Write a v1-style record (no decision, no schema_version)
        reviews = Path(self.cfg["management_root"]) / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        qa_path = reviews / f"t-legacy-v1.qa.json"
        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump({"ticket_id": "t-legacy-v1", "passed": True,
                        "notes": "legacy", "validated_at": "2026-01-01T00:00:00Z",
                        "validator": "test"}, f)
        # Should NOT raise — legacy record is promotable
        request = orc.create_promotion_request(self.cfg, "t-legacy-v1")
        self.assertEqual(request["status"], "pending")


# ---------------------------------------------------------------------------
# Promotion execution (Sprint 5)
# ---------------------------------------------------------------------------

class TestPromotionExecution(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)
        mgmt = Path(self.cfg["management_root"])
        for sub in ["orchestrator", "worker", "agent-runs"]:
            (mgmt / "logs" / sub).mkdir(parents=True, exist_ok=True)
        os.makedirs(self.cfg["repo_targets"]["prod_repo"], exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _setup_promotable_ticket(self, ticket_id="t-exec1"):
        _create_ticket(self.cfg, "review", ticket_id, branch="feature/test")
        orc.create_review_package(self.cfg, ticket_id)
        orc.create_approval_decision(self.cfg, ticket_id, "approved")
        orc.create_qa_result(self.cfg, ticket_id, True)
        orc.create_promotion_request(self.cfg, ticket_id)
        return ticket_id

    def test_execute_requires_promotion_request(self):
        with self.assertRaises(FileNotFoundError):
            orc.execute_promotion(self.cfg, "nonexistent")

    def test_execute_already_executed_blocked(self):
        tid = self._setup_promotable_ticket()
        orc.update_promotion_status(self.cfg, tid, "executed")
        with self.assertRaises(RuntimeError) as ctx:
            orc.execute_promotion(self.cfg, tid)
        self.assertIn("already executed", str(ctx.exception))

    @patch("orchestrator.subprocess.run")
    def test_preview_records_audit(self, mock_run):
        tid = self._setup_promotable_ticket()
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
        audit = orc.execute_promotion(self.cfg, tid, dry_run=True)
        self.assertEqual(audit["result"], "preview_ok")
        self.assertTrue(audit["dry_run"])
        self.assertEqual(mock_run.call_count, 1)

    @patch("orchestrator.subprocess.run")
    def test_execute_calls_git_fetch(self, mock_run):
        tid = self._setup_promotable_ticket()
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
        audit = orc.execute_promotion(self.cfg, tid, dry_run=False)
        self.assertEqual(audit["result"], "executed")
        self.assertEqual(mock_run.call_count, 2)

    @patch("orchestrator.subprocess.run")
    def test_execute_records_audit(self, mock_run):
        tid = self._setup_promotable_ticket()
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
        orc.execute_promotion(self.cfg, tid, dry_run=False)
        trail = orc.load_audit_trail(self.cfg, tid)
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["result"], "executed")
        self.assertEqual(trail[0]["ticket_id"], tid)


# ---------------------------------------------------------------------------
# Promotion status tracking (Sprint 5)
# ---------------------------------------------------------------------------

class TestPromotionStatusTracking(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)
        mgmt = Path(self.cfg["management_root"])
        for sub in ["orchestrator", "worker", "agent-runs"]:
            (mgmt / "logs" / sub).mkdir(parents=True, exist_ok=True)
        os.makedirs(self.cfg["repo_targets"]["prod_repo"], exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _setup_promotable_ticket(self, ticket_id="t-stat1"):
        _create_ticket(self.cfg, "review", ticket_id, branch="feature/test")
        orc.create_review_package(self.cfg, ticket_id)
        orc.create_approval_decision(self.cfg, ticket_id, "approved")
        orc.create_qa_result(self.cfg, ticket_id, True)
        orc.create_promotion_request(self.cfg, ticket_id)
        return ticket_id

    def test_initial_status_pending(self):
        tid = self._setup_promotable_ticket()
        request = orc.load_promotion_request(self.cfg, tid)
        self.assertEqual(request["status"], "pending")

    def test_status_update_to_previewed(self):
        tid = self._setup_promotable_ticket()
        orc.update_promotion_status(self.cfg, tid, "previewed")
        request = orc.load_promotion_request(self.cfg, tid)
        self.assertEqual(request["status"], "previewed")

    def test_status_history_recorded(self):
        tid = self._setup_promotable_ticket()
        orc.update_promotion_status(self.cfg, tid, "previewed")
        orc.update_promotion_status(self.cfg, tid, "executed")
        request = orc.load_promotion_request(self.cfg, tid)
        self.assertEqual(len(request["status_history"]), 2)
        self.assertEqual(request["status_history"][0]["status"], "previewed")
        self.assertEqual(request["status_history"][1]["status"], "executed")

    def test_invalid_status_rejected(self):
        tid = self._setup_promotable_ticket()
        with self.assertRaises(ValueError):
            orc.update_promotion_status(self.cfg, tid, "magic_state")


# ---------------------------------------------------------------------------
# Audit trail (Sprint 5)
# ---------------------------------------------------------------------------

class TestAuditTrail(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _make_cfg(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_audit_trail(self):
        records = orc.load_audit_trail(self.cfg, "nonexistent")
        self.assertEqual(records, [])

    def test_append_and_load(self):
        record = {"ticket_id": "t-aud1", "action": "test", "timestamp": "2026-03-16"}
        orc._append_audit_record(self.cfg, "t-aud1", record)
        trail = orc.load_audit_trail(self.cfg, "t-aud1")
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["action"], "test")

    def test_multiple_records(self):
        for i in range(3):
            record = {"ticket_id": "t-aud2", "action": f"action_{i}"}
            orc._append_audit_record(self.cfg, "t-aud2", record)
        trail = orc.load_audit_trail(self.cfg, "t-aud2")
        self.assertEqual(len(trail), 3)

    def test_audit_captures_key_fields(self):
        record = {
            "ticket_id": "t-aud3",
            "promotion_request": "promotions/t-aud3.promotion.json",
            "source_repo": "/test",
            "target_repo": "/prod",
            "review_package": "reviews/t-aud3.review.json",
            "approval_decision": "reviews/t-aud3.approval.json",
            "qa_result": "reviews/t-aud3.qa.json",
            "branch": "feature/test",
            "action": "execute",
            "dry_run": False,
            "timestamp": "2026-03-16T12:00:00Z",
            "result": "executed",
        }
        orc._append_audit_record(self.cfg, "t-aud3", record)
        trail = orc.load_audit_trail(self.cfg, "t-aud3")
        r = trail[0]
        for key in ["ticket_id", "source_repo", "target_repo", "review_package",
                     "approval_decision", "qa_result", "branch", "action",
                     "dry_run", "timestamp", "result"]:
            self.assertIn(key, r, f"Missing key: {key}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
