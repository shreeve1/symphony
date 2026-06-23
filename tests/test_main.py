from __future__ import annotations

import asyncio
import fcntl
from pathlib import Path
from typing import Any, cast

import pytest

import main
from agent_runner import AgentRunnerError, RemoteAgentAdapter, RoutingAgentAdapter
from plane_poller import CandidateIssue


class StopLoop(Exception):
    pass


def test_render_candidate_prompt_maps_plane_issue(monkeypatch, tmp_path):
    captured = {}

    def fake_render(issue_data, *, path=None, binding_type="infra"):
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
    # ADR-0016: render_prompt no longer reads a WORKFLOW.md, so _render_candidate_prompt
    # passes no path (it renders the engine-owned INFRA_PREAMBLE constant instead).
    assert captured["path"] is None
    assert captured["issue"].schedule_not_before == "2026-05-08T20:00:00+00:00"
    assert captured["issue"].schedule_not_after == "2026-05-08T22:00:00+00:00"
    assert captured["issue"].schedule_reason == "maintenance window"
    assert captured["issue"].schedule_source == "Symphony-Schedule comment"
    assert captured["issue"].schedule_late == "false"


def test_async_main_disables_issue_telegram_notifications_by_default(monkeypatch):
    calls = {}

    class FakeConfig:
        bindings = ("binding",)
        issue_telegram_notifications_enabled = False

        @classmethod
        def from_env(cls):
            return cls()

    async def fake_run_bindings_loop(config, *, notifier=None):
        calls["run_bindings_loop"] = (config, notifier)

    def fail_from_env():
        raise AssertionError("Telegram notifier should not be loaded by default")

    monkeypatch.setattr(main, "SymphonyConfig", FakeConfig)
    monkeypatch.setattr(main.TelegramNotifier, "from_env", staticmethod(fail_from_env))
    monkeypatch.setattr(main, "run_bindings_loop", fake_run_bindings_loop)

    asyncio.run(main.async_main())

    assert isinstance(calls["run_bindings_loop"][0], FakeConfig)
    assert calls["run_bindings_loop"][1] is None


def test_async_main_passes_opted_in_issue_telegram_notifier(monkeypatch):
    calls = {}

    class FakeConfig:
        bindings = ("binding",)
        issue_telegram_notifications_enabled = True

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

    monkeypatch.setattr(main, "_probe_binding", lambda config, binding: None)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
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
        main,
        "reap_orphan_claude_sockets",
        lambda **kwargs: calls.append(("reap", kwargs["lock_confirmed"])),
    )
    monkeypatch.setattr(main, "verify_claude_support", lambda: calls.append("probe"))
    monkeypatch.setattr(main, "_probe_binding", lambda config, binding: None)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert calls.count(("reap", False)) == 1
    assert calls.count("probe") == 1
    assert calls[:2] == [("reap", False), "probe"]


@pytest.mark.asyncio
async def test_run_bindings_loop_passes_confirmed_lock_to_claude_reaper(
    monkeypatch, tmp_path
):
    calls = []

    class FakeConfig:
        bindings = ("one",)
        lock_path = tmp_path / "scheduler.lock"

    class FakeRuntimeConfig:
        homelab_repo_path = tmp_path

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
            agent_adapter=cast(Any, "agent"),
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        return 0

    async def fake_run_loop(
        config, adapter, *, agent_runner, render_prompt, notifier=None, binding=None
    ):
        raise StopLoop

    monkeypatch.setattr(
        main,
        "reap_orphan_claude_sockets",
        lambda **kwargs: calls.append(kwargs["lock_confirmed"]),
    )
    monkeypatch.setattr(main, "verify_claude_support", lambda: None)
    monkeypatch.setattr(main, "reap_orphan_rpc_processes", lambda: None)
    monkeypatch.setattr(main, "_probe_binding", lambda config, binding: None)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert calls == [True]


@pytest.mark.asyncio
async def test_run_bindings_loop_passes_unconfirmed_lock_when_lock_is_held(
    monkeypatch, tmp_path
):
    calls = []
    lock_path = tmp_path / "scheduler.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as locked:
        fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        FakeConfig = type(
            "FakeConfig", (), {"bindings": ("one",), "lock_path": lock_path}
        )

        class FakeRuntimeConfig:
            homelab_repo_path = tmp_path

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
                agent_adapter=cast(Any, "agent"),
            )

        async def fake_reconcile_startup(
            config, adapter, *, notifier=None, binding=None
        ):
            return 0

        async def fake_run_loop(
            config, adapter, *, agent_runner, render_prompt, notifier=None, binding=None
        ):
            raise StopLoop

        monkeypatch.setattr(
            main,
            "reap_orphan_claude_sockets",
            lambda **kwargs: calls.append(kwargs["lock_confirmed"]),
        )
        monkeypatch.setattr(main, "verify_claude_support", lambda: None)
        monkeypatch.setattr(main, "reap_orphan_rpc_processes", lambda: None)
        monkeypatch.setattr(main, "_probe_binding", lambda config, binding: None)
        monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
        monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
        monkeypatch.setattr(main, "run_loop", fake_run_loop)

        with pytest.raises(StopLoop):
            await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert calls == [False]


