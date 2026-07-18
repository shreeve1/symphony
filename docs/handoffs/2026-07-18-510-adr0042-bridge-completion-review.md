# Handoff — verify ADR-0042 bridge build (issues #513–#517) + smoke test

## Purpose of the next session

The GitHub ⇄ Podium dispatch bridge (`docs/adr/0042-github-podium-dispatch-bridge.md`,
`status: accepted`) was sliced into five Podium issues on the `symphony` binding.
The standing scheduler is implementing them. This session should:

1. **Verify every slice landed and each acceptance criterion is actually met** in
   the merged code — not just that the Podium row says `done`.
2. **Confirm the slices compose** end-to-end (the bridge works as one feature).
3. **Help the operator run a smoke test** of the real Sync → dispatch → land →
   close-back loop against a throwaway GitHub issue.

This is `finish-spec` territory in spirit (verify + fix small gaps + close), but
the "spec" here is ADR-0042 and the tickets are Podium issues, not GitHub issues.

## The slices (Podium `symphony` binding)

Check live status first: `uv run python -m web.cli.podium issues list --binding symphony | grep -E '#51[3-7]'`

| # | Title | Blocked by | Verification command |
|---|-------|-----------|----------------------|
| 513 | `resolve_github_repo(repo_path)` remote inference helper | — | `uv run pytest web/api/tests/test_worktree.py -q` |
| 514 | `sync-from-github` insert-only reconcile CLI subcommand | 513 | `uv run pytest web/cli/tests/test_podium_issues.py -q` |
| 515 | Close-back hook on todo→done for `github:` issues | 514 | `uv run pytest scheduler/tests/test_tracker_podium.py -q` |
| 516 | Podium UI Sync-from-GitHub button | 514, 513 | `uv run pytest web/api/tests/test_worktree_api.py -q` |
| 517 | Fail-soft `gh` wrapper (land succeeds if `gh` down) | 515 | `uv run pytest scheduler/tests/test_tracker_podium.py -q` |

**State at handoff authoring (2026-07-18):** #513 `done` (landed, commit
`85f7767`, `resolve_github_repo` in `web/api/worktree.py:28`); #514 `running`;
#515–#517 `todo` waiting on their blockers. By the time you pick this up the
whole chain should be `done` — re-check.

## What to verify per slice (acceptance walk)

Re-ground each against the merged code; do not trust the `done` column alone.

1. **#513 `resolve_github_repo`** (already landed) — confirm it parses
   `git@github-personal:owner/repo.git` (SSH alias), `git@github.com:...`, and
   `https://github.com/owner/repo.git`, and returns `None` for a non-GitHub
   remote. Tests: `web/api/tests/test_worktree.py` (`test_resolve_github_repo_*`).
2. **#514 `sync-from-github`** — the crux slice. Verify:
   - a new subcommand exists in `web/cli/podium.py` (was absent at handoff time).
   - it lists `gh issue list --label ready-for-agent` scoped to the binding repo,
     restricted to children linking a parent spec (parent itself never mirrored).
   - lookup by `external_id = "github:<owner>/<repo>#<number>"`; **insert-only**
     (not-found → INSERT; found → leave untouched, no mutation).
   - **provenance gate (the load-bearing decision):** `auto_land=true` **iff**
     `_extract_runnable_verification` (`scheduler/__init__.py:396`) extracts a
     runnable command from the GitHub body; **else `auto_land=false`**. Prove a
     verification-less issue inserts `auto_land=false` and thus can never reach
     the auto-land terminal at `scheduler/__init__.py:2290`.
   - GitHub "Blocked by" edges map to Podium `blocked_by`.
   - re-run is idempotent (UNIQUE `external_id`, no dupes, no mutation).
