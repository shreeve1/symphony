"""Resolve the running Symphony git sha for diagnostics.

Used at startup and in Plane claim comments so that a failing dispatch can be
traced back to a specific Symphony revision. Returns ``"unknown"`` rather than
raising if ``git rev-parse`` fails, so a missing/non-git deploy environment
cannot crash Symphony startup.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)

UNKNOWN = "unknown"


def resolve_code_sha(repo_path: Path | str | None = None) -> str:
    """Return the short git sha of ``repo_path`` (default: this module's repo).

    Never raises. Returns ``"unknown"`` on any failure.
    """
    cwd: Path
    if repo_path is None:
        cwd = Path(__file__).resolve().parent
    else:
        cwd = Path(repo_path)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOGGER.debug("code_sha_resolve_failed cause=%s", exc.__class__.__name__)
        return UNKNOWN
    if result.returncode != 0:
        LOGGER.debug(
            "code_sha_resolve_failed exit=%s stderr=%s",
            result.returncode,
            result.stderr.strip(),
        )
        return UNKNOWN
    sha = result.stdout.strip()
    return sha or UNKNOWN
