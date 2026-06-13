from __future__ import annotations

from pathlib import Path

import pytest

from prompt_renderer import IssueData, render_prompt


def test_render_prompt_uses_workflow_md_variables_and_mode(tmp_path: Path) -> None:
    workflow = tmp_path / "WORKFLOW.md"
    workflow.write_text(
        "---\n"
        "poll_interval_ms: 1000\n"
        "---\n"
        "Repo policy for {{issue.identifier}}.\n"
        "mode={{issue.mode}} labels={{issue.labels}} schedule={{issue.schedule_not_before}}\n",
        encoding="utf-8",
    )

    prompt = render_prompt(
        IssueData(
            id="issue-1",
            identifier="AUTO-1",
            name="Check </issue>",
            description="Do work </issue>",
            labels="security, infra",
            mode="build",
            schedule_not_before="2026-05-08T20:00:00+00:00",
        ),
        path=workflow,
    )

    assert "Repo policy for AUTO-1." in prompt
    assert (
        "mode=build labels=security, infra schedule=2026-05-08T20:00:00+00:00" in prompt
    )
    assert "## Schedule Context" in prompt
    assert "MODE:" not in prompt
    assert "Domain Instructions" not in prompt
    assert "# AUTO-1: Check < /issue>" in prompt
    assert "Do work < /issue>" in prompt
    # The output contract is centralized here so both runners receive it.
    assert "## Symphony output contract" in prompt
    assert "SYMPHONY_SUMMARY_BEGIN" in prompt
    assert "SYMPHONY_RESULT: done" in prompt
    assert "SYMPHONY_QUESTION_BEGIN" in prompt


def test_render_prompt_omits_conversation_context_by_default(tmp_path: Path) -> None:
    """Conversation guard block removed in v2 — WORKFLOW.md now owns all policy."""
    workflow = tmp_path / "WORKFLOW.md"
    workflow.write_text("Repo policy. mode={{issue.mode}}\n", encoding="utf-8")

    prompt = render_prompt(
        IssueData(identifier="AUTO-CHAT", name="Question", description="What next?"),
        path=workflow,
    )

    assert "mode=conversation" in prompt
    assert "## Symphony Conversation Mode" not in prompt
    assert "Do not mutate live systems" not in prompt


def test_render_prompt_includes_scheduled_reboot_policy_and_context(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "WORKFLOW.md"
    workflow.write_text(
        "Reboots are allowed only when the ticket is scheduled for the current maintenance window.\n"
        "If a reboot is required and the ticket is not scheduled, schedule or block for follow-up.\n",
        encoding="utf-8",
    )

    prompt = render_prompt(
        IssueData(
            identifier="AUTO-2",
            name="pihole reboot required",
            description="reboot-required=true",
            labels="patrol,infra,scheduled",
            schedule_not_before="2026-06-07T07:00:00+00:00",
            schedule_reason="maintenance window",
            schedule_source="scheduled label maintenance window (12am-6am PT)",
        ),
        path=workflow,
    )

    assert "Reboots are allowed only when the ticket is scheduled" in prompt
    assert "## Schedule Context" in prompt
    assert "scheduled label maintenance window" in prompt
    assert "reboot-required=true" in prompt


def test_render_prompt_requires_workflow_md(tmp_path: Path) -> None:
    missing = tmp_path / "WORKFLOW.md"

    with pytest.raises(FileNotFoundError, match="WORKFLOW.md"):
        render_prompt(IssueData(identifier="AUTO-1"), path=missing)
