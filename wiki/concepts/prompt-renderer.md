---
title: Prompt renderer
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-30
sources:
  - prompt_renderer.py
  - scheduler/__init__.py
  - skill_mode_map.py
  - skill_mode_map.py
  - tests/test_prompt_renderer_podium.py
  - wiki/raw/sessions/2026-06-18-retire-context-md-refeed-floor.md
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

`render_previous_comments_block(comments_text, *, truncate=True, flag_operator_replies=False)` preserves Plane behavior by default: it strips empty input, tail-truncates to `_PREVIOUS_COMMENTS_MAX_CHARS = 12000`, prepends `[Earlier previous comments truncated]` when truncating, and wraps content in `<previous_comments>` [source: prompt_renderer.py]. Podium calls the same helper with `truncate=False` so the full operator/comment continuity surface is preserved [source: prompt_renderer.py]. The keyword-only `flag_operator_replies` (Podium path only) appends, after the untrusted-context caveat, a directive that blocks headed `### Operator Reply` are the operator's directives and the most recent one is the current request to act on, while other comment text stays untrusted; the Plane path leaves it `False` and is byte-for-byte unchanged [source: prompt_renderer.py]. See [Operator reply comments](operator-reply.md).

> **RETIRED 2026-06-18 (C-0244):** `render_issue_context_block` and the `context_md`/`## Issue Context` prompt block were removed. `context_md` is no longer injected into any Podium prompt; `comments_md` is the sole Symphony-managed prompt continuity surface for non-resumed dispatch. `IssueData.context_md` remains a dormant field (stored/serialized only). `_escape_untrusted_block` still defensively escapes `</issue_context>` even though no context block is emitted [source: prompt_renderer.py] [source: wiki/raw/sessions/2026-06-18-retire-context-md-refeed-floor.md].

## Schedule context

For non-coding bindings, `_render_schedule_context(issue)` appends one-shot schedule metadata when `schedule_not_before` is set. Schedule fields are escaped through `_escape_untrusted_block` [source: prompt_renderer.py#141-158,177-180].

## Skill→Mode bridge

`skill_mode_map.py` is the transitional single source for projecting Podium `preferred_skill` values back to legacy renderer Mode values. Known mappings: `/dev-plan → plan`, `/dev-build → build`, `/diagnose → execute`, `/code-review → execute`; unknown or missing skills default to `execute` [source: skill_mode_map.py#1-28].

> **2026-06-30 — plan/build is now INERT (ADR-0031, C-0351).** `mode_for_skill`/`SKILL_TO_MODE` and the Podium `preferred_skill`→`plan`/`build` label projection still run, but **no engine branch acts on `plan`/`build` anymore**: the scheduler `mode == "build"` gate (return-to-plan recovery + plan-path discovery) is deleted, and the Plan Mode / Build Mode sections of `INFRA_PREAMBLE` are removed. Plan-vs-build is now an instruction the operator writes in the issue body. `_resolve_mode`/`mode_for_skill` survive for logging/label display only; removal of the dormant vocabulary is a deferred cleanup. See [../analyses/adr-0031-operator-driven-plan-build.md](../analyses/adr-0031-operator-driven-plan-build.md). The same change fixed a double-injection bug: the Podium `render_prompt` already embeds `comments_md`, so the scheduler's `_render_for_dispatch` comment append is now Plane-only.

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
5. Appends the final `<issue>` block [source: prompt_renderer.py]. (The former step that appended `context_md` through an Issue Context block was removed 2026-06-18 — C-0244.)

The final `<issue>` block remains last and escapes `name` + `description` [source: prompt_renderer.py#190-197].

## Test coverage

`tests/test_prompt_renderer_podium.py` verifies the Skill→Mode table, that Podium prompts include `comments_md` but **not** `context_md` (dormant), no Podium comment truncation, missing/unknown skill defaulting to `execute`, and Plane-path regression behavior [source: tests/test_prompt_renderer_podium.py].

## Notes / known divergences

- `IssueData.mode` still defaults to `conversation`, but current `prompt_renderer.py` no longer appends a dedicated conversation guard block; `WORKFLOW.md` owns policy text [source: prompt_renderer.py#22-37,161-197] [source: tests/test_prompt_renderer.py#38-54].
- Variable list is hardcoded in `_substitute`. Adding a new `{{issue.<field>}}` requires editing both `IssueData` and the substitution mapping [source: prompt_renderer.py#22-37,87-106].
- Podium keeps Mode only as a renderer-compatibility bridge. The tracker-side work-shape source is `preferred_skill`; full Mode retirement remains a later migration step.

## Related

- [Symphony engine — Workflow section](symphony-engine.md)
- [Podium tracker](podium-tracker.md)
- [homelab WORKFLOW.md](../entities/workflow-homelab.md), [trading WORKFLOW.md](../entities/workflow-trading.md)
- [Scheduler loop — verdict markers](scheduler-loop.md)

> **2026-06-12 update; timeout amended 2026-06-23:** for Podium issues with a `preferred_skill`, the renderer now prepends a skill-invocation directive to the prompt. Runtime timeout is owned by `SymphonyConfig`; default is now `7_200_000` ms. See [../analyses/podium-issue-dispatch-contract.md](../analyses/podium-issue-dispatch-contract.md).

> **2026-06-23 — `OUTPUT_CONTRACT` change planned (ADR-0022, `proposed`, C-0308):** the forced `SYMPHONY_SUMMARY` block will be downgraded to an optional fallback. The engine will post the agent's captured natural turn as the comment (pi `assistant_parts` / claude transcript turn) and the contract wording changes to "answer naturally; no summary block required" while keeping the terminal `SYMPHONY_RESULT:` marker. Not yet built. See [../analyses/adr-0022-post-captured-turn-not-forced-summary.md](../analyses/adr-0022-post-captured-turn-not-forced-summary.md).
