#!/usr/bin/env python3
"""
HYBRIS Host CLI — Entrypoint for ticket-based orchestration.

Usage:
    python3 cli.py list [--state STATE]
    python3 cli.py show TICKET_ID
    python3 cli.py process TICKET_ID [--dry-run]
    python3 cli.py transition TICKET_ID TARGET_STATE [--dry-run]
    python3 cli.py validate
    python3 cli.py repo-targets
    python3 cli.py review-show TICKET_ID
    python3 cli.py approve TICKET_ID [--reason REASON]
    python3 cli.py reject TICKET_ID [--reason REASON]
    python3 cli.py reticket TICKET_ID [--reason REASON]
    python3 cli.py qa-pass TICKET_ID [--notes TEXT]
    python3 cli.py qa-fail TICKET_ID [--notes TEXT]
    python3 cli.py qa-check TICKET_ID
    python3 cli.py promote TICKET_ID [--dry-run | --preview | --execute]
    python3 cli.py promotion-check TICKET_ID
    python3 cli.py promotion-status TICKET_ID
    python3 cli.py audit-show TICKET_ID
    python3 cli.py intake-config
    python3 cli.py intake-validate SOURCE --title TITLE --worker WORKER [--description TEXT] [--branch BRANCH] [--priority PRIORITY]
    python3 cli.py intake-simulate SOURCE --title TITLE --worker WORKER [--description TEXT] [--branch BRANCH] [--priority PRIORITY]
    python3 cli.py intake-submit SOURCE --title TITLE --worker WORKER [--description TEXT] [--branch BRANCH] [--priority PRIORITY]
    python3 cli.py intake-normalize SOURCE --title TITLE --worker WORKER [--description TEXT] [--branch BRANCH] [--priority PRIORITY]
    python3 cli.py intake-audit-show
    python3 cli.py intake-status
    python3 cli.py whatsapp-config
    python3 cli.py whatsapp-validate
    python3 cli.py whatsapp-simulate-batch --messages SENDER:TEXT [SENDER:TEXT ...]
    python3 cli.py whatsapp-status
    python3 cli.py branch-status TICKET_ID
    python3 cli.py branch-prepare TICKET_ID [--dry-run]
    python3 cli.py branch-commit TICKET_ID [--message MSG] [--dry-run]
    python3 cli.py whatsapp-audit-show
    python3 cli.py whatsapp-allowlist-show
"""

import argparse
import json
import sys
import time
from pathlib import Path

from orchestrator import (
    load_config,
    find_ticket,
    list_tickets,
    parse_ticket,
    process_ticket,
    transition_ticket,
    write_log,
    resolve_agent_repo,
    resolve_prod_repo,
    validate_repo_separation,
    create_review_package,
    load_review_package,
    create_approval_decision,
    load_approval_decision,
    create_qa_result,
    load_qa_result,
    check_promotion_readiness,
    create_promotion_request,
    load_promotion_request,
    update_promotion_status,
    execute_promotion,
    load_audit_trail,
    prepare_worker_branch,
    commit_worker_changes,
    check_branch_status,
)

from intake import (
    get_source_trust,
    get_rate_limit,
    load_intake_config,
    validate_source,
    validate_payload,
    normalize_request,
    process_intake,
    load_intake_audit,
    INTAKE_SOURCES,
    SOURCE_TRUST_LEVELS,
    INTAKE_STATUSES,
    ALLOWED_WORKERS as INTAKE_ALLOWED_WORKERS,
)

from whatsapp import (
    load_whatsapp_config,
    is_whatsapp_enabled,
    get_whatsapp_access_token,
    get_whatsapp_verify_token,
    get_authorized_senders,
    get_whatsapp_rate_limit,
    get_whatsapp_dedup_window,
    verify_webhook_request,
    authorize_sender,
    process_whatsapp_webhook,
    load_whatsapp_audit,
    WHATSAPP_MESSAGE_TYPES,
    WHATSAPP_STATUSES,
)

_HERE = Path(__file__).resolve().parent


def cmd_list(cfg, args):
    """List tickets, optionally filtered by state."""
    tickets = list_tickets(cfg, state_filter=args.state)
    if not tickets:
        print("No tickets found.")
        return 0

    # Column header
    print(f"{'STATE':<10} {'ID':<35} {'TITLE'}")
    print("-" * 80)
    for state, tid, title, path in tickets:
        print(f"{state:<10} {tid:<35} {title}")
    print(f"\nTotal: {len(tickets)} ticket(s)")
    return 0


def cmd_show(cfg, args):
    """Show details of a single ticket."""
    state, path = find_ticket(cfg, args.ticket_id)
    if state is None:
        print(f"Ticket not found: {args.ticket_id}")
        return 1

    ticket = parse_ticket(path)
    print(f"Ticket: {ticket.get('id', '?')}")
    print(f"State:  {state}")
    print(f"Title:  {ticket.get('title', '?')}")
    print(f"Worker: {ticket.get('worker', '?')}")
    print(f"Branch: {ticket.get('branch', '?')}")
    print(f"Priority: {ticket.get('priority', '?')}")
    print(f"File:   {path}")
    if ticket.get("description"):
        print(f"\nDescription:\n  {ticket['description']}")
    if ticket.get("_body"):
        print(f"\nBody:\n{ticket['_body']}")
    return 0


def cmd_process(cfg, args):
    """Process a ticket through the full pipeline."""
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Processing ticket: {args.ticket_id}")
    print("=" * 60)
    exit_code = process_ticket(cfg, args.ticket_id, dry_run=args.dry_run)
    print("=" * 60)
    print(f"Exit code: {exit_code}")
    return exit_code


