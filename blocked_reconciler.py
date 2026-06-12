"""Reconcile stale Blocked Plane issues whose comment history shows they are cured.

Symphony's normal scheduler only operates on the Todo bucket. Patrol-style
issues that hit a transient failure (e.g. ``qbittorrent-ct108: SSH probe
failed``) get parked in Blocked, and the underlying patrol may post a
follow-up *pass* comment on the next cycle without anything ever moving the
issue out of Blocked. The result is a steadily-growing Blocked column full of
already-cured tickets — see AUTO-100/101/103/110 (Apr-May 2026).

This module sweeps the Blocked column each tick, inspects the comment trail
for each issue against a small, ordered set of rules, and (when ``apply`` is
true) transitions the issue to its target state and leaves a Plane comment
explaining why. When ``apply`` is false the scan logs ``blocked_reconcile_*``
events but never mutates Plane — that is the default until an operator opts
in via ``SYMPHONY_BLOCKED_RECONCILER_APPLY=true``.

Rules are intentionally narrow:

  * Patrol tickets (``external_id`` prefix ``homelab-patrol-``) auto-resolve
    to Done once enough distinct ``Patrol pass for`` comments are newer than
    any failure comment. The embedded ``consecutive_passes=N`` value is logged
    only; it does not gate the decision.
  * A more conservative fallback rule moves tickets with a recent Symphony
    completion marker to In Review for human review. It is gated by an
    explicit external_id allowlist on the rule, empty by default.

The reconciler never touches Blocked issues that lack a matching rule, lack
the required marker, or carry the ``approval-required`` label.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Sequence

from plane_adapter import CommentPayload, TrackerAdapter
from tracker_contract import PlaneState, TrackerRole


LOGGER = logging.getLogger(__name__)

# Conservative pagination cap to match `plane_poller.MAX_PAGES_PER_TICK`. A
# growing Blocked column is itself a signal worth surfacing in logs, not
# something to silently chew through.
BLOCKED_PAGE_SIZE = 50
MAX_BLOCKED_PAGES_PER_TICK = 3
MAX_COMMENT_PAGES_PER_ISSUE = 3

# Comment markers emitted by the homelab patrol workers. These are matched
# against the *body* of comments fetched from Plane via the adapter; both
# `comment_html` and `comment_stripped` are checked so the reconciler is
# resilient to whichever form the adapter returns.
_PATROL_PASS_RE = re.compile(
    r"Patrol pass for\s+(?P<target>[^\s:]+)[^\n]*", re.IGNORECASE
)
_PATROL_FAIL_RE = re.compile(
    r"Patrol fail for\s+(?P<target>[^\s:]+)|SSH probe failed|probe failed",
    re.IGNORECASE,
)
_CONSECUTIVE_PASSES_RE = re.compile(
    r"consecutive_passes\s*=\s*(?P<n>\d+)", re.IGNORECASE
)
# Symphony itself emits this when an agent finishes cleanly. We use it as a
# weaker signal: it proves a Symphony run touched the ticket post-block, but
# not that the underlying check passed.
_SYMPHONY_COMPLETED_RE = re.compile(r"Symphony completed:", re.IGNORECASE)


@dataclass(frozen=True)
class ReconcileRule:
    """One ordered rule for moving an issue out of Blocked.

    Fields:
        name: short identifier used in logs and reconciler comments.
        external_id_prefix: only match issues whose ``external_id`` starts
            with this string. Empty string matches everything (use sparingly).
        target_state: which Plane state to move the issue to when the rule
            fires.
        min_pass_comments_since_fail: require at least this many *distinct*
            patrol-pass comments to be present in the comment trail since
            the most recent failure (or since ticket creation, if there is
            no failure comment). ``1`` means "any pass since the last fail
            is enough"; the patrol-passes rule defaults to ``2`` so a one-
            off transient pass does not auto-resolve a ticket. Counting
            distinct comments rather than the embedded ``consecutive_passes``
            counter is deliberate — the homelab patrol worker upserts a
            fresh ticket per cycle, which resets that counter to 1 on every
            run; real AUTO-110 evidence shows every pass comment carries
            ``consecutive_passes=1``.
        require_symphony_completion: when true, require a
            ``Symphony completed:`` comment newer than the most recent
            failure. Used by future rules that want to demand an agent
            actually ran before auto-resolving.
        comment_template: optional override for the reconciler's Plane
            comment. ``{target_state}`` and ``{rule}`` are interpolated.
    """

    name: str
    external_id_prefix: str
    target_state: PlaneState | TrackerRole
    min_pass_comments_since_fail: int = 1
    require_symphony_completion: bool = False
    comment_template: str = (
        "Symphony blocked-reconciler moved this issue to {target_state} via rule "
        "`{rule}`: latest patrol comment shows the underlying check now passes."
    )


# Ordered: first match wins. Adding a rule = adding a new entry here. The
# default deployment ships with only the patrol rule active. The fallback
# `symphony-completed-review` rule is intentionally left with an empty
# `external_id_prefix` for the comment template but a non-matching prefix so
# it cannot fire by accident; an operator who wants it must edit this file or
# replace `DEFAULT_RULES` from the call site.
DEFAULT_RULES: tuple[ReconcileRule, ...] = (
    ReconcileRule(
        name="patrol-passes",
        external_id_prefix="homelab-patrol-",
        target_state=PlaneState.DONE,
        min_pass_comments_since_fail=2,
        require_symphony_completion=False,
    ),
)


@dataclass(frozen=True)
class _CommentRecord:
    body: str
    created_at: datetime | None


@dataclass(frozen=True)
class ReconcileDecision:
    """Result of evaluating one Blocked issue against the rule list."""

    issue_id: str
    identifier: str
    name: str
    external_id: str
    rule: ReconcileRule | None
    target_state: PlaneState | TrackerRole | None
    reason: str
    applied: bool = False


def _target_state_name(adapter: TrackerAdapter, state: PlaneState | TrackerRole) -> str:
    if isinstance(state, TrackerRole):
        return adapter.contract.state_name_for_role(state)
    return state.value


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _comment_body(comment: dict[str, Any]) -> str:
    # The Plane adapter normalises to comment_html, but live API responses
    # also expose comment_stripped. We concatenate so a marker present in
    # either form is matched.
    parts: list[str] = []
    for key in ("comment_stripped", "comment_html", "body"):
        value = comment.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    return "\n".join(parts)


def _extract_labels(issue: dict[str, Any], label_ids: dict[str, str] | None) -> tuple[str, ...]:
    labels = issue.get("labels") or []
    uuid_to_name: dict[str, str] = {}
    if label_ids:
        uuid_to_name = {v: k for k, v in label_ids.items()}
    extracted: list[str] = []
    for label in labels:
        if isinstance(label, str):
            extracted.append(uuid_to_name.get(label, label))
        elif isinstance(label, dict):
            value = label.get("name") or label.get("value")
            if isinstance(value, str):
                extracted.append(value)
    return tuple(extracted)


def _is_blocked(issue: dict[str, Any], adapter: TrackerAdapter) -> bool:
    state = issue.get("state")
    blocked_name = adapter.contract.state_name_for_role(TrackerRole.STATE_BLOCKED)
    blocked_values = {blocked_name, adapter.contract.state_value_for_role(TrackerRole.STATE_BLOCKED)}
    if isinstance(state, str):
        return state in blocked_values
    if isinstance(state, dict):
        return state.get("name") == blocked_name or state.get("id") in blocked_values
    return False


def _select_rule(external_id: str, rules: Sequence[ReconcileRule]) -> ReconcileRule | None:
    for rule in rules:
        if external_id.startswith(rule.external_id_prefix):
            return rule
    return None


def _classify_comment(body: str) -> str:
    """Classify a comment body as ``pass``, ``fail``, ``completion``, or ``other``.

    Classes are mutually exclusive — that is the C2 fix from the dev-review:
    a single comment whose body happens to contain a quoted failure string
    (e.g. a work-summary comment that references the original error, or a
    pass comment whose ``comment_stripped`` includes the issue title
    ``qbittorrent-ct108: SSH probe failed``) must NOT be double-counted as
    both a pass and a fail. Pass-pattern wins over fail-pattern wins over
    completion-pattern.
    """

    if _PATROL_PASS_RE.search(body):
        return "pass"
    if _PATROL_FAIL_RE.search(body):
        return "fail"
    if _SYMPHONY_COMPLETED_RE.search(body):
        return "completion"
    return "other"


def _evaluate_rule(
    rule: ReconcileRule, comments: list[_CommentRecord]
) -> tuple[bool, str]:
    """Return (fires, reason). ``reason`` is logged regardless of outcome.

    The fire decision is built from three observations about the comment
    trail:

    1. Find the timestamp of the most recent ``fail`` comment, or ``None``
       if the trail has never seen a failure.
    2. Count the distinct ``pass`` comments strictly newer than that
       timestamp.
    3. Optionally locate the most recent ``completion`` comment newer than
       the latest fail (for rules that require an agent to have run).

    The patrol worker upserts a fresh ticket per cycle, which resets the
    embedded ``consecutive_passes`` counter to 1 every time — so we deliberately
    count comments, not the embedded number. The number is still parsed and
    logged for diagnostics but never gates the decision.
    """

    classified: list[tuple[_CommentRecord, str]] = [
        (record, _classify_comment(record.body)) for record in comments
    ]

    latest_fail: _CommentRecord | None = None
    for record, klass in classified:
        if klass != "fail":
            continue
        if latest_fail is None or (
            record.created_at is not None
            and latest_fail.created_at is not None
            and record.created_at > latest_fail.created_at
        ):
            latest_fail = record

    def _is_after_fail(record: _CommentRecord) -> bool:
        if latest_fail is None:
            return True
        if record.created_at is None or latest_fail.created_at is None:
            return False
        return record.created_at > latest_fail.created_at

    pass_records_since_fail = [
        record for record, klass in classified
        if klass == "pass" and _is_after_fail(record)
    ]

    if not pass_records_since_fail:
        # The trail either has no pass comment at all, or the latest fail is
        # newer than every pass. Both surface as the same operator signal:
        # the check has not produced a clean run since the failure.
        return False, "no-pass-since-fail"

    if rule.min_pass_comments_since_fail > 0 and (
        len(pass_records_since_fail) < rule.min_pass_comments_since_fail
    ):
        return (
            False,
            f"pass-comments-below-threshold "
            f"({len(pass_records_since_fail)}<{rule.min_pass_comments_since_fail})",
        )

    if rule.require_symphony_completion:
        completion_after_fail = [
            record for record, klass in classified
            if klass == "completion" and _is_after_fail(record)
        ]
        if not completion_after_fail:
            return False, "no-symphony-completion-since-fail"

    return True, "pass"


async def _fetch_blocked_issues(
    adapter: TrackerAdapter,
) -> list[dict[str, Any]]:
    return await adapter.list_issues_by_state(
        TrackerRole.STATE_BLOCKED,
        per_page=BLOCKED_PAGE_SIZE,
        max_pages=MAX_BLOCKED_PAGES_PER_TICK,
    )


async def _fetch_comments(adapter: TrackerAdapter, issue_id: str) -> list[_CommentRecord]:
    records: list[_CommentRecord] = []
    raw_comments = await adapter.list_comments(issue_id, max_pages=MAX_COMMENT_PAGES_PER_ISSUE)
    for idx, comment in enumerate(raw_comments):
        created = _parse_iso(comment.get("created_at"))
        # Fall back to insertion order for transports that don't track timestamps
        # (e.g. InMemoryTransport during tests). The Unix epoch + idx ordering
        # preserves comment order without polluting the "newer than failure"
        # comparison against real timestamps from live Plane.
        if created is None:
            created = datetime.fromtimestamp(float(idx), tz=UTC)
        records.append(_CommentRecord(body=_comment_body(comment), created_at=created))
    return records


async def reconcile_blocked(
    adapter: TrackerAdapter,
    *,
    apply: bool = False,
    rules: Sequence[ReconcileRule] = DEFAULT_RULES,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[ReconcileDecision]:
    """Scan the Blocked column and (optionally) move cured issues forward.

    Returns a list of ``ReconcileDecision`` records — one per Blocked issue
    inspected — so callers (tests, scheduler logging) can see exactly what
    fired and what was skipped. When ``apply`` is false no Plane writes
    happen; every decision records ``applied=False`` and the ``reason``
    field captures why.
    """

    decisions: list[ReconcileDecision] = []
    issues = await _fetch_blocked_issues(adapter)
    if not issues:
        LOGGER.info("blocked_reconcile_no_candidates apply=%s", str(apply).lower())
        return decisions

    label_ids = adapter.contract.label_ids if adapter.contract else None

    for issue in issues:
        issue_id = str(issue.get("id") or "")
        identifier = str(issue.get("sequence_id") or issue.get("identifier") or issue_id)
        name = str(issue.get("name") or "")
        external_id = str(issue.get("external_id") or "")

        labels = _extract_labels(issue, label_ids=label_ids)
        if adapter.labels_contain_role(labels, TrackerRole.APPROVAL_REQUIRED):
            decisions.append(
                ReconcileDecision(
                    issue_id, identifier, name, external_id,
                    rule=None, target_state=None,
                    reason="approval-required-label",
                )
            )
            LOGGER.info(
                "blocked_reconcile_skipped issue_id=%s identifier=%s reason=approval-required-label",
                issue_id, identifier,
            )
            continue

        rule = _select_rule(external_id, rules)
        if rule is None:
            decisions.append(
                ReconcileDecision(
                    issue_id, identifier, name, external_id,
                    rule=None, target_state=None,
                    reason="no-matching-rule",
                )
            )
            LOGGER.info(
                "blocked_reconcile_skipped issue_id=%s identifier=%s external_id=%s reason=no-matching-rule",
                issue_id, identifier, external_id,
            )
            continue

        try:
            comments = await _fetch_comments(adapter, issue_id)
        except Exception as exc:
            decisions.append(
                ReconcileDecision(
                    issue_id, identifier, name, external_id,
                    rule=rule, target_state=None,
                    reason=f"comment-fetch-failed: {exc}",
                )
            )
            LOGGER.warning(
                "blocked_reconcile_comment_fetch_failed issue_id=%s error=%s",
                issue_id, exc,
            )
            continue

        fires, reason = _evaluate_rule(rule, comments)
        if not fires:
            decisions.append(
                ReconcileDecision(
                    issue_id, identifier, name, external_id,
                    rule=rule, target_state=None,
                    reason=reason,
                )
            )
            LOGGER.info(
                "blocked_reconcile_skipped issue_id=%s identifier=%s rule=%s reason=%s",
                issue_id, identifier, rule.name, reason,
            )
            continue

        decision = ReconcileDecision(
            issue_id, identifier, name, external_id,
            rule=rule, target_state=rule.target_state,
            reason=reason,
            applied=False,
        )

        target_state_name = _target_state_name(adapter, rule.target_state)
        if not apply:
            LOGGER.info(
                "blocked_reconcile_would_apply issue_id=%s identifier=%s rule=%s target_state=%s",
                issue_id, identifier, rule.name, target_state_name,
            )
            decisions.append(decision)
            continue

        comment_body = rule.comment_template.format(
            target_state=target_state_name,
            rule=rule.name,
        )
        # W3 (dev-review): transition first, then comment. If the transition
        # fails we surface a clean ``apply-failed`` decision and never leave
        # an orphan "Symphony moved this issue" comment on a ticket whose
        # state never moved. If the *comment* later fails, the journalctl
        # ``blocked_reconcile_applied`` line is still the source of truth —
        # a missing comment is strictly less harmful than a comment that lies.
        try:
            await adapter.transition_state(issue_id, rule.target_state)
        except Exception as exc:
            LOGGER.warning(
                "blocked_reconcile_apply_failed issue_id=%s rule=%s error=%s",
                issue_id, rule.name, exc,
                exc_info=True,
            )
            decisions.append(
                ReconcileDecision(
                    issue_id, identifier, name, external_id,
                    rule=rule, target_state=rule.target_state,
                    reason=f"apply-failed: {exc}",
                    applied=False,
                )
            )
            continue

        try:
            await adapter.add_comment(issue_id, CommentPayload(body=comment_body))
        except Exception as exc:
            # Transition already succeeded — log loudly but mark applied=True
            # because the state change is the authoritative outcome.
            LOGGER.warning(
                "blocked_reconcile_comment_failed_after_transition issue_id=%s rule=%s error=%s",
                issue_id, rule.name, exc,
                exc_info=True,
            )

        LOGGER.info(
            "blocked_reconcile_applied issue_id=%s identifier=%s rule=%s target_state=%s",
            issue_id, identifier, rule.name, _target_state_name(adapter, rule.target_state),
        )
        decisions.append(
            ReconcileDecision(
                issue_id, identifier, name, external_id,
                rule=rule, target_state=rule.target_state,
                reason=reason,
                applied=True,
            )
        )

    return decisions


__all__ = [
    "BLOCKED_PAGE_SIZE",
    "DEFAULT_RULES",
    "MAX_BLOCKED_PAGES_PER_TICK",
    "ReconcileDecision",
    "ReconcileRule",
    "reconcile_blocked",
]