@pytest.mark.asyncio
async def test_run_bindings_loop_probes_before_runtime_construction(monkeypatch):
    calls = []

    class FakeConfig:
        bindings = ("one",)

    class FakeRuntimeConfig:
        homelab_repo_path = Path("/tmp/repo")

        @property
        def bindings(self):
            return (type("Binding", (), {"binding_type": "infra"})(),)

    class FakeAdapter:
        contract = None

    def fake_probe_binding(config, binding):
        calls.append(("probe", binding))

    def fake_build_runtime(config, binding):
        calls.append(("build", binding))
        return main.BindingRuntime(
            name=binding,
            config=cast(Any, FakeRuntimeConfig()),
            transport=None,
            adapter=cast(Any, FakeAdapter()),
            agent_adapter=cast(Any, "agent"),
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        calls.append(("reconcile", binding))
        return 0

    async def fake_run_loop(
        config, adapter, *, agent_runner, render_prompt, notifier=None, binding=None
    ):
        calls.append(("run-loop", binding))
        raise StopLoop

    monkeypatch.setattr(main, "_probe_binding", fake_probe_binding)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert calls[:2] == [("probe", "one"), ("build", "one")]


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

    monkeypatch.setattr(main, "_probe_binding", lambda config, binding: None)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
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

    runtime = main.build_binding_runtime(config, binding)

    assert runtime.name == "homelab"
    assert runtime.transport is None
    assert runtime.binding is binding
    assert "verify" not in calls
    assert "transport" not in calls

    main._probe_binding(config, binding)

    assert "verify" in calls
    assert "transport" not in calls


def test_build_binding_runtime_passes_claude_persist_to_adapter(monkeypatch, tmp_path):
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
        claude_persist=True,
        approval_policy=binding.approval_policy,
        landing_policy=binding.landing_policy,
    )

    class FakeTransport:
        def __init__(self, api_url, api_key):
            calls["transport"] = (api_url, api_key)

        async def aclose(self):
            pass

    monkeypatch.setattr(main, "HttpxPlaneTransport", FakeTransport)

    runtime = main.build_binding_runtime(config, binding)

    assert isinstance(runtime.agent_adapter, RoutingAgentAdapter)
    assert isinstance(runtime.agent_adapter.claude_adapter, main.ClaudeAgentAdapter)
    assert runtime.agent_adapter.claude_adapter.persist is True


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

    runtime = main.build_binding_runtime(config, binding)

    assert runtime.name == "default"
    assert "transport" in calls
    assert "verify" not in calls


def test_probe_binding_remote_skips_local_pi_probe(monkeypatch, tmp_path):
    # ADR-0012: a remote binding's repo_path lives on the remote host, so the
    # LOCAL verify_pi_support probe must be skipped (else it crashes startup with
    # PermissionError/FileNotFoundError on the unreadable path).
    from config import RemotePolicy

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
    base = config.bindings[0]
    binding = type(base)(
        name="n8n",
        plane_project_id="n8n",
        repo_path=base.repo_path,
        base_branch=base.base_branch,
        tracker_contract=base.tracker_contract,
        default_agent="pi",
        tracker="podium",
        approval_policy=base.approval_policy,
        landing_policy=base.landing_policy,
        remote=RemotePolicy(host="100.95.224.218", user="itadmin"),
    )

    monkeypatch.setattr(
        main, "verify_pi_support", lambda *args: calls.setdefault("verify", args)
    )

    main._probe_binding(config, binding)
    runtime = main.build_binding_runtime(config, binding)

    assert "verify" not in calls  # local probe skipped for the remote binding
    assert isinstance(runtime.agent_adapter, RoutingAgentAdapter)
    assert isinstance(runtime.agent_adapter.remote_adapter, RemoteAgentAdapter)


def test_probe_binding_remote_reachability_never_raises(monkeypatch, tmp_path):
    # ADR-0012 task 10.1: the remote branch logs a reachability result via
    # repo_host_for(binding).code_sha() and must never raise — a "unknown" sha
    # (unreachable host / bad path) warns but lets startup proceed.
    from config import RemotePolicy

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
    base = config.bindings[0]
    binding = type(base)(
        name="n8n",
        plane_project_id="n8n",
        repo_path=base.repo_path,
        base_branch=base.base_branch,
        tracker_contract=base.tracker_contract,
        default_agent="pi",
        tracker="podium",
        approval_policy=base.approval_policy,
        landing_policy=base.landing_policy,
        remote=RemotePolicy(host="100.95.224.218", user="itadmin"),
    )

    calls = {}

    class StubRepoHost:
        def code_sha(self):
            calls["code_sha"] = True
            return "unknown"

    monkeypatch.setattr(main, "repo_host_for", lambda b: StubRepoHost())

    main._probe_binding(config, binding)
    runtime = main.build_binding_runtime(config, binding)

    assert calls.get("code_sha") is True
    assert runtime.name == "n8n"


def test_probe_binding_verifier_failure_aborts_before_transport(monkeypatch, tmp_path):
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
        main._probe_binding(config, config.bindings[0])

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

    monkeypatch.setattr(main, "_probe_binding", lambda config, binding: None)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build_runtime)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with pytest.raises(StopLoop):
        await main.run_bindings_loop(cast(Any, FakeConfig()))

    assert "limited" in calls
    assert "healthy" in calls
    assert closed == ["limited", "healthy"]
