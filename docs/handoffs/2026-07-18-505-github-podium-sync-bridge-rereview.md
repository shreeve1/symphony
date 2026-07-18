# Handoff — re-review ADR-0042 (GitHub ⇄ Podium sync bridge)

## Purpose of the next session

Fresh-eyes review of the **design** captured in `docs/adr/0042-github-podium-dispatch-bridge.md`
(committed, `status: proposed`). The originating session (Podium issue #505) was long
and the operator flagged confusion; this session should independently re-read the ADR
against the live codebase and confirm nothing was missed, contradicted, or left
ambiguous before the design is sliced into build tickets.

**Suggested starting skill:** `grill-with-docs` (adversarial design review + fact-check
discipline). Read the ADR, then verify each factual claim it makes against the code
with an independent `pi -p` fact-check per the skill's VERIFY.md.

## The one source of truth

Everything decided lives in **`docs/adr/0042-github-podium-dispatch-bridge.md`**
(commits `bbe5d14` initial, `ab765a8` settled semantics). Do NOT re-derive the design
from the issue thread — read the ADR. The issue thread (#505) has the reasoning trail
if needed, but the ADR supersedes any earlier, looser statements made mid-thread.

## One-paragraph orientation (so you know what you're reviewing)

The operator's plan pipeline is GitHub-native and hands-off (`grill → to-spec →
to-tickets → implement → finish-spec`), where `to-spec`/`to-tickets` create the parent
+ child issues **in GitHub**. Symphony's scheduler only dispatches from **Podium**
(separate SQLite store; no GitHub awareness exists in the code today). The ADR adds a
**complementary** bridge: a re-runnable "Sync from GitHub" action mirrors open GitHub
issues into Podium (insert-only, `auto_land=true`) so the standing scheduler loop
implements → independently reviews → locally FF-merges → closes each; the ONLY write
back to GitHub is `gh issue close` when a Podium issue reaches `done`. GitHub stays the
human surface; Podium is private execution.

## What to verify against the codebase (claims the ADR rests on)

Re-ground each independently — these were checked during authoring but re-verify:

1. `external_id` has a UNIQUE index (`web/api/schema.py:86`) → the idempotent
   insert-only key. Confirm insert-only reconcile can't duplicate or mutate.
2. All four `STATE_DONE` transition sites (`scheduler/__init__.py:1566, 1805, 2290,
   2482`) funnel through the single `PodiumTrackerAdapter.transition_state`
   (`tracker_podium.py:457`) — the ADR's "one centralized close-back seam" claim. Verify
   a hook there covers every land path (verified-close, spawn-worktree-off, review land,
   operator-reland), and that gating on `external_id` prefix `github:` is sound.
3. Landing is a LOCAL `git merge --ff-only` (`web/api/worktree.py:246`) — no push, no PR.
   Confirm close-back has a real "landed sha" to reference and that GitHub isn't
   otherwise touched.
4. `mode` CHECK is `('spawn','loop')` (`web/api/schema.py:143`) — the ADR rejects a new
   automation mode. Confirm the button/action framing doesn't need a schema change.
5. The reconcile-by-external_id pattern the ADR reuses:
   `reconcile_loop_automations` (`tracker_podium.py` ~749, lookup ~794).
6. Runtime owner/repo inference (`resolve_github_repo(repo_path)`, to be built) must
   handle the `github-personal` SSH-alias remote (CLAUDE.md Git Remote note), not just
   `github.com` URLs. Resolvability = the opt-in (no `bindings.yml` field).

## Open questions worth a fresh reviewer's challenge

- **Which GitHub issues does Sync pull?** ADR says "open issues matching filter" but the
  filter is underspecified (label `ready-for-agent`? milestone? parent linkage?). A
  bare "all open issues" would sweep in non-dispatch issues. Nail the selection rule.
- **`## Verification` provenance.** Auto-land (ADR-0023) requires a runnable
  `## Verification` line. GitHub child issues from `to-tickets` do NOT contain one today
  (`to-tickets` template has no verification field). The ADR says it's "authored at sync
  time" — HOW? This is the biggest hand-wave; a synced issue with no runnable
  verification either can't auto-land or lands unverified. Pin this down.
- **Closed-on-GitHub while mid-flight in Podium** — ADR says leave Podium alone. Confirm
  that's still desired (no cancel path).
- **Parent/spec issue** — child issues get mirrored+worked; what closes the PARENT
  GitHub issue? (`finish-spec` territory — is it in or out of scope?)

## Scope boundaries already locked (don't reopen unless flawed)

- GitHub→Podium is **insert-only**; never mutates an existing Podium row (safe mid-flight).
- Only Podium→GitHub write is close-on-`done`. No title/body/state write-back, no reopen.
- No native GitHub TrackerAdapter (mirror reuses existing dispatch/land/review machinery).
- No PR-based landing (keeps ADR-0023 local FF-merge; PRs are a separate future decision).
- No recurring background poller in v1 (operator presses Sync).

## Proposed next step after review

If the review passes, slice ADR-0042 via `podium-issues` into ~5 tickets:
(1) `resolve_github_repo`, (2) `sync-from-github` CLI insert-only reconcile,
(3) close-back hook in `transition_state`, (4) `gh` fail-soft wrapper,
(5) Podium UI Sync button. Each independently verifiable.
