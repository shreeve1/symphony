---
title: Pre-git pytest gate OOM-killed concurrent live agents (issues #14/#15)
type: analysis
status: promoted
created: 2026-06-14
updated: 2026-06-14
sources:
  - wiki/raw/sessions/2026-06-14-pre-git-pytest-gate-agent-oom.md
  - wiki/raw/sessions/2026-06-14-claude-agent-socket-reap-root-cause.md
  - .claude/hooks/pre-git-checks.sh
  - tests/conftest.py
  - tests/test_main.py
  - claude_runner.py
  - web/api/migrations/versions/0004_archived_state.py
confidence: high
tags: [pre-git-hook, pytest, uv, claude, dispatch, live-repo, alembic, drift, archived, failure-mode, reaper, test-isolation, tmux-socket]
---

# Claude agent socket deaths on `uv run pytest` (issues #14/#15/#17)

> **CORRECTION (2026-06-14, C-0200):** the original OOM root cause below is **DISPROVEN**. A third
> failure (#17, a *single* agent with 20 GiB free) reproduced the death, and a sentinel experiment proved
> the **test suite reaps live agent tmux sockets**. The true root cause and fix are in the section
> **"Real root cause: the suite reaps live sockets"** at the bottom. The OOM narrative is retained for the
> record but is wrong. The pre-git hook change is kept as hygiene, not as the hazard fix.

## Summary (original, OOM hypothesis — superseded)

Both `symphony`-binding issues dispatched 2026-06-14 — #14 "Column changing" and #15 "Inbox" — failed with the
recorded reason `error connecting to /tmp/symphony-claude-*.sock`. That reason is a **diagnostic artifact**, not the
cause (this part stands — C-0197). The originally-hypothesised cause — a full-suite memory spike OOM-killing the
agents — was **wrong**; see the correction section below.

## Failure chain

1. Issue #15's agent (cwd `/home/james/symphony`, the **live repo**, `worktree_active=false`) staged a
   **frontend-only** change (`Sidebar.tsx`, `inbox.spec.ts` — zero Python) and ran `git commit`.
2. The `pre-git-checks.sh` `PreToolUse` hook unconditionally ran `uv run pytest` over the **full suite**, regardless
   of what changed [source: .claude/hooks/pre-git-checks.sh].
3. `uv` was not on the dispatch PATH — `symphony-host.service` sets no `PATH`, so it inherits systemd's default
   (`/usr/bin:...`), which omits `~/.local/bin/uv`. The hook errored `uv: command not found`.
4. The agent worked around the broken hook: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q`, an
   unbounded full-suite run, **inside the live tmux session**.
5. That suite, alongside the still-running issue #14 Opus agent, exhausted resources. Both `claude` processes were
   **SIGKILL'd (exit 137)** within one second of each other (14:09:08/09 UTC), `timed_out=false`, mid-tool-use
   [source: wiki/raw/sessions/2026-06-14-pre-git-pytest-gate-agent-oom.md].
6. Each run's loop then detected its dead tmux session and captured stderr via `capture-pane` — which returns
   `error connecting to ...sock` because the server is gone. No `pipe-pane` logging exists, so the real error is
   lost [source: claude_runner.py].

Ruled out: no service restart (`NRestarts=0`, same MainPID), no `claude_socket_reaped` in journal, and the reap
tests inject mocked glob/run/unlink so pytest never touches real `/tmp` sockets. The kill was external resource
pressure, not an app-level reap.

## Fix (hazard #3)

Surgical, hook-only — chosen over worktree isolation or systemd resource caps. Confined to
`.claude/hooks/pre-git-checks.sh`; no service/unit/DB change; live immediately (PreToolUse hooks re-read the script
per invocation):

- **Resolve `uv` in-hook**: prepend `~/.local/bin` to PATH if absent, so the hook runs `uv run pytest` itself
  (once, bounded by the existing 180s cap) instead of erroring and provoking an agent workaround.
- **Scope the pytest gate to Python changes**: `changed_py` = staged `*.py` (commit) ∪ `*.py` in `@{u}..HEAD`
  (push). Skip pytest entirely when empty. Frontend-only commits like issue #15 no longer run the suite; the push
  gate is preserved because it inspects unpushed commits.

Verified: frontend-only commit → skip; Python staged → run; Python in unpushed commits → run; non-Python push →
skip; `uv` resolves under systemd default PATH; bash `-n` clean.

## Second bug found: archive CHECK drift (issue #14's real complaint — UNFIXED)

Issue #14's agent found the root cause of "change status / archive does nothing" before being killed: live
`podium.db` `issue.state` CHECK is `('todo','in_review','running','blocked','done')` — **no `'archived'`** — while
`alembic_version='0007_...'`. Migration `0004_archived_state` (which rebuilds `issue` to add `'archived'`) never
materialized against this DB. `state='archived'` → `CHECK constraint failed` → 500 → silent UI revert
[source: web/api/migrations/versions/0004_archived_state.py].

This is a **new instance of the stamp-vs-run drift** in C-0145. It survived because C-0147's startup guard checks
for *missing columns*, not CHECK-constraint differences. `0006_drop_max_duration_seconds` uses a direct
`DROP COLUMN` (no table rebuild), so it did not regress the CHECK — `0004` simply never ran here. Fix (deferred):
manually rebuild the `issue` table per 0004's DDL, since alembic is stamped past 0004 and will not re-run it.

## Real root cause: the suite reaps live sockets (C-0200, supersedes the OOM narrative)

A third failure — issue #17 "Archive", a **single** Claude agent with no concurrent runs and ~20 GiB free —
reproduced the death ~5s into `uv run pytest -q`. No cgroup memory cap, no restart, and memory headroom alone
refutes OOM.

The true mechanism: `main.run_bindings_loop()` → `run_dispatcher` calls `reap_orphan_claude_sockets()` (real
`tmux kill-server` over the host glob `/tmp/symphony-claude-*.sock`) and `reap_orphan_rpc_processes()` as startup
side effects [source: main.py]. Three tests in `tests/test_main.py` drive `run_bindings_loop` **without stubbing the
reapers** (only `test_run_bindings_loop_reaps_claude_sockets_once_for_multiple_bindings` does):

- `test_run_bindings_loop_continues_after_startup_reconcile_transient_failure`
- `test_run_bindings_loop_iterates_all_bindings`
- `test_rate_limited_binding_does_not_block_other_binding`

So **any** `uv run pytest -q` run reaps every live Claude agent's own tmux socket — the agent dies with the
capture-after-death artifact (C-0197). Proven empirically: a sentinel `tmux -S /tmp/symphony-claude-sentinel-9999.sock`
session was killed by the full suite (777 passed) and bisected to those three tests. Pi agents (RPC, no tmux socket)
and subset runs are unaffected — matching #16's success and the survival of `tests/test_alembic_baseline.py` alone.

**Fix (commit `f096476`):** an autouse `_no_real_orphan_reap` fixture in `tests/conftest.py` neutralises both reapers
for every test; reaping-assertion tests override it with their own stub. Verified: the sentinel survives a full-suite
run after the fix [source: tests/conftest.py].

**Why the pre-git hook change isn't the fix:** issue #17's agent ran the suite *voluntarily* (not via commit), so the
hook scoping never engaged. The hook change (C-0198) is retained as hygiene only.

**Archive fix landed:** issue #17's agent authored the correct repair before dying — migration
`0008_fix_issue_archived_check` (commit `b26f31f`, idempotent). Live `podium.db` apply is a pending operator step.

## Related claims

- C-0200 — real root cause (test reaps live sockets) + the `tests/conftest.py` fix; corrects C-0198.
- C-0197 — the `...sock` string is a capture-after-death artifact (still correct).
- C-0198 — pre-git hook hygiene change; its OOM rationale is corrected by C-0200.
- C-0199 — the archive CHECK drift (extends C-0145); fix landed in code via migration 0008, live apply pending.
- C-0145 / C-0147 — prior stamp-vs-run drift and the `ensure_schema` no-re-stamp fix; the archive bug extends C-0145.
- C-0131 — `uv run pytest` (not bare `python3 -m pytest`) is the runnable test command; harness profile context.
- See `wiki/analyses/claude-code-harness-profile.md` for the hook harness overview (pre-git bullet updated this session).
