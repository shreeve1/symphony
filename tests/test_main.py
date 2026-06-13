from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from agent_runner import AgentRunnerError
from plane_poller import CandidateIssue

import main


class StopLoop(Exception):
    pass


def test_render_candidate_prompt_maps_plane_issue(monkeypatch, tmp_path):
    captured = {}

    def fake_render(issue_data, *, path, binding_type="infra"):
        captured["issue"] = issue_data
        captured["path"] = path
        captured["binding_type"] = binding_type
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

    prompt = main._render_candidate_prompt(issue, repo_path=tmp_path)

    assert prompt == "rendered prompt"
    assert captured["issue"].id == "issue-1"
    assert captured["issue"].identifier == "AUTO-1"
    assert captured["issue"].name == "Check proxy"
    assert captured["issue"].description == "Verify proxy container"
    assert captured["issue"].labels == "media, maintenance"
    assert captured["issue"].mode == "conversation"
    assert captured["path"] == tmp_path / "WORKFLOW.md"
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
    monkeypatch.setattr(
        main.TelegramNotifier, "from_env", staticmethod(lambda: "notifier")
    )
    monkeypatch.setattr(main, "run_bindings_loop", fake_run_bindings_loop)

    asyncio.run(main.async_main())

    assert isinstance(calls["run_bindings_loop"][0], FakeConfig)
    assert calls["run_bindings_loop"][1] == "notifier"


