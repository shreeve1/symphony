---
title: ADR-0011 — WORKFLOW.md is infra-only autonomy policy
type: analysis
status: promoted
created: 2026-06-14
updated: 2026-06-14
sources:
  - docs/adr/0011-workflow-md-infra-only.md
  - prompt_renderer.py
  - CONTEXT.md
  - wiki/raw/sessions/2026-06-14-workflow-md-infra-only.md
confidence: high
tags: [adr, workflow, binding-type, coding, infra, cli, autonomy, safety, prompt-renderer]
---

# ADR-0011 — WORKFLOW.md is infra-only autonomy policy

`accepted` 2026-06-14. Outcome of a grill-me design pass on the split James perceived between Symphony-as-infra-ticketing and Symphony-as-cli-issue-tracker.

## The split is the existing `binding_type` axis

The cli-vs-infra distinction is **not a new dimension** — it is the existing `binding_type` (`coding` vs `infra`), which already gates schedule, scheduled-candidate selection, blocked reconciler, approval gate, build-mode handling, landing/worktree, and the schedule-context prompt block behind `is_coding` [source: scheduler.py] [source: prompt_renderer.py:264]. The only behavior that had *not* split was `WORKFLOW.md`.

## Decision

`WORKFLOW.md` is **infra-only autonomy policy**:

- **infra** — mandatory, rendered on every fresh dispatch; a missing file is still a hard `workflow-missing` block.
- **coding** — **ignored**, not optional. `render_prompt` skips `load_workflow` when `binding_type == "coding"` and assembles the prompt from the issue (+ comments/context on the re-feed floor) + the renderer-constant `OUTPUT_CONTRACT` only [source: prompt_renderer.py] [source: docs/adr/0011-workflow-md-infra-only.md].

Two conflations were rejected: WORKFLOW.md as "the whole policy" (it is the *autonomy* slice only) and WORKFLOW.md as a safety net (safety is the bound repo's responsibility via native `CLAUDE.md`/`AGENTS.md`, owned by the project maintainer; Symphony stays narrow). "Read if present" was rejected as a silent-surprise trap — *ignored* is predictable.

## Why dropping the body is safe

- The output contract is independent of WORKFLOW.md (`OUTPUT_CONTRACT` constant), so verdict scraping survives [source: prompt_renderer.py:25-49].
- The `WorkflowConfig` frontmatter (`poll_interval_ms`/`run_timeout_ms`) was already dead — discarded by `render_prompt`; runtime timeouts come from `SymphonyConfig` [source: prompt_renderer.py:261] [source: config.py:131-132].
- Resume dispatches already omitted WORKFLOW.md; it only entered on the fresh dispatch [source: prompt_renderer.py:286-312].

## Implementation in the same session

- `prompt_renderer.py` — coding branch sets `body=""`, skips `load_workflow`; empty-body assembly avoids leading blank lines.
- Tests — added `test_coding_binding_ignores_workflow_md` and `test_coding_binding_renders_without_workflow_file`; flipped coding-prompt assertions in `test_trading_podium_dispatch.py`, `test_engine_against_podium.py`, `test_dispatch_compaction.py` to "WORKFLOW body absent". Full suite 786 passed, 2 skipped.
- `WORKFLOW.md` deleted from the `symphony` and `trading` repos (code change landed first so dispatch never hit `workflow-missing`).
- Skills — `symphony-onboard-project` branches on type (infra → `symphony-workflow-author`; coding → skip + flag missing native config); `symphony-workflow-author` is now infra-only and refuses coding bindings. `symphony-binding-scaffold` unchanged (already `binding_type`-parameterized).

## Consequences and follow-ups

- **Restart pending** — live dispatch behavior changes; needs a James-approved `symphony-restart`.
- **trading safety** — its only safety statement lived in the deleted WORKFLOW.md and it has no native agent config; accepted as a test repo, migrate to `CLAUDE.md`/`AGENTS.md` if it ever does live work.
- Supersedes the CONTEXT.md framing of WORKFLOW.md as "the whole policy" / "mandatory for every Binding".

## Related

- [homelab WORKFLOW.md](../entities/workflow-homelab.md) — still active (infra binding keeps WORKFLOW.md)
- [trading WORKFLOW.md](../entities/workflow-trading.md) — superseded; file deleted
- [Symphony engine — Workflow section](../concepts/symphony-engine.md)
- [thin-engine-v2 — coding vs infra differences](../concepts/thin-engine-v2.md)
- [symphony skills index](symphony-skills-index.md)
