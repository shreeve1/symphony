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
issues — no manual `gh issue create`.

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

### 1. Mirror GitHub → Podium (dispatch enablement)

A new bridge step (a skill or a `web.cli.podium` subcommand — the same direct
`INSERT` path `podium-issues` already uses, plus `gh issue list`) reads the
just-created GitHub issues for a spec and mirrors each into Podium as a `todo`
issue:

- `auto_land=true` and `worktree_active` per binding default, so the standing
  loop implements → reviews → lands → closes with zero operator merges;
- `external_id = "github:<owner>/<repo>#<number>"` — the backlink. `external_id`
  is already a nullable free-form TEXT column reused for automation provenance
  (`automation:<id>:loop`); no schema change is needed. It is the join key for
  idempotence (never mirror the same GitHub issue twice) and for close-back;
- GitHub blocking relationships / "Blocked by" edges map to Podium `blocked_by`
  so the scheduler walks the backlog in dependency order.

The GitHub issue body/title flow into the Podium issue description. The runnable
`## Verification` line ADR-0023 requires for auto-land is authored at mirror time
(the bridge is the provenance source, mirroring what `podium-issues` guarantees).

### 2. Close GitHub ← Podium (land-time close-back)

When the scheduler lands a mirrored issue and transitions it to `done`, the
bridge closes the linked GitHub issue via `gh issue close <n> --comment
"Landed in <sha>."`.

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
- The pipeline becomes `grill → to-spec → to-tickets → bridge-mirror →
  [scheduler runs the backlog] → finish-spec`, and the **`implement` skill and
  both spawn automations are dropped** — the scheduler *is* the implement+review
  loop.

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

## Consequences

- GitHub stays the source of truth and the human surface; Podium is complementary
  and private — the open-source-friendly shape.
- The operator's flow loses two spawn automations and the manual `implement`
  orchestration; the standing scheduler does implement→review→land→close.
- New coupling: Symphony now shells `gh` on land. Requires `gh` auth in the
  binding environment (note the `github-personal` SSH-alias / account caveat in
  CLAUDE.md) and a fail-soft path if `gh` is unavailable (land must still
  succeed; close-back is best-effort with a logged warning, mirroring the
  Plane-rate-limit tolerance already around the done transition).
- `external_id` gains a second documented convention (`github:…` alongside
  `automation:…`); both are prefix-namespaced so lookups stay unambiguous.
- Idempotence is mandatory: re-running the mirror must not duplicate rows
  (dedupe on `external_id`), and close-back must tolerate an already-closed
  GitHub issue.

## Out of scope

- A native GitHub `TrackerAdapter` (dispatch without a mirror).
- Bidirectional live sync (GitHub comment → Podium, label edits, reopen on
  GitHub). v1 is create-time mirror + land-time close-back only.
- GitHub Pull Requests as the landing mechanism (that is the separate
  "Option B" PR-landing decision; this bridge keeps ADR-0023 local FF-merge).
- Mirroring non-spec ad-hoc GitHub issues; the bridge runs against a spec's
  child issues produced by `to-tickets`.