@pytest.mark.asyncio
async def test_run_bindings_loop_continues_after_startup_reconcile_transient_failure(
    monkeypatch,
):
    calls = []
    closed = []

    class FakeTransport:
        async def aclose(self):
            closed.append("closed")

    class FakeConfig:
        bindings = ("one",)

    class FakeRuntimeConfig:
        homelab_repo_path = Path("/tmp/one")

        @property
        def bindings(self):
            return (type("Binding", (), {"binding_type": "infra"})(),)

    class FakeAdapter:
        contract = None

    def fake_build_runtime(config, binding):
        return main.BindingRuntime(
            name=binding,
            config=cast(Any, FakeRuntimeConfig()),
            transport=cast(Any, FakeTransport()),
            adapter=cast(Any, FakeAdapter()),
            agent_adapter=cast(Any, "agent"),
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        calls.append("reconcile")
        raise RuntimeError("temporary 429")

    async def fake_run_loop(
        config, adapter, *, agent_runner, render_prompt, notifier=None, binding=None
    ):
        calls.append("run-loop")
        raise StopLoop

    monkeypatch.setattr(main, "_build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(
            cast(Any, FakeConfig()), notifier=cast(Any, "notifier")
        )

    assert calls == ["reconcile", "run-loop"]
    assert closed == ["closed"]


@pytest.mark.asyncio
async def test_run_bindings_loop_reaps_claude_sockets_once_for_multiple_bindings(
    monkeypatch,
):
    calls = []

    class FakeConfig:
        bindings = ("one", "two")

    class FakeRuntimeConfig:
        homelab_repo_path = Path("/tmp/repo")

        @property
        def bindings(self):
            return (type("Binding", (), {"binding_type": "infra"})(),)

    class FakeAdapter:
        contract = None

    def fake_build_runtime(config, binding):
        return main.BindingRuntime(
            name=binding,
            config=cast(Any, FakeRuntimeConfig()),
            transport=None,
            adapter=cast(Any, FakeAdapter()),
            agent_adapter=cast(Any, f"agent-{binding}"),
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        calls.append(("reconcile-startup", binding))
        return 0

    async def fake_run_loop(
        config, adapter, *, agent_runner, render_prompt, notifier=None, binding=None
    ):
        calls.append(("run-loop", binding))
        raise StopLoop

    monkeypatch.setattr(
        main, "reap_orphan_claude_sockets", lambda: calls.append("reap")
    )
    monkeypatch.setattr(main, "verify_claude_support", lambda: calls.append("probe"))
    monkeypatch.setattr(main, "_build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert calls.count("reap") == 1
    assert calls.count("probe") == 1
    assert calls[:2] == ["reap", "probe"]


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
        run_cap = 2
        blocked_reconciler_enabled = True
        blocked_reconciler_apply = False
        blocked_reconciler_interval_ms = 1_800_000

    class FakeAdapter:
        contract = None

        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return other == f"adapter-{self.name}"

    class FakeRuntimeConfig:
        def __init__(self, name):
            self.name = name
            self.homelab_repo_path = Path(f"/tmp/{name}")

        def __eq__(self, other):
            return other == f"config-{self.name}"

        @property
        def bindings(self):
            return (type("Binding", (), {"binding_type": "infra"})(),)

    def fake_build_runtime(config, binding):
        return main.BindingRuntime(
            name=binding,
            config=cast(Any, FakeRuntimeConfig(binding)),
            transport=cast(Any, FakeTransport(binding)),
            adapter=cast(Any, FakeAdapter(binding)),
            agent_adapter=cast(Any, f"agent-{binding}"),
        )

    async def fake_run_loop(
        config,
        adapter,
        *,
        agent_runner,
        render_prompt,
        notifier=None,
        binding=None,
    ):
        """Simulate run_loop: one reconcile+tick cycle then raises StopLoop."""
        calls.append(("reconcile-tick", config, adapter, notifier))
        calls.append(("tick", config, adapter, agent_runner, notifier))
        raise StopLoop

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        calls.append(("reconcile-startup", config, adapter, notifier))
        return 0

    async def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop

    monkeypatch.setattr(main, "_build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(
            cast(Any, FakeConfig()), notifier=cast(Any, "notifier")
        )

    # Structure: startup reconcile for all bindings (sequential), then
    # concurrent run_loop tasks run in parallel (gather) — order of tick
    # entries is non-deterministic but all appear before StopLoop exits.
    reconcile_startups = [(c[0], c[1]) for c in calls if c[0] == "reconcile-startup"]
    tick_calls = [(c[0], c[1]) for c in calls if c[0] in ("reconcile-tick", "tick")]

    assert reconcile_startups == [
        ("reconcile-startup", "config-one"),
        ("reconcile-startup", "config-two"),
    ], f"Startup reconcile should run sequentially before dispatch: {calls}"
    assert len(tick_calls) == 4, (
        f"Expected 4 dispatch calls (reconcile+tick per binding): {calls}"
    )
    assert ("tick", "config-one") in tick_calls
    assert ("tick", "config-two") in tick_calls
    assert closed == ["one", "two"]


def test_homelab_podium_binding_builds_without_plane_transport(monkeypatch):
    calls = {}
    config = main.SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.test",
            "PLANE_API_KEY": "key",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "pi",
        }
    )
    binding = next(item for item in config.bindings if item.name == "homelab")

    class ExplodingTransport:
        def __init__(self, *args):
            calls["transport"] = args
            raise AssertionError(
                "homelab Podium binding must not create Plane transport"
            )

    monkeypatch.setattr(main, "HttpxPlaneTransport", ExplodingTransport)
    monkeypatch.setattr(
        main, "verify_pi_support", lambda *args: calls.setdefault("verify", args)
    )

    runtime = main._build_binding_runtime(config, binding)

    assert runtime.name == "homelab"
    assert runtime.transport is None
    assert runtime.binding is binding
    assert "verify" in calls
    assert "transport" not in calls


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
            "SYMPHONY_BINDINGS_PATH": "/nonexistent/symphony-bindings.yml",
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
    monkeypatch.setattr(
        main, "verify_pi_support", lambda *args: calls.setdefault("verify", args)
    )

    runtime = main._build_binding_runtime(config, binding)

    assert runtime.name == "default"
    assert "transport" in calls
    assert "verify" not in calls


def test_build_binding_runtime_verifier_failure_aborts_before_transport(
    monkeypatch, tmp_path
):
    calls = {}
    config = main.SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.test",
            "PLANE_API_KEY": "key",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PLANE_PROJECT_ID": "project",
            "HOMELAB_REPO_PATH": str(tmp_path),
            "PI_BIN": "pi",
            "SYMPHONY_BINDINGS_PATH": "/nonexistent/symphony-bindings.yml",
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


@pytest.mark.asyncio
async def test_rate_limited_binding_does_not_block_other_binding(monkeypatch):
    calls = []
    closed = []

    class FakeTransport:
        def __init__(self, name):
            self.name = name

        async def aclose(self):
            closed.append(self.name)

    class FakeConfig:
        bindings = ("limited", "healthy")

    class FakeRuntimeConfig:
        def __init__(self, name):
            self.name = name
            self.homelab_repo_path = Path(f"/tmp/{name}")

        @property
        def bindings(self):
            return (type("Binding", (), {"binding_type": "infra"})(),)

    class FakeAdapter:
        contract = None

    def fake_build_runtime(config, binding):
        return main.BindingRuntime(
            name=binding,
            config=cast(Any, FakeRuntimeConfig(binding)),
            transport=cast(Any, FakeTransport(binding)),
            adapter=cast(Any, FakeAdapter()),
            agent_adapter=cast(Any, f"agent-{binding}"),
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        return 0

    async def fake_run_loop(
        config, adapter, *, agent_runner, render_prompt, notifier=None, binding=None
    ):
        calls.append(config.name)
        if config.name == "healthy":
            raise StopLoop
        await asyncio.sleep(10)

    monkeypatch.setattr(main, "_build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert "limited" in calls
    assert "healthy" in calls
    assert closed == ["limited", "healthy"]