def cmd_transition(cfg, args):
    """Manually transition a ticket to a target state."""
    try:
        msg = transition_ticket(cfg, args.ticket_id, args.target_state, dry_run=args.dry_run)
        print(msg)
        if not args.dry_run:
            write_log(cfg, "orchestrator", args.ticket_id, msg)
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_validate(cfg, args):
    """Validate orchestrator setup: dirs, config, workers."""
    errors = []
    mgmt = Path(cfg["management_root"])

    # Check directories
    for state in cfg["ticket_states"]:
        d = mgmt / cfg["tickets_dir"] / state
        if not d.is_dir():
            errors.append(f"Missing directory: {d}")

    for log_sub in ["agent-runs", "orchestrator", "worker"]:
        d = mgmt / cfg["logs_dir"] / log_sub
        if not d.is_dir():
            errors.append(f"Missing log directory: {d}")

    if not (mgmt / cfg["artifacts_dir"]).is_dir():
        errors.append(f"Missing artifacts directory: {mgmt / cfg['artifacts_dir']}")

    if not (mgmt / cfg["sessions_dir"]).is_dir():
        errors.append(f"Missing sessions directory: {mgmt / cfg['sessions_dir']}")

    # Check repo targets
    repo_targets = cfg.get("repo_targets", {})
    test_repo = repo_targets.get("test_repo", "")
    prod_repo = repo_targets.get("prod_repo", "")
    if not test_repo:
        errors.append("repo_targets.test_repo is not configured")
    elif not Path(test_repo).is_dir():
        errors.append(f"test_repo not found: {test_repo}")
    elif not (Path(test_repo) / "Assets").is_dir():
        errors.append(f"Assets/ not found in test_repo: {test_repo}")

    if not prod_repo:
        errors.append("repo_targets.prod_repo is not configured")
    elif not Path(prod_repo).is_dir():
        errors.append(f"prod_repo not found: {prod_repo}")

    # Check repo separation (Sprint 4: must be distinct physical paths)
    if test_repo and prod_repo and Path(test_repo).is_dir() and Path(prod_repo).is_dir():
        try:
            validate_repo_separation(cfg)
        except ValueError as e:
            errors.append(str(e))

    # Check repo root (legacy compat)
    repo = Path(cfg.get("game_repo_root", ""))
    if repo and repo.is_dir() and not (repo / "Assets").is_dir():
        errors.append(f"Assets/ not found in game_repo_root: {repo}")

    # Check worker modules
    workers_dir = _HERE / "workers"
    for worker in cfg["allowed_workers"]:
        module_name = worker.replace("-", "_")
        module_file = workers_dir / f"{module_name}.py"
        if not module_file.exists():
            errors.append(f"Missing worker module: {module_file}")

    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    else:
        print("VALIDATION PASSED:")
        print(f"  ✓ All {len(cfg['ticket_states'])} ticket state directories exist")
        print(f"  ✓ All log directories exist")
        print(f"  ✓ Artifacts and sessions directories exist")
        print(f"  ✓ Repo targets: test_repo={test_repo}")
        print(f"  ✓ Repo targets: prod_repo={prod_repo}")
        print(f"  ✓ Repo separation: physically distinct paths")
        print(f"  ✓ All {len(cfg['allowed_workers'])} worker modules present")
        return 0


def cmd_repo_targets(cfg, args):
    """Show configured repo targets with separation status."""
    repo_targets = cfg.get("repo_targets", {})
    test_repo = repo_targets.get("test_repo", "(not set)")
    prod_repo = repo_targets.get("prod_repo", "(not set)")
    print("Repo Targets:")
    print(f"  test_repo: {test_repo}")
    if test_repo != "(not set)":
        print(f"    resolved: {Path(test_repo).resolve()}")
    print(f"  prod_repo: {prod_repo}")
    if prod_repo != "(not set)":
        print(f"    resolved: {Path(prod_repo).resolve()}")
    print()

    # Separation check
    try:
        validate_repo_separation(cfg)
        print("Separation: ✓ physically distinct paths")
    except ValueError:
        print("Separation: ✗ SAME PHYSICAL PATH — not safe for operation")
    print()
    print("Rules:")
    print("  • Agents work exclusively in test_repo")
    print("  • prod_repo is only accessible via approved promotion")
    return 0


def cmd_review_show(cfg, args):
    """Show ReviewPackage for a ticket."""
    try:
        package = load_review_package(cfg, args.ticket_id)
        print(f"ReviewPackage: {args.ticket_id}")
        print(f"  Created:  {package.get('created_at', '?')}")
        print(f"  Worker:   {package.get('worker', '?')}")
        print(f"  Branch:   {package.get('branch', '?')}")
        print(f"  Repo:     {package.get('repo_target', '?')}")
        print(f"  Summary:  {package.get('summary', '?')}")
        if package.get("artifacts"):
            print(f"  Artifacts: {', '.join(package['artifacts'])}")
        if package.get("worker_log"):
            print(f"  Worker log: {package['worker_log']}")
    except FileNotFoundError:
        # Try to create it if ticket is in review state
        try:
            package = create_review_package(cfg, args.ticket_id)
            print(f"ReviewPackage created for: {args.ticket_id}")
            print(f"  Worker:   {package.get('worker', '?')}")
            print(f"  Branch:   {package.get('branch', '?')}")
            print(f"  Repo:     {package.get('repo_target', '?')}")
        except (FileNotFoundError, ValueError) as e:
            print(f"ERROR: {e}")
            return 1

    # Show approval if exists
    try:
        approval = load_approval_decision(cfg, args.ticket_id)
        print(f"\n  Decision: {approval['decision']}")
        print(f"  Reviewer: {approval.get('reviewer', '?')}")
        print(f"  Reason:   {approval.get('reason', '(none)')}")
        print(f"  Decided:  {approval.get('decided_at', '?')}")
    except FileNotFoundError:
        print("\n  Decision: (pending)")
    return 0


