"""Scheduler selection concern module.

Pure candidate-selection predicates: role membership on a candidate's labels and
picking the oldest eligible candidate. No dispatch state, no I/O — the impure
reservation helpers remain in ``scheduler.__init__`` until later slices move them
behind stable module seams.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from tracker_adapter import TrackerAdapter
from tracker_contract import DEFAULT_CONTRACT, TrackerContract, TrackerRole
from tracker_types import CandidateIssue


def labels_contain_role(
    labels: tuple[str, ...] | list[str],
    tracker: TrackerAdapter | TrackerContract,
    role: TrackerRole,
) -> bool:
    if hasattr(tracker, "labels_contain_role"):
        return cast(TrackerAdapter, tracker).labels_contain_role(labels, role)
    contract = cast(TrackerContract, tracker)
    binding = contract.optional_label_binding(role)
    if binding is None:
        return False
    values = {binding.name}
    if binding.uuid:
        values.add(binding.uuid)
    return bool(values & set(labels))


def oldest_candidate(
    candidates: Sequence[CandidateIssue],
    contract: TrackerContract = DEFAULT_CONTRACT,
    *,
    approval_policy_enabled: bool = True,
) -> CandidateIssue | None:
    eligible = [
        issue
        for issue in candidates
        if (
            not approval_policy_enabled
            or not labels_contain_role(
                issue.labels, contract, TrackerRole.APPROVAL_REQUIRED
            )
        )
        and not labels_contain_role(issue.labels, contract, TrackerRole.SCHEDULED)
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda issue: issue.created_at)[0]
