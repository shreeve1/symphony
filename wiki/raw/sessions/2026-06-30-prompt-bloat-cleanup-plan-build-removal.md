# Session capture — prompt bloat cleanup + plan/build mode removal (2026-06-30)

Interactive session (not a Podium slice). Operator asked to identify prompt bloat in the dispatch path, then to remove it and remove engine-owned plan/build entirely. Working tree on top of `af7ccbd`; not yet committed at capture time.

## Trigger

Operator noticed comments to the issue flyout changed (the agent's natural turn now posts instead of a forced summary — confirmed as ADR-0022, accepted/implemented 2026-06-26, working as designed). Follow-up question: is there bloat the LLM receives from the Symphony dispatch process?

## Findings (what the agent actually receives)

1. **Double comment injection on the Podium path (bug).** `render_prompt` (podium branch, `prompt_renderer.py`) already embeds `comments_md` as the canonical `## Previous Issue Comments` block (untruncated, operator-reply-flagged, from #025 `36a7cd4`). `_render_for_dispatch` (`scheduler/__init__.py:588`) then appended a SECOND differently-formatted copy from `_fetch_issue_comments` (added later by #050 resume work `831e9f3`). Confirmed by render probe: `render_prompt` → 1× body / 1× header; after `_render_for_dispatch` → 2× body / 2× header. Only the non-resume Podium path double-injected (resume already guarded). Scaled with thread length; affected both coding and infra bindings.

2. **Plan/Build mode always sent + a real scheduler gate behind it.** `INFRA_PREAMBLE` carried ~30 lines of Plan Mode (rules 17–27) + Build Mode (28–39) — hardcoded host skill paths, Codex loop, plan-file conventions — rendered into EVERY infra dispatch regardless of `plan`/`build` label. Behind it: a `mode == "build" and not is_coding` scheduler gate (return-to-plan recovery, grace window, terminal block), `BUILD_PLAN_MISSING_GRACE_ATTEMPTS`, `_BUILD_PLAN_RETURN_MARKER`, plan-path helpers.

3. **Duplicate rule "17"** in `INFRA_PREAMBLE` (one under Completion, one under Plan Mode).

4. **Stale OUTPUT_CONTRACT + preamble rules post-ADR-0022.** The contract still spent ~10 lines explaining `SYMPHONY_SUMMARY_BEGIN/END` override semantics; preamble rules 12/15 still said "the summary is the only per-run signal" — false after ADR-0022 (natural turn is the channel).

## Decision (operator)

Remove engine-owned plan/build entirely — "I will instruct issues when to plan and build. I would rather control it." Chose **surgical (A)** over full rip-out: drive plan vs build by the issue body, delete the behavior, keep the inert vocabulary (enums, skills, label projection, `_resolve_mode`, `mode_for_skill`) for reversibility. See ADR-0031.

## Implementation

- **Finding 1**: gated the `_render_for_dispatch` append on `not getattr(adapter, "stores_context", False)` — Plane-only. `stores_context` is the established Podium discriminator (`tracker_podium.py:72`; used at scheduler 528/894/1688/etc.).
- **Finding 2 — scheduler**: deleted the `mode == "build"` gate (~105 lines), the two constants, and the now-orphaned plan-path helpers (`_validated_fallback_plan_path`, `_expected_plan_path`, `_validate_issue_plan_path`, `_plan_stem_matches_issue`, `_issue_slug`). Removed the now-unused `from skill_mode_map import mode_for_skill` import. Kept `_resolve_mode` + `gate.mode` (logging) and `mode_for_skill`/label projection (inert).
- **Finding 2 — preamble**: stripped Plan Mode + Build Mode sections from `INFRA_PREAMBLE`. Surviving rules 1–17 renumber cleanly (duplicate 17 resolved — Finding 3).
- **Finding 4**: trimmed OUTPUT_CONTRACT summary-override block to a one-line "optional override" note (kept the START-of-line parser self-match guard + the question block); rewrote preamble rules 12/14/15 to the captured-turn model.
- **Follow-up cleanup (same session)**: removed two PRE-EXISTING dead helpers `_state_path_for_plan` + `_final_non_empty_line` (zero callers before this change, confirmed via `git stash`).
- **CONTEXT.md**: corrected the **Mode** and **Tracker Contract** glossary entries — `mode:plan`/`mode:build` are no longer engine-branched (ADR-0031).

## Tests

- Removed obsolete `test_scheduler.py` build-mode block (`test_build_mode_*`, `_validated_fallback_plan_path` tests, `_write_plan` helper, the `_validated_fallback_plan_path` import) and the `test_engine_against_podium.py` `test_infra_build_grace_then_block_against_podium_when_no_plan` (+ now-unused `import scheduler`).
- Kept `test_resolve_mode_*` and `test_skill_to_mode_projection_table` (functions survive).
- Added `test_infra_preamble_has_no_plan_or_build_mode_sections` (renderer) and `test_podium_dispatch_injects_comments_once` (real PodiumTrackerAdapter run_tick, asserts 1× comment marker + 1× header in the dispatched prompt).
- Full suite green: **1224 passed, 2 skipped**. Ruff + LSP clean.

## Net

6 files, ~84 insertions / 613 deletions. `docs/adr/0031-operator-driven-plan-build-not-engine-modes.md` written.

## Flagged, not touched (pre-existing, out of scope)

- `.claude/skills/symphony-workflow-author/templates/WORKFLOW.infra.md` still contains Plan/Build text — dead since ADR-0016 retired the `symphony-workflow-author` skill; no live code reads it.
- Vestigial `path` param on `render_prompt`; dormant `context_md` plumbing; inert plan/build label vocabulary (Plane enums, `dev-plan`/`dev-build` skills, `mode_for_skill` projection) — all noted in ADR-0031 as deferred cleanup.

## Deploy

Not deployed. This is the symphony self-binding repo (live dispatcher) — deploy = `symphony-host.service` restart, NOT podium-api/web. Changes also not yet committed.