def cmd_approve(cfg, args):
    """Approve a ticket in review."""
    try:
        record = create_approval_decision(cfg, args.ticket_id, "approved",
                                          reason=args.reason or "")
        print(f"APPROVED: {args.ticket_id}")
        print(f"  Decided at: {record['decided_at']}")
        if args.reason:
            print(f"  Reason: {args.reason}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_reject(cfg, args):
    """Reject a ticket in review."""
    try:
        record = create_approval_decision(cfg, args.ticket_id, "rejected",
                                          reason=args.reason or "")
        print(f"REJECTED: {args.ticket_id}")
        print(f"  Decided at: {record['decided_at']}")
        if args.reason:
            print(f"  Reason: {args.reason}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_reticket(cfg, args):
    """Reticket a ticket in review (send back for rework with new scope)."""
    try:
        record = create_approval_decision(cfg, args.ticket_id, "reticketed",
                                          reason=args.reason or "")
        print(f"RETICKETED: {args.ticket_id}")
        print(f"  Decided at: {record['decided_at']}")
        if args.reason:
            print(f"  Reason: {args.reason}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_promote(cfg, args):
    """Create a promotion request, preview, or execute promotion."""
    if args.preview:
        try:
            audit = execute_promotion(cfg, args.ticket_id, dry_run=True)
            print(f"PROMOTION PREVIEW: {args.ticket_id}")
            print(f"  Branch:  {audit.get('branch', '?')}")
            print(f"  Source:  {audit.get('source_repo', '?')}")
            print(f"  Target:  {audit.get('target_repo', '?')}")
            print(f"  Commit:  {audit.get('source_commit', '?')}")
            print(f"  Plan:    {audit.get('detail', '?')}")
            print(f"  Status:  previewed (no changes made)")
            return 0
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            print(f"ERROR: {e}")
            return 1
    elif args.execute:
        try:
            audit = execute_promotion(cfg, args.ticket_id, dry_run=False)
            print(f"PROMOTION EXECUTED: {args.ticket_id}")
            print(f"  Branch:  {audit.get('branch', '?')}")
            print(f"  Source:  {audit.get('source_repo', '?')}")
            print(f"  Target:  {audit.get('target_repo', '?')}")
            print(f"  Commit:  {audit.get('source_commit', '?')}")
            print(f"  Result:  {audit.get('result', '?')}")
            print(f"  Detail:  {audit.get('detail', '?')}")
            return 0
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            print(f"ERROR: {e}")
            return 1
    else:
        try:
            request = create_promotion_request(cfg, args.ticket_id,
                                               dry_run=args.dry_run)
            prefix = "[DRY-RUN] " if args.dry_run else ""
            print(f"{prefix}PROMOTION REQUEST: {args.ticket_id}")
            print(f"  Branch:    {request.get('branch', '?')}")
            print(f"  Source:    {request.get('source_repo', '?')} → {request.get('source_path', '?')}")
            print(f"  Target:    {request.get('target_repo', '?')} → {request.get('target_path', '?')}")
            print(f"  Status:    {request.get('status', '?')}")
            print(f"  Requested: {request.get('requested_at', '?')}")
            return 0
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            print(f"ERROR: {e}")
            return 1


def cmd_promotion_check(cfg, args):
    """Check promotion readiness for a ticket."""
    try:
        result = check_promotion_readiness(cfg, args.ticket_id)
        print(f"Promotion Readiness: {args.ticket_id}")
        print(f"  Ready: {'✓ YES' if result['ready'] else '✗ NO'}")
        print()
        for check in result["checks"]:
            mark = "✓" if check["passed"] else "✗"
            print(f"  {mark} {check['name']}: {check['detail']}")
        return 0 if result["ready"] else 1
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

def cmd_qa_pass(cfg, args):
    """Mark QA as passed for a ticket."""
    try:
        record = create_qa_result(cfg, args.ticket_id, True,
                                  notes=args.notes or "",
                                  decision="pass")
        print(f"QA PASSED: {args.ticket_id}")
        print(f"  Decision:     pass")
        print(f"  Validated at: {record['validated_at']}")
        if args.notes:
            print(f"  Notes: {args.notes}")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_qa_fail(cfg, args):
    """Mark QA as failed for a ticket."""
    try:
        record = create_qa_result(cfg, args.ticket_id, False,
                                  notes=args.notes or "",
                                  decision="fail")
        print(f"QA FAILED: {args.ticket_id}")
        print(f"  Decision:     fail")
        print(f"  Validated at: {record['validated_at']}")
        if args.notes:
            print(f"  Notes: {args.notes}")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_qa_decide(cfg, args):
    """Record a QA decision for a ticket (pass/fail/blocked/inconclusive)."""
    try:
        record = create_qa_result(cfg, args.ticket_id, False,
                                  notes=args.notes or "",
                                  decision=args.decision)
        label = record["decision"].upper()
        print(f"QA {label}: {args.ticket_id}")
        print(f"  Decision:     {record['decision']}")
        print(f"  Promotable:   {'yes' if record['passed'] else 'no'}")
        print(f"  Validated at: {record['validated_at']}")
        if args.notes:
            print(f"  Notes: {args.notes}")
        return 0 if record["passed"] else 1
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_qa_check(cfg, args):
    """Show QA status for a ticket."""
    try:
        qa = load_qa_result(cfg, args.ticket_id)
        decision = qa.get("decision")
        if decision:
            label = decision.upper()
        else:
            label = "PASSED" if qa.get("passed") else "FAILED"
        promotable = "yes" if qa.get("passed") else "no"
        print(f"QA Status: {args.ticket_id}")
        print(f"  Decision:   {decision or ('pass' if qa.get('passed') else 'fail')}")
        print(f"  Promotable: {promotable}")
        print(f"  Validated:  {qa.get('validated_at', '?')}")
        print(f"  Validator:  {qa.get('validator', '?')}")
        if qa.get("notes"):
            print(f"  Notes:      {qa['notes']}")
        return 0 if qa.get("passed") else 1
    except FileNotFoundError:
        print(f"QA Status: {args.ticket_id}")
        print("  Result: NOT YET VALIDATED")
        print("  Use 'qa-pass', 'qa-fail', or 'qa-decide' to record a QA result.")
        return 1


def cmd_promotion_status(cfg, args):
    """Show promotion status for a ticket."""
    try:
        request = load_promotion_request(cfg, args.ticket_id)
        print(f"Promotion Status: {args.ticket_id}")
        print(f"  Status:    {request.get('status', '?')}")
        print(f"  Branch:    {request.get('branch', '?')}")
        print(f"  Source:    {request.get('source_repo', '?')} \u2192 {request.get('source_path', '?')}")
        print(f"  Target:    {request.get('target_repo', '?')} \u2192 {request.get('target_path', '?')}")
        print(f"  Requested: {request.get('requested_at', '?')}")
        if request.get("updated_at"):
            print(f"  Updated:   {request['updated_at']}")
        if request.get("status_history"):
            print("  History:")
            for entry in request["status_history"]:
                print(f"    {entry.get('at', '?')}: {entry.get('status', '?')}")
        return 0
    except FileNotFoundError:
        print(f"No promotion request found for: {args.ticket_id}")
        return 1


def cmd_audit_show(cfg, args):
    """Show audit trail for a ticket."""
    records = load_audit_trail(cfg, args.ticket_id)
    if not records:
        print(f"No audit records found for: {args.ticket_id}")
        return 0

    print(f"Audit Trail: {args.ticket_id}")
    print(f"  Records: {len(records)}")
    print()
    for i, r in enumerate(records, 1):
        print(f"  [{i}] {r.get('timestamp', '?')} \u2014 {r.get('action', '?')}")
        print(f"      Result: {r.get('result', '?')}")
        print(f"      Branch: {r.get('branch', '?')}")
        print(f"      Source: {r.get('source_repo', '?')}")
        print(f"      Target: {r.get('target_repo', '?')}")
        if r.get('detail'):
            print(f"      Detail: {r['detail']}")
        if r.get('dry_run') is not None:
            print(f"      Dry-run: {r['dry_run']}")
        print()
    return 0


# ---------------------------------------------------------------------------
# Branch / Commit commands (Sprint 14X-A.1)
# ---------------------------------------------------------------------------

def cmd_branch_status(cfg, args):
    """Show branch status in test_repo for a ticket."""
    try:
        result = check_branch_status(cfg, args.ticket_id)
        print(f"Branch Status: {args.ticket_id}")
        print(f"  Expected branch: {result['branch']}")
        print(f"  Branch exists:   {'yes' if result['branch_exists'] else 'no'}")
        print(f"  Checked out:     {'yes' if result['checked_out'] else 'no'}"
              f" (current: {result['current_branch']})")
        if result['uncommitted_changes']:
            print(f"  Uncommitted:     {len(result['uncommitted_changes'])} file(s)")
            for change in result['uncommitted_changes'][:10]:
                print(f"    {change}")
        else:
            print(f"  Uncommitted:     none")
        if result['branch_exists']:
            print(f"  Commits ahead:   {result['commit_count']} (vs main)")
        return 0
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_branch_prepare(cfg, args):
    """Prepare the target branch in test_repo for a ticket."""
    try:
        result = prepare_worker_branch(cfg, args.ticket_id, dry_run=args.dry_run)
        prefix = "[DRY-RUN] " if args.dry_run else ""
        print(f"{prefix}BRANCH PREPARED: {args.ticket_id}")
        print(f"  Branch:    {result['branch']}")
        print(f"  Created:   {result['created']}")
        print(f"  Detail:    {result['detail']}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1


def cmd_branch_commit(cfg, args):
    """Commit worker changes in test_repo for a ticket."""
    try:
        result = commit_worker_changes(cfg, args.ticket_id,
                                       message=args.message or None,
                                       dry_run=args.dry_run)
        prefix = "[DRY-RUN] " if args.dry_run else ""
        if result['committed']:
            print(f"{prefix}COMMITTED: {args.ticket_id}")
            print(f"  Branch:    {result['branch']}")
            print(f"  Commit:    {result['commit_hash']}")
            print(f"  Files:     {len(result['files_changed'])}")
        elif result['files_changed']:
            print(f"{prefix}WOULD COMMIT: {args.ticket_id}")
            print(f"  Branch:    {result['branch']}")
            print(f"  Files:     {len(result['files_changed'])}")
        else:
            print(f"NO CHANGES: {args.ticket_id}")
        print(f"  Detail:    {result['detail']}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# Intake commands (Sprint 6)
# ---------------------------------------------------------------------------

def _build_intake_payload(args):
    """Build intake payload dict from CLI args."""
    payload = {"title": args.title, "worker": args.worker}
    if args.description:
        payload["description"] = args.description
    if args.branch:
        payload["branch"] = args.branch
    if args.priority:
        payload["priority"] = args.priority
    return payload


def cmd_intake_config(cfg, args):
    """Show current intake configuration."""
    intake = load_intake_config(cfg)
    print("Intake Configuration:")
    print(f"  Trusted sources:  {intake.get('trusted_sources', [])}")
    print(f"  Blocked sources:  {intake.get('blocked_sources', [])}")
    rl = intake.get("rate_limit", {})
    print(f"  Rate limit:       {rl.get('max_per_source_per_minute', 5)}/min per source, "
          f"{rl.get('max_global_per_minute', 20)}/min global")
    print(f"  Dedup window:     {intake.get('duplicate_window_seconds', 300)}s")
    print(f"\n  Known sources: {sorted(INTAKE_SOURCES)}")
    print(f"  Trust levels:  {sorted(SOURCE_TRUST_LEVELS)}")
    print(f"  Intake states: {sorted(INTAKE_STATUSES)}")
    return 0


def cmd_intake_validate(cfg, args):
    """Validate an intake request without admitting it."""
    source = args.source
    payload = _build_intake_payload(args)

    print(f"Validating intake from source: {source}")
    print()

    source_errors = validate_source(source)
    if source_errors:
        print("  Source validation: FAILED")
        for e in source_errors:
            print(f"    \u2717 {e}")
    else:
        trust = get_source_trust(cfg, source)
        print(f"  Source validation: OK (trust={trust})")

    payload_errors = validate_payload(payload)
    if payload_errors:
        print("  Payload validation: FAILED")
        for e in payload_errors:
            print(f"    \u2717 {e}")
    else:
        print("  Payload validation: OK")

    if source_errors or payload_errors:
        return 1
    print("\n  Result: intake request is valid")
    return 0


def cmd_intake_simulate(cfg, args):
    """Simulate full intake pipeline without admitting (dry-run)."""
    source = args.source
    payload = _build_intake_payload(args)

    print(f"Simulating intake from source: {source}")
    result = process_intake(cfg, source, payload, admit=False)
    print(f"  Intake ID: {result['intake_id']}")
    print(f"  Status:    {result['status']}")
    print(f"  Detail:    {result['detail']}")
    if result.get("normalized"):
        print("  Normalized:")
        for k, v in result["normalized"].items():
            print(f"    {k}: {v}")
    return 0 if result["status"] == "normalized" else 1


def cmd_intake_submit(cfg, args):
    """Submit an intake request — full pipeline with admission."""
    source = args.source
    payload = _build_intake_payload(args)

    print(f"Submitting intake from source: {source}")
    result = process_intake(cfg, source, payload, admit=True)
    print(f"  Intake ID:   {result['intake_id']}")
    print(f"  Status:      {result['status']}")
    print(f"  Detail:      {result['detail']}")
    if result.get("ticket_path"):
        print(f"  Ticket file: {result['ticket_path']}")
    return 0 if result["status"] == "admitted" else 1


def cmd_intake_normalize(cfg, args):
    """Show normalization result for an intake payload."""
    source = args.source
    payload = _build_intake_payload(args)

    print(f"Normalizing intake from source: {source}")
    normalized = normalize_request(source, payload)
    print("  Normalized form:")
    for k, v in normalized.items():
        print(f"    {k}: {v}")
    return 0


def cmd_intake_audit_show(cfg, args):
    """Show intake audit trail."""
    records = load_intake_audit(cfg)
    if not records:
        print("No intake audit records found.")
        return 0

    print(f"Intake Audit Trail: {len(records)} record(s)")
    print()
    for i, r in enumerate(records, 1):
        print(f"  [{i}] {r.get('timestamp', '?')} \u2014 {r.get('status', '?')}")
        print(f"      Intake ID: {r.get('intake_id', '?')}")
        print(f"      Source:    {r.get('source', '?')}")
        if r.get("detail"):
            print(f"      Detail:    {r['detail']}")
        print()
    return 0


def cmd_intake_status(cfg, args):
    """Show summary of intake system status."""
    records = load_intake_audit(cfg)
    intake = load_intake_config(cfg)

    status_counts = {}
    source_counts = {}
    for r in records:
        s = r.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
        src = r.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    print("Intake System Status:")
    print(f"  Total records:    {len(records)}")
    print(f"  Trusted sources:  {intake.get('trusted_sources', [])}")
    print(f"  Blocked sources:  {intake.get('blocked_sources', [])}")
    if status_counts:
        print("  By status:")
        for s, c in sorted(status_counts.items()):
            print(f"    {s}: {c}")
    if source_counts:
        print("  By source:")
        for s, c in sorted(source_counts.items()):
            print(f"    {s}: {c}")
    return 0

# ---------------------------------------------------------------------------
# WhatsApp connector commands
# ---------------------------------------------------------------------------

def cmd_whatsapp_config(cfg, args):
    """Show current WhatsApp connector configuration."""
    whatsapp = load_whatsapp_config(cfg)
    print("WhatsApp Connector Configuration:")
    print(f"  Enabled:           {is_whatsapp_enabled(cfg)}")
    print(f"  Webhook URL:       {whatsapp.get('webhook_url', 'not set')}")
    print(f"  Verify token:      {'configured' if get_whatsapp_verify_token(cfg) else 'not set'}")
    print(f"  Access token:      {'configured' if get_whatsapp_access_token(cfg) else 'not set'}")
    print(f"  Authorized senders: {get_authorized_senders(cfg)}")
    print(f"  Rate limit:        {get_whatsapp_rate_limit(cfg)}/min per sender")
    print(f"  Dedup window:      {get_whatsapp_dedup_window(cfg)}s")
    print(f"\n  Supported message types: {sorted(WHATSAPP_MESSAGE_TYPES)}")
    print(f"  WhatsApp statuses: {sorted(WHATSAPP_STATUSES)}")
    return 0


def cmd_whatsapp_validate(cfg, args):
    """Validate WhatsApp connector configuration and readiness."""
    errors = []

    if not is_whatsapp_enabled(cfg):
        print("WhatsApp connector is disabled (set 'enabled: true' in config)")
        return 1

    if not get_whatsapp_access_token(cfg):
        errors.append("Access token not configured")

    if not get_whatsapp_verify_token(cfg):
        errors.append("Verify token not configured")

    authorized = get_authorized_senders(cfg)
    if not authorized:
        errors.append("No authorized senders configured")

    webhook_url = load_whatsapp_config(cfg).get("webhook_url", "")
    if not webhook_url:
        errors.append("Webhook URL not configured")

    if errors:
        print("WhatsApp configuration validation FAILED:")
        for e in errors:
            print(f"  \u2717 {e}")
        return 1

    print("WhatsApp configuration validation PASSED")
    print(f"  Authorized senders: {authorized}")
    print(f"  Webhook URL: {webhook_url}")
    return 0


def cmd_whatsapp_simulate_batch(cfg, args):
    """Simulate a WhatsApp batch webhook with multiple messages."""
    # Parse messages from format "sender:text"
    messages = []
    for msg_str in args.messages:
        if ":" not in msg_str:
            print(f"ERROR: Invalid message format: {msg_str} (expected sender:text)")
            return 1
        sender, text = msg_str.split(":", 1)
        messages.append({"sender": sender, "text": text})

    print(f"Simulating WhatsApp batch with {len(messages)} messages")
    for i, msg in enumerate(messages, 1):
        print(f"  [{i}] From {msg['sender']}: {msg['text']}")
    print()

    # Create mock webhook payload with multiple messages
    mock_messages = []
    for i, msg in enumerate(messages):
        mock_messages.append({
            "id": f"mock_batch_{int(time.time())}_{i}",
            "from": msg["sender"],
            "timestamp": str(int(time.time()) + i),
            "type": "text",
            "text": {"body": msg["text"]}
        })

    mock_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messages": mock_messages
                }
            }]
        }]
    }

    payload_bytes = json.dumps(mock_payload).encode("utf-8")

    # Enable WhatsApp for simulation and allow unsigned webhooks
    if "whatsapp" not in cfg:
        cfg["whatsapp"] = {}
    cfg["whatsapp"]["enabled"] = True
    cfg["whatsapp"]["allow_unsigned_webhooks"] = True
    cfg["whatsapp"]["authorized_senders"] = ["+1234567890"]  # Add test sender
    cfg["whatsapp"]["verify_token"] = "test_verify_token"
    cfg["whatsapp"]["access_token"] = "test_access_token"

    # Enable intake for WhatsApp
    if "intake" not in cfg:
        cfg["intake"] = {}
    cfg["intake"]["trusted_sources"] = ["whatsapp"]

    # Process through connector
    result = process_whatsapp_webhook(cfg, payload_bytes)

    print(f"Batch processing result: {result['status']}")
    print(f"Batch size: {result.get('batch_size', 0)}")
    print(f"Processed: {result.get('processed_messages', 0)}")
    print(f"Admitted: {result.get('admitted_count', 0)}")
    print(f"Rejected: {result.get('rejected_count', 0)}")
    print(f"Duplicates: {result.get('duplicate_count', 0)}")
    print(f"Rate limited: {result.get('rate_limited_count', 0)}")
    if result.get("detail"):
        print(f"Detail: {result['detail']}")
    print()

    # Show per-message results
    if result.get("message_results"):
        print("Per-message results:")
        for i, msg_result in enumerate(result["message_results"], 1):
            status = msg_result.get("status", "unknown")
            msg_id = msg_result.get("message_id", "unknown")
            sender = msg_result.get("sender", "unknown")
            detail = msg_result.get("detail", "")
            print(f"  [{i}] {status.upper()}: {msg_id} from {sender}")
            if detail:
                print(f"      {detail}")

    return 0 if result["status"] in ("admitted", "processed") else 1


