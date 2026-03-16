"""
Unity Worker — handles Unity Editor tasks (scene setup, prefab creation, build).

STUB: validates ticket, logs action, returns success.
Does NOT open Unity or modify Assets/ without explicit approval.
"""

from datetime import datetime, timezone
from pathlib import Path


def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    ticket_id = ticket.get("id", "unknown")
    title = ticket.get("title", "untitled")

    if dry_run:
        return {
            "success": True,
            "message": f"[DRY-RUN] unity-worker would process: {title}",
            "artifacts": [],
        }

    # Stub: confirm ticket is valid for Unity work
    repo_root = Path(cfg["game_repo_root"])
    assets_exists = (repo_root / "Assets").is_dir()

    artifacts_dir = Path(cfg["management_root"]) / cfg["artifacts_dir"]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact_path = artifacts_dir / f"{ticket_id}_unity_result.md"
    artifact_path.write_text(
        f"# Unity Worker Result\n\n"
        f"- Ticket: {ticket_id}\n"
        f"- Title: {title}\n"
        f"- Worker: unity-worker\n"
        f"- Executed: {now}\n"
        f"- Repo root valid: {repo_root.exists()}\n"
        f"- Assets/ found: {assets_exists}\n"
        f"- Status: STUB — no Unity operations performed\n"
        f"\nThis is a stub result. In production, this worker would invoke "
        f"Unity Editor via batch mode or RunCommand tool.\n",
        encoding="utf-8",
    )

    return {
        "success": True,
        "message": f"unity-worker validated '{title}' (stub). Assets/ present: {assets_exists}",
        "artifacts": [str(artifact_path)],
    }