3. **#515 close-back hook** — verify it fires `gh issue close <n> --comment
   "Landed in <sha>."` exactly once on any `→done` transition for an issue whose
   `external_id` starts with `github:`, and is centralized behind the ONE seam
   all four `STATE_DONE` sites funnel through (`scheduler/__init__.py:1566, 1805,
   2290, 2482` → `PodiumTrackerAdapter.transition_state`, `tracker_podium.py:457`).
   A non-`github:` issue reaching `done` must trigger **no** `gh` call.
4. **#516 UI Sync button** — present only when `resolve_github_repo` resolves the
   binding remote to GitHub (runtime resolvability = opt-in); pressing it runs the
   reconcile and reports an inserted count.
5. **#517 fail-soft `gh`** — a failing/absent/unauthenticated `gh` must NOT break
   the run: land still succeeds, close-back is best-effort with a logged warning;
   closing an already-closed GitHub issue is tolerated.

**Cross-slice composition checks:**
- Full suite green: `uv run pytest -q` (a bridge that touches `transition_state`
  and the CLI can regress sibling suites — run the whole thing, not just the
  per-slice files).
- Trace one issue end-to-end in code: Sync INSERT (#514) → scheduler dispatch →
  land (`web/api/worktree.py` FF-merge at `:273/:325`) → `→done`
  (`transition_state`) → close-back (#515) → fail-soft (#517).

## Smoke test (operator-assisted, do with James)

Use a **throwaway** GitHub issue in `shreeve1/symphony`; never a real one.

**Preconditions**
- `gh auth status` is authenticated as `shreeve1` via the `github-personal` SSH
  alias (CLAUDE.md Git Remote note — the default `github.com` key is the wrong
  account). Confirm `gh` can `issue list`/`issue close` in this repo.
- Scheduler running for the `symphony` binding (or run one manual tick).

**Happy path (auto_land)**
1. Create a throwaway child issue with label `ready-for-agent`, linked to a parent
   spec issue, whose body contains a trivially-passing runnable
   `## Verification` (e.g. a single backtick `true` command) so it lands cleanly.
2. Press **Sync from GitHub** (or run the `sync-from-github` subcommand).
3. Verify a Podium row appears with `external_id = github:shreeve1/symphony#<n>`
   and `auto_land=true`; **press Sync again → no duplicate, no mutation**.
4. Let the scheduler implement → review → verify → FF-land → `done`.
5. Confirm the GitHub issue is **closed** with a "Landed in <sha>." comment, and
   that the local branch fast-forward-merged (no push, no PR).

**Provenance-gate path (auto_land=false)**
6. Create a throwaway `ready-for-agent` child with **no** `## Verification`.
7. Sync → Podium row inserts with `auto_land=false`. Confirm after
   implement+review it **stops at `in_review`** (manual merge) and the GitHub
   issue stays **open** (no close-back).

**Fail-soft path**
8. Temporarily make `gh` unavailable (e.g. `PATH` without it) during a `done`
   transition → confirm the land still completes and only a warning is logged;
   restore `gh`.

**Mid-flight safety**
9. While a mirrored issue is `running`, close its GitHub issue by hand → confirm
   Podium keeps running and finishes normally; close-back then no-ops on the
   already-closed issue (dispatch is local-SQLite only, `tracker_podium.py:319`).

## Known gap to carry forward

The `to-tickets` skill lives in the **dotfiles** repo
(`/home/james/dotfiles/.claude/skills/to-tickets`), NOT symphony — so the planned
"add a `## Verification` field to the `to-tickets` template" slice is **not** in
#513–#517 and cannot be a symphony ticket. Until it lands on the dotfiles binding,
real `to-tickets`-produced GitHub children carry no verification and will all
insert `auto_land=false` (safe — manual merge — but not yet hands-off). Queue that
work on the dotfiles binding.

## If verification passes

- Report the acceptance walk per slice + full-suite result + smoke-test outcome.
- Run a consolidated `/wiki-update` (interactive, not a slice run) capturing the
  settled insert-time provenance-gate decision and the new `github:` `external_id`
  convention — deferred from the slice runs per ADR-0028.
