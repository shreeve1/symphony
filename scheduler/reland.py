"""Pure text helpers for review reland / commit-redispatch marker generation.

Leaf module — no __init__ dependency to avoid import cycles.
"""

from __future__ import annotations

import re
from datetime import datetime
from importlib import import_module

from config import SymphonyConfig
from redispatch_core import (
    COMMIT_REDISPATCH_REPLY_PREFIX,
    RELAND_DONE_PREFIX,
    RELAND_DONE_RE,
    RELAND_PENDING_PREFIX,
    RELAND_PENDING_RE,
    redispatch_commit_note,
)

_REVIEW_DISPATCH_MARKER_RE = re.compile(
    r"^### Symphony Review(?: \((\d+)\))?[ \t]*$", re.MULTILINE
)


def _next_review_dispatch_marker(comments_md: str) -> str:
    prior = len(_REVIEW_DISPATCH_MARKER_RE.findall(comments_md or ""))
    return f"### Symphony Review ({prior + 1})\n\nReview run dispatched."


def _reland_pending_count(comments_md: str) -> int:
    return len(RELAND_PENDING_RE.findall(comments_md or ""))


def _reland_done_count(comments_md: str) -> int:
    return len(RELAND_DONE_RE.findall(comments_md or ""))


def _commit_redispatch_body(
    config: SymphonyConfig,
    binding_name: str,
    issue_id: str,
    *,
    auto_land: bool,
    now: datetime,
) -> str:
    worktree_helpers = import_module("worktree_facade")
    worktree_path = worktree_helpers.worktree_dir(
        config.homelab_repo_path, binding_name, issue_id
    )
    branch = worktree_helpers.branch_name(binding_name, issue_id)
    body = (
        f"{COMMIT_REDISPATCH_REPLY_PREFIX} · {now.isoformat()})\n\n"
        f"{redispatch_commit_note(worktree_path, branch)}"
    )
    if auto_land:
        body += f"\n\n{RELAND_PENDING_PREFIX} · {now.isoformat()}"
    return body


def _reland_done_body(comments_md: str, *, now: datetime) -> str:
    outstanding = _reland_pending_count(comments_md) - _reland_done_count(comments_md)
    if outstanding <= 0:
        return ""
    return "\n".join(
        f"{RELAND_DONE_PREFIX} · {now.isoformat()}" for _ in range(outstanding)
    )
