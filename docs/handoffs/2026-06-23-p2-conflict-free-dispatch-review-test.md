# Handoff — P2 conflict-free parallel dispatch: review Ralph's build, then test with deferred issues

**Date:** 2026-06-23
**Issue:** Podium #102 "Tralph"
**For:** a fresh session that (1) reviews the P2 code the Ralph loop builds, then (2) tests it with the deferred issues.

## Mission

The operator is running the **Ralph loop** to build the "podium ralph issue system" =
the **P2 conflict-free parallel dispatch** stack. Your job, fresh session, is NOT to
re-design it (design is locked) and NOT to build it (Ralph does that). It is to:

1. **Review** the work Ralph produces against the slice specs + ADR.
2. **Test** the built system using the deferred issues as the live workload.

## Design is already locked — read these, don't re-derive

- **ADR:** `docs/adr/0021-podium-issue-dependencies-and-parallel-dispatch.md`. Read
  Updates **(2)** (P2 three-layer architecture), **(3)** (direct-to-Podium slicer,
  folder mirror retired), and **(4)** (merge-contention rebase-retry). Status is still
  `proposed` — promote/accept once the build lands.
- **Build specs (the 9 slices), currently in `.kanban/deferred/`:**
  - `105` schema — adds `issue.blocked_by` (JSON int[]) + `issue.locks` (JSON str[]) + Alembic `0010`. `blocked_by: []`, locks `[schema]`.
  - `106` dependency dispatch gate (todo eligible only when blockers done/archived; gated stays `todo`). `blocked_by: [105]`, locks `[scheduler]`.
  - `107` create/patch API carries `blocked_by` + `locks`, cycle reject (400). `blocked_by: [105]`, locks `[web-api]`.
  - `108` worktree-per-run default-ON for local bindings (invert `_worktree_run_fields`, scheduler/__init__.py:385). `blocked_by: []`, locks `[scheduler]`.
  - `109` mutual-exclusion lock gate (lock-set disjoint from in-flight + claimed-this-tick). `blocked_by: [105,108]`, locks `[scheduler]`.
  - `110` read-only UI "Waiting on #N" / "Locked: x" chip. `blocked_by: [105,107]`, locks `[web-frontend]`.
  - `112` repurpose `/podium-issues` into a plan→Podium slicer + retire the folder mirror. `blocked_by: [107]`, locks `[skills]`.
  - `113` FF-merge rebase-retry (worktree.py:170; rebase onto advanced base + retry once, conflict→block). `blocked_by: []`, locks `[web-api]`.
  - `111` **MANUAL deploy** (backup → Alembic 0010 live → next build → restart symphony-host + podium → live-verify). `blocked_by: [106,107,108,109,110,113]`.

Each slice file carries its own acceptance criteria + a `uv run pytest ...`
verification command — use those as your review checklist; don't reinvent them.

## ⚠️ Mechanical gap to resolve first

Ralph grinds `.kanban/issues/*.md`. The 9 specs are in **`.kanban/deferred/`** (the
operator deferred them). For Ralph to build them they must be moved back to
`.kanban/issues/` (105-110, 112, 113 — the code slices). **Leave `111` out of the
Ralph run**: it is the hard-to-reverse live deploy and is operator-gated. Confirm
with the operator whether they've already staged the move or want you to.

## Review focus (where this is most likely to go wrong)

- **108 worktree-default** is the riskiest behavioral flip. Confirm: remote bindings
  still get `{}` (run in `binding.repo_path`, cap 1); local bindings get a
  deterministic `worktree_dir(repo,binding,issue_id)`; warm/`claude_persist` resume
  re-enters the *same* worktree path; `remove_worktree` fires on every terminal
  outcome (no accumulation).
- **113 rebase-retry** — the thing that makes P2 actually conflict-free. Verify the
  two-branches-off-same-base case lands both (journal `merge_succeeded` after a
  rebase), and a real rebase conflict aborts cleanly → block with worktree intact.
- **106 + 109 gates** keep gated issues in `todo` (NOT flipped to `blocked` — that
  state means agent-failure). Selection-only filter.
- **107 cycle reject** returns 400 on a→b→a; omitted fields → `[]`.

Suggested review skill: **`/dev-review-claude`** (fresh-session independent review) or
`/review`. Run each slice's pytest command; all green before trusting the slice.

## Test plan (after build + operator-gated deploy)

This mirrors slice `111`'s live-verify checklist. Use a **throwaway test batch** on
the `symphony` binding (small issues whose only purpose is to exercise the gates —
their dep/lock STRUCTURE matters, not their content), all set to `todo` at once:

- **Dependency:** B `blocked_by:[A]` + independent C → A and C dispatch in parallel
  (separate worktrees); B stays `todo` until A done, then dispatches.
- **Isolation:** A and C each in their own `worktree_dir(...)`, not the shared
  `/home/james/symphony` checkout; worktrees removed on terminal.
- **Mutual exclusion:** D `locks:[x]` + E `locks:[x]` both eligible → only one runs
  at a time; the other waits until the first is terminal.
- **Merge contention (113):** A and C edit different files off the same base, finish
  close together → both land (second's FF-fail rescued by rebase-retry); neither
  left blocked with a leftover worktree.
- Then archive the throwaway issues.

(The deferred slices themselves, once Ralph has built them, are *done* — so the test
corpus is a fresh throwaway batch shaped like them, not the build slices re-run.
Confirm this reading with the operator if unsure.)

## Gotchas / live-environment notes

- **symphony-host.service is the LIVE dispatcher** (runs `python -m main`). Scheduler
  changes (106/108/109) do NOT take effect until it is restarted — that's slice 111,
  operator-gated. Use `/symphony-restart` for the ritual; `/symphony-troubleshooter`
  for safe log review.
- **podium-web** crash-loops on restart unless a systemd drop-in sets
  `PNPM_CONFIG_VERIFY_DEPS_BEFORE_RUN=false`; run `next build` before restart.
- **Flaky test:** `test_podium_sqlite_concurrent` flakes "database is locked" under
  parallel pre-commit load — re-run in isolation before treating as a regression.
- **Git remote:** always use the `github-personal` SSH host alias (see
  `/home/james/symphony/CLAUDE.md`).
- Ralph builds in its own worktree (`~/symphony-ralph`, branch `ralph/run`); land it
  with **`/tralph-merge`**.
- **Wiki:** ADR-0021 promotion to `wiki/analyses/` + index/ROUTING/CLAIMS is still
  deferred — promote once the build lands and the ADR flips to accepted.
