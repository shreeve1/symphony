"""Scheduler selection concern module.

Candidate-selection predicates and reservation helpers for in-flight dispatch
state management.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from tracker_adapter import TrackerAdapter
from tracker_contract import DEFAULT_CONTRACT, TrackerContract, TrackerRole
from tracker_types import CandidateIssue

from .dispatch_state import SchedulerError, _DispatchState


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


async def _reserve_candidate(
    candidates: Sequence[CandidateIssue],
    contract: TrackerContract,
    *,
    approval_policy_enabled: bool,
    dispatch_state: _DispatchState | None = None,
) -> CandidateIssue | None:
    if dispatch_state is None:
        raise SchedulerError("dispatch_state is required")
    async with dispatch_state.in_flight_lock:
        held_locks = (
            set().union(*dispatch_state.in_flight_locks.values())
            if dispatch_state.in_flight_locks
            else set()
        )
        available = [
            candidate
            for candidate in candidates
            if candidate.id not in dispatch_state.in_flight_ids
            and set(candidate.locks).isdisjoint(held_locks)
        ]
        selected = oldest_candidate(
            available,
            contract,
            approval_policy_enabled=approval_policy_enabled,
        )
        if selected is not None:
            dispatch_state.in_flight_ids.add(selected.id)
            dispatch_state.in_flight_locks[selected.id] = frozenset(selected.locks)
        return selected


async def _reserve_specific_candidate(
    candidate: CandidateIssue,
    *,
    dispatch_state: _DispatchState | None = None,
) -> bool:
    if dispatch_state is None:
        raise SchedulerError("dispatch_state is required")
    async with dispatch_state.in_flight_lock:
        held_locks = (
            set().union(*dispatch_state.in_flight_locks.values())
            if dispatch_state.in_flight_locks
            else set()
        )
        if candidate.id in dispatch_state.in_flight_ids:
            return False
        if not set(candidate.locks).isdisjoint(held_locks):
            return False
        dispatch_state.in_flight_ids.add(candidate.id)
        dispatch_state.in_flight_locks[candidate.id] = frozenset(candidate.locks)
        return True


async def _release_candidate(
    issue_id: str,
    *,
    dispatch_state: _DispatchState | None = None,
) -> None:
    if dispatch_state is None:
        raise SchedulerError("dispatch_state is required")
    async with dispatch_state.in_flight_lock:
        dispatch_state.in_flight_ids.discard(issue_id)
        dispatch_state.in_flight_locks.pop(issue_id, None)
