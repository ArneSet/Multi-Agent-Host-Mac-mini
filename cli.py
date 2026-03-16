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
    python3 cli.py promote TICKET_ID [--dry-run]
"""

import argparse
import json
import sys
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
    create_review_package,
    load_review_package,
    create_approval_decision,
    load_approval_decision,
    create_promotion_request,
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
        print(f"  ✓ All {len(cfg['allowed_workers'])} worker modules present")
        return 0


def cmd_repo_targets(cfg, args):
    """Show configured repo targets."""
    repo_targets = cfg.get("repo_targets", {})
    test_repo = repo_targets.get("test_repo", "(not set)")
    prod_repo = repo_targets.get("prod_repo", "(not set)")
    print("Repo Targets:")
    print(f"  test_repo: {test_repo}")
    print(f"  prod_repo: {prod_repo}")
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
    """Create a promotion request for an approved ticket."""
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
    p_promote = sub.add_parser("promote", help="Create promotion request for approved ticket")
    p_promote.add_argument("ticket_id", help="Ticket ID")
    p_promote.add_argument("--dry-run", action="store_true", help="Simulate without writing files")

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
    }

    return commands[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
