"""
Base worker interface for HYBRIS host orchestrator.

All workers must implement execute(cfg, ticket, dry_run=False) -> dict
returning: {"success": bool, "message": str, "artifacts": list,
            "changeset_dir": str|None, "files_written": list}

See docs/worker-output-format.md for field semantics.
"""


def execute(cfg: dict, ticket: dict, dry_run: bool = False) -> dict:
    """Override this in each worker."""
    raise NotImplementedError("Worker must implement execute()")
