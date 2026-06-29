---
status: proposed
relates-to: ADR-0021 (issue dependencies + conflict-free parallel dispatch), ADR-0014 (worktree done-commit-redispatch + FF-only landing), ADR-0020 (verified done closes infra issue), ADR-0016 (INFRA_PREAMBLE renderer constant), ADR-0003 (worktree-per-run)
context: tralph runs an independent review/validation pass after every implement DONE; Podium has no equivalent — a coding run lands in In Review and waits for a human merge, with no automated second-opinion or verification gate
decided-with: James, 2026-06-24 (Podium Issue #102 "Tralph" follow-up; grill-me on "bring tralph's per-issue review follow-up runs into the Podium dispatch loop")
supersedes: partially supersedes ADR-0014's "all coding work lands in In Review for an operator merge" invariant — only for slicer-authored (auto_land) issues
---

# Native per-issue review phase for coding bindings, with provenance-gated auto-land

## Context

The `tralph` loop reviews every issue after it is implemented: once an implement
worker emits `DONE`, a **fresh independent reviewer session** runs the issue's
`## Verification`, may fix/test/commit in place, and flips the issue back to
`blocked` if it finds an unfixable gap. A driver backstop re-runs runnable
verification commands so the reviewer's `DONE` is never trusted on faith
(`~/.claude/skills/ralph/SKILL.md`, "Per-issue review on DONE").

Podium has no equivalent. Today a coding run finishes, the scheduler parks the
issue in `in_review` (`scheduler/__init__.py` terminal handler, `reason_code =
"agent-marker-review"` for both `review` and `done` verdicts), and it sits there
until the **operator** transitions it to `done` in the UI — which is the only
path that triggers the worktree FF-merge into `main` (`web/api/main.py:1141`
`patch_issue` → `_maybe_merge_worktree`; the scheduler itself never merges,
ADR-0014). The only "review" is the human merge gate; there is no automated
verification or independent second-opinion before that gate.

With ADR-0021 P2 landing (worktree-per-run default-ON, dependency + lock gates,
the `/podium-issues` plan→Podium slicer that guarantees every slice carries an
objectively-checkable `## Verification` command), the missing piece to reach
tralph fidelity is the per-issue review phase.

## Decision

Add a **native review phase** to the coding dispatch loop — not a catalog skill
the operator selects, but built into the Symphony service.

1. **Trigger / flow.** An implement run finishing a `type: coding` issue parks it
   in `in_review` exactly as today (the implement terminal handler is unchanged).
   The review run is then a **second candidate-selection source**: a coding issue
   in `in_review` whose `comments_md` lacks a `### Symphony Review` marker is
   selected and dispatched through the **normal render→run→classify machinery**,
   re-entering the issue's deterministic `worktree_dir(repo, binding, issue_id)`
   (the ADR-0021/0003 worktree) and rendering `REVIEW_PREAMBLE` instead of the
   implement prompt. The marker (written at review dispatch) makes the phase
   idempotent across ticks (marker present ⇒ already reviewed ⇒ not re-selected).

   This is the corrected trigger model. The earlier draft — "keep the issue
   `running` and dispatch review inline" — was **not implementable**: candidate
   selection only picks `STATE_TODO` (`scheduler/__init__.py:1263`), so a `running`
   issue is never re-selected and nothing would trigger the second dispatch; an
   inline same-tick dispatch would also hold the `run_cap` semaphore + ADR-0021
   lock for the full implement+review duration. Selecting the review run from
   `in_review` reuses a state the scheduler already understands, makes the issue
   visibly sit in `in_review` during review (matching the operator's intended
   `running → in_review → done` flow), and lets each run take its own semaphore slot.

2. **Reviewer.** The review run is Pi-powered (the binding `default_agent`) and
   driven by a new `REVIEW_PREAMBLE` renderer constant in `prompt_renderer.py`
   (sibling to `INFRA_PREAMBLE`, the ADR-0016 pattern), forked from the
   `dev-review-pi` skill's review-brief prose but **stripped of its interactive
   verify-scope / discuss-findings / apply-with-user steps** (Symphony runs
   unattended). The reviewer must: gather context, run the issue's
   `## Verification` exactly as written, **fix in place** if it can, and emit a
   `SYMPHONY_RESULT: done|blocked` marker. A driver backstop (its own slice)
   re-runs the verification command itself when it is composed of clean backtick
   commands, so a too-optimistic review `done` is overridden (tralph parity); no
   Python verification extractor exists today, so the backstop builds one.

3. **Scope.** ~~The review phase is **universal for all `type: coding` bindings**.~~
   **Superseded by issue #149 (2026-06-29):** the review run now fires **only for
   slicer-authored (`auto_land=true`) issues** — the `/podium-issues` slicer
   guarantees an objectively-runnable `## Verification`, which is the trust basis
   for an unattended review. Operator-authored issues (`auto_land=false`) skip the
   review run entirely and stay in `in_review` for a manual merge (pure ADR-0014
   behavior). The gate lives in `tracker_podium.list_candidates`: `review_dispatch`
   now also requires `auto_land`. Infra bindings remain excluded — they already
   have ADR-0020's `auto_close_on_verified` re-measure-and-close path.

4. **Pass-terminal is provenance-gated** (the load-bearing decision):
   A review pass first requires a **clean, committed worktree** (the reviewer was
   mandated to commit); a dirty worktree at pass time is treated as a fail →
   `blocked`, never a redispatch-to-`todo`. Then:
   - **Slicer-authored issues** (new `issue.auto_land` boolean, set `true` by the
     `/podium-issues` slicer; everything else defaults `false`): review pass →
     scheduler transitions `in_review → done` and calls `land_worktree(...)` — a
     **process-neutral merge+land core extracted from `_maybe_merge_worktree`**
     (incl. ADR-0021 slice 113 rebase-onto-base + FF retry) and re-exported via
     `worktree_facade`, which the scheduler already imports. The scheduler does NOT
     call `_maybe_merge_worktree` directly (it lives in the `web/api/main.py`
     FastAPI process, takes a `sqlite3.Connection`, and on a dirty tree flips state
     to `todo` — importing it would pull FastAPI into the scheduler and the
     todo-flip would break the flow). **Unattended merge into `main`**, full tralph
     fidelity, with a merge notification (an unattended merge to `main` must not be
     silent). Justified because the slicer guarantees an objectively-checkable
     `## Verification`, so the fresh reviewer has a real runnable gate — the same
     "verification is the agent re-measuring the real thing" trust basis ADR-0020
     used for infra auto-close.
   - **Operator-authored issues** (`auto_land = false`): review pass → issue STAYS
     in `in_review`; the **operator merges** via the existing `_maybe_merge_worktree`
     done path (ADR-0014 status quo). Hand-authored issues carry no verification
     guarantee, so the human stays the merge gate.

5. **Fail-terminal (both provenances).** Unfixable gap (review emits `blocked`),
   dirty worktree at pass time, or a backstop verification failure → issue flips
   `in_review → blocked` (feeds the existing `blocked_reconciler` and ADR-0021
   dependency gate — downstream `blocked_by` issues correctly keep waiting).
   **One review per issue — no retry.** The `### Symphony Review` marker means the
   issue is never re-reviewed: a failed review is terminal `blocked`. A retry would
   only re-review unchanged code (the reviewer already had its fix-in-place shot),
   so the earlier "retry cap" framing is dropped.

6. **Schema.** Add `issue.auto_land BOOLEAN DEFAULT FALSE` in its own Alembic
   migration (`0011`, revises ADR-0021's `0010`). `IssueCreate` carries it; the
   slicer (112) stamps it `true`.

## Design choices

- **Native loop behavior + renderer constant, not a selectable skill.** The
  reviewer is a fixed role; the operator shouldn't pick it per issue and the
  slicer shouldn't stamp a `preferred_skill` for it. `REVIEW_PREAMBLE` follows the
  proven `INFRA_PREAMBLE` (ADR-0016) pattern. `dev-review-pi` is the donor text
  only — its interactive, review-only, operator-in-the-loop shape is the wrong fit
  for an unattended fix-in-place gate.
- **Review selected from `in_review`, not held inline.** The issue visibly sits in
  `in_review` during review (no new state); a marker-gated second selection source
  triggers the review dispatch on a later tick through the normal machinery, so
  each run takes its own `run_cap` slot rather than one issue holding the slot +
  ADR-0021 lock for the full implement+review duration.
- **Explicit `auto_land` column, not inferred.** Provenance decides unattended
  merge-into-`main`, so it must be explicit. Rejected piggybacking on
  `external_id` presence (overloads the ADR-0015 dedup key with behavioral meaning
  — anything that ever sets `external_id` would silently auto-land).
- **Process-neutral `land_worktree`, not a cross-process call.** The scheduler and
  `podium-api` are separate processes. The merge+land core (FF-merge + 113
  rebase-retry + cleanup, no state mutation) is extracted from
  `_maybe_merge_worktree` into `web/api/worktree.py` and re-exported via
  `worktree_facade` so both the API's operator-merge wrapper and the scheduler's
  auto-land path share it. The scheduler never imports `web/api/main.py`.

## Consequences

- **Reverses an ADR-0014 invariant for the slicer subset.** Coding work no longer
  *always* waits for an operator merge: a slicer-authored issue can merge into
  `main` unattended on a passing automated review. The fresh reviewer running the
  issue's verification is the trust basis (same logic as ADR-0020). Operator-
  authored issues keep the human merge gate, so the reversal is scoped, not
  blanket.
- **~2x runs per coding issue** (implement + review). Because review is a separate
  dispatch, this is also ~2x semaphore/lock occupancy over an issue's life, not
  just 2x run records — it lowers effective host throughput; called out in the
  MANUAL slice's calibration.
- **`latest_verdict` / `latest_run_state` reflect the review run** once it finishes
  (two run records per issue; the review run is the latest). Anything downstream
  reading the implement run's verdict after review must not assume it is `latest`.
- **Hard-to-reverse live step:** the new Alembic migration on the live Podium DB +
  a `symphony-host` restart to pick up the review-phase dispatch — a gated MANUAL
  slice, like ADR-0021's 111. Precondition: ADR-0021 slice 108 (worktree-per-run
  default-ON) must be live so review-phase issues carry `worktree_active=true`;
  otherwise an auto_land issue flips `done` but the merge no-ops.
- The `symphony` self-binding dogfoods this, so the auto-land path lands code into
  the live infrastructure repo unattended — verify on a throwaway slicer-authored
  batch before trusting it broadly.

## Considered options

- **Auto-land for all coding issues** (blanket tralph fidelity) — rejected:
  hand-authored issues lack the verification guarantee that makes unattended merge
  trustworthy. The provenance split keeps the human gate exactly where confidence
  is low.
- **Review as a read-only judge that bounces to `todo`** (no fix-in-place) —
  rejected: not the tralph behavior asked for, and risks an uncapped
  implement→review→implement loop.
- **Use `dev-review-pi` as-is** — rejected: it is interactive, review-only, and
  operator-in-the-loop; it neither runs unattended, fixes in place, nor emits the
  `SYMPHONY_RESULT` marker the loop keys off.
- **"Keep the issue `running`, dispatch review inline"** (the original draft
  trigger) — rejected as not implementable: candidate selection only picks
  `STATE_TODO`, so a `running` issue is never re-selected; an inline same-tick
  dispatch would hold the semaphore + lock for the whole implement+review span.
  Selecting from `in_review` fixes both.
- **Scheduler calls `_maybe_merge_worktree` directly** — rejected: it lives in the
  FastAPI process, takes a `sqlite3.Connection`, and flips a dirty tree to `todo`
  (which would re-enter the implement pool). Extracted `land_worktree` instead.
- **Retry / retry cap > 1** — dropped: a retry re-reviews unchanged code (the
  reviewer already fixed in place), so it accomplishes nothing. One review per
  issue; fail → `blocked`.

## Slice plan

New work past the locked ADR-0021 set (105–113); depends on 105 (schema/0010), 108
(worktree default-ON), 112 (slicer), 113 (rebase-retry).

- **114** — schema: `issue.auto_land BOOLEAN DEFAULT FALSE` + Alembic `0011`
  (revises `0010`); tracker reads it. `blocked_by:[105]`, lock `schema`.
- **115** — create/patch API carries `auto_land`. `blocked_by:[114]`, lock `web-api`.
- **116** — `REVIEW_PREAMBLE` renderer constant + review render path.
  `blocked_by:[]`, lock `renderer`.
- **117** — extract process-neutral `land_worktree` (merge+113+cleanup, no state
  mutation) from `_maybe_merge_worktree`; re-export via `worktree_facade`.
  `blocked_by:[113]`, lock `web-api`.
- **118** — review selection + dispatch: coding issue in `in_review` with no
  `### Symphony Review` marker → review run via normal machinery, same worktree,
  marker written. `blocked_by:[108,116]`, lock `scheduler`.
- **119** — review terminal: clean-worktree gate, provenance-gated pass
  (auto_land → `land_worktree`+done; operator → stays `in_review`), fail →
  `blocked`, one review per issue. `blocked_by:[114,117,118]`, lock `scheduler`.
- **120** — driver backstop: Python runnable-`## Verification` extractor + re-run +
  override an over-optimistic `done` to `blocked`. `blocked_by:[119]`, lock
  `scheduler`.
- **121** — `/podium-issues` slicer stamps `auto_land=true`. `blocked_by:[112,115]`,
  lock `skills`.
- **122** — MANUAL: backup → Alembic `0011` → restart → live verify. `blocked_by:
  [115,118,119,120,121]`.

## Out of v1 / deferred

- A visible `reviewing` state or board chip (review is visible as `in_review`).
- Per-binding opt-out of the review phase (offer a `bindings.yml` flag only if the
  universal-for-coding default proves too blunt).
- Agent re-dispatch to resolve review-found conflicts (upgrade path if single-pass
  review proves insufficient, mirroring 113's rebase-retry rationale).

## Note on a sibling ADR-0021 fix

Review of this plan surfaced that ADR-0021 slice 105's text references
`web/api/tests/test_alembic_baseline.py`, which does not exist — only
`tests/test_alembic_baseline.py` is real. Flagged for correction in the 105 slice;
this plan's 114 uses the correct path.
