---
title: Prompt renderer
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-12
sources:
  - prompt_renderer.py
  - skill_mode_map.py
  - tests/test_prompt_renderer_podium.py
confidence: high
tags: [prompt-renderer, workflow, variable-substitution, schedule-context, podium, skill-mode-map]
---

# Prompt renderer (`prompt_renderer.py`)

The renderer is pure mechanism: read `WORKFLOW.md`, apply issue-variable substitution, escape untrusted issue/comment content, and append scheduler-owned context blocks. Repo-specific policy lives entirely in `WORKFLOW.md` [source: prompt_renderer.py#1-6].

## `IssueData` (the substitution payload)

`IssueData` carries Plane-era fields (`id`, `identifier`, `name`, `description`, `labels`, `mode`, schedule fields) plus Podium bridge fields (`comments_md`, `context_md`, `preferred_skill`) [source: prompt_renderer.py#22-37].

Variable substitution currently maps only the legacy template variables (`id`, `identifier`, `name`, `description`, `labels`, `mode`, and schedule fields). `comments_md`, `context_md`, and `preferred_skill` are read by the Podium rendering path but are not exposed as `{{issue.*}}` variables [source: prompt_renderer.py#87-106]. Unknown variables pass through verbatim [source: prompt_renderer.py#102-105].

## Workflow loading

`load_workflow(path)` raises `FileNotFoundError` when `WORKFLOW.md` is missing or unreadable, parses YAML front matter defensively, and returns `WorkflowConfig` plus body text [source: prompt_renderer.py#40-69].

## Escaping and context blocks

`_escape_issue_content` prevents `</issue>` from closing the rendered issue block [source: prompt_renderer.py#72-73]. `_escape_untrusted_block` escapes `</issue>`, `</previous_comments>`, and `</issue_context>` for comment/context blocks [source: prompt_renderer.py#76-81].

`render_previous_comments_block(comments_text, *, truncate=True, flag_operator_replies=False)` preserves Plane behavior by default: it strips empty input, tail-truncates to `_PREVIOUS_COMMENTS_MAX_CHARS = 12000`, prepends `[Earlier previous comments truncated]` when truncating, and wraps content in `<previous_comments>` [source: prompt_renderer.py#19,109-124]. Podium calls the same helper with `truncate=False`, because engine-built compaction owns Podium size control [source: prompt_renderer.py#182-185]. The keyword-only `flag_operator_replies` (Podium path only) appends, after the untrusted-context caveat, a directive that blocks headed `### Operator Reply` are the operator's directives and the most recent one is the current request to act on, while other comment text stays untrusted; the Plane path leaves it `False` and is byte-for-byte unchanged [source: prompt_renderer.py#109-124,182-185]. See [Operator reply comments](operator-reply.md).

`render_issue_context_block(context_text)` wraps Podium Issue Context in a dedicated `## Issue Context` / `<issue_context>` block and escapes closing tags [source: prompt_renderer.py#127-138].

## Schedule context

For non-coding bindings, `_render_schedule_context(issue)` appends one-shot schedule metadata when `schedule_not_before` is set. Schedule fields are escaped through `_escape_untrusted_block` [source: prompt_renderer.py#141-158,177-180].

## Skill→Mode bridge

`skill_mode_map.py` is the transitional single source for projecting Podium `preferred_skill` values back to legacy renderer Mode values. Known mappings: `/dev-plan → plan`, `/dev-build → build`, `/diagnose → execute`, `/code-review → execute`; unknown or missing skills default to `execute` [source: skill_mode_map.py#1-28].

This bridge exists because Podium stores work shape as `preferred_skill`, while existing `WORKFLOW.md` templates still consume `{{issue.mode}}` [source: skill_mode_map.py#1-6].

## `render_prompt(issue, *, path, binding_type="infra", tracker_kind="plane")`

`render_prompt(...)` accepts `tracker_kind: Literal["plane", "podium"] = "plane"`, preserving existing Plane call sites. Unsupported tracker kinds raise `ValueError` [source: prompt_renderer.py#161-169].

Plane path:

1. Loads `WORKFLOW.md`.
2. Substitutes legacy variables using the caller-provided `issue.mode`.
3. Appends schedule context for non-coding bindings.
4. Appends the final `<issue>` block.

Podium path:

1. Replaces `issue.mode` with `mode_for_skill(issue.preferred_skill)`.
2. Loads and substitutes `WORKFLOW.md`.
3. Appends schedule context for non-coding bindings.
4. Appends non-truncated `comments_md` through the previous-comments block.
5. Appends `context_md` through the Issue Context block.
6. Appends the final `<issue>` block [source: prompt_renderer.py#171-197].

The final `<issue>` block remains last and escapes `name` + `description` [source: prompt_renderer.py#190-197].

## Test coverage

`tests/test_prompt_renderer_podium.py` verifies the Skill→Mode table, Podium direct reads from `comments_md`/`context_md`, no Podium comment truncation, missing/unknown skill defaulting to `execute`, and Plane-path regression behavior [source: tests/test_prompt_renderer_podium.py#9-85].

## Notes / known divergences

- `IssueData.mode` still defaults to `conversation`, but current `prompt_renderer.py` no longer appends a dedicated conversation guard block; `WORKFLOW.md` owns policy text [source: prompt_renderer.py#22-37,161-197] [source: tests/test_prompt_renderer.py#38-54].
- Variable list is hardcoded in `_substitute`. Adding a new `{{issue.<field>}}` requires editing both `IssueData` and the substitution mapping [source: prompt_renderer.py#22-37,87-106].
- Podium keeps Mode only as a renderer-compatibility bridge. The tracker-side work-shape source is `preferred_skill`; full Mode retirement remains a later migration step.

## Related

- [Symphony engine — Workflow section](symphony-engine.md)
- [Podium tracker](podium-tracker.md)
- [homelab WORKFLOW.md](../entities/workflow-homelab.md), [trading WORKFLOW.md](../entities/workflow-trading.md)
- [Scheduler loop — verdict markers](scheduler-loop.md)

> **2026-06-12 update:** for Podium issues with a `preferred_skill`, the renderer now prepends a skill-invocation directive to the prompt, and `WorkflowConfig.run_timeout_ms` defaults to 3600000. See [../analyses/podium-issue-dispatch-contract.md](../analyses/podium-issue-dispatch-contract.md).
