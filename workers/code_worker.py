"""
Code Worker — handles general code tasks (scripts, config, docs).

STUB: validates ticket, logs action, returns success.
Does NOT execute shell commands from ticket content.
"""

from pathlib import Path
from datetime import datetime, timezone


def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    ticket_id = ticket.get("id", "unknown")
    title = ticket.get("title", "untitled")

    if dry_run:
        return {
            "success": True,
            "message": f"[DRY-RUN] code-worker would process: {title}",
            "artifacts": [],
        }

    # Stub: write a proof-of-execution artifact
    artifacts_dir = Path(cfg["management_root"]) / cfg["artifacts_dir"]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact_path = artifacts_dir / f"{ticket_id}_code_result.md"
    artifact_path.write_text(
        f"# Code Worker Result\n\n"
        f"- Ticket: {ticket_id}\n"
        f"- Title: {title}\n"
        f"- Worker: code-worker\n"
        f"- Executed: {now}\n"
        f"- Status: STUB — no real code execution\n"
        f"\nThis is a stub result. The code-worker validated the ticket "
        f"and confirmed it can be processed. No repository changes were made.\n",
        encoding="utf-8",
    )

    return {
        "success": True,
        "message": f"code-worker processed '{title}' (stub). Artifact: {artifact_path}",
        "artifacts": [str(artifact_path)],
    }
