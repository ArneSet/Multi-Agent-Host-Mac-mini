#!/usr/bin/env python3
"""
HYBRIS Host CLI — Entrypoint for ticket-based orchestration.

Usage:
    python3 cli.py list [--state STATE]
    python3 cli.py show TICKET_ID
    python3 cli.py process TICKET_ID [--dry-run]
    python3 cli.py transition TICKET_ID TARGET_STATE [--dry-run]
    python3 cli.py validate
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

    # Check repo root
    repo = Path(cfg["game_repo_root"])
    if not repo.is_dir():
        errors.append(f"Repo root not found: {repo}")
    elif not (repo / "Assets").is_dir():
        errors.append(f"Assets/ not found in repo root: {repo}")

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
        print(f"  ✓ Repo root valid: {repo}")
        print(f"  ✓ All {len(cfg['allowed_workers'])} worker modules present")
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

    args = parser.parse_args()
    cfg = load_config()

    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "process": cmd_process,
        "transition": cmd_transition,
        "validate": cmd_validate,
    }

    return commands[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
