---
status: accepted
relates-to: ADR-0023 (native per-issue review phase + provenance-gated auto-land), ADR-0014 (worktree done-commit-redispatch + FF-only landing), ADR-0020 (verified done closes infra issue)
amends: ADR-0023 — adds a structural review-mode gate and replaces the dirty-worktree instant-block with commit-redispatch
context: ADR-0023's review phase assumes every coding issue is a diff-to-verify; a no-code planning/discussion issue dispatched as a review has no clean terminal but `blocked`, and a passing review with a dirty worktree is blocked outright instead of committing
decided-with: James, 2026-06-24 (grill-me on the review flow; Run #374 / Issue #127 as the motivating mis-dispatch); implemented by Podium issues #128-#132 and landed 2026-06-24 (main `712469c`)
---

# Review-mode gate (coding vs validation) and dirty-worktree commit-redispatch

## Context

ADR-0023 added a native review phase: a `type: coding` issue parked in
`in_review` with no `### Symphony Review` marker is re-selected, run through
`REVIEW_PREAMBLE`, and terminated by `_handle_review_terminal_done`
(`scheduler/__init__.py`). That handler assumes **every** review is a coding
review with three things present: an implementation diff, acceptance criteria,
and a `## Verification` command. Two gaps surfaced in practice:

1. **No-code issues have no clean terminal.** Run #374 dispatched a review against
   Issue #127 — an explicit planning request ("don't make any changes. I want to
   make a plan file from this") with no diff, no acceptance criteria, and no
   `## Verification`. The reviewer correctly judged there was nothing to review,
   but its only non-pass terminal is `blocked`, so a planning issue landed in
   `blocked`. This is the operator-observed "sometimes it goes back to in_review,
   sometimes to blocked" inconsistency: the routing is actually deterministic, but
   the review prompt has no notion of a non-coding issue.

2. **A passing review with a dirty worktree is blocked outright.** ADR-0023's
   pass-terminal requires a clean committed worktree; a dirty tree at pass time is
   blocked ("Review auto-land halted: review worktree has uncommitted changes").
   This is *more* punitive than ADR-0014's normal operator-merge path, which on a
   dirty tree re-dispatches the agent to commit its own work (capped) rather than
   blocking or force-merging.

## Decision

### 1. Structural review-mode gate (scheduler-decided, not agent-judged)

Before rendering the review prompt, the scheduler classifies the review by an
**objective signal in the issue body**, not by the diff and not by the agent's
self-judgement:

- Issue body contains a runnable `## Verification` command → **coding-review**
  branch (ADR-0023 behavior).
- No verification command → **validation** branch (new).

The mode is passed into the render so `REVIEW_PREAMBLE` carries two clearly
labelled branches and the agent gets prose guidance for the mode it is in.

**Empty diff is a secondary signal, not the mode decider.** A genuinely-intended
coding issue can have an empty diff if its implement run silently no-op'd (Issue
#127's implement "finished without a summary"). Keying the mode on the diff would
misroute such a failure into the soft validation path. So the diff is only
consulted *inside* the coding-review branch: no verification command is not the
case here, but an empty diff there means "nothing was built" → `blocked`, not a
pass.

### 2. Validation branch terminals

The validation branch confirms the discussed outcome/decision holds against repo
reality. It is operator-authored by construction (slicer issues always carry a
verification command — see §4) and has no code to land:

- Outcome holds → emit `done`/`review` → issue **stays `in_review`** for the
  operator to eyeball and close. **Never auto-land** — there is nothing to merge.
- A real contradiction (what was discussed does not match reality) → `blocked`
  with the discrepancy in the summary. This is the *only* validation path to
  `blocked`.

The validation branch **skips the worktree dirty-gate and `land_worktree`
entirely** — those are coding-branch-only.

### 3. Dirty worktree on a passing coding review → commit-redispatch (not block)

Replaces ADR-0023's instant-block with ADR-0014's proven commit-redispatch
pattern. On a review that passed verification but left a dirty worktree:

- Re-dispatch the agent to commit its own work, capped at the **existing**
  `MAX_COMMIT_REDISPATCH = 2` constant and counted via the existing
  `### Operator Reply (Symphony auto-commit` marker / `_count_commit_redispatches`
  — no new review-specific cap or marker.
- The commit run **re-enters through the review terminal** so that once the tree
  is clean the provenance gate runs: `auto_land=true` → `land_worktree` → `done`;
  operator-authored → stays `in_review` for the operator's merge. This guarantees
  committed history for both provenances; only the final land differs.
- Over the cap → `blocked`, worktree left intact for manual handling (ADR-0014
  parity).

This **deliberately reopens ADR-0023's "one review per issue, no retry" rule**,
but narrowly: only for the dirty-but-passing case. Verification already passed and
committing does not change file contents, so the re-entry is a commit-then-land,
not a real re-review.

### 4. Slicer issues unchanged

`/podium-issues` always stamps `auto_land=true` and requires an objective runnable
`verification:` command on every slice (`.claude/skills/podium-issues/SKILL.md`).
So under §1 slicer issues always route to coding-review and keep ADR-0023's fully
automated pass→auto-land→`done` / fail→`blocked` terminal — now with
commit-redispatch resilience (§3) instead of an instant block on a dirty tree. The
validation branch is operator-only by construction; no slicer issue reaches it.

## Consequences

- **Run #374's failure mode is fixed:** a no-code planning issue routes to the
  validation branch and parks in `in_review` (or blocks only on a real
  contradiction), never blocking merely because there is no diff to review.
- **A passing coding review no longer blocks on a dirty tree** — it commits and
  lands (or parks for operator merge), matching ADR-0014's normal path.
- **Reopens "one review per issue"** for the dirty-but-passing case only. A failed
  review (verification fail, real contradiction) is still terminal `blocked` with
  no retry.
- **Process-neutral extraction:** the commit-redispatch core must be extracted so
  the scheduler can drive it without importing the FastAPI process — same
  constraint that forced ADR-0023's `land_worktree` extraction (the redispatch
  logic currently lives in `web/api/main.py` and takes a `sqlite3.Connection`).

