# WORKFLOW.md is infra-only autonomy policy; coding bindings ignore it

## Status

accepted

## Context

Symphony began as a homelab infra ticketing/response system and has grown into a CLI-first issue tracker as well. Those are two operating models on one engine, and the `binding_type` axis (`infra` vs `coding`) already separates most of their behavior: coding bindings skip the schedule, blocked reconciler, approval gate, and landing — the agent owns its own git and each issue reads like a prompt typed into a CLI.

One thing did *not* split. `render_prompt` read `WORKFLOW.md` for **every** binding (`prompt_renderer.py`), and a missing/unreadable file was a hard `workflow-missing` block at dispatch (`scheduler.py`). For a coding binding this means the repo's autonomy-policy preamble is prepended to the top of every fresh dispatch — and, because that prompt seeds the agent's native CLI session, it lingers in the conversation for the life of the issue. For an "issue is the prompt" model that is noise that pollutes the session.

Two conflations drove the original design and are now rejected:

1. **WORKFLOW.md as "the whole policy."** It was treated as the single per-repo policy file. In practice it carries *autonomy* instruction (how to operate under Symphony's orchestration: patrol lifecycle, plan/build/execute, completion contract) — which only an orchestrated infra binding needs.
2. **WORKFLOW.md as a safety net.** Some bindings (e.g. `trading`) parked safety rules there. Safety is **not Symphony's responsibility.** It belongs to the bound repo, expressed in the repo's native agent config (`CLAUDE.md`/`AGENTS.md`) and owned by whoever manages that project. Symphony stays strict to its job: dispatch issues, scrape verdicts, run the autonomy lifecycle for infra.

## Decision

`WORKFLOW.md` is **infra-only autonomy policy**:

- **Infra bindings**: `WORKFLOW.md` is mandatory and rendered on every fresh dispatch, exactly as before. A missing file is still a hard config error.
- **Coding bindings**: Symphony **never reads** `WORKFLOW.md` — not optional, *ignored*. `render_prompt` skips `load_workflow` when `binding_type == "coding"` and assembles the prompt from the issue (+ comments/context on the re-feed floor) + the `OUTPUT_CONTRACT` only. The output contract is a renderer constant, independent of `WORKFLOW.md`, so verdict scraping survives.

Safety and repo conventions for a coding binding come from the repo's native agent config, which the in-checkout agent reads itself — not from a Symphony-rendered file.

## Considered Options

- **Make WORKFLOW.md optional for coding (read if present).** Rejected: "read if present" reintroduces the pollution and creates a silent surprise — a stray `WORKFLOW.md` would change dispatch behavior for no visible reason. *Ignored* is predictable; *optional* is a trap.
- **Keep WORKFLOW.md mandatory everywhere, just trim its content for coding.** Rejected: still pays the session-pollution cost and still pretends Symphony owns per-repo coding policy. The agent's native config is the CLI-native home for that.
- **Have Symphony enforce safety (scan/guard) at dispatch.** Rejected: out of scope. Symphony stays narrow. At most the onboarding skill *flags* (warns, does not block) when a coding repo has no `CLAUDE.md`/`AGENTS.md`.

## Consequences

- **Order of operations matters.** The code change (skip the read) must land before deleting any coding repo's `WORKFLOW.md`; deleting first would block dispatch on the old code path. Done in this change: `prompt_renderer.py` updated, then `WORKFLOW.md` removed from the `symphony` and `trading` repos.
- **Skill flow branches on type.** `symphony-onboard-project` runs `symphony-workflow-author` only for infra bindings; `symphony-workflow-author` becomes infra-only. `symphony-binding-scaffold` is unchanged (already `binding_type`-parameterized).
- **Safety-migration hazard.** A coding repo that parked safety rules only in `WORKFLOW.md` loses them on deletion unless migrated to `CLAUDE.md`/`AGENTS.md` first. `trading` is a test repo, accepted; future coding onboards get the flag at bind time.
- Supersedes the CONTEXT.md framing of WORKFLOW.md as "the whole policy" and "mandatory" for all bindings.
