"""Tests for the Blocked-section reconciler.

These tests cover the rule engine, the dry-run safety contract, and the
pagination cap. They use ``InMemoryTransport`` exclusively — no live Plane
calls — and exercise the same code path the scheduler wires into ``run_tick``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any  # noqa: F401  (used by transport subclasses below)

import pytest

from blocked_reconciler import (
    DEFAULT_RULES,
    MAX_BLOCKED_PAGES_PER_TICK,
    ReconcileRule,
    reconcile_blocked,
)
from homelab_router.plane_adapter import InMemoryTransport, PlaneAdapter
from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneState


def _blocked_issue(
    issue_id: str,
    *,
    external_id: str = "homelab-patrol-test",
    name: str = "qbittorrent-ct108: SSH probe failed",
    labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "sequence_id": 110,
        "name": name,
        "external_id": external_id,
        "state": PlaneState.BLOCKED.value,
        "labels": labels or [],
        "created_at": "2026-05-17T00:00:00Z",
    }


def _comment(body: str, *, when: datetime) -> dict[str, Any]:
    return {
        "comment_html": f"<p>{body}</p>",
        "comment_stripped": body,
        "created_at": when.isoformat().replace("+00:00", "Z"),
    }


def _patrol_pass(target: str, consecutive: int, when: datetime) -> dict[str, Any]:
    return _comment(
        f"Patrol pass for {target}: no LXC update scheduling needed\n\n"
        f"**Outcome:** pass (consecutive_passes={consecutive})\n\n"
        f"**Affected service:** infra",
        when=when,
    )


def _patrol_fail(target: str, when: datetime) -> dict[str, Any]:
    return _comment(
        f"{target}: SSH probe failed\nEXIT(2): bash syntax error",
        when=when,
    )


def _make_adapter(
    issue: dict[str, Any], comments: list[dict[str, Any]]
) -> tuple[PlaneAdapter, InMemoryTransport]:
    transport = InMemoryTransport()
    transport.issues[issue["id"]] = issue
    transport.comments[issue["id"]] = comments
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)
    return adapter, transport


@pytest.mark.asyncio
async def test_patrol_rule_fires_against_realistic_auto110_evidence():
    """The AUTO-110 evidence shape: every pass comment carries consecutive_passes=1,
    because the patrol worker upserts a fresh ticket per cycle. The default rule
    must still fire on this real-world shape after observing 2 distinct passes
    newer than the original failure."""
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    fail = _patrol_fail("qbittorrent-ct108", now - timedelta(days=2))
    pass1 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=24))
    pass2 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        [fail, pass1, pass2],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.applied is True
    assert decision.rule is not None and decision.rule.name == "patrol-passes"
    assert decision.target_state == PlaneState.DONE
    assert transport.issues["issue-110"]["state"] == adapter._resolve_state(PlaneState.DONE)
    posted = transport.comments["issue-110"]
    assert posted[-1]["comment_html"].count("blocked-reconciler") == 1


@pytest.mark.asyncio
async def test_dry_run_logs_decision_but_does_not_mutate_plane():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass1 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12))
    pass2 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=1))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        [pass1, pass2],
    )
    before_state = transport.issues["issue-110"]["state"]
    before_comments = len(transport.comments["issue-110"])

    decisions = await reconcile_blocked(adapter, apply=False)

    assert len(decisions) == 1
    assert decisions[0].applied is False
    assert decisions[0].target_state == PlaneState.DONE
    assert transport.issues["issue-110"]["state"] == before_state
    assert len(transport.comments["issue-110"]) == before_comments


@pytest.mark.asyncio
async def test_failure_newer_than_passes_blocks_resolution():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass1 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12))
    pass2 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=2))
    fail = _patrol_fail("qbittorrent-ct108", now - timedelta(minutes=30))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        [pass1, pass2, fail],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert len(decisions) == 1
    assert decisions[0].applied is False
    assert decisions[0].reason == "no-pass-since-fail"
    assert transport.issues["issue-110"]["state"] == PlaneState.BLOCKED.value


@pytest.mark.asyncio
async def test_single_pass_below_threshold():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass1 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        [pass1],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert decisions[0].applied is False
    assert "pass-comments-below-threshold" in decisions[0].reason
    assert transport.issues["issue-110"]["state"] == PlaneState.BLOCKED.value


@pytest.mark.asyncio
async def test_pass_comment_quoting_prior_failure_does_not_double_count():
    """C2 dev-review fix: a pass comment whose body happens to include the
    failure substring (e.g. because Plane includes the issue title
    'qbittorrent-ct108: SSH probe failed' in the comment context) must NOT
    be classified as both a pass and a fail. If it were, this test would
    record a phantom fail newer than the pass and refuse to resolve."""
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass_with_quoted_fail_body = _comment(
        "Patrol pass for qbittorrent-ct108: no LXC update scheduling needed\n\n"
        "**Outcome:** pass (consecutive_passes=1)\n\n"
        "Note: previously reported as 'qbittorrent-ct108: SSH probe failed'",
        when=now - timedelta(hours=1),
    )
    pass_clean = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        [pass_clean, pass_with_quoted_fail_body],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert decisions[0].applied is True
    assert decisions[0].reason == "pass"
    assert transport.issues["issue-110"]["state"] == adapter._resolve_state(
        PlaneState.DONE
    )


@pytest.mark.asyncio
async def test_no_matching_rule_for_non_patrol_external_id():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass1 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=1))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-200", external_id="manual-ops-2026-05-18"),
        [pass1],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert len(decisions) == 1
    assert decisions[0].rule is None
    assert decisions[0].reason == "no-matching-rule"
    assert transport.issues["issue-200"]["state"] == PlaneState.BLOCKED.value


@pytest.mark.asyncio
async def test_approval_required_label_short_circuits_rule_evaluation():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass1 = _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=1))
    approval_uuid = DEFAULT_CONTRACT.label_ids["approval-required"]
    adapter, transport = _make_adapter(
        _blocked_issue(
            "issue-110",
            external_id="homelab-patrol-infra-ced58b20",
            labels=[approval_uuid],
        ),
        [pass1],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert decisions[0].reason == "approval-required-label"
    assert decisions[0].applied is False
    assert transport.issues["issue-110"]["state"] == PlaneState.BLOCKED.value


@pytest.mark.asyncio
async def test_no_patrol_pass_comment_skips_issue():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    only_fail = _patrol_fail("qbittorrent-ct108", now - timedelta(hours=1))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        [only_fail],
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert decisions[0].reason == "no-pass-since-fail"
    assert decisions[0].applied is False


@pytest.mark.asyncio
async def test_default_rules_contain_only_patrol_rule():
    # Guards against accidentally shipping a broader fallback rule. Adding a
    # new default rule requires updating this test deliberately.
    assert [r.name for r in DEFAULT_RULES] == ["patrol-passes"]
    rule = DEFAULT_RULES[0]
    assert rule.target_state == PlaneState.DONE
    assert rule.external_id_prefix == "homelab-patrol-"
    assert rule.min_pass_comments_since_fail >= 2


@pytest.mark.asyncio
async def test_custom_rule_targets_in_review_state():
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    pass1 = _patrol_pass("foo", 1, now - timedelta(hours=1))
    adapter, transport = _make_adapter(
        _blocked_issue("issue-1", external_id="custom-prefix-abc"),
        [pass1],
    )
    custom_rule = ReconcileRule(
        name="custom-review",
        external_id_prefix="custom-prefix-",
        target_state=PlaneState.IN_REVIEW,
        min_pass_comments_since_fail=1,
    )

    decisions = await reconcile_blocked(adapter, apply=True, rules=(custom_rule,))

    assert decisions[0].applied is True
    assert decisions[0].target_state == PlaneState.IN_REVIEW
    assert transport.issues["issue-1"]["state"] == adapter._resolve_state(
        PlaneState.IN_REVIEW
    )


@pytest.mark.asyncio
async def test_no_blocked_issues_returns_empty():
    transport = InMemoryTransport()
    transport.issues["todo-1"] = {
        "id": "todo-1",
        "name": "irrelevant",
        "external_id": "",
        "state": PlaneState.TODO.value,
        "labels": [],
    }
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    decisions = await reconcile_blocked(adapter, apply=True)

    assert decisions == []


def test_max_pages_per_tick_is_bounded():
    # Cheap structural assertion to catch a future change that would let the
    # reconciler iterate unboundedly through a giant Blocked column.
    assert MAX_BLOCKED_PAGES_PER_TICK <= 5


# ---- W5 / W6 / N13 / N14 dev-review tests ----------------------------------


class _FailingTransitionTransport(InMemoryTransport):
    """Transport that raises on `transition_state` PATCH but allows reads/comments."""

    def __init__(self) -> None:
        super().__init__()
        self.transition_attempts = 0

    async def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if "state" in body:
            self.transition_attempts += 1
            raise RuntimeError("simulated Plane outage during state transition")
        return await super().patch(path, body)


@pytest.mark.asyncio
async def test_apply_failed_path_records_decision_without_orphan_comment():
    """W5 dev-review: when transition_state raises, no Plane comment is left
    behind. The C-equivalent of an orphan transition note saying 'Symphony
    moved this issue' on a ticket whose state did not move would actively
    mislead an operator; the dev-review fix swapped the order to transition
    first, then comment, so a failed transition cannot leave a phantom note."""
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    transport = _FailingTransitionTransport()
    issue = _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20")
    transport.issues[issue["id"]] = issue
    transport.comments[issue["id"]] = [
        _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12)),
        _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=1)),
    ]
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    decisions = await reconcile_blocked(adapter, apply=True)

    assert transport.transition_attempts == 1
    assert decisions[0].applied is False
    assert decisions[0].reason.startswith("apply-failed:")
    # Phantom-comment guard: the reconciler must NOT have posted its move
    # comment because the transition failed.
    posted_bodies = [
        c.get("comment_html", "") + c.get("body", "")
        for c in transport.comments[issue["id"]]
    ]
    assert not any("blocked-reconciler" in body for body in posted_bodies)
    # State unchanged (transition raised before applying):
    assert transport.issues[issue["id"]]["state"] == PlaneState.BLOCKED.value


class _MultiPageTransport(InMemoryTransport):
    """Transport that paginates issue list responses across two pages."""

    def __init__(self, page1: list[dict[str, Any]], page2: list[dict[str, Any]]) -> None:
        super().__init__()
        self._page1 = page1
        self._page2 = page2
        self.list_calls: list[str] = []

    async def get(self, path: str) -> dict[str, Any]:
        if "/issues/" in path and "/comments" not in path and "?" in path:
            self.list_calls.append(path)
            cursor = "page-2" if "cursor=page-2" in path else None
            if cursor == "page-2":
                return {"results": list(self._page2), "next_cursor": None}
            return {"results": list(self._page1), "next_cursor": "page-2"}
        return await super().get(path)


@pytest.mark.asyncio
async def test_multi_page_pagination_processes_every_issue_once():
    """W6 dev-review: cursor pagination crosses page boundaries and each issue
    is processed exactly once (no double-dispatch from the catch-all branch
    of InMemoryTransport)."""
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    issue_a = _blocked_issue("issue-A", external_id="homelab-patrol-infra-a")
    issue_b = _blocked_issue("issue-B", external_id="homelab-patrol-infra-b")
    transport = _MultiPageTransport(page1=[issue_a], page2=[issue_b])
    transport.issues[issue_a["id"]] = issue_a
    transport.issues[issue_b["id"]] = issue_b
    for iid in (issue_a["id"], issue_b["id"]):
        transport.comments[iid] = [
            _patrol_pass("foo", 1, now - timedelta(hours=12)),
            _patrol_pass("foo", 1, now - timedelta(hours=1)),
        ]
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    decisions = await reconcile_blocked(adapter, apply=True)

    seen_ids = sorted(d.issue_id for d in decisions)
    assert seen_ids == ["issue-A", "issue-B"]
    assert all(d.applied for d in decisions)
    # Two list calls: page 1 + page 2 (cursor follow-up).
    assert len(transport.list_calls) == 2
    assert "cursor=page-2" in transport.list_calls[1]


@pytest.mark.asyncio
async def test_state_field_as_dict_is_recognised_as_blocked():
    """N13 dev-review: some Plane endpoints return state as a dict
    {'id': '<uuid>', 'name': 'Blocked'} instead of a bare UUID string."""
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    transport = InMemoryTransport()
    blocked_uuid = DEFAULT_CONTRACT.state_ids["Blocked"]
    issue = _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20")
    issue["state"] = {"id": blocked_uuid, "name": "Blocked"}
    transport.issues[issue["id"]] = issue
    transport.comments[issue["id"]] = [
        _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=12)),
        _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=1)),
    ]
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    decisions = await reconcile_blocked(adapter, apply=True)

    assert len(decisions) == 1
    assert decisions[0].applied is True


@pytest.mark.asyncio
async def test_comments_returned_out_of_order_still_evaluated_by_timestamp():
    """N14 dev-review: timestamp comparison must win over API list order.
    A pass comment appearing first in the list but with a newer timestamp
    than a later 'fail' comment should still count as a post-fail pass."""
    now = datetime(2026, 5, 18, 15, 5, tzinfo=UTC)
    # Order in the list: newer pass first, then two older fails. Counting
    # by list-position would treat 'fail' as latest. Timestamp-based logic
    # must instead see passes newer than the latest fail.
    out_of_order_comments = [
        _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=1)),
        _patrol_pass("qbittorrent-ct108", 1, now - timedelta(hours=2)),
        _patrol_fail("qbittorrent-ct108", now - timedelta(days=2)),
        _patrol_fail("qbittorrent-ct108", now - timedelta(days=5)),
    ]
    adapter, transport = _make_adapter(
        _blocked_issue("issue-110", external_id="homelab-patrol-infra-ced58b20"),
        out_of_order_comments,
    )

    decisions = await reconcile_blocked(adapter, apply=True)

    assert decisions[0].applied is True
    assert decisions[0].reason == "pass"
    assert transport.issues["issue-110"]["state"] == adapter._resolve_state(
        PlaneState.DONE
    )
