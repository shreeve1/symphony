from __future__ import annotations

import fcntl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_runner import AgentResult
from config import SymphonyConfig
from plane_poller import CandidateIssue
from scheduler import reconcile_stale_running, run_tick

from homelab_router.plane_adapter import PlaneAdapter
from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneLabel, PlaneState


class FakeTransport:
    def __init__(self) -> None:
        self.issues: dict[str, dict[str, Any]] = {}
        self.comments: dict[str, list[dict[str, Any]]] = {}

    async def get(self, path: str) -> dict[str, Any]:
        if path.endswith("/comments"):
            issue_id = path.split("/issues/")[1].split("/comments")[0]
            return {"results": self.comments.get(issue_id, [])}
        if "/issues/" in path:
            issue_id = path.rsplit("/issues/", 1)[1].split("?", 1)[0]
            return self.issues[issue_id]
        return {"results": list(self.issues.values())}

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        issue_id = path.split("/issues/")[1].split("/comments")[0]
        self.comments.setdefault(issue_id, []).append(body)
        return {"id": f"comment-{len(self.comments[issue_id])}", **body}

    async def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        issue_id = path.rsplit("/issues/", 1)[1].split("?", 1)[0]
        self.issues[issue_id].update(body)
        return self.issues[issue_id]


def _config(tmp_path: Path) -> SymphonyConfig:
    return SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="fake-project-id",
        homelab_repo_path=tmp_path,
        opencode_bin="opencode",
        run_timeout_ms=1000,
    )


def _adapter(transport: FakeTransport) -> PlaneAdapter:
    return PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)


def _issue(issue_id: str, *, state: str = PlaneState.TODO.value, labels=()) -> dict[str, Any]:
    return {
        "id": issue_id,
        "name": f"Issue {issue_id}",
        "state": state,
        "labels": list(labels),
        "created_at": "2026-05-04T00:00:00+00:00",
    }


def _candidate(issue_id: str, *, labels=(), created_at="2026-05-04T00:00:00+00:00") -> CandidateIssue:
    return CandidateIssue(issue_id, issue_id, f"Issue {issue_id}", "", tuple(labels), created_at)


@pytest.mark.asyncio
async def test_run_tick_skips_when_lock_is_held(tmp_path: Path) -> None:
    lock_path = tmp_path / ".symphony.lock"
    with lock_path.open("w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = await run_tick(
            _config(tmp_path),
            _adapter(FakeTransport()),
            agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
            render_prompt=lambda issue: "prompt",
            lock_path=lock_path,
        )

    assert result.dispatched is False
    assert result.reason == "lock-held"


