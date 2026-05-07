from __future__ import annotations

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
    )

    prompt = main._render_candidate_prompt(issue)

    assert prompt == "rendered prompt"
    assert captured["issue"].id == "issue-1"
    assert captured["issue"].identifier == "AUTO-1"
    assert captured["issue"].name == "Check proxy"
    assert captured["issue"].description == "Verify proxy container"
    assert captured["issue"].labels == "media, maintenance"


def test_async_main_passes_configured_agent_runner(monkeypatch):
    calls = {}

    class FakeConfig:
        plane_api_url = "http://plane.local"
        plane_api_key = "token"
        plane_workspace_slug = "homelab"
        plane_project_id = "project-uuid"

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

    def fake_run_agent(config, issue, rendered_prompt):
        calls["run_agent"] = (config, issue, rendered_prompt)
        return "agent-result"

    async def fake_run_loop(config, adapter, *, agent_runner, render_prompt, notifier=None):
        calls["run_loop"] = (config, adapter, render_prompt)
        calls["notifier"] = notifier
        calls["agent_result"] = agent_runner("issue", "prompt")

    monkeypatch.setattr(main, "SymphonyConfig", FakeConfig)
    monkeypatch.setattr(main, "HttpxPlaneTransport", FakeTransport)
    monkeypatch.setattr(main, "build_adapter", fake_build_adapter)
    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    import asyncio

    asyncio.run(main.async_main())

    config = calls["run_loop"][0]
    assert calls["transport"] == ("http://plane.local", "token")
    assert calls["adapter"][1:] == ("homelab", "project-uuid")
    assert calls["run_agent"] == (config, "issue", "prompt")
    assert calls["agent_result"] == "agent-result"
    assert calls["closed"] is True