def cmd_whatsapp_status(cfg, args):
    """Show WhatsApp connector status and statistics."""
    records = load_whatsapp_audit(cfg)

    status_counts = {}
    sender_counts = {}
    for r in records:
        s = r.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
        sender = r.get("sender", "unknown")
        sender_counts[sender] = sender_counts.get(sender, 0) + 1

    print("WhatsApp Connector Status:")
    print(f"  Enabled:         {is_whatsapp_enabled(cfg)}")
    print(f"  Total records:   {len(records)}")
    if status_counts:
        print("  By status:")
        for s, c in sorted(status_counts.items()):
            print(f"    {s}: {c}")
    if sender_counts:
        print("  By sender:")
        for s, c in sorted(sender_counts.items()):
            print(f"    {s}: {c}")
    return 0


def cmd_whatsapp_audit_show(cfg, args):
    """Show WhatsApp connector audit trail."""
    records = load_whatsapp_audit(cfg)
    if not records:
        print("No WhatsApp audit records found.")
        return 0

    print(f"WhatsApp Audit Trail: {len(records)} record(s)")
    print()
    for i, r in enumerate(records, 1):
        print(f"  [{i}] {r.get('timestamp', '?')} \u2014 {r.get('status', '?')}")
        if r.get("message_id"):
            print(f"      Message ID: {r['message_id']}")
        if r.get("sender"):
            print(f"      Sender:     {r['sender']}")
        if r.get("detail"):
            print(f"      Detail:     {r['detail']}")
        if r.get("intake_result"):
            intake_status = r["intake_result"].get("status")
            print(f"      Intake:     {intake_status}")
        print()
    return 0


