# Session Capture: pre-git pytest gate OOM-killed concurrent live agents

- Date: 2026-06-14
- Purpose: Diagnose why both `symphony`-binding issues (#14 "Column changing", #15 "Inbox") failed, and harden the pre-git hook so agent commits can no longer kill the live agent fleet.
- Scope: Root cause of the dual failure; the surgical hook fix applied; a separately-verified live archive bug surfaced during diagnosis (root cause only, fix deferred). Excludes secret env values.

## Durable Facts

- Symphony Run failures recorded in `comments_md` as `error connecting to /tmp/symphony-claude-<issue>-<nonce>.sock (No such file or directory)` are a **misleading artifact**, not the real agent error. The runner captures stderr via tmux `capture-pane` *after* the tmux server is already gone, so the message reflects the dead socket, not why the agent stopped. There is no `pipe-pane` logging, so the real agent error is lost. — Evidence: `claude_runner.py:305-314`, `runs/13.log`, `runs/14.log`
- Issues #14 (run 13) and #15 (run 14), both `agent=claude` `model=claude-opus-4-8` on the `symphony` binding (cwd `/home/james/symphony`, the live repo), were **killed within one second of each other (14:09:08/09 UTC)** with exit 137 (SIGKILL), `timed_out=false`, despite starting 52s apart. Both agents were mid-tool-use doing correct work, not crashing. — Evidence: journal `claude_runner agent_exited issue_id=14/15 exit_code=1 ... timed_out=false`; transcripts `/home/james/.claude/projects/-home-james-symphony/911e344f-*.jsonl`, `12019815-*.jsonl`
- Trigger chain: issue #15's agent tried `git commit` (frontend-only: `Sidebar.tsx`, `inbox.spec.ts`, **zero Python staged**). The pre-git hook ran `uv run pytest` but `uv` was not on the dispatch PATH (`symphony-host.service` inherits systemd's default PATH, omitting `~/.local/bin`), so the hook errored `uv: command not found`. The agent worked around the broken hook by hand-rolling `export PATH=... && uv run pytest -q` — the full, unbounded suite — inside its live tmux session. That suite under two concurrent live Opus agents exhausted resources → SIGKILL of both agent processes. — Evidence: transcript of session `12019815-...` tool_use at 14:09:04 with `Exit code 137`; `bash: uv: command not found` from the hook block message
- No app-level cause: `NRestarts=0`, MainPID unchanged (3713404), no `claude_socket_reaped` lines in journal, and the reap tests inject mocks (`tests/test_claude_runner.py:184,203`) so pytest does not touch real `/tmp` sockets. The kill was external (resource pressure). — Evidence: `systemctl show symphony-host.service`, journal grep, `tests/test_claude_runner.py`
- Separately verified during diagnosis: live `podium.db` `issue.state` CHECK constraint is `('todo','in_review','running','blocked','done')` — it **omits `'archived'`** — while `alembic_version='0007_add_run_session_tracking_columns'`. Migration `0004_archived_state` (which rebuilds `issue` to add `'archived'`) never materialized against this DB. Setting `state='archived'` raises `CHECK constraint failed`, surfacing as a 500 and a silent UI revert — this is issue #14's "change status / archive does nothing" complaint. This is a new instance of the stamp-vs-run drift documented in C-0145; C-0147's startup guard only catches *missing columns*, not a CHECK-constraint difference, so it went undetected. — Evidence: `sqlite3 -readonly podium.db` schema + `alembic_version`, `web/api/migrations/versions/0004_archived_state.py`, `0006_drop_max_duration_seconds.py` (direct `DROP COLUMN`, no CHECK rebuild), transcript of session `911e344f-...` ("CHECK constraint failed ... lacks 'archived'")

## Decisions

- Fix hazard #3 (agents running the full suite in the live repo and killing the fleet) with a **surgical hook-only change**, not worktree isolation or systemd resource caps. James chose "Surgical hook fix". — Evidence: AskUserQuestion answer this session
- Edit confined to `.claude/hooks/pre-git-checks.sh`: (1) resolve `uv` via `~/.local/bin` inside the hook so it never errors into an agent workaround; (2) gate `uv run pytest` on Python actually changing — staged files for `git commit`, files in unpushed commits (`@{u}..HEAD`) for `git push`, so the push gate is not weakened. No service/unit/DB change, no restart (PreToolUse hooks read the `.sh` fresh per invocation, so the fix is live immediately). — Evidence: `.claude/hooks/pre-git-checks.sh` diff

## Evidence

- `.claude/hooks/pre-git-checks.sh` — the hardened hook (uv PATH resolution + Python-scoped pytest gate)
- `claude_runner.py:305-314` — failure stderr captured by `capture-pane` after session death
- `runs/13.log`, `runs/14.log` — both contain only the socket-connect artifact
- `podium.db` (read-only) — live `issue.state` CHECK lacks `'archived'`; `alembic_version=0007`
- transcripts `911e344f-...jsonl` (issue #14, found archive root cause), `12019815-...jsonl` (issue #15, ran the killing pytest)

## Exclusions

- No values from `/home/james/symphony-host.env` were read or recorded.
- Did not commit issue #15's orphaned frontend edits (`Sidebar.tsx`, `inbox.spec.ts`) — that completed-but-uncommitted work is a separate operator decision (#2), left in the working tree.
- Did not apply the archive-bug DB fix (#1) — root cause only; deferred to James's decision.

## Open Questions And Follow-Ups

- **#1 (open):** Repair the live `issue.state` CHECK to include `'archived'` (manually rebuild the table per 0004's DDL; alembic is stamped past 0004 and will not re-run it). This unblocks the original archive/status complaint.
- **#2 (open):** Decide whether to commit or discard issue #15's completed frontend edits sitting in the live working tree.
- **Detection gap:** C-0147's missing-column startup guard does not catch CHECK-constraint drift. Consider extending the startup pragma diff to compare CHECK definitions, or run `uv run alembic upgrade head` reconciliation differently.
- **Residual risk:** the hook fix bounds but does not eliminate RAM pressure when two Python-touching commits run their suites at once; worktree isolation + concurrency/MemoryMax caps remain the deeper structural fix (descoped this session).
