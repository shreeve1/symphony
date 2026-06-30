---
title: "ADR-0031 — Operator-driven plan/build + dispatch prompt-bloat cleanup"
type: analysis
status: promoted
created: 2026-06-30
updated: 2026-06-30
sources:
  - docs/adr/0031-operator-driven-plan-build-not-engine-modes.md
  - prompt_renderer.py
  - scheduler/__init__.py
  - scheduler/sanitize.py
  - tracker_podium.py
  - CONTEXT.md
  - tests/test_scheduler.py
  - tests/test_engine_against_podium.py
  - tests/test_prompt_renderer_podium.py
  - wiki/raw/sessions/2026-06-30-prompt-bloat-cleanup-plan-build-removal.md
confidence: high
tags: [adr, prompt-renderer, scheduler, plan-build, output-contract, comments, bloat, infra-preamble]
---

# ADR-0031 — Operator-driven plan/build + dispatch prompt-bloat cleanup

**Status: `accepted` (2026-06-30), implemented same day. Deploy = `symphony-host.service` restart (the live dispatcher); not committed/deployed at capture time.**

A prompt-bloat review of the dispatch path found four issues in what the agent actually receives. The operator decided to remove engine-owned plan/build mode entirely and control plan-vs-build by writing it in the issue body. All four were fixed surgically, leaving the dormant plan/build vocabulary inert for reversibility [source: docs/adr/0031-operator-driven-plan-build-not-engine-modes.md; source: wiki/raw/sessions/2026-06-30-prompt-bloat-cleanup-plan-build-removal.md].

## 1. Double comment injection on the Podium path (bug, C-0351)

The Podium `render_prompt` branch already embeds `comments_md` as the canonical `## Previous Issue Comments` block — untruncated, operator-reply-flagged — from #025. The scheduler's `_render_for_dispatch` then appended a SECOND differently-formatted copy from `_fetch_issue_comments` (added later by #050's resume work). On every non-resume Podium dispatch the whole comment thread went to the model twice (the renderer's untruncated copy + the scheduler's per-comment 1500-char-bounded copy, no operator-reply flagging). The resume path was already guarded; only non-resume Podium double-injected. Fix: gate the scheduler append on `not getattr(adapter, "stores_context", False)` so it fires for Plane only — `stores_context` is the established Podium discriminator. The renderer's embed stays canonical [source: prompt_renderer.py; source: scheduler/__init__.py; source: tracker_podium.py].

## 2. Plan/Build mode removed (C-0351)

`INFRA_PREAMBLE` carried ~30 lines of Plan Mode (rules 17–27) and Build Mode (28–39) — hardcoded host skill paths (`/home/james/.claude/skills/Development/...`), a Codex audit-loop directive, plan-file conventions — rendered into every infra dispatch regardless of label. Behind the text sat a real scheduler mechanism: a `mode == "build" and not is_coding` gate that resolved mode from labels, searched for a plan file under `plans/`, and on a miss either flipped the issue back to Plan mode or blocked after a grace window (the skill-projected Podium bounce guard).

Removed: the whole `mode == "build"` gate (~105 lines), the constants `BUILD_PLAN_MISSING_GRACE_ATTEMPTS` / `_BUILD_PLAN_RETURN_MARKER`, the orphaned plan-path helpers (`_validated_fallback_plan_path`, `_expected_plan_path`, `_validate_issue_plan_path`, `_plan_stem_matches_issue`, `_issue_slug`), the now-unused `mode_for_skill` import, and both preamble mode sections. A `dev-build` issue with no plan now just dispatches; the agent handles a missing plan in-conversation. The operator drives plan vs build by writing it in the issue body [source: scheduler/__init__.py; source: prompt_renderer.py].

### What deliberately stays (surgical, reversible)

`_resolve_mode` and the `mode` field on `TickResult` are kept (degrade to logging-only). `mode_for_skill` / `SKILL_TO_MODE` and the Podium `preferred_skill`→`plan`/`build` label projection in `tracker_podium.py` stay but are now **inert** — labels are produced, no gate acts on them. The dormant Plane `MODE_PLAN`/`MODE_BUILD` contract enums and the `dev-plan`/`dev-build` skill catalog rows remain as ordinary selectable skills. None reach the prompt or change behavior; removal is a deferred cleanup [source: scheduler/__init__.py; source: skill_mode_map.py; source: tracker_podium.py].

## 3. Duplicate rule "17"

`INFRA_PREAMBLE` had two `17.`s (one under Completion, one under Plan Mode). Resolved automatically by the Plan Mode removal; surviving Completion rules 12–17 are now unique [source: prompt_renderer.py].

## 4. OUTPUT_CONTRACT + stale preamble rules (post-ADR-0022)

ADR-0022 (C-0308) made the agent's natural turn the comment channel and downgraded `SYMPHONY_SUMMARY` to an optional fallback, but the contract still spent ~10 lines explaining the override block and preamble rules 12/15 still claimed "the summary is the only per-run signal." Trimmed the override section to a one-line "optional override" note (kept the START-of-line parser self-match guard and the question block) and rewrote preamble rules 12/14/15 to the captured-turn model [source: prompt_renderer.py].

## CONTEXT.md glossary correction

The change made two glossary statements factually wrong. The **Mode** entry (said the plan/build bridge lives "inside the prompt renderer and scheduler") and the **Tracker Contract** entry (listed `mode:plan`/`mode:build` as "a thing the engine branches on") were corrected: the vocabulary survives as an inert compatibility bridge (logging/display only); the engine no longer branches on `plan`/`build` [source: CONTEXT.md].

## Pre-existing dead-code cleanup

Two pre-existing dead helpers in `scheduler/__init__.py` — `_state_path_for_plan` and `_final_non_empty_line` — were removed in the same session (zero callers before this change, confirmed via `git stash`). The `WORKFLOW.infra.md` template in `symphony-workflow-author` still carries Plan/Build text but is dead weight from ADR-0016 (skill retired); no live code reads it — flagged, not touched [source: scheduler/__init__.py].

## Verification

`uv run pytest` green: **1224 passed, 2 skipped**. Ruff + LSP clean on all changed files. Removed obsolete build-mode tests; kept `test_resolve_mode_*` and `test_skill_to_mode_projection_table` (functions survive). Added regression tests: `test_infra_preamble_has_no_plan_or_build_mode_sections` and `test_podium_dispatch_injects_comments_once` (real `PodiumTrackerAdapter` `run_tick`, asserts a single comment marker + single header in the dispatched prompt). Net: 6 files, ~84 insertions / 613 deletions [source: tests/test_scheduler.py; source: tests/test_engine_against_podium.py; source: tests/test_prompt_renderer_podium.py].

## Related

- [ADR-0022 — post the captured turn, not a forced summary](adr-0022-post-captured-turn-not-forced-summary.md) (C-0308)
- [ADR-0016 — WORKFLOW.md retired, renderer constant](adr-0016-workflow-md-retired-renderer-constant.md) (C-0276; plan/build lived in `INFRA_PREAMBLE`)
- [#046 unified output contract](podium-046-unified-output-contract.md)
- [Prompt renderer](../concepts/prompt-renderer.md)
