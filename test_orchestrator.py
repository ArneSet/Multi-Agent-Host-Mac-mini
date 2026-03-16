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

if __name__ == "__main__":
    unittest.main()
