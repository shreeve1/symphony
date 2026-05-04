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
