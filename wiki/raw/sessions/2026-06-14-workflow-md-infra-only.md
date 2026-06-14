# Session Capture: WORKFLOW.md is infra-only autonomy policy (ADR-0011)

- Date: 2026-06-14
- Purpose: grill-me design pass on the cli-vs-infra split James perceived; resolved into a concrete contract change to WORKFLOW.md handling, captured as ADR-0011 and implemented.
- Scope: the binding_type axis, the WORKFLOW.md contract, the autonomy-vs-safety boundary, the resulting code/test/skill/file changes. Excludes routine exploration chatter.

## Durable Facts

- The "cli-first issue tracker" vs "infra management" split James perceived maps onto the *existing* `binding_type` axis (`coding` vs `infra`), not a new dimension. `coding` bindings already skip schedule, blocked reconciler, approval gate, build-mode handling, landing/worktree, and the schedule-context prompt block — all gated on `is_coding`. — Evidence: `scheduler.py` (`is_coding` at ~1155; gates at 1172/1187/1279/1316/1719/1912), `prompt_renderer.py:264`, `CONTEXT.md` Project Binding term.
- Before this change, `render_prompt` read `WORKFLOW.md` for **every** binding; a missing/unreadable file blocked dispatch with reason `workflow-missing`. — Evidence: `prompt_renderer.py:98-110` (`load_workflow` raises), `scheduler.py:1429-1441`.
- The Symphony output contract (`SYMPHONY_RESULT`/`SYMPHONY_SUMMARY`/`SYMPHONY_QUESTION`) is a renderer constant (`OUTPUT_CONTRACT`), appended independently of `WORKFLOW.md`; verdict scraping survives dropping the workflow body. — Evidence: `prompt_renderer.py:25-49`.
- `WorkflowConfig` frontmatter (`poll_interval_ms`/`run_timeout_ms`) parsed from `WORKFLOW.md` was already dead — `render_prompt` discards it (`_cfg, body = load_workflow(...)`); runtime timeouts come from `SymphonyConfig` (env). — Evidence: `prompt_renderer.py:261`, `config.py:131-132,202-203`, `scheduler.py:2134`, `agent_runner.py:328`, `claude_runner.py:461`.
- On a resume-mode dispatch, `WORKFLOW.md` was already omitted entirely (only `OUTPUT_CONTRACT` + newest operator-reply delta + skill directive). So WORKFLOW.md only ever entered on the *fresh* dispatch, then persisted in the agent's native session. — Evidence: `prompt_renderer.py:286-312`.
- Repo agent-config inventory at change time: homelab (infra) has `CLAUDE.md` + `WORKFLOW.md`; trading (coding) had only `WORKFLOW.md` (no `CLAUDE.md`/`AGENTS.md`); symphony (coding) has `CLAUDE.md` + `WORKFLOW.md`. — Evidence: `ls` of the three repo roots.

## Decisions

- **WORKFLOW.md is infra-only autonomy policy (ADR-0011).** Mandatory + rendered for `infra`; **ignored** (not optional) for `coding` — `render_prompt` skips `load_workflow` when `binding_type == "coding"`. — Evidence: `docs/adr/0011-workflow-md-infra-only.md`, `prompt_renderer.py` (coding branch sets `body=""`).
- **WORKFLOW.md is autonomy instruction, not safety.** Safety and repo conventions are the bound repo's responsibility, expressed in native `CLAUDE.md`/`AGENTS.md` and owned by the project maintainer. Symphony stays strict to dispatch/verdict/autonomy-lifecycle. — Evidence: James in-session; `CONTEXT.md` Workflow term (updated inline this session).
- **Ignored, not optional.** "Read if present" was rejected — it reintroduces session pollution and a silent surprise. — Evidence: ADR-0011 Considered Options.
- **`binding_type` value names stay `coding`/`infra`.** No rename to `cli`; "cli" is the product framing only. — Evidence: James in-session; `config.py:365` validation unchanged.
- **Symphony does not enforce safety.** At most the onboarding skill *flags* (warns, never blocks) a coding repo lacking native agent config. — Evidence: James in-session; `symphony-onboard-project` SKILL.md updated.

## Evidence

- `prompt_renderer.py` — coding branch skips `load_workflow`; clean prompt assembly when body empty.
- `docs/adr/0011-workflow-md-infra-only.md` — the decision record.
- `CONTEXT.md` — Workflow term rewritten (autonomy not safety; infra-mandatory, cli-omitted).
- `tests/test_prompt_renderer_podium.py` — added `test_coding_binding_ignores_workflow_md`, `test_coding_binding_renders_without_workflow_file`.
- `tests/test_trading_podium_dispatch.py`, `tests/test_engine_against_podium.py`, `tests/test_dispatch_compaction.py` — coding-prompt assertions flipped to "WORKFLOW body absent".
- `.claude/skills/symphony-onboard-project/SKILL.md`, `.claude/skills/symphony-workflow-author/SKILL.md` — type-branch + infra-only guard.
- Full suite: 786 passed, 2 skipped after the change.

## Exclusions

- No secrets, env values, or `/home/james/symphony-host.env` contents.
- Restart of `symphony-host.service` not yet performed (live behavior change pending James-approved restart).

## Open Questions And Follow-Ups

- **Restart pending:** the code change alters live dispatch (coding bindings stop rendering WORKFLOW.md). Requires a James-approved `symphony-restart` to take effect on the running scheduler.
- **trading safety migration:** trading had its only safety statement (Trading Safety Boundary) in the now-deleted WORKFLOW.md and has no native `CLAUDE.md`/`AGENTS.md`. Accepted as a test repo; if it ever does live work, migrate that boundary into a native agent-config file.
- **homelab Plane WORKFLOW.md raw copies** in `wiki/raw/workflow-homelab.md` / `wiki/raw/workflow-trading.md` are pre-change snapshots; trading's is now orphaned source.