@pytest.mark.asyncio
async def test_run_tick_claims_oldest_issue_before_dispatch(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.issues["newer"] = _issue("newer")
    transport.issues["older"] = _issue("older")
    seen: list[str] = []

    result = await run_tick(
        _config(tmp_path),
        _adapter(transport),
        agent_runner=lambda issue, prompt: seen.append(issue.id) or AgentResult(0, 10, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock",
        poller=lambda adapter: [
            _candidate("newer", created_at="2026-05-04T02:00:00+00:00"),
            _candidate("older", created_at="2026-05-04T01:00:00+00:00"),
        ],
        repo_dirty=lambda path: False,
        now=lambda: datetime(2026, 5, 4, 2, 0, tzinfo=UTC),
    )

    assert result.reason == "agent-managed"
    assert seen == ["older"]
    assert transport.issues["older"]["state"] == DEFAULT_CONTRACT.state_ids[PlaneState.RUNNING.value]
    assert "Symphony claimed at 2026-05-04T02:00:00+00:00" in transport.comments["older"][0]["comment_html"]


@pytest.mark.asyncio
async def test_run_tick_dirty_after_clean_exit_moves_to_review(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.issues["issue-1"] = _issue("issue-1")
    dirty_checks = iter([False, True])

    result = await run_tick(
        _config(tmp_path),
        _adapter(transport),
        agent_runner=lambda issue, prompt: AgentResult(0, 10, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock",
        poller=lambda adapter: [_candidate("issue-1")],
        repo_dirty=lambda path: next(dirty_checks),
        diff_stat=lambda path: "docs/file.md | 2 ++",
    )

    assert result.reason == "review"
    assert transport.issues["issue-1"]["state"] == DEFAULT_CONTRACT.state_ids[PlaneState.IN_REVIEW.value]
    assert any("docs/file.md | 2 ++" in c["comment_html"] for c in transport.comments["issue-1"])


@pytest.mark.asyncio
async def test_run_tick_nonzero_and_timeout_move_to_blocked(tmp_path: Path) -> None:
    for result, reason in [(AgentResult(2, 10, False), "nonzero"), (AgentResult(-1, 20, True), "timeout")]:
        transport = FakeTransport()
        transport.issues["issue-1"] = _issue("issue-1")
        tick = await run_tick(
            _config(tmp_path),
            _adapter(transport),
            agent_runner=lambda issue, prompt, result=result: result,
            render_prompt=lambda issue: "prompt",
            lock_path=tmp_path / f"lock-{reason}",
            poller=lambda adapter: [_candidate("issue-1")],
            repo_dirty=lambda path: False,
        )

        assert tick.reason == reason
        assert transport.issues["issue-1"]["state"] == DEFAULT_CONTRACT.state_ids[PlaneState.BLOCKED.value]
        assert len(transport.comments["issue-1"]) == 2


@pytest.mark.asyncio
async def test_run_tick_skips_dirty_tree_and_approval_required(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.issues["issue-1"] = _issue("issue-1", labels=[PlaneLabel.APPROVAL_REQUIRED.value])

    dirty = await run_tick(
        _config(tmp_path),
        _adapter(transport),
        agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock-dirty",
        poller=lambda adapter: [_candidate("issue-1")],
        repo_dirty=lambda path: True,
    )
    approval = await run_tick(
        _config(tmp_path),
        _adapter(transport),
        agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock-approval",
        poller=lambda adapter: [_candidate("issue-1", labels=[PlaneLabel.APPROVAL_REQUIRED.value])],
        repo_dirty=lambda path: False,
    )

    assert dirty.reason == "dirty-worktree"
    assert approval.reason == "no-candidates"


@pytest.mark.asyncio
async def test_reconcile_stale_running_blocks_expired_claim(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.issues["issue-1"] = _issue("issue-1", state=PlaneState.RUNNING.value)
    transport.comments["issue-1"] = [
        {"comment_html": "Symphony claimed at 2026-05-04T01:00:00+00:00"}
    ]

    await reconcile_stale_running(
        _adapter(transport),
        1000,
        now=lambda: datetime(2026, 5, 4, 1, 1, 1, tzinfo=UTC),
    )

    assert transport.issues["issue-1"]["state"] == DEFAULT_CONTRACT.state_ids[PlaneState.BLOCKED.value]
    assert any("claim timed out" in c["comment_html"] for c in transport.comments["issue-1"])


@pytest.mark.asyncio
async def test_reconcile_uses_newest_claim_comment(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.issues["issue-1"] = _issue("issue-1", state=PlaneState.RUNNING.value)
    transport.comments["issue-1"] = [
        {"comment_html": "Symphony claimed at 2026-05-04T01:00:00+00:00"},
        {"comment_html": "Symphony claimed at 2026-05-04T01:02:00+00:00"},
    ]

    await reconcile_stale_running(
        _adapter(transport),
        90_000,
        now=lambda: datetime(2026, 5, 4, 1, 2, 30, tzinfo=UTC),
    )

    assert transport.issues["issue-1"]["state"] == PlaneState.RUNNING.value


@pytest.mark.asyncio
async def test_run_tick_refetch_race_skips_changed_state_and_fresh_approval(tmp_path: Path) -> None:
    changed = FakeTransport()
    changed.issues["issue-1"] = _issue("issue-1", state=PlaneState.BLOCKED.value)
    changed_result = await run_tick(
        _config(tmp_path),
        _adapter(changed),
        agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock-changed",
        poller=lambda adapter: [_candidate("issue-1")],
        repo_dirty=lambda path: False,
    )

    approval = FakeTransport()
    approval.issues["issue-2"] = _issue("issue-2", labels=[PlaneLabel.APPROVAL_REQUIRED.value])
    approval_result = await run_tick(
        _config(tmp_path),
        _adapter(approval),
        agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock-fresh-approval",
        poller=lambda adapter: [_candidate("issue-2")],
        repo_dirty=lambda path: False,
    )

    assert changed_result.reason == "state-changed"
    assert approval_result.reason == "approval-required"


@pytest.mark.asyncio
async def test_run_tick_continues_when_plane_polling_fails(tmp_path: Path) -> None:
    result = await run_tick(
        _config(tmp_path),
        _adapter(FakeTransport()),
        agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
        render_prompt=lambda issue: "prompt",
        lock_path=tmp_path / "lock",
        poller=lambda adapter: (_ for _ in ()).throw(ConnectionError("offline")),
        repo_dirty=lambda path: False,
    )

    assert result.dispatched is False
    assert result.reason == "plane-unreachable"
