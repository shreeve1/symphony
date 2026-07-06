"""Scheduler schedule concern — schedule event detection, release, and repair.

Naming disambiguation: ``import schedule`` / ``from schedule import ...`` always
refers to the **top-level** ``schedule.py`` (ScheduleEvent, etc.).  Explicit
relative imports (``from .schedule import ...``) refer to *this* module.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from schedule import (  # top-level schedule.py — ScheduleEvent + parsing
    CandidateComment,
    ScheduleEvent,
    ScheduleEventType,
    ScheduleParseError,
    latest_event,
    next_maintenance_window,
)
from tracker_contract import TrackerRole
from tracker_types import (
    CandidateIssue,
    CommentPayload,
    _candidate_from_issue,
    _extract_labels,
    _is_state,
)

from .markers import _parse_summary_marker
from .ports import fetch_issue as _fetch_issue

if TYPE_CHECKING:
    from config import SymphonyConfig  # noqa: F811
    from notifier import TelegramNotifier  # noqa: F811
    from . import _ScheduledSelection  # noqa: F811
    from tracker_adapter import TrackerAdapter  # noqa: F811

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local helpers (only called from the 7 schedule functions below)
# ---------------------------------------------------------------------------


def _response_items(
    response: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return response
    results = response.get("results")
    if isinstance(results, list):
        return results
    return []


def _prefers_latest_control_line(adapter: TrackerAdapter) -> bool:
    return bool(getattr(adapter, "single_blob_comments", False)) or (
        adapter.__class__.__module__ == "tracker_podium"
        and adapter.__class__.__name__ == "PodiumTrackerAdapter"
    )


def _parse_optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


# ---------------------------------------------------------------------------
# 7 schedule helpers
# ---------------------------------------------------------------------------


async def _select_scheduled_candidate(
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime],
) -> _ScheduledSelection | None:
    label_ids = adapter.contract.label_ids if adapter.contract else None
    due: list[tuple[datetime, str, str, CandidateIssue, ScheduleEvent]] = []
    now_dt = now()

    from . import (
        SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
        SCHEDULED_RELEASE_PAGE_SIZE,
        _ScheduledSelection,
    )

    issues = await adapter.list_issues_by_state(
        TrackerRole.STATE_TODO,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    )
    for issue in issues:
        labels = _extract_labels(issue, label_ids=label_ids)
        if not adapter.labels_contain_role(labels, TrackerRole.SCHEDULED):
            continue
        candidate = _candidate_from_issue(issue, labels=labels)
        try:
            event = await _latest_schedule_event(adapter, candidate.id)
        except ScheduleParseError as exc:
            return _ScheduledSelection(candidate, "scheduled-malformed", error=str(exc))
        if event is None:
            event = _default_scheduled_label_event(now_dt)
        if event.is_cancellation:
            return _ScheduledSelection(candidate, "scheduled-cancelled", event=event)
        if event.not_before is None:
            return _ScheduledSelection(
                candidate, "scheduled-malformed", error="not_before missing"
            )
        if event.not_before > now_dt:
            continue
        due.append(
            (event.not_before, candidate.created_at, candidate.id, candidate, event)
        )
    if not due:
        return None
    _, _, _, candidate, event = sorted(due, key=lambda item: item[:3])[0]
    return _ScheduledSelection(candidate, "scheduled-release", event=event)


def _with_schedule_context(
    candidate: CandidateIssue,
    event: ScheduleEvent | None,
    *,
    now: datetime,
) -> CandidateIssue:
    from . import SCHEDULED_LABEL_DEFAULT_SOURCE

    if event is None or event.not_before is None:
        return candidate
    late = bool(event.not_after and now.astimezone(UTC) > event.not_after)
    source = (
        SCHEDULED_LABEL_DEFAULT_SOURCE
        if event.raw_comment == SCHEDULED_LABEL_DEFAULT_SOURCE
        else "Symphony-Schedule comment"
    )
    return replace(
        candidate,
        schedule_not_before=event.not_before.isoformat(),
        schedule_not_after=event.not_after.isoformat() if event.not_after else "",
        schedule_reason=event.reason,
        schedule_source=source,
        schedule_late="true" if late else "false",
    )


def _default_scheduled_label_event(now_dt: datetime) -> ScheduleEvent:
    from . import SCHEDULED_LABEL_DEFAULT_REASON, SCHEDULED_LABEL_DEFAULT_SOURCE

    window_start, window_end = next_maintenance_window(now_dt)
    return ScheduleEvent(
        ScheduleEventType.SCHEDULE,
        SCHEDULED_LABEL_DEFAULT_REASON,
        not_before=window_start,
        not_after=window_end,
        raw_comment=SCHEDULED_LABEL_DEFAULT_SOURCE,
    )


async def _latest_schedule_event(
    adapter: TrackerAdapter, issue_id: str
) -> ScheduleEvent | None:
    comments: list[CandidateComment] = []
    for idx, comment in enumerate(await adapter.list_comments(issue_id)):
        created = _parse_optional_datetime(comment.get("created_at"))
        comments.append(
            CandidateComment(
                comment.get("body") or comment.get("comment_html") or "",
                comment_id=str(comment.get("id") or ""),
                created_at=created,
                api_order=idx,
            )
        )
    return latest_event(comments, prefer_last=_prefers_latest_control_line(adapter))


async def _release_scheduled_candidate(
    adapter: TrackerAdapter,
    issue_id: str,
    event: ScheduleEvent | None,
) -> ScheduleEvent:
    from . import SCHEDULED_LABEL_DEFAULT_SOURCE, SchedulerError

    if event is None or event.not_before is None:
        raise SchedulerError("scheduled release missing event")
    latest = await _latest_schedule_event(adapter, issue_id)
    if latest is None and event.raw_comment == SCHEDULED_LABEL_DEFAULT_SOURCE:
        latest = event
    if latest is None:
        raise SchedulerError("latest schedule event disappeared before release")
    if latest.is_cancellation:
        raise SchedulerError("schedule was cancelled before release")
    if latest.not_before is None:
        raise SchedulerError("latest schedule event missing not_before")
    if (
        latest.not_before != event.not_before
        or latest.not_after != event.not_after
        or latest.reason != event.reason
    ):
        raise SchedulerError("schedule changed before release")
    await adapter.add_comment(
        issue_id,
        CommentPayload(
            body=(
                "Symphony scheduled release: not_before="
                f"{latest.not_before.isoformat()} reason={latest.reason}"
            )
        ),
    )
    await adapter.remove_labels(issue_id, [TrackerRole.SCHEDULED])
    return latest


async def _repair_cancelled_schedule(
    adapter: TrackerAdapter,
    issue_id: str,
    event: ScheduleEvent | None,
) -> None:
    reason = event.reason if event is not None else "unknown"
    await adapter.add_comment(
        issue_id,
        CommentPayload(
            body=f"Symphony schedule cancellation repaired stale scheduled label: {reason}"
        ),
    )
    await adapter.remove_labels(issue_id, [TrackerRole.SCHEDULED])


async def _detect_agent_schedule(
    adapter: TrackerAdapter,
    candidate: CandidateIssue,
    *,
    claim_dt: datetime,
    stdout: str,
    stderr: str,
    notifier: TelegramNotifier | None,
    config: SymphonyConfig | None = None,
) -> str | None:
    after_agent = await _fetch_issue(adapter, candidate.id)
    label_ids = adapter.contract.label_ids if adapter.contract else None
    labels = _extract_labels(after_agent, label_ids=label_ids)
    if not _is_state(
        after_agent,
        adapter.contract.state_name_for_role(TrackerRole.STATE_TODO),
        adapter.contract.state_value_for_role(TrackerRole.STATE_TODO),
    ):
        return None
    if not adapter.labels_contain_role(labels, TrackerRole.SCHEDULED):
        return None
    try:
        event = await _latest_schedule_event(adapter, candidate.id)
    except ScheduleParseError as exc:
        from . import _block_issue, _build_urls

        _iu, _du = _build_urls(config, candidate.id)
        await _block_issue(
            adapter,
            candidate.id,
            f"Agent created a malformed schedule comment: {exc}",
            issue_name=candidate.name,
            issue_identifier=candidate.identifier,
            notifier=notifier,
            issue_url=_iu,
            dashboard_url=_du,
        )
        return "agent-scheduled-malformed"
    if event is None or not event.is_schedule or event.comment_created_at is None:
        return None
    if event.comment_created_at <= claim_dt.astimezone(UTC):
        return None
    schedule_summary = _parse_summary_marker(stdout, stderr)
    body = "Symphony scheduled follow-up."
    if schedule_summary:
        body += f" {schedule_summary}"
    await adapter.add_comment(candidate.id, CommentPayload(body=body))
    return "agent-scheduled"
