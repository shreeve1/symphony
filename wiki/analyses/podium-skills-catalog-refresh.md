---
title: Podium skill catalog refresh — CLI semantics, FK hazard, first live run
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-18
sources:
  - web/cli/podium_skills.py
  - web/cli/podium.py
  - web/api/seed.py
  - .claude/skills/symphony-skills/SKILL.md
  - wiki/raw/sessions/2026-06-12-podium-skills-catalog-refresh.md
  - wiki/raw/sessions/2026-06-18-podium-skills-refresh-32-row-catalog.md
confidence: high
tags: [podium, skills, catalog, cli, sqlite, foreign-key, operations]
---

# Podium skill catalog refresh — CLI semantics, FK hazard, first live run

First operator-confirmed live run of `python -m web.cli.podium skills refresh` (2026-06-12, via the `symphony-skills` skill) populated the Podium Skill dropdown and surfaced three durable behaviors of the refresh CLI. [source: wiki/raw/sessions/2026-06-12-podium-skills-catalog-refresh.md]

## Dry-run is a catalog listing, not a diff

`--dry-run` returns the full scanned catalog as `name\tdescription\tsource` TSV lines (`_format_record`). The `+`/`~`/`-` change markers exist only on the live path: `_apply_refresh` computes them while mutating the DB. [source: web/cli/podium_skills.py#L84-L85] [source: web/cli/podium_skills.py#L121-L140]

`.claude/skills/symphony-skills/SKILL.md` workflow step 2 wrongly describes dry-run output as `+`/`~`/`-` lines. To preview the real diff today, compare `scan_skills()` output against the `skill` table read-only (done in-session), or accept the live run's printed markers as the after-the-fact record. Follow-up: fix the SKILL.md wording or make dry-run compute a true diff. [source: .claude/skills/symphony-skills/SKILL.md]

## Single-source scan contract

Default source is `~/.claude/skills` (`DEFAULT_SOURCE`) — on aidev a symlink to `/home/james/dotfiles/.claude/skills`. Repo-local `/home/james/symphony/.claude/skills/` (eleven `symphony-*` skills) is not scanned, so symphony-* skills are absent from the dropdown. [source: web/cli/podium_skills.py#L19]

Refresh deletes every file-backed row absent from its own scan, so two sequential runs with different `--source` values clobber each other — there is no additive mode. Cataloging dotfiles plus repo-local skills requires a combined source directory or a code change. [source: web/cli/podium_skills.py#L135-L141]

## FK deletion hazard and atomic rollback

`issue.preferred_skill TEXT REFERENCES skill(name)` blocks the stale-row `DELETE`: the first live run aborted with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` because 12 throwaway e2e issues (homelab, ids 5–16) referenced the legacy `/diagnose` seed row. The failure is clean — commit happens only after `_apply_refresh` returns, so the whole run rolled back with no partial writes (verified: 7 pre-refresh rows intact). Resolution, operator-approved: repoint the 12 issues to `diagnose`, rerun. [source: web/cli/podium_skills.py#L141] [source: wiki/raw/sessions/2026-06-12-podium-skills-catalog-refresh.md]

Manual-row protection (`source = ''`) covers deletion only; the upsert overwrites any existing row whose name matches a scanned skill. The manual `diagnose` row was converted to file-backed this run. Operator-curated rows survive only if their names never collide with scanned skills. [source: web/cli/podium_skills.py#L138]

## Skill seeding is retired

`web/api/seed.py` no longer has `_seed_skills`/`SEED_SKILLS`; seeding covers bindings/issues/runs only, gated on an empty `binding` table. Removed seed rows (e.g. `/diagnose`) stay removed across `podium-api` restarts — the refresh CLI now owns the `skill` table, which resolves the C-0055 resurrection warning. [source: web/api/seed.py]

## Resulting catalog state (2026-06-12)

50 rows after refresh: 44 added from dotfiles, 4 updated (`blueprint`, `code-review`, `diagnose`, `tdd`), `/diagnose` seed removed, manual rows `catalog-alpha`/`catalog-bravo` initially untouched. Post-run: zero pending diff vs scan; `uv run pytest tests/skills/test_catalog_maintenance_skills.py` 6 passed. [source: wiki/raw/sessions/2026-06-12-podium-skills-catalog-refresh.md]

Same evening, James flagged `catalog-alpha`/`catalog-bravo` in the dropdown: they were leaked Playwright e2e fixtures, not operator rows. An older `seedSkills` version wrote them with `source=''` into the live DB (fixture strings traceable to `web/frontend/tests/skill-catalog.spec.ts`, commit `6d9f1c6`), and the `source=''` value made the refresh treat them as protected manual rows. Deleted after confirming zero FK references — final state 48 rows, zero manual rows. Current `web/frontend/tests/fixtures.ts` is isolated: `PODIUM_DB_PATH` → `web/test-results/podium-e2e.db`, rows tagged `source='e2e'` (which a live refresh would auto-delete if ever leaked, since `'e2e'` is neither manual nor in scan). [source: web/frontend/tests/fixtures.ts] [source: web/frontend/tests/skill-catalog.spec.ts]

On 2026-06-18, another operator-confirmed live refresh updated the catalog to match the then-current default scan: `netbird-troubleshoot` and `tralph-merge` were added; seventeen stale file-backed rows were removed (`architecture-review`, `blueprint`, `changelog`, `code-review`, `design`, `discover`, `explore`, `gap-sweep`, `implement`, `omp-config`, `plan`, `question`, `research`, `revise`, `rpiv-merge`, `rpiv-monitor`, `triage-issue`, `validate`). A read-only FK preflight found no `issue.preferred_skill` blockers before deletion; post-refresh diff was empty with `scanned=32 existing=32`; `uv run pytest tests/skills/test_catalog_maintenance_skills.py` passed 7 tests. No service restart, Plane call, or env/secret read occurred. [source: wiki/raw/sessions/2026-06-18-podium-skills-refresh-32-row-catalog.md]

## Follow-ups

- Fix `symphony-skills` SKILL.md step 2 dry-run description.
- Decide whether `symphony-*` repo-local skills belong in the dropdown; if yes, add multi-source or combined-dir support.
- Consider graceful FK-referenced stale-row handling (skip + warn) instead of whole-run abort.
- Consider protecting manual rows from upsert overwrite if curated descriptions matter.
