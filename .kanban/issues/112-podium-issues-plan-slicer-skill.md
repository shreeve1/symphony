---
id: 112
title: Skill — repurpose /podium-issues into a plan→Podium slicer (no folder scan)
status: in-progress
blocked_by: [107]
locks: [skills]
priority: 2
created: 2026-06-23
updated: 2026-06-24
actor: ralph
---

## What to build

Per ADR-0021 Update (3). Collapse the two-step authoring (`/to-issues` writes
`.kanban`, then `/podium-issues` mirrors the folder) into a single skill that
slices a plan straight into Podium. Target chain: `grill-me → dev-plan →
podium-issues`.

- **Repurpose `/podium-issues`** (`~/.claude/skills/podium-issues/SKILL.md`) from a
  folder mirror into a **plan slicer**, reusing `to-issues`' slicing rules
  (vertical tracer-bullet slices; explicit, objectively-checkable acceptance
  criteria; repo-correct verification command; dependency order). The sink is
  Podium, not `.kanban` files — no folder scan.
- Resolve the target binding from cwd (same `tracker: podium` + `repo_path` match
  the current mirror uses). No match → exit non-zero with available bindings.
- Create issues **in dependency order (blockers first)** via the create path (107),
  capturing each new Podium issue id so a dependent's `blocked_by` references real
  ids. Set `locks` labels inline per slice. No kanban-id translation.
- Quiz step (granularity / dependencies / verifiability) is preserved — but note
  Symphony runs unattended, so this skill is operator-authoring-time, not in the
  dispatch loop.
- **Retire the old folder-mirror skill.** Operator confirmed no folder mirroring,
  so the previous kanban→Podium mirror behavior is removed (delete or fold away the
  `import-kanban` SKILL content). Drop any `/to-issues` auto-chain reference to it.
  `/to-issues` + `.kanban` remain only for the unrelated Ralph local-coding loop.

## Acceptance criteria

- [ ] `/podium-issues` slices a plan in context into Podium issues directly, no
      `.kanban` files written, no separate mirror step.
- [ ] Dependent slices get `blocked_by` populated with real Podium ids; `locks`
      labels are set per slice.
- [ ] Binding resolves from cwd; no-match exits non-zero with the binding list.
- [ ] The old folder-mirror behavior is removed; no kanban→Podium scan remains.

## Verification

`PATH="$HOME/.local/bin:$PATH" uv run pytest web/cli/tests/test_podium_issues.py -q`
