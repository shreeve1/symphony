"""Binding-lookup and worktree helpers.

Pure leaf over config + worktree_facade + tracker_types — no dispatch state,
no I/O beyond worktree_facade, no dependency on scheduler.__init__.

Extracted from scheduler.__init__ as part of the shared-infra seam (same
precedent as scheduler/ports.py).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from config import ProjectBinding, SymphonyConfig

if TYPE_CHECKING:
    from tracker_types import CandidateIssue


def binding_from_config(config: SymphonyConfig) -> ProjectBinding | None:
    if len(config.bindings) == 1:
        return config.bindings[0]
    return None


def binding_for_issue(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None = None,
) -> ProjectBinding | None:
    if binding is not None:
        return binding
    candidate_binding_name = getattr(candidate, "binding_name", "")
    if candidate_binding_name:
        for configured_binding in config.bindings:
            if configured_binding.name == candidate_binding_name:
                return configured_binding
    return binding_from_config(config)


def worktree_enabled(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    *,
    binding: ProjectBinding | None = None,
) -> bool:
    # per-binding capability (ADR-0032); falls back to global config when binding is None
    wt_default = (
        binding.worktree_default if binding is not None else config.worktree_default
    )
    if not wt_default:
        return False
    return bool(getattr(candidate, "worktree_active", False))


def worktree_run_fields(
    config: SymphonyConfig,
    candidate: CandidateIssue,
    base_branch: str,
    *,
    binding: ProjectBinding | None = None,
) -> dict[str, str]:
    if not worktree_enabled(config, candidate, binding=binding):
        return {}
    resolved_binding = binding_for_issue(config, candidate, binding=binding)
    worktree_helpers = import_module("worktree_facade")
    branch_name = worktree_helpers.branch_name
    worktree_dir = worktree_helpers.worktree_dir

    binding_name = getattr(candidate, "binding_name", "") or (
        resolved_binding.name if resolved_binding is not None else ""
    )
    issue_id = str(candidate.id)
    return {
        "worktree_path": str(
            worktree_dir(config.homelab_repo_path, binding_name, issue_id)
        ),
        "branch_name": branch_name(binding_name, issue_id),
        "base_branch": base_branch,
    }
