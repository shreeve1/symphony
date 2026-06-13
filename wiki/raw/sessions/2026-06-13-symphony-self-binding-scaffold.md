# Session Capture: symphony-binding-scaffold accuracy review + live symphony self-binding

- Date: 2026-06-13
- Purpose: Review `symphony-binding-scaffold` SKILL.md for accuracy, harden it, then use it to create a live Podium binding for the Symphony repo itself.
- Scope: SKILL.md doc gaps and fix; verified `scaffold_podium_binding` behavior (incl. a comment-stripping side effect); the new live `symphony` binding; one superseded claim (C-0066).

## Durable Facts

- `symphony-binding-scaffold` mechanics are sound: `scaffold_podium_binding` exists (`skill_migration.py:53`), `web.api.db.resolve_db_path` exists, `tests/skills/test_binding_scaffold.py` passes (2 tests). — Evidence: `uv run pytest tests/skills/test_binding_scaffold.py`
- The call requires a `PodiumBindingScaffoldRequest` dataclass plus required keyword-only `db_path` and `bindings_path`; `default_agent` must be `pi|claude` and `binding_type` must be `infra|coding`, else `ValueError`. — Evidence: `skill_migration.py:30-93`
- On this host `resolve_db_path()` → `/home/james/symphony/podium.db` (no `PODIUM_DB_PATH` on the unit; `/var/lib/symphony` absent → repo-root fallback). This is the live DB. — Evidence: `web/api/db.py:13-21`, `systemctl show symphony-host.service --property=Environment`
- **Verified side effect:** `scaffold_podium_binding` strips all comments from `bindings.yml`. `_append_binding` does `yaml.safe_load` → mutate dict → `yaml.safe_dump`; PyYAML drops comments on round-trip. Live run deleted 77 lines (the `# Plane rollback tracker_contract:` blocks under `homelab` and `trading`) and reflowed list indentation. Active config data unchanged; only human-only annotation lost; recoverable from `git show HEAD:bindings.yml`. — Evidence: `skill_migration.py:201-215`, `git diff --stat bindings.yml` (33 insertions / 77 deletions)
- The scaffold is dupe-guarded and idempotent: `_insert_binding_row` raises if the name exists in the DB; `_append_binding` raises if it exists in `bindings.yml`; schema creation uses `CREATE TABLE IF NOT EXISTS`. — Evidence: `skill_migration.py:166-215`, `web/api/schema.py:6,14`
- C-0066 is now FIXED: `is_coding = tick_binding is not None and tick_binding.binding_type == "coding"` (`scheduler.py:948`) — keyed off the per-tick binding, not `config.bindings[0].binding_type`. So a `coding` binding resolves correctly even when an `infra` binding (`homelab`) is first in `bindings.yml`. — Evidence: `scheduler.py:948`

## Decisions

- Hardened SKILL.md: added the exact `PodiumBindingScaffoldRequest` call snippet (run from `/home/james/symphony` via `uv run python`), enum values, `db_path`/`bindings_path` resolution, a real DB+yaml verification block (the old "Verification" only ran the tmp-fixture pytest), a `plane_project_id` transitional-field note, and a not-live-until-restart note. — Evidence: `.claude/skills/symphony-binding-scaffold/SKILL.md`
- James chose to bind the Symphony repo itself, live, despite the self-binding risk (agents dispatched here can edit the running scheduler's own source and land commits). — Evidence: this session
- Created live binding `symphony`: `repo_path=/home/james/symphony`, `base_branch=main`, `type=coding`, `default_agent=pi`, `tracker=podium`, `display_name=Symphony`, `plane_project_id=symphony` (transitional). DB row + `binding_settings` (threshold 16000) inserted; `bindings.yml` appended as the 3rd binding. — Evidence: live `podium.db` query, `bindings.yml`
- James chose to leave the stripped `bindings.yml` rollback comments removed (dead Plane rollback data, retained in git). — Evidence: this session

## Evidence

- `.claude/skills/symphony-binding-scaffold/SKILL.md` — the hardened skill doc.
- `skill_migration.py:53-93,166-215` — scaffold helper + lossy yaml round-trip.
- `web/api/db.py:13-52` — db path resolution + `connect`.
- `scheduler.py:948` — fixed per-binding `is_coding`.
- `bindings.yml` — new `symphony` entry; comments now stripped.

## Exclusions

- Did not read or print `/home/james/symphony-host.env`.
- Did not restart `symphony-host.service` (binding not yet live in the running process).
- Did not author a `WORKFLOW.md` for the symphony repo (scaffold stub remains; `symphony-workflow-author` is the follow-up).

## Open Questions And Follow-Ups

- Restart `symphony-host.service` (ask James) to make the `symphony` binding live in the running scheduler.
- Author a real `WORKFLOW.md` for the symphony repo before any smoke/dispatch (`symphony-binding-smoke` refuses on the stub).
- Consider hardening `_append_binding` to preserve comments (e.g. `ruamel.yaml`) or at least warn that it rewrites the whole file, since the skill's own "show the diff before committing" rule is the only current guard against silent comment loss.
- Self-binding caution: monitor any Run dispatched against `symphony`; it can modify scheduler source.