def cmd_whatsapp_allowlist_show(cfg, args):
    """Show authorized WhatsApp senders and their authorization status."""
    authorized = get_authorized_senders(cfg)
    if not authorized:
        print("No authorized senders configured.")
        return 1

    print("Authorized WhatsApp Senders:")
    for sender in authorized:
        auth_result, reason = authorize_sender(cfg, sender)
        status = "✓ Authorized" if auth_result else f"✗ {reason}"
        print(f"  {sender}: {status}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="HYBRIS Host Orchestrator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List tickets")
    p_list.add_argument("--state", help="Filter by state")

    # show
    p_show = sub.add_parser("show", help="Show ticket details")
    p_show.add_argument("ticket_id", help="Ticket ID")

    # process
    p_proc = sub.add_parser("process", help="Process a ticket (full pipeline)")
    p_proc.add_argument("ticket_id", help="Ticket ID")
    p_proc.add_argument("--dry-run", action="store_true", help="Simulate without moving files")

    # transition
    p_trans = sub.add_parser("transition", help="Manually transition a ticket")
    p_trans.add_argument("ticket_id", help="Ticket ID")
    p_trans.add_argument("target_state", help="Target state")
    p_trans.add_argument("--dry-run", action="store_true", help="Simulate without moving files")

    # validate
    sub.add_parser("validate", help="Validate orchestrator setup")

    # repo-targets
    sub.add_parser("repo-targets", help="Show configured repo targets")

    # review-show
    p_review = sub.add_parser("review-show", help="Show review package for a ticket")
    p_review.add_argument("ticket_id", help="Ticket ID")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a ticket in review")
    p_approve.add_argument("ticket_id", help="Ticket ID")
    p_approve.add_argument("--reason", default="", help="Approval reason")

    # reject
    p_reject = sub.add_parser("reject", help="Reject a ticket in review")
    p_reject.add_argument("ticket_id", help="Ticket ID")
    p_reject.add_argument("--reason", default="", help="Rejection reason")

    # reticket
    p_reticket = sub.add_parser("reticket", help="Reticket (send back with new scope)")
    p_reticket.add_argument("ticket_id", help="Ticket ID")
    p_reticket.add_argument("--reason", default="", help="Reticket reason")

    # promote
    p_promote = sub.add_parser("promote", help="Create, preview, or execute promotion")
    p_promote.add_argument("ticket_id", help="Ticket ID")
    promote_group = p_promote.add_mutually_exclusive_group()
    promote_group.add_argument("--dry-run", action="store_true",
                               help="Simulate request creation")
    promote_group.add_argument("--preview", action="store_true",
                               help="Preview promotion execution (no changes)")
    promote_group.add_argument("--execute", action="store_true",
                               help="Execute promotion (fetch branch into prod_repo)")

    # promotion-check
    p_promcheck = sub.add_parser("promotion-check", help="Check promotion readiness")
    p_promcheck.add_argument("ticket_id", help="Ticket ID")

    # qa-pass
    p_qa_pass = sub.add_parser("qa-pass", help="Mark QA as passed for a ticket")
    p_qa_pass.add_argument("ticket_id", help="Ticket ID")
    p_qa_pass.add_argument("--notes", default="", help="QA notes")

    # qa-fail
    p_qa_fail = sub.add_parser("qa-fail", help="Mark QA as failed for a ticket")
    p_qa_fail.add_argument("ticket_id", help="Ticket ID")
    p_qa_fail.add_argument("--notes", default="", help="QA notes")

    # qa-decide
    p_qa_decide = sub.add_parser("qa-decide",
                                  help="Record QA decision (pass/fail/blocked/inconclusive)")
    p_qa_decide.add_argument("ticket_id", help="Ticket ID")
    p_qa_decide.add_argument("decision",
                              choices=["pass", "fail", "blocked", "inconclusive"],
                              help="QA decision")
    p_qa_decide.add_argument("--notes", default="", help="QA notes")

    # qa-check
    p_qa_check = sub.add_parser("qa-check", help="Show QA status for a ticket")
    p_qa_check.add_argument("ticket_id", help="Ticket ID")

    # promotion-status
    p_promstatus = sub.add_parser("promotion-status",
                                   help="Show promotion status for a ticket")
    p_promstatus.add_argument("ticket_id", help="Ticket ID")

    # audit-show
    p_audit = sub.add_parser("audit-show", help="Show audit trail for a ticket")
    p_audit.add_argument("ticket_id", help="Ticket ID")

    # intake-config
    sub.add_parser("intake-config", help="Show intake configuration")

    # intake-validate
    p_iv = sub.add_parser("intake-validate", help="Validate an intake request")
    p_iv.add_argument("source", help="Intake source identifier")
    p_iv.add_argument("--title", required=True, help="Ticket title")
    p_iv.add_argument("--worker", required=True, help="Worker type")
    p_iv.add_argument("--description", default="", help="Description")
    p_iv.add_argument("--branch", default="", help="Branch name")
    p_iv.add_argument("--priority", default="normal", help="Priority")

    # intake-simulate
    p_is = sub.add_parser("intake-simulate", help="Simulate intake (dry-run)")
    p_is.add_argument("source", help="Intake source identifier")
    p_is.add_argument("--title", required=True, help="Ticket title")
    p_is.add_argument("--worker", required=True, help="Worker type")
    p_is.add_argument("--description", default="", help="Description")
    p_is.add_argument("--branch", default="", help="Branch name")
    p_is.add_argument("--priority", default="normal", help="Priority")

    # intake-submit
    p_isub = sub.add_parser("intake-submit", help="Submit intake (creates ticket)")
    p_isub.add_argument("source", help="Intake source identifier")
    p_isub.add_argument("--title", required=True, help="Ticket title")
    p_isub.add_argument("--worker", required=True, help="Worker type")
    p_isub.add_argument("--description", default="", help="Description")
    p_isub.add_argument("--branch", default="", help="Branch name")
    p_isub.add_argument("--priority", default="normal", help="Priority")

    # intake-normalize
    p_in = sub.add_parser("intake-normalize", help="Show normalized form")
    p_in.add_argument("source", help="Intake source identifier")
    p_in.add_argument("--title", required=True, help="Ticket title")
    p_in.add_argument("--worker", required=True, help="Worker type")
    p_in.add_argument("--description", default="", help="Description")
    p_in.add_argument("--branch", default="", help="Branch name")
    p_in.add_argument("--priority", default="normal", help="Priority")

    # intake-audit-show
    sub.add_parser("intake-audit-show", help="Show intake audit trail")

    # intake-status
    sub.add_parser("intake-status", help="Show intake system status")

    # branch-status
    p_bstatus = sub.add_parser("branch-status",
                               help="Show branch status in test_repo for a ticket")
    p_bstatus.add_argument("ticket_id", help="Ticket ID")

    # branch-prepare
    p_bprep = sub.add_parser("branch-prepare",
                              help="Prepare target branch in test_repo")
    p_bprep.add_argument("ticket_id", help="Ticket ID")
    p_bprep.add_argument("--dry-run", action="store_true",
                         help="Simulate without creating/checking out branch")

    # branch-commit
    p_bcommit = sub.add_parser("branch-commit",
                                help="Commit worker changes in test_repo")
    p_bcommit.add_argument("ticket_id", help="Ticket ID")
    p_bcommit.add_argument("--message", default="",
                           help="Custom commit message")
    p_bcommit.add_argument("--dry-run", action="store_true",
                           help="Simulate without committing")

    # whatsapp-config
    sub.add_parser("whatsapp-config", help="Show WhatsApp connector configuration")

    # whatsapp-validate
    sub.add_parser("whatsapp-validate", help="Validate WhatsApp connector configuration")

    # whatsapp-simulate-batch
    p_wsimb = sub.add_parser("whatsapp-simulate-batch", help="Simulate WhatsApp batch")
    p_wsimb.add_argument("--messages", nargs="+", required=True,
                         help="Messages in format sender:text (e.g. '+123:hello +456:world')")

    # whatsapp-status
    sub.add_parser("whatsapp-status", help="Show WhatsApp connector status")

    # whatsapp-audit-show
    sub.add_parser("whatsapp-audit-show", help="Show WhatsApp audit trail")

    # whatsapp-allowlist-show
    sub.add_parser("whatsapp-allowlist-show", help="Show authorized WhatsApp senders")

    args = parser.parse_args()
    cfg = load_config()

    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "process": cmd_process,
        "transition": cmd_transition,
        "validate": cmd_validate,
        "repo-targets": cmd_repo_targets,
        "review-show": cmd_review_show,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "reticket": cmd_reticket,
        "promote": cmd_promote,
        "promotion-check": cmd_promotion_check,
        "qa-pass": cmd_qa_pass,
        "qa-fail": cmd_qa_fail,
        "qa-decide": cmd_qa_decide,
        "qa-check": cmd_qa_check,
        "promotion-status": cmd_promotion_status,
        "audit-show": cmd_audit_show,
        "intake-config": cmd_intake_config,
        "intake-validate": cmd_intake_validate,
        "intake-simulate": cmd_intake_simulate,
        "intake-submit": cmd_intake_submit,
        "intake-normalize": cmd_intake_normalize,
        "intake-audit-show": cmd_intake_audit_show,
        "intake-status": cmd_intake_status,
        "branch-status": cmd_branch_status,
        "branch-prepare": cmd_branch_prepare,
        "branch-commit": cmd_branch_commit,
        "whatsapp-config": cmd_whatsapp_config,
        "whatsapp-validate": cmd_whatsapp_validate,
        "whatsapp-simulate-batch": cmd_whatsapp_simulate_batch,
        "whatsapp-status": cmd_whatsapp_status,
        "whatsapp-audit-show": cmd_whatsapp_audit_show,
        "whatsapp-allowlist-show": cmd_whatsapp_allowlist_show,
    }

    return commands[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
