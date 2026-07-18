---
status: proposed
relates-to: ADR-0005 (Podium replaces Plane), ADR-0023 (provenance-gated auto-land), ADR-0038 (spawn/loop automations), ADR-0041 (automation terminal landing)
decided-with: James, 2026-07-18 (Podium issue #505 grill)
---

# GitHub ⇄ Podium dispatch bridge (GitHub-primary, Podium-as-execution)

## Context

The operator's AI-driven planning pipeline is GitHub-native and fully hands-off:
`grill → to-spec → to-tickets → implement → finish-spec`. `to-spec` creates the
parent GitHub issue (the spec/PRD) and `to-tickets` creates the child GitHub
issues — no manual `gh issue create`. Child issues may be added under the parent
later, so any bridge must be re-runnable, not a one-shot import.

Separately, Symphony's standing per-binding scheduler already implements the
"implement → independent fresh-session review → land → close" loop over a whole
backlog, **but only for issues that live in Podium with `auto_land=true`**
(ADR-0023). GitHub Issues and Podium issues are two entirely separate stores:
`web/cli/podium_issues.py` writes issues by direct SQLite `INSERT` and never
calls `gh`; the scheduler dispatches only from the Podium `issue` table via
`PodiumTrackerAdapter.list_candidates`; there is **no sync** between the two.

This forces a bad choice. Today the operator either (a) keeps the GitHub-native
`to-tickets` flow but then hand-drives execution — currently by pointing a
**spawn** automation at the `implement` skill plus a **second** spawn automation
to review each ticket, which is jumbled because spawn mints a new unrelated issue
per fire and the per-ticket review run is already built into the scheduler
(`review_dispatch`, `tracker_podium.py`); or (b) swaps `to-tickets` for
`podium-issues` and gives up GitHub as the issue surface entirely.

Neither is acceptable for an open-source posture: **GitHub is the issue surface
users expect; Podium must be complementary, not a replacement.**

## Decision

Add a **GitHub ⇄ Podium bridge**: GitHub remains the canonical, human-visible
issue surface; Podium becomes the private execution mirror the scheduler
dispatches from. The bridge is opt-in per binding and does not change either
store's semantics.

### 1. Sync GitHub → Podium (re-runnable, insert-only)

A **re-runnable "Sync from GitHub" action** (a button on the binding's issue
view, backed by a `web.cli.podium` subcommand — the same direct `INSERT` path
`podium-issues` already uses, plus `gh issue list`) reconciles the binding's open
GitHub issues into Podium. It is **not** a one-shot import: pressing it again
picks up child issues added later and heals drift. It reuses the exact
reconcile-by-`external_id` pattern the loop reconciler already uses
(`reconcile_loop_automations`: `SELECT * FROM issue WHERE external_id = ?` → insert
if absent, else leave alone).

For each matching open GitHub issue, look up Podium by
`external_id = "github:<owner>/<repo>#<number>"`:

- **not found →** insert a new `todo` Podium issue with `auto_land=true` and
  `worktree_active` per binding default, so the standing loop implements →
  reviews → lands → closes with zero operator merges. GitHub "Blocked by" edges
  map to Podium `blocked_by` for dependency ordering. The GitHub title/body flow
  into the description; the runnable `## Verification` line ADR-0023 requires is
  authored at sync time (the bridge is the provenance source, mirroring what
  `podium-issues` guarantees).
- **found →** leave the Podium row untouched. **Sync is one-directional and
  insert-only: it never mutates an existing Podium issue** (no title/body
  overwrite, no state change, no cancel-on-GitHub-close). This makes "press
  again" always safe even while issues are `running`/`in_review` — the risk that
  a re-run corrupts active work is eliminated by never touching existing rows.

`external_id` is already a nullable free-form TEXT column with a **UNIQUE index**
(`web/api/schema.py:86`), reused for automation provenance (`automation:<id>:loop`);
no schema change is needed. The unique index is what makes the upsert key
idempotent — a duplicate insert is structurally impossible. Both conventions are
prefix-namespaced (`github:` / `automation:`) so lookups stay unambiguous.

Owner/repo is **inferred at runtime** from the binding's git remote in
`repo_path` (a `resolve_github_repo(repo_path)` helper that handles both
`git@host:owner/repo.git` SSH-alias remotes — note this repo's `github-personal`
alias, CLAUDE.md — and `https://github.com/owner/repo.git`). A binding whose
remote does not resolve to a GitHub repo simply has no Sync button: **runtime
resolvability is the opt-in mechanism** (no `bindings.yml` field needed).

### 2. Close GitHub ← Podium (the ONLY sync-back, gated on `done`)

The **only** write from Podium back to GitHub is issue closure, and it fires
**only when a Podium issue reaches `done`** (moved into the done column). No
other Podium state change ever touches GitHub. When the scheduler lands a
mirrored issue and transitions it to `done`, the bridge closes the linked GitHub
issue via `gh issue close <n> --comment "Landed in <sha>."`.

**The close-back hook must be centralized, not attached to the review path.**
There are **four** distinct `transition_state(…, STATE_DONE)` call sites across
three functions (`scheduler/__init__.py:1566` verified-close, `:1805`
spawn-worktree-off auto-land, `:2290` review-terminal land, `:2482`
operator-reland). A hook bolted onto `_handle_review_terminal_done` alone would
miss three of them. The bridge instead fires **once**, keyed on the
`todo/…→done` transition for any issue whose `external_id` starts with
`github:` — implemented either inside `PodiumTrackerAdapter.transition_state`
(when role resolves to `STATE_DONE`) or a single post-transition dispatch hook
that every done-path already funnels through. This keeps the bridge behind one
seam regardless of which terminal path closed the issue.

### 3. Posture: GitHub-primary, Podium-private

- Humans read, comment on, and triage in **GitHub** (unchanged `to-spec` /
  `to-tickets`).
- Podium is an internal execution detail — the mirror row and its Run history.
- The pipeline becomes `grill → to-spec → to-tickets → [click Sync from GitHub]
  → [scheduler runs the backlog] → finish-spec`, and the **`implement` skill and
  both spawn automations are dropped** — the scheduler *is* the implement+review
  loop. The Sync button is re-runnable: adding child issues later and pressing
  it again enqueues them.

## Considered options

- **Replace GitHub with Podium (`to-tickets`→`podium-issues`).** Rejected:
  incompatible with open-sourcing; users won't abandon GitHub.
- **A full GitHub `TrackerAdapter`** so the scheduler dispatches GitHub issues
  directly (no mirror). Rejected for v1: much larger; the scheduler assumes a
  local SQL `issue` table with columns GitHub lacks (`auto_land`,
  `worktree_active`, `blocked_by`, `locks`, Run rows, `comments_md` continuity).
  The mirror reuses all existing dispatch/land/review machinery unchanged. A
  native adapter can supersede the bridge later if warranted.
- **Close-back only in the review path.** Rejected: misses three of four
  done-paths (verified-close, spawn-worktree-off, operator-reland).
- **A recurring background GitHub poller / new automation `mode`.** Rejected for
  v1: the `mode` column is CHECK-constrained to `('spawn','loop')` and both are
  recurring triggers; a re-runnable operator-pressed Sync action models the need
  without widening the enum or adding a standing poll. A background poll can be
  added later as a binding-level job (like `blocked_reconciler`), not an
  Automations-list entry.
- **Bidirectional field sync (title/body/state write-back).** Rejected: the
  operator explicitly wants no sync-back except issue closure on `done`. Sync is
  insert-only into Podium; the sole Podium→GitHub write is close-on-done.

## Consequences

- GitHub stays the source of truth and the human surface; Podium is complementary
  and private — the open-source-friendly shape.
- The operator's flow loses two spawn automations and the manual `implement`
  orchestration; the standing scheduler does implement→review→land→close.
- New coupling: Symphony now shells `gh` (at sync time for `gh issue list`, at
  land time for `gh issue close`). Requires `gh` auth in the binding environment
  (note the `github-personal` SSH-alias / account caveat in CLAUDE.md) and a
  fail-soft path if `gh` is unavailable (land must still succeed; close-back is
  best-effort with a logged warning, mirroring the Plane-rate-limit tolerance
  already around the done transition).
- `external_id` gains a second documented convention (`github:…` alongside
  `automation:…`); both are prefix-namespaced so lookups stay unambiguous.
- Idempotence is mandatory: re-running Sync must not duplicate rows (dedupe on
  the UNIQUE `external_id`) and must never mutate an existing row; close-back
  must tolerate an already-closed GitHub issue.

## Out of scope

- A native GitHub `TrackerAdapter` (dispatch without a mirror).
- Any Podium→GitHub write other than close-on-`done` (no title/body/state
  write-back, no reopen, no comment mirroring). Sync is GitHub→Podium insert-only
  plus the single close-on-done write.
- Bidirectional live sync (GitHub comment → Podium, label edits, reopen on
  GitHub). v1 is re-runnable insert-only sync + close-on-done only.
- A recurring background GitHub poller (operator presses Sync in v1).
- GitHub Pull Requests as the landing mechanism (that is the separate
  "Option B" PR-landing decision; this bridge keeps ADR-0023 local FF-merge).
- Mirroring non-spec ad-hoc GitHub issues; the bridge runs against a spec's
  child issues produced by `to-tickets`.
