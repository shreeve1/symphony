# Session Capture: real root cause of Claude agent socket deaths — unmocked reaper in test suite

- Date: 2026-06-14
- Purpose: A third issue (#17 "Archive") died the same way. Investigation disproved the OOM hypothesis from the earlier capture and found the true root cause: the test suite reaps live agent tmux sockets. Records the fix and corrects the prior analysis.
- Scope: Root-cause correction (supersedes the OOM mechanism in `2026-06-14-pre-git-pytest-gate-agent-oom.md` / C-0198), the test-isolation fix, and the landing of issue #17's archive fix. Excludes secret env values.

## Durable Facts

- **The kill is NOT OOM.** A single Claude agent (issue #17, no concurrent runs) died ~5s into `uv run pytest -q`; the box had ~20 GiB available; no cgroup memory cap (`MemoryMax=infinity`); no kernel OOM observable (journald restricted, but memory headroom alone refutes OOM). The earlier OOM hypothesis (C-0198) is **disproven**. — Evidence: `free -h`, `systemctl show symphony-host.service`, run 20 timing
- **Real root cause:** `main.run_bindings_loop()` (→ `run_dispatcher`) calls `reap_orphan_claude_sockets()` and `reap_orphan_rpc_processes()` as real side effects at startup. Three tests in `tests/test_main.py` — `test_run_bindings_loop_continues_after_startup_reconcile_transient_failure`, `test_run_bindings_loop_iterates_all_bindings`, `test_rate_limited_binding_does_not_block_other_binding` — call `run_bindings_loop` **without stubbing the reapers** (only `test_run_bindings_loop_reaps_claude_sockets_once_for_multiple_bindings` does). So running the suite globs the shared host `/tmp/symphony-claude-*.sock` and runs real `tmux kill-server`, killing any live Claude agent's own tmux socket. — Evidence: `main.py:150`, `tests/test_main.py:133,278,463`, `claude_runner.py:102-129`
- **Proven empirically:** planted a sentinel `tmux -S /tmp/symphony-claude-sentinel-9999.sock` session; `uv run pytest -q` (777 passed) killed it; bisected to `tests/test_main.py`, then to the three unstubbed tests. After the fix the sentinel survives a full suite run. — Evidence: sentinel experiment this session
- Explains every prior symptom: agents die running the full suite (commit-hook OR voluntary), concurrent agents die together (one suite reaps all sockets), the pi agent (#16) survives (RPC, no tmux socket), subset runs survive (no reaper test collected). The recorded `error connecting to ...sock` remains the capture-after-death artifact (C-0197).
- Issue #17's Claude agent **wrote the correct archive fix** before dying: idempotent migration `0008_fix_issue_archived_check.py` rebuilding `issue` with `'archived'` in the CHECK, `INITIAL_REVISION` bumped to 0008, plus `test_upgrade_repairs_stale_archived_check`. Targeted test green (3 passed). — Evidence: `web/api/migrations/versions/0008_fix_issue_archived_check.py`, `web/api/schema.py`, `tests/test_alembic_baseline.py`

## Decisions

- Fix the hazard at its true root: an autouse fixture in `tests/conftest.py` neutralises both orphan reapers for every test; reaping-assertion tests override with their own stub. This protects any agent (hook or voluntary suite run) from reaping live sockets — broader and more correct than the earlier commit-hook scoping. — Evidence: `tests/conftest.py`, commit `f096476`
- The pre-git hook change (C-0198: Python-scoped pytest gate + in-hook `uv` PATH) is **kept as hygiene** but is **not** the fix for the agent-death hazard; its OOM rationale was wrong. — Evidence: commit `c2c6187`
- Land issue #17's archive fix: committed the code (`b26f31f`); applying migration 0008 to the live `podium.db` is a separate operator step (live DB mutation + possible `podium-api` restart) pending James. — Evidence: commit `b26f31f`

## Evidence

- `tests/conftest.py` — autouse `_no_real_orphan_reap` fixture (the fix)
- `tests/test_main.py:133,278,463` — the three unstubbed `run_bindings_loop` calls
- `main.py:150` — `reap_orphan_claude_sockets()` real call in `run_dispatcher`
- commits `f096476` (test-isolation fix), `b26f31f` (archive migration 0008)
- sentinel experiment: full suite reaped `/tmp/symphony-claude-sentinel-9999.sock` before the fix, not after

## Exclusions

- No values from `/home/james/symphony-host.env`.
- Did not apply migration 0008 to live `podium.db` (operator step; needs approval).
- `web/frontend/tests/inbox.spec.ts` working-tree change and `podium.db.bak.*` files left untouched (unrelated to these fixes).

## Open Questions And Follow-Ups

- **Apply migration 0008 to live `podium.db`** (`uv run alembic upgrade head`), back up first; consider quiescing `podium-api` during the table rebuild; verify live `issue.state` CHECK then includes `'archived'` and archiving works.
- **Detection gap (still open):** `ensure_schema` (C-0147) compares only the alembic revision and missing columns, not CHECK-constraint DDL — it did not catch this drift. Consider a startup DDL/CHECK fingerprint check.
- **Defence in depth:** consider making `reap_orphan_claude_sockets` scope to the current run/PID or guard it behind a service-only flag so production code can never reap unrelated sockets even outside tests.
