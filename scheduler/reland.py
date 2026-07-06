"""Pure text helpers for review reland / commit-redispatch marker generation.

Leaf module — no __init__ dependency to avoid import cycles.
"""

from __future__ import annotations

import re
from datetime import datetime
from importlib import import_module
from typing import cast

from config import ProjectBinding, SymphonyConfig
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


# ---------------------------------------------------------------------------
# Impure worktree helpers (slice 2b)
# ---------------------------------------------------------------------------


def _review_worktree_is_dirty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
) -> bool:
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(
            bool,
            remote_worktree.worktree_is_dirty(
                binding.remote, config.homelab_repo_path, binding_name, issue_id
            ),
        )
    worktree_helpers = import_module("worktree_facade")
    return cast(
        bool,
        worktree_helpers.worktree_is_dirty(
            config.homelab_repo_path, binding_name, issue_id
        ),
    )


def _review_worktree_diff_empty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> bool:
    if binding is not None and binding.is_remote:
        return False
    worktree_helpers = import_module("worktree_facade")
    return cast(
        bool,
        worktree_helpers.worktree_diff_empty(
            config.homelab_repo_path, binding_name, issue_id, base_branch
        ),
    )


def _review_base_repo_dirty(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
) -> bool:
    """Return True if the base repo checkout has uncommitted changes.

    Mirror of `_review_worktree_is_dirty` that checks the base repo
    rather than a specific worktree. Local path uses
    ``web.api.worktree.base_repo_dirty`` directly because
    ``worktree_facade.__all__`` does not export it.
    """
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(
            bool,
            remote_worktree.base_repo_dirty(binding.remote, config.homelab_repo_path),
        )
    from web.api.worktree import base_repo_dirty as _local_base_repo_dirty

    return _local_base_repo_dirty(config.homelab_repo_path)


def _land_review_worktree(
    config: SymphonyConfig,
    binding: ProjectBinding | None,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> str | None:
    if binding is not None and binding.is_remote:
        remote_worktree = import_module("remote_worktree")
        return cast(
            str | None,
            remote_worktree.land_worktree(
                binding.remote,
                config.homelab_repo_path,
                binding_name,
                issue_id,
                base_branch,
            ),
        )
    worktree_helpers = import_module("worktree_facade")
    return cast(
        str | None,
        worktree_helpers.land_worktree(
            config.homelab_repo_path, binding_name, issue_id, base_branch
        ),
    )
