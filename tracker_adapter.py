"""Common tracker adapter protocol for Symphony engine integrations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from tracker_contract import TrackerContract, TrackerLabel, TrackerRole, TrackerState
from tracker_types import CandidateIssue, CommentPayload

PAGE_SIZE = 50
MAX_PAGES_PER_TICK = 3


@runtime_checkable
class TrackerAdapter(Protocol):
    """Issue-tracker operations the engine is allowed to use."""

    contract: TrackerContract

    def issue_labels(self, issue: dict[str, Any]) -> tuple[str, ...]: ...
    def issue_is_state(self, issue: dict[str, Any], state: TrackerRole) -> bool: ...
    def labels_contain_role(
        self, labels: tuple[str, ...] | list[str], role: TrackerRole
    ) -> bool: ...
    async def list_candidates(self) -> list[CandidateIssue]: ...
    async def list_issues(
        self,
        state_filter: TrackerState | TrackerRole | None = None,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]: ...
    async def list_issues_by_state(
        self,
        state: TrackerState | TrackerRole,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]: ...
    async def get_issue(self, issue_id: str) -> dict[str, Any]: ...
    async def list_comments(
        self, issue_id: str, *, max_pages: int = MAX_PAGES_PER_TICK
    ) -> list[dict[str, Any]]: ...
    async def add_comment(
        self, issue_id: str, comment: CommentPayload
    ) -> dict[str, Any]: ...
    async def post_comment(self, issue_id: str, body: str) -> dict[str, Any]: ...
    async def append_context(self, issue_id: str, body: str) -> dict[str, Any]: ...
    async def transition_state(
        self, issue_id: str, state: TrackerState | TrackerRole
    ) -> dict[str, Any]: ...
    async def add_label(
        self, issue_id: str, label: TrackerLabel | TrackerRole
    ) -> dict[str, Any]: ...
    async def remove_label(
        self, issue_id: str, label: TrackerLabel | TrackerRole
    ) -> dict[str, Any]: ...
    async def add_labels(
        self, issue_id: str, labels: list[TrackerLabel | TrackerRole]
    ) -> dict[str, Any]: ...
    async def remove_labels(
        self, issue_id: str, labels: list[TrackerLabel | TrackerRole]
    ) -> dict[str, Any]: ...
    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    async def record_run(self, run_row: dict[str, Any]) -> dict[str, Any]: ...
