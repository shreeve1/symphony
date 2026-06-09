---
title: Symphony skills index
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - ~/.claude/skills/symphony-binding-smoke/SKILL.md
  - ~/.claude/skills/symphony-bindings-status/SKILL.md
  - ~/.claude/skills/symphony-onboard-project/SKILL.md
  - ~/.claude/skills/symphony-plane-recover/SKILL.md
  - ~/.claude/skills/symphony-project-scaffold/SKILL.md
  - ~/.claude/skills/symphony-restart/SKILL.md
  - ~/.claude/skills/symphony-troubleshooter/SKILL.md
  - ~/.claude/skills/symphony-workflow-author/SKILL.md
confidence: medium
tags: [skills, claude-code, onboarding, operations, scaffold, smoke, recovery]
---

# Symphony skills index

Eight `symphony-*` Claude Code skills live under `~/.claude/skills/`. Skill files are dotfile-repo content (symlinks into `~/dotfiles/` per the refactor-move plan); CLAUDE.md's Skill Suite section lists their names. This page summarises *what each one does and when to use it*, sourced from the SKILL.md frontmatter descriptions plus the SKILL.md body intros.

## Lifecycle map

```
new repo flow:
  symphony-project-scaffold → symphony-workflow-author → symphony-restart → symphony-binding-smoke
  └── orchestrated by: symphony-onboard-project (umbrella)

recovery:
  symphony-plane-recover (archive / state-fill)

operations / situational awareness:
  symphony-bindings-status (before any change)
  symphony-restart (any service restart)
  symphony-troubleshooter (incident copilot)
```

## Per-skill summary

### `symphony-project-scaffold`

Scaffold a new Plane project and register it in `bindings.yml`. Creates the project in the `homelab` workspace from the standard template (states Todo/In Review/Running/Blocked/Done; labels plan/build/approval-required + agent:claude/agent:pi). Introspects the fresh per-project state/label UUIDs onto the binding, appends a complete entry to `bindings.yml`, drops a `WORKFLOW.md` stub for the human to author. **Live Plane mutation requires explicit typed confirmation.** Preview with `--dry-run`.

Maps to CONTEXT.md's Project Scaffold entry; this is the implementation.

### `symphony-workflow-author`

Replaces the generic `WORKFLOW.md` stub from `symphony-project-scaffold` with a repo-specific dispatch policy. Interviews the operator and renders against the `prompt_renderer.py` contract. **Without a real `WORKFLOW.md`, `prompt_renderer.load_workflow` raises `FileNotFoundError` and every issue is blocked.** Symphony refuses to dispatch — see CONTEXT.md and [prompt-renderer](../concepts/prompt-renderer.md).

### `symphony-restart`

Pre-sanity → ask-then-restart → verify log lines (`symphony_started`, `reconcile_startup_*`, `dispatch_completed`). Wraps the operational ritual James ran 3× during the 2026-06-08 multi-binding rollout. **Refuses to restart silently** — restart is on the must-confirm list per `~/plane/CLAUDE.md`.

Documented in CLAUDE.md "Restart ritual" section.

### `symphony-bindings-status`

Read-only situational awareness. Combines `bindings.yml`, the systemd journal, and Plane reads into one compact table: binding name, project, repo, last reconcile, last dispatch, open issue count. **Safe by construction — no mutations, no env file reads.** Run before any restart, scaffold, smoke, or binding edit.

### `symphony-binding-smoke`

Files a single low-risk smoke ticket on a binding's Plane project, watches the dispatcher loop pick it up, locates the worktree, reports the `SYMPHONY_RESULT` verdict. **Refuses if the binding's `WORKFLOW.md` is still the scaffold stub.** Plane write requires explicit James approval at the moment of action.

Use to prove a freshly bound or freshly authored repo actually dispatches end-to-end.

### `symphony-plane-recover`

Escape hatch for half-built Plane projects. Two subcommands [source: ~/.claude/skills/symphony-plane-recover/SKILL.md]:

- `archive` — archive a Plane project (reversible from Plane UI but visually disruptive). **Typed-slug confirmation required.**
- `state-fill` — idempotent Todo/In Review/Running/Blocked/Done + standard label set.

Codifies the cleanup paths James used after scaffold Bug 1 on 2026-06-08. `bindings.yml` ownership stays with `symphony-project-scaffold`.

### `symphony-onboard-project`

Umbrella that orchestrates the full new-project flow: scaffold → workflow-author → restart → binding-smoke. Checkpoint with James between steps. **Does not bypass any sub-skill's safety gate** — each step still requires its own approval. Trusts each sub-skill's dry-run; no separate umbrella-level dry-run.

### `symphony-troubleshooter`

Real-time diagnostic copilot. Use when Symphony is not dispatching, a Plane ticket is stuck, a binding looks stale, a run failed/blocked, logs look odd, or James wants a future AI session prepped to debug with him. **Actively drives investigation**, not just context-gathering: collect evidence, explain, hypothesis list, focused questions, recommend next safe action, hand off mutations to the proper Symphony skill.

## Safety pattern across the suite

Every mutating skill requires explicit approval at the moment of action; every gated skill names its gate:

| Skill | Gate |
|---|---|
| `symphony-project-scaffold` | typed slug confirmation; `--dry-run` preview available |
| `symphony-plane-recover archive` | typed slug confirmation |
| `symphony-restart` | James must confirm at the restart step |
| `symphony-binding-smoke` | James approval at Plane-write moment; refuses on stub `WORKFLOW.md` |
| `symphony-workflow-author` | interactive; produces file diffs for review before writing |
| `symphony-bindings-status` | read-only by construction |
| `symphony-troubleshooter` | read-only; hands off any mutation |
| `symphony-onboard-project` | composes the above; preserves each step's gate |

This is consistent with `~/symphony/CLAUDE.md`'s Safety section ("Ask James before `systemctl restart`, `stop`, unit edits, Plane API mutations, or smoke ticket requeues unless he has already approved that exact live mutation").

## Where SKILL.md files live

Skill files are symlinks into `~/dotfiles/` per the refactor-move plan. Each `symphony-*` directory under `~/.claude/skills/` has:

- `SKILL.md` — entry point with frontmatter description and body
- (subdir) various `Workflows/`, helper scripts, or assets as needed

Skills are loaded into Claude Code via the harness. CLAUDE.md's Skill suite section enumerates them with one-line summaries.

## Notes

- Skill content is **not** mirrored into `wiki/raw/` because:
  - they live in a separate repo (`~/dotfiles/`), not the Symphony tree
  - their frontmatter descriptions are already reproduced verbatim in CLAUDE.md and in Claude Code's runtime skill listing
  - the operational gate language is the durable bit; this index captures it
- For deep questions about a specific skill, read its SKILL.md directly — this page is the orientation layer, not the source of truth.

## Related

- [Symphony operations](../concepts/symphony-operations.md) — restart ritual, smoke evidence
- [homelab Binding](../entities/binding-homelab.md), [trading Binding](../entities/binding-trading.md) — the targets these skills operate on
- [Plane CLAUDE.md safety policy] — `~/symphony/CLAUDE.md` is the policy these skills implement
