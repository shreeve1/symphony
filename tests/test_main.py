from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from agent_runner import AgentRunnerError
from plane_poller import CandidateIssue

import main


class StopLoop(Exception):
    pass


def test_render_candidate_prompt_maps_plane_issue(monkeypatch):
    captured = {}

    def fake_render(issue_data):
        captured["issue"] = issue_data
        return "rendered prompt"

    monkeypatch.setattr(main, "render_prompt", fake_render)
    issue = CandidateIssue(
        id="issue-1",
        identifier="AUTO-1",
        name="Check proxy",
        description="Verify proxy container",
        labels=("media", "maintenance"),
        created_at="2026-05-04T00:00:00Z",
        schedule_not_before="2026-05-08T20:00:00+00:00",
        schedule_not_after="2026-05-08T22:00:00+00:00",
        schedule_reason="maintenance window",
        schedule_source="Symphony-Schedule comment",
        schedule_late="false",
    )

    prompt = main._render_candidate_prompt(issue)

    assert prompt == "rendered prompt"
    assert captured["issue"].id == "issue-1"
    assert captured["issue"].identifier == "AUTO-1"
    assert captured["issue"].name == "Check proxy"
    assert captured["issue"].description == "Verify proxy container"
    assert captured["issue"].labels == "media, maintenance"
    assert captured["issue"].schedule_not_before == "2026-05-08T20:00:00+00:00"
    assert captured["issue"].schedule_not_after == "2026-05-08T22:00:00+00:00"
    assert captured["issue"].schedule_reason == "maintenance window"
    assert captured["issue"].schedule_source == "Symphony-Schedule comment"
    assert captured["issue"].schedule_late == "false"


def test_async_main_passes_configured_bindings_loop(monkeypatch):
    calls = {}

    class FakeConfig:
        bindings = ("binding",)

        @classmethod
        def from_env(cls):
            return cls()

    async def fake_run_bindings_loop(config, *, notifier=None):
        calls["run_bindings_loop"] = (config, notifier)

    monkeypatch.setattr(main, "SymphonyConfig", FakeConfig)
    monkeypatch.setattr(main.TelegramNotifier, "from_env", staticmethod(lambda: "notifier"))
    monkeypatch.setattr(main, "run_bindings_loop", fake_run_bindings_loop)

    asyncio.run(main.async_main())

    assert isinstance(calls["run_bindings_loop"][0], FakeConfig)
    assert calls["run_bindings_loop"][1] == "notifier"


@pytest.mark.asyncio
async def test_run_bindings_loop_iterates_all_bindings(monkeypatch):
    calls = []
    closed = []

    class FakeTransport:
        def __init__(self, name):
            self.name = name

        async def aclose(self):
            closed.append(self.name)

    class FakeResult:
        dispatched = False
        reason = "no-candidates"
        issue_id = None

    class FakeConfig:
        bindings = ("one", "two")
        poll_interval_ms = 30000

    class FakeAdapter:
        contract = None

        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return other == f"adapter-{self.name}"

    def fake_build_runtime(config, binding):
        return main.BindingRuntime(
            name=binding,
            config=cast(Any, f"config-{binding}"),
            transport=cast(Any, FakeTransport(binding)),
            adapter=cast(Any, FakeAdapter(binding)),
            agent_adapter=cast(Any, f"agent-{binding}"),
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None):
        calls.append(("reconcile", config, adapter, notifier))
        return 0

    async def fake_run_tick(config, adapter, *, agent_runner, render_prompt, notifier=None):
        calls.append(("tick", config, adapter, agent_runner, notifier))
        return FakeResult()

    async def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop

    monkeypatch.setattr(main, "_build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_tick", fake_run_tick)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()), notifier=cast(Any, "notifier"))

    assert calls == [
        ("reconcile", "config-one", "adapter-one", "notifier"),
        ("reconcile", "config-two", "adapter-two", "notifier"),
        ("tick", "config-one", "adapter-one", "agent-one", "notifier"),
        ("tick", "config-two", "adapter-two", "agent-two", "notifier"),
        ("sleep", 30.0),
    ]
    assert closed == ["one", "two"]


def test_build_binding_runtime_allows_claude_default(monkeypatch, tmp_path):
    calls = {}
    config = main.SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.test",
            "PLANE_API_KEY": "key",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PLANE_PROJECT_ID": "project",
            "HOMELAB_REPO_PATH": str(tmp_path),
            "PI_BIN": "pi",
        }
    )
    binding = config.bindings[0]
    binding = type(binding)(
        name=binding.name,
        plane_project_id=binding.plane_project_id,
        repo_path=binding.repo_path,
        base_branch=binding.base_branch,
        tracker_contract=binding.tracker_contract,
        default_agent="claude",
        approval_policy=binding.approval_policy,
        landing_policy=binding.landing_policy,
    )

    class FakeTransport:
        def __init__(self, api_url, api_key):
            calls["transport"] = (api_url, api_key)

        async def aclose(self):
            pass

    monkeypatch.setattr(main, "HttpxPlaneTransport", FakeTransport)
    monkeypatch.setattr(main, "verify_pi_support", lambda *args: calls.setdefault("verify", args))

    runtime = main._build_binding_runtime(config, binding)

    assert runtime.name == "default"
    assert "transport" in calls
    assert "verify" not in calls


def test_build_binding_runtime_verifier_failure_aborts_before_transport(monkeypatch, tmp_path):
    calls = {}
    config = main.SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.test",
            "PLANE_API_KEY": "key",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PLANE_PROJECT_ID": "project",
            "HOMELAB_REPO_PATH": str(tmp_path),
            "PI_BIN": "pi",
        }
    )

    class FakeTransport:
        def __init__(self, api_url, api_key):
            calls["transport"] = (api_url, api_key)

    def fake_verify_pi_support(*args):
        calls["verify"] = args
        raise AgentRunnerError("bad pi")

    monkeypatch.setattr(main, "HttpxPlaneTransport", FakeTransport)
    monkeypatch.setattr(main, "verify_pi_support", fake_verify_pi_support)

    with pytest.raises(AgentRunnerError, match="bad pi"):
        main._build_binding_runtime(config, config.bindings[0])

    assert "verify" in calls
    assert "transport" not in calls