## Considered options

- **Agent self-classifies coding-vs-validation as prompt step 1** (the operator's
  first instinct) — softened to a structural scheduler gate: the agent can guess
  wrong, and Run #374 showed that even when it guesses *right* it has no clean
  terminal to express "this is not a coding review." A structural gate decides the
  mode and gives the matching terminal; the prompt still carries both branches.
- **Empty diff as the mode decider** — rejected: a coding issue whose implement
  silently no-op'd also has an empty diff, so it would misroute to validation and
  be called fine. Body intent (verification command present) is the primary tell;
  empty diff is secondary, inside the coding branch only.
- **Keep ADR-0023's dirty → block** — rejected: more punitive than the ADR-0014
  operator-merge path and discards committable work. Operator wants an automated
  commit-then-land as long as history is preserved.
- **Dirty → redispatch with a new review-specific cap/marker** — rejected: reuse
  the existing `MAX_COMMIT_REDISPATCH` knob and auto-commit marker; one knob.


## Implementation / live lessons

Implemented by Podium issues #128-#132. Two live roadblocks during landing are intentionally **not** solved by this ADR and feed ADR-0026:

- Provider/transient failures (`server_is_overloaded`) blocked #128/#129/#131 review or implement runs and required manual requeue / review-marker reset.
- Auto-land of #130/#131 hit advanced-base and wiki claim-ID collisions; the branch could be rebased/renumbered, but the issue remained blocked until a human re-drove landing.

ADR-0026 records the retry/re-drive follow-up; this ADR's implemented scope is the review-mode gate, empty-diff guard, dirty-worktree commit-redispatch, and reland marker accounting.
