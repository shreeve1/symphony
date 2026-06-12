---
id: 015
title: Podium skill catalog — table + CLI refresh from ~/.claude/skills
status: done
blocked_by: [012a]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Make the `preferred_skill` chip drop down to a real catalog instead of a
hand-seeded list. Catalog is operator-curated (refreshed by a CLI, not
auto-discovered on each request — see CONTEXT.md `[[Skill]]`).

Schema (Alembic migration adds `skill` table if missing):

```
skill(name pk, description, source)
```

`source` is the absolute path to the SKILL.md (or empty string for hand-seeded).

CLI:

- `web/cli/podium_skills.py` (entry point also exposed as `python -m web.cli.podium skills refresh`)
- `podium skills refresh --dry-run` prints (name, description, source) for every
  SKILL.md under `~/.claude/skills/`, no DB writes; exit 0.
- `podium skills refresh` upserts into `skill` table, prints a diff
  (`+ added`, `~ changed`, `- removed`).
- `--source ~/.claude/skills` flag allows overriding the scan root for tests
  and CI. The default (`~/.claude/skills/`) assumes the operator's dotfiles
  layout — acceptable for this single-operator system; CI passes
  `--source web/api/tests/fixtures/skills`.

Frontend:

- `GET /api/skills` returns the catalog rows ordered by `name`.
- `preferred_skill` dropdown in the issue flyout (S013) and new-issue modal
  (S014) populates from `/api/skills` instead of the fake seed.
- Empty catalog renders an inline hint: "Run `podium skills refresh` to
  populate."

## Acceptance criteria

- [x] `python -m web.cli.podium skills refresh --dry-run --source web/api/tests/fixtures/skills` prints exactly the fixture skills (test fixture has 3 SKILL.md files).
- [x] Same command without `--dry-run` populates the `skill` table with 3 rows; second invocation is idempotent (no duplicates).
- [x] Removing a fixture file and re-running marks `- removed`; row is deleted from `skill`.
- [x] `GET /api/skills` returns the rows sorted by `name`.
- [x] Playwright `skill-catalog.spec.ts` confirms the dropdown in the issue flyout shows real catalog entries (test seeds 2 known skills before navigating).
- [x] `web/cli/tests/test_skills_refresh.py` covers add / no-op / change / remove cases.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Blocked by

- #012

## Notes

- #014 changed boot seeding to `INSERT OR IGNORE` over `SEED_SKILLS`
  (`web/api/seed.py:_seed_skills`), so any seed skill missing from the table
  is re-inserted on every boot. A catalog refresh that deletes a stale seed
  row will see it resurrected at next startup, and changed seed descriptions
  are never rewritten. This slice must retire `SEED_SKILLS`/`_seed_skills`
  (or transfer table ownership to the refresh CLI) when the real catalog
  lands — emptiness checks are no longer a valid signal.
