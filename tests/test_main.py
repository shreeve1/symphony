from __future__ import annotations

import asyncio

import pytest

from agent_runner import AgentRunnerError
from plane_poller import CandidateIssue

import main


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


def test_async_main_passes_configured_agent_runner(monkeypatch):
    calls = {}

    class FakeConfig:
        plane_api_url = "http://plane.local"
        plane_api_key = "token"
        plane_workspace_slug = "homelab"
        plane_project_id = "project-uuid"
        pi_bin = "pi"
        pi_provider = "zai"
        pi_model = "glm-5.1:high"
        homelab_repo_path = "/home/james/homelab"

        @classmethod
        def from_env(cls):
            return cls()

    class FakeTransport:
        def __init__(self, api_url, api_key):
            calls["transport"] = (api_url, api_key)

        async def aclose(self):
            calls["closed"] = True

    def fake_build_adapter(transport, *, workspace_slug, project_id):
        calls["adapter"] = (transport, workspace_slug, project_id)
        return "adapter"

    class FakePiAgentAdapter:
        def __init__(self, config):
            calls["agent_adapter_config"] = config

        def __call__(self, issue, rendered_prompt):
            calls["agent_adapter_call"] = (issue, rendered_prompt)
            return "agent-result"

    def fake_verify_pi_support(pi_bin, provider, model, cwd):
        calls["verify"] = (pi_bin, provider, model, cwd)
        assert "transport" not in calls

    async def fake_run_loop(config, adapter, *, agent_runner, render_prompt, notifier=None):
        calls["run_loop"] = (config, adapter, render_prompt)
        calls["notifier"] = notifier
        calls["agent_result"] = agent_runner("issue", "prompt")

    monkeypatch.setattr(main, "SymphonyConfig", FakeConfig)
    monkeypatch.setattr(main, "HttpxPlaneTransport", FakeTransport)
    monkeypatch.setattr(main, "build_adapter", fake_build_adapter)
    monkeypatch.setattr(main, "PiAgentAdapter", FakePiAgentAdapter)
    monkeypatch.setattr(main, "verify_pi_support", fake_verify_pi_support)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    asyncio.run(main.async_main())

    config = calls["run_loop"][0]
    assert calls["verify"] == ("pi", "zai", "glm-5.1:high", "/home/james/homelab")
    assert calls["transport"] == ("http://plane.local", "token")
    assert calls["adapter"][1:] == ("homelab", "project-uuid")
    assert calls["agent_adapter_config"] == config
    assert calls["agent_adapter_call"] == ("issue", "prompt")
    assert calls["agent_result"] == "agent-result"
    assert calls["closed"] is True


def test_async_main_verifier_failure_aborts_before_transport(monkeypatch):
    calls = {}

    class FakeConfig:
        plane_api_url = "http://plane.local"
        plane_api_key = "token"
        plane_workspace_slug = "homelab"
        plane_project_id = "project-uuid"
        pi_bin = "pi"
        pi_provider = "zai"
        pi_model = "glm-5.1:high"
        homelab_repo_path = "/home/james/homelab"

        @classmethod
        def from_env(cls):
            return cls()

    class FakeTransport:
        def __init__(self, api_url, api_key):
            calls["transport"] = (api_url, api_key)

    def fake_verify_pi_support(*args):
        calls["verify"] = args
        raise AgentRunnerError("bad pi")

    monkeypatch.setattr(main, "SymphonyConfig", FakeConfig)
    monkeypatch.setattr(main, "HttpxPlaneTransport", FakeTransport)
    monkeypatch.setattr(main, "verify_pi_support", fake_verify_pi_support)

    with pytest.raises(AgentRunnerError, match="bad pi"):
        asyncio.run(main.async_main())

    assert "verify" in calls
    assert "transport" not in calls
