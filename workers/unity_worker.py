"""
Unity Worker — validation and inspection of Unity projects in test_repo.

Invokes Unity CLI in batchmode for project health checks.
Does NOT mutate project content (read-only validation in Sprint 10B).
Does NOT access prod_repo, network, or protected branches.
See docs/unity-worker-contract.md for full contract.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Protected branches — worker must never target these
_PROTECTED_BRANCHES = frozenset(["main", "master", "develop"])

# Unity batchmode timeout in seconds
_BATCHMODE_TIMEOUT = 120

# Supported validation types
_VALIDATION_TYPES = frozenset(["project-health"])

# Unity Editor base path (macOS, Hub install)
_UNITY_HUB_EDITORS = Path("/Applications/Unity/Hub/Editor")


def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    """
    Execute a Unity validation task against test_repo.

    Reads validation_type from ticket body, invokes Unity batchmode,
    parses log output for errors, produces validation report.

    Returns: {"success": bool, "message": str, "artifacts": list,
              "changeset_dir": str, "files_written": list}
    """
    started_at = _now()

    # --- 1. Validate inputs ---
    ticket_id = ticket.get("id", "")
    title = ticket.get("title", "untitled")
    description = ticket.get("_body") or ticket.get("description", "")
    branch = ticket.get("branch", "")

    validation_err = _validate_inputs(cfg, ticket_id, branch)
    if validation_err:
        return _fail(validation_err)

    agent_repo = Path(cfg["_agent_repo"]).expanduser().resolve()

    # --- 2. Parse validation type from ticket body ---
    validation_type = _parse_validation_type(description)
    if not validation_type:
        return _fail(
            f"No validation_type found in ticket body. "
            f"Supported types: {', '.join(sorted(_VALIDATION_TYPES))}"
        )
    if validation_type not in _VALIDATION_TYPES:
        return _fail(
            f"Unknown validation_type: '{validation_type}'. "
            f"Supported: {', '.join(sorted(_VALIDATION_TYPES))}"
        )

    # --- 3. Resolve Unity Editor binary ---
    unity_binary, version_err = _resolve_unity_binary(agent_repo)
    if version_err:
        return _fail(version_err)

    # --- 4. Dry-run ---
    if dry_run:
        return {
            "success": True,
            "message": (
                f"[DRY-RUN] unity-worker would run '{validation_type}' "
                f"against {agent_repo} using {unity_binary}"
            ),
            "artifacts": [],
            "changeset_dir": None,
            "files_written": [],
        }

    # --- 5. Prepare log capture path ---
    mgmt = Path(cfg["management_root"]).expanduser().resolve()
    changeset_dir = mgmt / "changeset" / f"ticket-{ticket_id}"
    metadata_dir = changeset_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    log_path = metadata_dir / "unity_log.txt"

    # --- 6. Run Unity batchmode ---
    cmd = [
        str(unity_binary),
        "-batchmode",
        "-nographics",
        "-projectPath", str(agent_repo),
        "-quit",
        "-logFile", str(log_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_BATCHMODE_TIMEOUT,
        )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        # Read whatever log was produced before timeout
        log_content = _safe_read(log_path)
        return _fail(
            f"Unity batchmode timed out after {_BATCHMODE_TIMEOUT}s. "
            f"Partial log: {len(log_content)} chars captured."
        )
    except OSError as e:
        return _fail(f"Failed to invoke Unity CLI: {e}")

    # --- 7. Parse log for results ---
    log_content = _safe_read(log_path)
    compile_errors = _extract_compile_errors(log_content)
    batch_success = "Exiting batchmode successfully now!" in log_content

    validation_passed = (exit_code == 0 and batch_success and not compile_errors)

    # --- 8. Write changeset metadata ---
    finished_at = _now()

    changeset_json = {
        "ticket_id": ticket_id,
        "worker_type": "unity-worker",
        "validation_type": validation_type,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "completed" if validation_passed else "failed",
        "unity_exit_code": exit_code,
        "batch_success": batch_success,
        "compile_errors_count": len(compile_errors),
        "files_written": [],
    }
    (metadata_dir / "changeset.json").write_text(
        json.dumps(changeset_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest_json = {
        "ticket_id": ticket_id,
        "worker_type": "unity-worker",
        "timestamp": finished_at,
        "files_added": [],
        "files_modified": [],
        "files_deleted": [],
        "artifact_summary": f"{cfg['artifacts_dir']}/{ticket_id}_unity_result.md",
    }
    (metadata_dir / "manifest.json").write_text(
        json.dumps(manifest_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- 9. Write artifact report ---
    artifacts_dir = mgmt / cfg["artifacts_dir"]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / f"{ticket_id}_unity_result.md"

    error_section = ""
    if compile_errors:
        error_section = "\n## Compile Errors\n\n"
        for err in compile_errors[:20]:  # cap at 20
            error_section += f"- {err}\n"
        if len(compile_errors) > 20:
            error_section += f"\n... and {len(compile_errors) - 20} more.\n"

    artifact_path.write_text(
        f"# Unity Worker Validation Report\n\n"
        f"- **Ticket:** {ticket_id}\n"
        f"- **Title:** {title}\n"
        f"- **Worker:** unity-worker\n"
        f"- **Validation Type:** {validation_type}\n"
        f"- **Started:** {started_at}\n"
        f"- **Finished:** {finished_at}\n"
        f"- **Unity Exit Code:** {exit_code}\n"
        f"- **Batchmode Success:** {batch_success}\n"
        f"- **Compile Errors:** {len(compile_errors)}\n"
        f"- **Validation Result:** {'PASSED' if validation_passed else 'FAILED'}\n"
        f"- **Target Repo:** test_repo\n"
        f"- **Project Path:** `{agent_repo}`\n"
        f"{error_section}"
        f"\n## Changeset\n\n"
        f"See `changeset/ticket-{ticket_id}/metadata/` for machine-readable details.\n"
        f"Unity log: `changeset/ticket-{ticket_id}/metadata/unity_log.txt`\n",
        encoding="utf-8",
    )

    changeset_dir_rel = str(changeset_dir.relative_to(mgmt))
    artifact_rel = str(artifact_path.relative_to(mgmt))

    status_word = "PASSED" if validation_passed else "FAILED"
    message = (
        f"unity-worker {validation_type} {status_word} for ticket '{ticket_id}'. "
        f"Exit code: {exit_code}, compile errors: {len(compile_errors)}."
    )

    return {
        "success": validation_passed,
        "message": message,
        "artifacts": [artifact_rel],
        "changeset_dir": changeset_dir_rel,
        "files_written": [],  # validation-only, no test_repo writes
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
        "message": f"unity-worker FAILED: {message}",
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

    # Verify Unity project structure
    if not (agent_repo / "Assets").is_dir():
        return f"Not a Unity project: Assets/ missing in {agent_repo}"
    if not (agent_repo / "ProjectSettings").is_dir():
        return f"Not a Unity project: ProjectSettings/ missing in {agent_repo}"

    if branch and branch in _PROTECTED_BRANCHES:
        return f"SECURITY: Target branch '{branch}' is protected. Refusing to execute."

    return None


def _parse_validation_type(body: str) -> Optional[str]:
    """Extract validation_type: value from ticket body."""
    if not body:
        return None
    for line in body.strip().split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("validation_type:"):
            return stripped.split(":", 1)[1].strip().lower()
    return None


def _resolve_unity_binary(project_path: Path) -> tuple:
    """
    Resolve Unity Editor binary matching the project's version.

    Returns (Path, None) on success, or (None, error_str) on failure.
    """
    version_file = project_path / "ProjectSettings" / "ProjectVersion.txt"
    if not version_file.exists():
        return None, f"ProjectVersion.txt not found at {version_file}"

    try:
        text = version_file.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"Cannot read ProjectVersion.txt: {e}"

    # Parse: m_EditorVersion: 6000.3.10f1
    match = re.search(r"m_EditorVersion:\s*(\S+)", text)
    if not match:
        return None, f"Cannot parse editor version from ProjectVersion.txt"

    version = match.group(1)
    binary = _UNITY_HUB_EDITORS / version / "Unity.app" / "Contents" / "MacOS" / "Unity"

    if not binary.exists():
        return None, (
            f"Unity Editor {version} not found at {binary}. "
            f"Install via Unity Hub."
        )

    if not binary.is_file():
        return None, f"Unity binary path is not a file: {binary}"

    return binary, None


def _safe_read(path: Path) -> str:
    """Read a file, returning empty string on error."""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return ""


def _extract_compile_errors(log_content: str) -> list:
    """
    Extract compile error lines from Unity log output.

    Unity compile errors typically appear as:
    Assets/Scripts/Foo.cs(10,5): error CS1234: message
    """
    errors = []
    for line in log_content.split("\n"):
        # Match Unity-style compile errors
        if re.search(r"error CS\d+:", line):
            errors.append(line.strip())
        elif re.search(r"\.cs\(\d+,\d+\):\s*error", line):
            errors.append(line.strip())
    return errors
