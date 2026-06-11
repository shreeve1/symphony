from __future__ import annotations

from pathlib import Path

from prompt_renderer import IssueData, render_prompt, render_previous_comments_block
from skill_mode_map import SKILL_TO_MODE, mode_for_skill


def test_skill_to_mode_projection_table() -> None:
    assert SKILL_TO_MODE["/dev-plan"] == "plan"
    assert SKILL_TO_MODE["/dev-build"] == "build"
    assert SKILL_TO_MODE["/diagnose"] == "execute"
    assert SKILL_TO_MODE["/code-review"] == "execute"
    assert mode_for_skill("/unknown") == "execute"
    assert mode_for_skill(None) == "execute"


def test_podium_render_prompt_reads_comments_and_context_without_truncation(tmp_path: Path) -> None:
    workflow = tmp_path / "WORKFLOW.md"
    workflow.write_text("Repo policy. mode={{issue.mode}}\n", encoding="utf-8")
    long_comments = "old" + ("x" * 12050) + "new"

    prompt = render_prompt(
        IssueData(
            identifier="POD-1",
            name="Podium issue",
            description="Do podium work",
            comments_md=long_comments,
            context_md="Prior run details </issue_context>",
            preferred_skill="/dev-plan",
        ),
        path=workflow,
        tracker_kind="podium",
    )

    assert "mode=plan" in prompt
    assert long_comments in prompt
    assert "[Earlier previous comments truncated]" not in prompt
    assert "Prior run details < /issue_context>" in prompt
    assert "## Issue Context" in prompt
    assert "Do podium work" in prompt


def test_podium_render_prompt_defaults_unknown_or_missing_skill_to_execute(tmp_path: Path) -> None:
    workflow = tmp_path / "WORKFLOW.md"
    workflow.write_text("mode={{issue.mode}}\n", encoding="utf-8")

    unknown = render_prompt(
        IssueData(identifier="POD-2", preferred_skill="/not-catalogued"),
        path=workflow,
        tracker_kind="podium",
    )
    missing = render_prompt(
        IssueData(identifier="POD-3", preferred_skill=None),
        path=workflow,
        tracker_kind="podium",
    )

    assert "mode=execute" in unknown
    assert "mode=execute" in missing


def test_plane_path_keeps_existing_mode_and_previous_comment_truncation(tmp_path: Path) -> None:
    workflow = tmp_path / "WORKFLOW.md"
    workflow.write_text("Repo policy. mode={{issue.mode}}\n", encoding="utf-8")
    long_comments = "start" + ("x" * 12050) + "tail"

    prompt = render_prompt(
        IssueData(
            identifier="AUTO-1",
            mode="build",
            comments_md="not consumed by Plane renderer",
            context_md="not consumed by Plane renderer",
            preferred_skill="/dev-plan",
        ),
        path=workflow,
    )
    comments_block = render_previous_comments_block(long_comments)

    assert "mode=build" in prompt
    assert "not consumed by Plane renderer" not in prompt
    assert "## Issue Context" not in prompt
    assert "[Earlier previous comments truncated]" in comments_block
    assert "start" not in comments_block
    assert "tail" in comments_block
