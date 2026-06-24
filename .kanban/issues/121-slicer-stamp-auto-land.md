---
id: 121
title: Skill — /podium-issues slicer stamps auto_land=true on created issues
status: pending
blocked_by: [112, 115]
locks: [skills]
priority: 2
created: 2026-06-24
---

## What to build

Per ADR-0023, make the `/podium-issues` plan→Podium slicer (112) mark every issue it
creates as auto-land-eligible, so the review phase (119) may unattended-merge them on
a passing review. This ties "slicer-authored ⇒ guaranteed runnable `## Verification`
⇒ trustworthy auto-land" together.

- In `~/.claude/skills/podium-issues/SKILL.md`, set `auto_land: true` on the
  create-API payload for **every** issue the slicer creates (alongside the
  `blocked_by`/`locks` it already writes via the create path 115 extends).
- Reinforce in the skill prose that each slice's `## Verification` must be a real,
  runnable command — the review phase's driver backstop (120) re-runs it, and a
  prose-only verification means auto-land rests on the reviewer's judgment alone.
- Operator/UI-created issues are untouched: they never set `auto_land`, stay `false`,
  and keep the operator merge gate.

## Acceptance criteria

- [ ] Issues created by `/podium-issues` carry `auto_land = true` (verify via the GET
      payload / `web.cli.podium issues`).
- [ ] The skill prose ties auto-land to a mandatory runnable `## Verification`.
- [ ] Operator/UI-created issues remain `auto_land = false`.

## Verification

Prose (skill, no unit harness): run the slicer on a sample plan from a repo with a
`tracker: podium` binding; confirm created Podium issues have `auto_land = true`
(`GET /api/bindings/{name}/issues` or `python -m web.cli.podium issues`), and a
manually UI-created issue is `false`.
