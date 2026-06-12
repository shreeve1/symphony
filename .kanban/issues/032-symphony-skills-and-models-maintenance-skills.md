---
id: 032
title: symphony-skills + symphony-models catalog maintenance skills
status: review
blocked_by: [028]
parent: null
priority: 1
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

Two manually-run operator skills for keeping the dropdown catalogs current,
following the #027 repo-local `symphony-*` skill convention
(`.claude/skills/<name>/SKILL.md` + `tests/skills/` coverage). Operator runs
them on demand — catalogs change rarely, so no auto-refresh (deliberate
decision from the grilling session).

**1. `symphony-skills` skill.**

Wraps the existing CLI `python -m web.cli.podium skills refresh`
(`web/cli/podium.py`; scans `SKILL.md` files under `DEFAULT_SOURCE` and
upserts the `skill` table that feeds the new-issue Skill dropdown). The
skill:
- Previews with `--dry-run` first, shows the diff of skills to add/update.
- Runs the live refresh after the operator confirms.
- Reports the resulting catalog (or points at `GET /api/skills`).
- No service restart, no Plane, no `.env` reads.

**2. `symphony-models` skill.**

Edits `models.yml` at the repo root (introduced in #028). Supports:
- list — show current models grouped by agent.
- add — append `{id, agent, [provider], [label]}`; validate `agent ∈
  {pi, claude}` (mirror `config._validate_agent`), reject duplicate `id`,
  keep valid YAML.
- remove — delete by `id`.
Lints the file after edit by **reusing the shared `models.yml` validator
introduced in #028** (valid YAML, every entry has `id` + valid `agent`, no
dup ids) rather than reimplementing validation. Reminds the operator that
the change is git-tracked (suggest commit) and that `preferred_model` stays
free text server-side (C-0058), so an unlisted model still dispatches. No
service action.

Like `symphony-workflow-author` (C-0102), this can be a doc-driven SKILL.md
where the agent edits `models.yml` on disk directly; the shared #028
validator is the lint gate, so no bespoke add/remove helper is required
unless it simplifies the skill.

## Acceptance criteria

- [ ] `.claude/skills/symphony-skills/SKILL.md` exists; documents dry-run → confirm → live `podium skills refresh` flow; no restart/Plane/env-read.
- [ ] `.claude/skills/symphony-models/SKILL.md` exists; documents list/add/remove against `models.yml` with agent validation and YAML lint.
- [ ] `symphony-models` reuses the shared #028 `models.yml` validator; if any add/remove helper is added it has `tests/skills/` coverage (bad agent rejected, duplicate id rejected, round-trip preserves valid YAML).
- [ ] An edit made per the `symphony-models` SKILL.md leaves `models.yml` loadable by the `/options` loader from #028 (cross-check test).
- [ ] Neither skill writes secrets, calls Plane, or restarts a service.

## Verification

```
cd /home/james/symphony && uv run pytest tests/skills/
```

## Blocked by

- #028
