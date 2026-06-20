# Session Capture: ADR-0015 gated podium-api window applied (full parity)

- Date: 2026-06-20
- Purpose: Execute the gated `podium-api` window that unblocks Wave C of plan 59 (Temporal patrols → Podium). Every live mutation operator-gated; James scheduled and confirmed.
- Scope: The prerequisites only (migration 0009 apply, podium-api restart, symphony-host restart) + verification. NOT Wave C (`worker.py` cutover) — explicitly deferred.

## Durable Facts

- **Migration 0009 (`0009_issue_external_id`) applied to live `podium.db`.** `alembic current` advanced `0008_fix_issue_archived_check` → `0009_issue_external_id (head)`; live `issue` table now has the `external_id` column + UNIQUE index `ix_issue_external_id`. Pre-apply state had neither (confirmed inert). — Evidence: `uv run alembic -c alembic.ini current`; `PRAGMA table_info(issue)` / `PRAGMA index_list(issue)`.
- **Correct alembic invocation is `uv run alembic -c alembic.ini upgrade head` — config is at repo ROOT (`/home/james/symphony/alembic.ini`), NOT `web/api/alembic.ini`** (the handoff path was wrong; `-c web/api/alembic.ini` fails with "No 'script_location' key found"). Root `alembic.ini`: `script_location = web/api/migrations`, `sqlalchemy.url = sqlite:///podium.db`. — Evidence: `grep script_location alembic.ini`.
- **Pre-migration backup taken via `scripts/podium-backup.sh` → `/backup/podium-2026-06-20.db`** (840k, rev `0008`, no `external_id`) — clean restore point. Script writes to `/backup` silently on success (no stdout). — Evidence: `sqlite3 /backup/podium-2026-06-20.db "SELECT version_num FROM alembic_version"`.
- **`podium-api.service` restarted onto Wave B code.** New PID, `active`, startup complete. `GET /api/bindings/homelab/issues?external_id=zzz` returns HTTP 200 `[]` (param accepted/filterable, NOT 422) — confirms Wave B endpoint live (external_id accept/persist/filter, UNIQUE→409). — Evidence: live HTTP probe via self-minted session cookie.
- **`symphony-host.service` restarted onto new code (full parity).** Ritual log lines all present: `symphony_started service=symphony code_sha=d7207f4 bindings=5`, `reconcile_startup_completed cleaned=0` (all 5 bindings), `dispatch_completed dispatched=false reason=no-candidates`. — Evidence: `journalctl -u symphony-host.service`.
- **Marker-first reconciler cure (Wave B) is live and behaving.** On startup the reconciler emitted `blocked_reconciler blocked_reconcile_skipped issue_id=61 external_id= reason=no-matching-rule` — it inspected the homelab blocked issue, saw empty `external_id` (UI-created, not a patrol id), and correctly skipped. — Evidence: `journalctl -u symphony-host.service`.
- **`homelab` binding healthy and unchanged** through the window: states `{blocked:1, archived:1}` before and after. Bindings list: `ai-web-chat, dotfiles, n8n, symphony, homelab`. — Evidence: `GET /api/bindings`, `GET /api/bindings/homelab/issues`.
- **Benign-but-noisy startup warning surfaced:** podium-api logs `podium_schema_revision_mismatch db=0009_issue_external_id code=0008_fix_issue_archived_check; refusing to stamp` on every startup. Cause: Wave B added `external_id` to `SCHEMA_SQL` and shipped migration 0009 but left `INITIAL_REVISION = "0008_fix_issue_archived_check"` (`web/api/schema.py:3`). Non-fatal — `ensure_schema` only warns on revision mismatch, and `_schema_drift` finds no MISSING column (live DB now has `external_id`), so startup completes. Migration is idempotent so a fresh-DB `upgrade head` is also harmless. Follow-up nit: bump `INITIAL_REVISION` to `0009_issue_external_id` to silence. — Evidence: `journalctl -u podium-api.service`; `web/api/main.py:424-476` (`ensure_schema`), `web/api/schema.py:3`.
- **Step ordering is load-bearing, proven by code:** restarting `podium-api` with Wave B code BEFORE applying the migration would CRASH startup — `ensure_schema` → `_schema_drift` would find `external_id` MISSING and raise `RuntimeError`. So migration (step 2) MUST precede the podium-api restart (step 3). — Evidence: `web/api/main.py:464-470`.

## Decisions

- **Scope = full parity (migration + podium-api restart + symphony-host restart).** James chose "Full parity (1+2+3+4)" over "Minimal (1+2+3)" at the gate. — Evidence: this session (AskUserQuestion gate).
- Per C-0267, NO new binding scaffolded and NO new WORKFLOW.md authored — patrols route to the existing `homelab` binding.

## Evidence

- `/backup/podium-2026-06-20.db` — pre-migration restore point (rev 0008).
- `journalctl -u podium-api.service` / `-u symphony-host.service` — restart + ritual + reconciler evidence.
- `web/api/schema.py:3`, `web/api/main.py:424-476` — INITIAL_REVISION / ensure_schema drift behavior.

## Exclusions

- `/home/james/symphony-host.env` never read or printed (secrets).
- Session cookie was minted locally from the configured secret for read-only probes; secret value never printed.
- Working-tree had unrelated dirty docs (`CLAUDE.md` modified, untracked `CLAUDE_1.md`) from a concurrent session — docs-only, irrelevant to this window, left untouched.

## Open Questions And Follow-Ups

- **Wave C** (NOT this session): wire `worker.py` → `PodiumAdapter(binding="homelab")`, add `PATROL_TRACKER=podium|plane` toggle, set patrol-worker host env (Podium base URL + token + `binding=homelab`), dry-run a patrol cycle, restart `homelab-temporal-patrol-worker.service`. Resume via `/dev-build /home/james/homelab/plans/59.md` (Wave C).
- Follow-up nit: bump `INITIAL_REVISION` to `0009_issue_external_id` to silence the per-startup `podium_schema_revision_mismatch` warning.
