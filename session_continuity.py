"""Session Resume continuity decisions for Symphony agent dispatch."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

ACTION_RESUME = "resume"
ACTION_REFEED = "refeed"

REASON_ELIGIBLE = "eligible"
REASON_AGENT_MISMATCH = "agent-mismatch"
REASON_CWD_MISSING = "cwd-missing"
REASON_SESSION_ABSENT = "session-absent"
REASON_SHA_DRIFT = "sha-drift"

_SESSION_NAMESPACE = uuid.NAMESPACE_URL
_SESSION_PREFIX = "symphony.issue:"


@dataclass(frozen=True)
class ResumeDecision:
    """Machine-readable Session Resume decision."""

    action: str
    reason: str
    session_id: str
    session_file: Path


def derive_session_id(issue_id: object, generation: int = 0) -> str:
    """Derive the stable agent session id for an issue.

    ``generation`` scopes patrol sessions so each three-Run generation
    receives a distinct id.  Generation 0 preserves the existing UUID for
    all non-patrol issues and the first three patrol Runs; higher generations
    produce stable, distinct ids that cannot be resumed by a prior generation.
    """

    if generation > 0:
        return str(
            uuid.uuid5(
                _SESSION_NAMESPACE,
                f"{_SESSION_PREFIX}{issue_id}/gen{generation}",
            )
        )
    return str(uuid.uuid5(_SESSION_NAMESPACE, f"{_SESSION_PREFIX}{issue_id}"))


def session_file_path(agent_kind: str, cwd: Path | str, session_id: str) -> Path:
    """Return the expected agent session file path for a cwd/session id."""

    normalized_agent = agent_kind.lower()
    resolved_cwd = _resolve_cwd(cwd)
    if normalized_agent == "claude":
        encoded_cwd = re.sub(r"[^A-Za-z0-9]", "-", str(resolved_cwd))
        return (
            Path.home() / ".claude" / "projects" / encoded_cwd / f"{session_id}.jsonl"
        )
    if normalized_agent == "pi":
        session_dir = _pi_session_dir(resolved_cwd)
        existing = sorted(session_dir.glob(f"*_{session_id}.jsonl"))
        if existing:
            return existing[-1]
        return session_dir / f"{session_id}.jsonl"
    raise ValueError(f"Unsupported agent kind: {agent_kind}")


def evaluate_resume_eligibility(
    *,
    previous_agent_kind: str,
    current_agent_kind: str,
    previous_cwd: Path | str,
    current_cwd: Path | str,
    session_id: str,
    agent_session_sha: str | None,
    current_git_sha: str | None,
) -> ResumeDecision:
    """Decide whether a parked issue can resume a prior agent session."""

    session_file = session_file_path(current_agent_kind, current_cwd, session_id)
    if previous_agent_kind.lower() != current_agent_kind.lower():
        return _refeed(REASON_AGENT_MISMATCH, session_id, session_file)

    if not _cwd_stable(previous_cwd, current_cwd):
        return _refeed(REASON_CWD_MISSING, session_id, session_file)

    if not _session_file_exists(current_agent_kind, session_file, session_id):
        return _refeed(REASON_SESSION_ABSENT, session_id, session_file)

    if not agent_session_sha or agent_session_sha != current_git_sha:
        return _refeed(REASON_SHA_DRIFT, session_id, session_file)

    return ResumeDecision(
        action=ACTION_RESUME,
        reason=REASON_ELIGIBLE,
        session_id=session_id,
        session_file=session_file,
    )


def _refeed(reason: str, session_id: str, session_file: Path) -> ResumeDecision:
    return ResumeDecision(
        action=ACTION_REFEED,
        reason=reason,
        session_id=session_id,
        session_file=session_file,
    )


def _resolve_cwd(cwd: Path | str) -> Path:
    return Path(cwd).expanduser().resolve(strict=False)


def _cwd_stable(previous_cwd: Path | str, current_cwd: Path | str) -> bool:
    resolved_previous = _resolve_cwd(previous_cwd)
    resolved_current = _resolve_cwd(current_cwd)
    # ponytail: .exists() raises OSError when cwd is a remote path whose parent
    # dir is unreadable locally (e.g. /home/itadmin/ 700). Treat as not-stable.
    try:
        return resolved_current.exists() and resolved_previous == resolved_current
    except OSError:
        return False


def _session_file_exists(agent_kind: str, session_file: Path, session_id: str) -> bool:
    if session_file.exists():
        return True
    if agent_kind.lower() == "pi":
        return any(session_file.parent.glob(f"*_{session_id}.jsonl"))
    return False


def _pi_session_dir(cwd: Path) -> Path:
    override = os.environ.get("PI_CODING_AGENT_SESSION_DIR")
    if override:
        return Path(override).expanduser().resolve(strict=False)
    cwd_text = str(cwd)
    safe_path = f"--{cwd_text.lstrip('/\\').replace('/', '-').replace('\\', '-').replace(':', '-')}--"
    return Path.home() / ".pi" / "agent" / "sessions" / safe_path
