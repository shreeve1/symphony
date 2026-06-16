# Session Capture: trading Binding Offboard (purge)

- Date: 2026-06-15
- Purpose: Offboard the `trading` Podium binding via `/symphony-offboard-project trading`; record the first live purge-mode teardown and the resulting live-binding set.
- Scope: binding teardown facts, purge counts, restart evidence, and the doc-staleness follow-ups. Excludes secrets and unrelated in-progress code that happened to go live in the same restart.

## Durable Facts

- The `trading` binding was offboarded on 2026-06-15. Mode was **purge** (`purge=True`), chosen by James over the default archive. The 1 issue + 1 run of history were disposable. — Evidence: `/symphony-offboard-project` session; `skill_migration.remove_podium_binding`
- Pre-teardown state: `binding.archived=0` (active), `type=coding`, issues=1, runs=1, `bindings.yml` entry present. — Evidence: pre-flight SQL against `web.api.db.resolve_db_path()` → `/home/james/symphony/podium.db`
- `remove_podium_binding("trading", purge=True)` returned `PodiumBindingRemovalResult(binding_name='trading', removed_from_bindings_yml=True, db_action='deleted', deleted_issue_count=1, deleted_run_count=1)`. — Evidence: session command output
- Purge deletes the binding's Runs, Issues, `binding_settings`, and `binding` row, and drops the `bindings.yml` entry. It is irreversible except from a `podium.db` backup. — Evidence: `symphony-binding-remove` SKILL.md; result shape above
- After `sudo systemctl restart symphony-host.service` (PID 988767, started 2026-06-15 05:17:20 UTC, `code_sha=48ca8c2`), the live binding set is **2: homelab, symphony** — `trading` is gone. — Evidence: `symphony_started ... bindings=2`; `reconcile_startup_begin/done` only for homelab + symphony
- Live bindings as of 2026-06-15 after offboard: `homelab` (infra), `symphony` (coding self-binding). `trading` no longer dispatched. — Evidence: restart journal
- Restart was healthy: `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, dispatch loop alive (`dispatch_completed dispatched=false reason=no-candidates`), zero ERROR/Traceback. — Evidence: restart journal

## Decisions

- James chose **purge over archive** for trading offboard; the 1 issue / 1 run history was confirmed disposable. — Evidence: AskUserQuestion answer this session
- James approved the restart despite a dirty working tree (uncommitted WIP in `web/api/main.py`, `seed.py`, new `web/api/files.py` feature, frontend) and stale running sha (`ac22602` → disk head `48ca8c2`), knowingly bringing that WIP live. — Evidence: AskUserQuestion answer this session

## Evidence

- `bindings.yml` — trading block (name/type/tracker/plane_project_id/repo_path/base_branch/default_agent/pi_mode/approval/landing) removed; backup at `/tmp/bindings.yml.pre-offboard-trading`.
- `podium.db` — trading binding/issue/run rows deleted.
- Restart journal for PID 988767 — `symphony_started bindings=2`, reconcile pair per binding, dispatch liveness.

## Exclusions

- No secrets from `/home/james/symphony-host.env`.
- Unrelated in-progress code (files-browser feature, frontend edits, wiki edits) that went live in the same restart is out of scope for this capture beyond noting it was deployed.

## Open Questions And Follow-Ups

- `/home/james/symphony/CLAUDE.md` "Live bindings" table still lists `trading`; now stale (source of truth `bindings.yml` no longer has it). Update pending — not done in this session (out of wiki scope).
- `entities/binding-trading.md` now describes a removed binding; updated with an offboard status banner this session.
