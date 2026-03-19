"""
Code Worker — handles general code tasks (scripts, config, docs).

Produces REAL output in test_repo. See docs/code-worker-contract.md.
Does NOT execute shell commands from ticket content.
Does NOT access prod_repo, network, or protected branches.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple


# Protected branches — worker must never target these
_PROTECTED_BRANCHES = frozenset(["main", "master", "develop"])

# Maximum file size the worker will create (safety cap)
_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB


def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    """
    Execute a code task: create or modify a file in test_repo.

    The ticket description is used to determine the target file path
    (relative to test_repo) and content. For Sprint 10A, the worker
    creates a small utility/config file as specified in the ticket.

    Returns: {"success": bool, "message": str, "artifacts": list,
              "changeset_dir": str, "files_written": list}
    """
    started_at = _now()

    # --- 1. Validate inputs ---
    ticket_id = ticket.get("id", "")
    title = ticket.get("title", "untitled")
    # Use _body (content after YAML frontmatter) for task specification.
    # Falls back to description for unit-test compatibility.
    description = ticket.get("_body") or ticket.get("description", "")
    branch = ticket.get("branch", "")

    validation_err = _validate_inputs(cfg, ticket_id, branch)
    if validation_err:
        return _fail(validation_err)

    agent_repo = Path(cfg["_agent_repo"]).expanduser().resolve()

    # --- 2. Determine target file and content from ticket ---
    target_relative, content = _determine_output(ticket_id, title, description)

    if not target_relative or not content:
        return _fail(
            f"Could not determine output file from ticket '{ticket_id}'. "
            "Ticket description must specify target_file and content."
        )

    # --- 3. Validate target path containment ---
    target_path = (agent_repo / target_relative).resolve()
    containment_err = _validate_containment(target_path, agent_repo)
    if containment_err:
        return _fail(containment_err)

    # --- 4. Content size check ---
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > _MAX_OUTPUT_BYTES:
        return _fail(
            f"Output content exceeds maximum size ({len(content_bytes)} > {_MAX_OUTPUT_BYTES} bytes)."
        )

    # --- 5. Dry-run: report what would happen ---
    if dry_run:
        return {
            "success": True,
            "message": f"[DRY-RUN] code-worker would write: {target_relative}",
            "artifacts": [],
            "changeset_dir": None,
            "files_written": [target_relative],
        }

    # --- 6. Write file to test_repo ---
    action = "modified" if target_path.exists() else "created"
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
    except OSError as e:
        return _fail(f"Failed to write {target_relative}: {e}")

    # Verify the write
    if not target_path.exists() or target_path.stat().st_size == 0:
        return _fail(f"Write verification failed for {target_relative}.")

    # --- 7. Write changeset metadata ---
    finished_at = _now()
    mgmt = Path(cfg["management_root"]).expanduser().resolve()
    changeset_dir = mgmt / "changeset" / f"ticket-{ticket_id}"
    metadata_dir = changeset_dir / "metadata"

    try:
        metadata_dir.mkdir(parents=True, exist_ok=True)

        changeset_json = {
            "ticket_id": ticket_id,
            "worker_type": "code-worker",
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "completed",
            "files_written": [
                {
                    "path": target_relative,
                    "action": action,
                    "size_bytes": target_path.stat().st_size,
                }
            ],
        }
        (metadata_dir / "changeset.json").write_text(
            json.dumps(changeset_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        manifest_json = {
            "ticket_id": ticket_id,
            "worker_type": "code-worker",
            "timestamp": finished_at,
            "files_added": [target_relative] if action == "created" else [],
            "files_modified": [target_relative] if action == "modified" else [],
            "files_deleted": [],
            "artifact_summary": f"{cfg['artifacts_dir']}/{ticket_id}_code_result.md",
        }
        (metadata_dir / "manifest.json").write_text(
            json.dumps(manifest_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as e:
        return _fail(f"Failed to write changeset metadata: {e}")

    # --- 8. Write artifact summary ---
    artifacts_dir = mgmt / cfg["artifacts_dir"]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / f"{ticket_id}_code_result.md"
    artifact_path.write_text(
        f"# Code Worker Result\n\n"
        f"- **Ticket:** {ticket_id}\n"
        f"- **Title:** {title}\n"
        f"- **Worker:** code-worker\n"
        f"- **Started:** {started_at}\n"
        f"- **Finished:** {finished_at}\n"
        f"- **Status:** completed — real output\n"
        f"- **Target repo:** test_repo\n"
        f"- **File {action}:** `{target_relative}`\n"
        f"- **File size:** {target_path.stat().st_size} bytes\n"
        f"\n## Change Description\n\n{title}\n"
        f"\n## Changeset\n\n"
        f"See `changeset/ticket-{ticket_id}/metadata/` for machine-readable details.\n",
        encoding="utf-8",
    )

    changeset_dir_rel = str(changeset_dir.relative_to(mgmt))
    artifact_rel = str(artifact_path.relative_to(mgmt))

    return {
        "success": True,
        "message": (
            f"code-worker {action} '{target_relative}' in test_repo "
            f"for ticket '{ticket_id}'."
        ),
        "artifacts": [artifact_rel],
        "changeset_dir": changeset_dir_rel,
        "files_written": [target_relative],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(message: str) -> dict:
    """Return a standardized failure result. Never raises."""
    return {
        "success": False,
        "message": f"code-worker FAILED: {message}",
        "artifacts": [],
        "changeset_dir": None,
        "files_written": [],
    }


def _validate_inputs(cfg: dict, ticket_id: str, branch: str) -> Optional[str]:
    """Validate required inputs. Returns error message or None."""
    if not ticket_id:
        return "ticket.id is missing or empty."

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$", ticket_id):
        return f"Invalid ticket ID format: '{ticket_id}'"

    if not cfg.get("_agent_repo"):
        return "cfg._agent_repo is missing — dispatch_worker() must set this."

    agent_repo = Path(cfg["_agent_repo"]).expanduser().resolve()
    if not agent_repo.is_dir():
        return f"_agent_repo is not a directory: {agent_repo}"

    # Reject if _agent_repo points to prod_repo
    prod_repo = cfg.get("repo_targets", {}).get("prod_repo", "")
    if prod_repo:
        prod_resolved = Path(prod_repo).expanduser().resolve()
        if agent_repo == prod_resolved:
            return "SECURITY: _agent_repo resolves to prod_repo. Refusing to execute."

    if branch and branch in _PROTECTED_BRANCHES:
        return f"SECURITY: Target branch '{branch}' is protected. Refusing to execute."

    return None


def _validate_containment(target_path: Path, agent_repo: Path) -> Optional[str]:
    """Ensure target_path is strictly under agent_repo. Returns error or None."""
    try:
        target_path.relative_to(agent_repo)
    except ValueError:
        return (
            f"SECURITY: Target path escapes agent_repo containment.\n"
            f"  target: {target_path}\n"
            f"  repo:   {agent_repo}"
        )
    return None


def _determine_output(ticket_id: str, title: str, description: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse the ticket description to determine target file and content.

    Expected description format (lines):
        target_file: relative/path/to/file.ext
        ---
        (file content follows)

    Returns (relative_path: str, content: str) or (None, None) on failure.
    """
    if not description:
        return None, None

    lines = description.strip().split("\n")

    # Parse target_file directive
    target_file = None
    separator_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("target_file:"):
            target_file = stripped.split(":", 1)[1].strip()
        if stripped == "---":
            separator_idx = i
            break

    if not target_file:
        return None, None

    # Validate target_file: no '..' or absolute paths
    if ".." in target_file or target_file.startswith("/"):
        return None, None

    # Content is everything after the '---' separator
    if separator_idx is not None and separator_idx + 1 < len(lines):
        content = "\n".join(lines[separator_idx + 1:])
        # Strip one leading newline if present
        if content.startswith("\n"):
            content = content[1:]
    else:
        # No separator: generate a minimal placeholder
        content = (
            f"// Generated by code-worker for ticket: {ticket_id}\n"
            f"// Title: {title}\n"
            f"// This file was created by the HYBRIS multi-agent pipeline.\n"
        )

    if not content.strip():
        return None, None

    return target_file, content
