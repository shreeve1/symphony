# Session Capture: Worktree feature walkthrough + done-time commit-redispatch design (ADR-0014)

- Date: 2026-06-18
- Purpose: Grill-me walkthrough of the Podium per-Issue worktree feature (how it works, whether it works, teardown/commit/merge/deletion handling), which surfaced a silent-data-loss gap and produced a design decision (ADR-0014, proposed) plus a CONTEXT.md glossary correction.
- Scope: Verified lifecycle against code; decided the done-time policy for an uncommitted worktree; corrected the glossary's infra-only framing of worktrees/landing. No implementation performed (ADR is `proposed`).

## Durable Facts

- Worktree merge-on-done is **not** binding-type-gated. `_maybe_merge_worktree` keys off `worktree_active` + non-remote, never `binding_type`. It applies to any binding (coding or infra) with `worktree_active=true`. Remote bindings (ADR-0012) force `worktree_active` off. — Evidence: `web/api/main.py:1000-1006,1272-1350`, `web/api/worktree.py`
- The CONTEXT.md glossary previously framed worktree+landing as **infra-only** ("For coding bindings Symphony performs no landing step"; "For infra bindings with `worktree_active=true`..."). The code and the #021 claims (C-0084..C-0088) were already binding-agnostic; the glossary lagged. Corrected this session. — Evidence: `CONTEXT.md` Run / Run Worktree / Landing terms (edited 2026-06-18)
- `done` is **operator-gated**: the scheduler transitions a successful run to `in_review` (never `done`). Merge-on-done therefore never fires autonomously — the operator marks `done` via PATCH, which triggers the merge. — Evidence: `scheduler/__init__.py:1699,1772`; `web/api/main.py:998-1006`
- **Silent-discard gap (Case 2):** if the agent leaves work uncommitted in the worktree, marking `done` runs `merge --ff-only` as a no-op "already up to date" (branch == base), then `cleanup_worktree` → `git worktree remove --force` silently deletes the uncommitted work; the Issue shows green `done` with nothing landed. — Evidence: `web/api/worktree.py:116-174` (`merge_worktree`, `cleanup_worktree`, `remove_worktree` uses `--force`); `web/api/main.py:1339-1347`
- The `symphony` self-binding (`type: coding`, `repo_path: /home/james/symphony`) is safe to enable: base repo is on `main`, `git status --porcelain` is clean, and `podium.db*` + build dirs are gitignored so `base_repo_dirty` does not false-trip; merge-on-done equals the manual `git pull`-into-`main` landing step and triggers no service restart (landed code is inert until `symphony-restart`). — Evidence: live `git rev-parse --abbrev-ref HEAD` (main), `git status --porcelain` (empty), `git check-ignore podium.db podium.db-wal podium.db-shm`
- The worktree feature is currently **dormant**: no `issue` row has `worktree_active=1` and there is no `worktrees/` directory on disk as of 2026-06-18. — Evidence: `sqlite3 podium.db "SELECT ... WHERE worktree_active=1"` (empty); `ls worktrees/` (absent)
- Re-dispatch-with-note machinery already exists end to end: `POST /api/issues/{id}/reply` appends an `### Operator Reply` block and flips `state='todo'`; `prompt_renderer.py` surfaces the newest operator reply as the current request on resume; `create_worktree` is idempotent so a re-dispatch reuses the same dirty worktree. — Evidence: `web/api/main.py:1074-1113`; `prompt_renderer.py:174,209,278-290`; `web/api/worktree.py:31-48`

## Decisions

- **ADR-0014 (proposed):** at done-time, classify the worktree. Case 1 (clean, commits ahead) → FF-merge + teardown unchanged. Case 2 (no commits ahead, or dirty working tree) → re-dispatch the agent to commit its own work (synthetic `### Operator Reply` + flip to `todo`), reusing the operator-reply path. Loop guard: re-dispatch at most **twice** (counted by the synthetic commit-note marker in `comments_md`, no schema change); after the cap, fall back to **`blocked`** (not auto-commit) so un-agent-committed work is never auto-landed into `main`. Non-FF block path unchanged. — Evidence: `docs/adr/0014-worktree-done-commit-redispatch.md`
- **Rejected alternatives:** (a) block immediately on Case 2 — too much friction; (b) `git add -A` auto-commit at done-time — bypasses agent pre-commit test obligation and risks auto-landing broken code (kept only as a considered post-cap fallback, rejected for `blocked`); (c) keep current silent force-remove — data loss. — Evidence: `docs/adr/0014-worktree-done-commit-redispatch.md` Considered options
- **Glossary correction accepted by James:** generalize `Run`, `Run Worktree`, `Landing`, and the lifecycle bullet so worktree opt-in + FF-merge-on-done apply to any binding regardless of type. — Evidence: `CONTEXT.md` (edited 2026-06-18)
- **Build deferred:** James asked to update the wiki and hold on building ADR-0014.

## Evidence

- `web/api/worktree.py` — `create_worktree`/`merge_worktree`/`remove_worktree` (`--force`)/`cleanup_worktree`/`base_repo_dirty`; supports the lifecycle and silent-discard facts.
- `web/api/main.py:998-1034,1272-1390` — done-merge / archive-teardown / toggle-off-archive orchestration; remote-binding short-circuit.
- `scheduler/__init__.py:1699,1772` — successful run lands `in_review`, never `done` (operator-gated merge).
- `worktree_facade.py` — import shim re-exporting the worktree helpers.
- `bindings.yml` — symphony=coding self-binding, n8n=remote.
- `docs/adr/0014-worktree-done-commit-redispatch.md` — the proposed decision.
- `CONTEXT.md` — corrected glossary terms.

## Exclusions

- No secrets, `.env`, or `/home/james/symphony-host.env` contents read or captured.
- No live mutations: no service restart, no Plane/Podium API writes, no DB writes, no smoke ticket. Read-only `git`/`sqlite3` inspection only.
- No full transcript archived.

## Open Questions And Follow-Ups

- Implement ADR-0014 (the guard + re-dispatch + loop-cap) in `web/api/worktree.py` / `web/api/main.py` with tests; promote ADR-0014 to `accepted` on landing.
- Decide whether to enable `worktree_active` on the `symphony` self-binding once ADR-0014 lands.
- On implementation, update promoted page `wiki/analyses/podium-021-worktree-auto-merge.md` to reference the commit-redispatch behavior and supersede the silent-discard claim.
