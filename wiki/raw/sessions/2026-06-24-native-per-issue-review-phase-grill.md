# Session — grill-me: bring tralph's per-issue review follow-up into the Podium dispatch loop (ADR-0023)

**Date:** 2026-06-24
**Mode:** grill-me (design interview)
**Trigger:** Operator asked, of Podium Issue #102 "Tralph" follow-up: "in tralph after each
issue there are review follow-up runs that are meant to validate and test code. how can we add
this [to] what we're building in podium issues."

## Background established

- "tralph" = the trading-ralph Playbook/loop. Podium Issue #102 "Tralph" already pivoted
  (through 4 operator updates) into **ADR-0021** — enforced issue dependencies + conflict-free
  parallel dispatch (slices 105-113, in `.kanban/issues/`; 105+106 already built by the Ralph
  loop in `~/symphony-ralph`, branch `ralph/run`; none merged to `main` yet).
- tralph's review model (`~/.claude/skills/ralph/SKILL.md`, "Per-issue review on DONE"): after
  every implement DONE, a fresh independent reviewer session runs the issue's `## Verification`,
  may fix/test/commit in place, flips to `blocked` on an unfixable gap; a driver backstop re-runs
  runnable verification so the reviewer's DONE isn't trusted on faith. ~2x workers/issue.
- Podium today: a coding run finishes → scheduler parks `in_review` (`scheduler/__init__.py`
  terminal handler) → the **operator** moves it to `done` in the UI → that transition
  (`web/api/main.py:1141` `patch_issue` → `_maybe_merge_worktree`) is the *only* path that
  FF-merges the worktree into `main` (ADR-0014; the scheduler never merges). The human merge is
  the only "review."

## Decisions reached (one at a time, each operator-confirmed)

1. **Goal:** add a new native review capability, not re-open ADR-0021's locked design.
2. **Trigger (Q1):** (A) implement finishes → fresh review run dispatched into the *same*
   deterministic `worktree_dir`, *before* the issue settles. Operator: "agreed."
3. **Pass destination (Q2→revised):** operator initially "have it go to done"; later refined to a
   **provenance split** (see 6).
4. **Fail path (Q3):** (A) reviewer fixes in place → proceeds; unfixable → `blocked`; with a
   retry cap so a thrashing issue parks instead of burning runs. Operator: "agreed."
5. **Mechanism (Q4):** issue stays `running` through review (no new visible state, 4a "agreed");
   a `comments_md` marker `### Symphony Review (n)` (mirrors `MAX_COMMIT_REDISPATCH` at
   `web/api/main.py:617`) distinguishes implement-done from review-done. Reviewer is **Pi**
   (4b). Driver backstop re-runs runnable verification.
6. **Reviewer is a service feature, not a selectable skill (Q5):** operator clarified "less of a
   skill ... more of a feature built into the symphony service." → `REVIEW_PREAMBLE` renderer
   constant in `prompt_renderer.py`, sibling to `INFRA_PREAMBLE` (ADR-0016 pattern). Forked from
   `dev-review-pi`'s brief prose, stripped of its interactive verify/discuss/apply-with-user
   steps (Symphony is unattended), plus fix-in-place + `SYMPHONY_RESULT` marker. Operator: "can
   we fork the skill and build it into symphony" → yes.
7. **Scope (Q5b):** review phase universal for **all `type: coding` bindings**; infra excluded
   (already covered by ADR-0020 `auto_close_on_verified`).
8. **Provenance-gated auto-land (Q2-final / Q6):** operator: "for issues I create in the coding
   bindings review but no auto flip to done. only issues created by the podium issue skill that
   go from running > in_review > gets reviewed and passes > done." →
   - slicer-authored (new `issue.auto_land` boolean, set by the 112 slicer) → review pass →
     scheduler auto-flips `in_review → done`, driving the existing `_maybe_merge_worktree` /
     `merge_worktree` path (+ ADR-0021 slice 113 rebase-retry). Unattended merge to `main`.
     Justified: the slicer guarantees an objectively-checkable `## Verification`, so the fresh
     reviewer has a real runnable gate (same trust basis as ADR-0020).
   - operator-authored (`auto_land = false`, the default) → review pass → parks `in_review`;
     human merges (ADR-0014 status quo).
9. **Provenance marker (Q6):** (A) explicit `issue.auto_land BOOLEAN DEFAULT FALSE` column, own
   Alembic migration (after ADR-0021's 0010). Operator: "option a". Rejected (B) piggybacking on
   `external_id` presence (overloads the ADR-0015 dedup key).

## Defaults assumed for the low-stakes remainder

- Review retry cap default 1 (tralph's "reviewed at most once per run"), counted via the
  `### Symphony Review (n)` marker.
- Review run agent = binding `default_agent` (pi); reuses implement run's model/effort.
- Review-in-progress shows as normal `running` (no new chip).

## Outcome

ADR-0023 drafted (`status: proposed`). Reverses ADR-0014's "all coding work lands in_review for
an operator merge" invariant — scoped to the `auto_land` (slicer-authored) subset only. This is
NEW work past the locked ADR-0021 slice set; needs its own slices (schema+migration, scheduler
review-phase dispatch+marker+terminal, `REVIEW_PREAMBLE` constant, slicer `auto_land` stamp,
MANUAL deploy). Not built, not deployed.

## Revision — dev-review-claude pass (same day, after slices first drafted)

An independent `dev-review-claude` (opus) review of the first slice draft (then
114–120) found the original mechanics unimplementable, and the design was reworked:

- **Trigger corrected.** "Keep the issue `running` and dispatch the review inline"
  doesn't work: candidate selection only picks `STATE_TODO` (`scheduler/__init__.py:1263`),
  so a `running` issue is never re-selected; inline dispatch would also hold the
  `run_cap` semaphore + ADR-0021 lock for the whole implement+review span. NEW model:
  implement parks `in_review` (unchanged); review is a SECOND selection source — a
  coding issue in `in_review` with no `### Symphony Review` marker is dispatched via
  the normal machinery. The issue visibly sits in `in_review` during review (matches
  the operator's stated "running > in_review > done").
- **Merge mechanism corrected.** The scheduler can't call `_maybe_merge_worktree`
  (it lives in the `web/api/main.py` FastAPI process, takes a `sqlite3.Connection`,
  and flips a dirty tree to `todo`). NEW: extract a process-neutral `land_worktree`
  (merge + 113 rebase-retry + cleanup, no state mutation) into `web/api/worktree.py`,
  re-export via `worktree_facade`; both the API wrapper and the scheduler share it.
- **Dirty-worktree guard added.** A review pass on a dirty worktree → `blocked`, never
  redispatch-to-`todo` (which would re-enter the implement pool).
- **Retry dropped.** A retry would re-review unchanged code (reviewer already fixed in
  place). One review per issue; fail → `blocked`.
- **Driver backstop split into its own slice** (no Python verification extractor
  exists; highest-risk trust component).
- **Misc:** notify on auto-land-to-`main`; documented `latest_verdict` now reflects the
  review run; flagged that ADR-0021 slice 105's `web/api/tests/test_alembic_baseline.py`
  reference is a nonexistent path (only `tests/test_alembic_baseline.py` is real).

Reworked slices: 114 schema · 115 API · 116 REVIEW_PREAMBLE · 117 land_worktree ·
118 review selection+dispatch · 119 review terminal · 120 driver backstop · 121 slicer
stamp · 122 MANUAL deploy. ADR-0023 patched to match.
