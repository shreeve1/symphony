---
title: Pre-git pytest gate OOM-killed concurrent live agents (issues #14/#15)
type: analysis
status: promoted
created: 2026-06-14
updated: 2026-06-14
sources:
  - wiki/raw/sessions/2026-06-14-pre-git-pytest-gate-agent-oom.md
  - .claude/hooks/pre-git-checks.sh
  - claude_runner.py
  - web/api/migrations/versions/0004_archived_state.py
confidence: high
tags: [pre-git-hook, pytest, uv, oom, claude, dispatch, live-repo, alembic, drift, archived, failure-mode]
---

# Pre-git pytest gate OOM-killed concurrent live agents (issues #14/#15)

## Summary

Both `symphony`-binding issues dispatched 2026-06-14 — #14 "Column changing" and #15 "Inbox" — failed with the
recorded reason `error connecting to /tmp/symphony-claude-*.sock`. That reason is a **diagnostic artifact**, not the
cause. The real cause: issue #15's agent ran the **full `uv run pytest` suite inside its live tmux session**, which
under two concurrent live Opus agents exhausted memory and SIGKILL'd both agent processes at the same instant.
Fixed by hardening `.claude/hooks/pre-git-checks.sh`. A second, independent live bug (the user's actual archive
complaint) was found during diagnosis and is documented here but **not yet fixed**.

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

## Related claims

- C-0145 / C-0147 — prior stamp-vs-run drift and the `ensure_schema` no-re-stamp fix; the archive bug extends C-0145.
- C-0131 — `uv run pytest` (not bare `python3 -m pytest`) is the runnable test command; harness profile context.
- See `wiki/analyses/claude-code-harness-profile.md` for the hook harness overview (pre-git bullet updated this session).
