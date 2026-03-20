"""
Tripo Worker — handles AI 3D generation tasks via Tripo API.

STUB: validates ticket, logs action, returns success.
Does NOT call any external API without explicit approval and secrets.
"""

from datetime import datetime, timezone
from pathlib import Path


def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    ticket_id = ticket.get("id", "unknown")
    title = ticket.get("title", "untitled")

    if dry_run:
        return {
            "success": True,
            "message": f"[DRY-RUN] tripo-worker would process: {title}",
            "artifacts": [],
            "changeset_dir": None,
            "files_written": [],
        }

    artifacts_dir = Path(cfg["management_root"]) / cfg["artifacts_dir"]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact_path = artifacts_dir / f"{ticket_id}_tripo_result.md"
    artifact_path.write_text(
        f"# Tripo Worker Result\n\n"
        f"- Ticket: {ticket_id}\n"
        f"- Title: {title}\n"
        f"- Worker: tripo-worker\n"
        f"- Executed: {now}\n"
        f"- Status: STUB — no API calls made\n"
        f"\nThis is a stub result. In production, this worker would call the "
        f"Tripo AI API to generate 3D models. Requires API key in secrets.\n",
        encoding="utf-8",
    )

    return {
        "success": True,
        "message": f"tripo-worker validated '{title}' (stub). No API calls made.",
        "artifacts": [str(artifact_path)],
        "changeset_dir": None,
        "files_written": [],
    }
