"""Neutral tracker vocabulary types and shared parse helpers.

No ``web.*``, ``plane_adapter``, ``tracker_podium``, or in-scope module imports.
Everything here is pure data transformations with no side-effect module
scaffolding (no adapter construction, no transport initialisation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class CandidateIssue:
    id: str
    identifier: str
    name: str
    description: str
    labels: tuple[str, ...]
    created_at: str
    schedule_not_before: str = ""
    schedule_not_after: str = ""
    schedule_reason: str = ""
    schedule_source: str = ""
    schedule_late: str = ""
    comments_md: str = ""
    context_md: str = ""
    preferred_skill: str | None = None
    worktree_active: bool = False
    base_branch: str = ""
    binding_name: str = ""
    preferred_model: str | None = None
    reasoning_effort: str = "high"
    skill_source: str = ""
    resolved_provider: str = ""
    resolved_model: str = ""
    agent_session_id: str = ""
    # Binding-repo git short-sha at dispatch, not a session id; guards resume against code drift.
    agent_session_sha: str = ""
    resumed: bool = False
    active_run_id: str = ""
    locks: tuple[str, ...] = ()
    review_dispatch: bool = False
    origin: str = "operator"


@dataclass
class CommentPayload:
    body: str
    outcome: str = ""
    affected_service: str = ""
    dependency_chain: str = ""
    likely_cause: str = ""
    suggested_next_step: str = ""
    diagnostic_excerpt: str = ""

    def render(self) -> str:
        parts: list[str] = [self.body]
        if self.outcome:
            parts.append(f"\n**Outcome:** {self.outcome}")
        if self.affected_service:
            parts.append(f"\n**Affected service:** {self.affected_service}")
        if self.dependency_chain:
            parts.append(f"\n**Dependency chain:** {self.dependency_chain}")
        if self.likely_cause:
            parts.append(f"\n**Likely cause:** {self.likely_cause}")
        if self.suggested_next_step:
            parts.append(f"\n**Suggested next step:** {self.suggested_next_step}")
        if self.diagnostic_excerpt:
            parts.append(f"\n**Diagnostic:**\n```\n{self.diagnostic_excerpt}\n```")
        return "\n".join(parts)


@dataclass
class IssuePayload:
    external_id: str
    name: str
    description: str = ""
    # PlaneState.TODO value, kept literal to avoid importing tracker_contract here.
    state: Any = "Todo"  # PlaneState | TrackerRole, deferred to avoid import
    labels: list[Any] = field(default_factory=list)  # list[PlaneLabel | TrackerRole]
    priority: str | None = None


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _extract_labels(
    issue: dict[str, Any],
    label_ids: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """Extract label names from a raw issue dict.

    When ``label_ids`` is provided (a {name: uuid} mapping) the reverse map is
    used to resolve UUID values to their human-readable names.  Unknown UUIDs
    and already-present names pass through unchanged.
    """
    labels = issue.get("labels") or []
    uuid_to_name: dict[str, str] = {}
    if label_ids:
        uuid_to_name = {v: k for k, v in label_ids.items()}
    extracted: list[str] = []
    for label in labels:
        if isinstance(label, str):
            extracted.append(uuid_to_name.get(label, label))
        elif isinstance(label, dict):
            name = label.get("name") or label.get("value")
            if isinstance(name, str):
                extracted.append(name)
    return tuple(extracted)


def _parse_iso(value: object, *, force_utc: bool = False) -> datetime | None:
    """Parse an ISO 8601 string to :class:`datetime`, or *None* on failure.

    Parameters
    ----------
    value:
        The raw value to parse.  Strings, ``None``, and empty values are all
        handled gracefully.
    force_utc:
        When *True*, naive datetimes (no timezone offset) are treated as UTC
        and the result is normalized to UTC via ``astimezone``.  When *False*,
        the parsed datetime is returned as-is (possibly naive).

    Returns
    -------
    :class:`datetime | None`
        *None* when the value is empty, is not a valid ISO 8601 string, or
        cannot be parsed by ``datetime.fromisoformat``.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if force_utc:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return parsed


def _is_state(
    issue: dict[str, Any],
    state_name: str,
    state_value: str,
) -> bool:
    """Return *True* when an issue dict matches the given state.

    Parameters
    ----------
    issue:
        Raw issue dictionary from a tracker adapter.
    state_name:
        Human-readable state name (e.g. ``"Todo"``).
    state_value:
        State value / identifier (e.g. ``"todo"`` or a UUID).

    Callers resolve these from the tracker contract::

        _is_state(issue, contract.state_name_for_role(TrackerRole.STATE_TODO),
                         contract.state_value_for_role(TrackerRole.STATE_TODO))
    """
    current = issue.get("state")
    wanted = {state_name, state_value}
    if isinstance(current, str):
        return current in wanted
    if isinstance(current, dict):
        return current.get("name") == state_name or current.get("id") in wanted
    return False


def _candidate_from_issue(
    issue: dict[str, Any],
    *,
    labels: tuple[str, ...] | None = None,
    required_fields: tuple[str, ...] = (),
) -> CandidateIssue:
    """Build a :class:`CandidateIssue` from a raw tracker issue dict.

    Parameters
    ----------
    issue:
        Raw issue dictionary from a tracker adapter.
    labels:
        Pre-extracted label tuple.  When *None*, labels are extracted from the
        issue dict via :func:`_extract_labels` (without a label_ids mapping).
    required_fields:
        Field names that must be present and truthy.  Neutral scheduler callers
        can keep the forgiving default; stricter adapters can request validation
        and translate :class:`ValueError` to their tracker-specific schema error.
    """
    missing = [field for field in required_fields if not issue.get(field)]
    if missing:
        raise ValueError(f"tracker issue missing field: {missing[0]}")
    issue_id = str(issue.get("id", ""))
    return CandidateIssue(
        id=issue_id,
        identifier=str(issue.get("identifier") or issue.get("sequence_id") or issue_id),
        name=str(issue.get("name") or ""),
        description=str(
            issue.get("description") or issue.get("description_html") or ""
        ),
        labels=labels if labels is not None else _extract_labels(issue),
        created_at=str(issue.get("created_at") or ""),
        locks=tuple(str(lock) for lock in (issue.get("locks") or ())),
    )


def _page_items(
    response: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract the items list from a paginated Plane-style API response."""
    if isinstance(response, list):
        return response
    results = response.get("results")
    if isinstance(results, list):
        return results
    raise ValueError("Plane response missing results list")


def _next_cursor(
    response: dict[str, Any] | list[dict[str, Any]],
) -> str | None:
    """Extract the next-page cursor from a paginated Plane-style API response."""
    if not isinstance(response, dict):
        return None
    cursor = response.get("next_cursor")
    if cursor:
        return str(cursor)
    next_url = response.get("next")
    if isinstance(next_url, str) and "cursor=" in next_url:
        return next_url.split("cursor=", 1)[1].split("&", 1)[0]
    return None


__all__ = [
    "CandidateIssue",
    "CommentPayload",
    "IssuePayload",
    "_extract_labels",
    "_is_state",
    "_candidate_from_issue",
    "_page_items",
    "_next_cursor",
    "_parse_iso",
]
