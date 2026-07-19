---
title: "ADR-0042 — GitHub ⇄ Podium dispatch bridge (GitHub-primary, Podium-as-execution)"
type: analysis
status: promoted
created: 2026-07-19
updated: 2026-07-19
sources:
  - docs/adr/0042-github-podium-dispatch-bridge.md
  - web/cli/podium_issues.py
  - tracker_podium.py
  - web/api/schema.py
  - scheduler/__init__.py
  - web/cli/tests/test_podium_issues.py
  - runs from Podium issues #522/#523 (GH #12/#13)
  - commit 430e468 (fix #514: sync blocked_by sort)
confidence: high
tags: [adr, github-bridge, podium, auto_land, external_id, blocked_by, dispatch, sync, close-back, lifecycle, provenance]
---

# ADR-0042 — GitHub ⇄ Podium dispatch bridge

**Status: `accepted` (grill 2026-07-18, Podium issue #505). Bridge + sync CLI + Sync button + close-back + blocked_by sort fix landed live 2026-07-19; smoke (GH #10 + children #12/#13) auto-landed to SHAs `cf7b922` + `3b95a21` and closed back to GitHub.**

GitHub remains the canonical, human-visible issue surface for the `grill → to-spec → to-tickets → implement → finish-spec` pipeline; Podium becomes the private execution mirror the scheduler dispatches from. The bridge is opt-in per binding (resolved at runtime by the binding's git remote shape) and does not change either store's semantics [source: docs/adr/0042-github-podium-dispatch-bridge.md].

## Sync: GitHub → Podium, re-runnable, insert-only

`podium_issues.sync_from_github(repo, bindings_path=...)` shells `gh issue list --label ready-for-agent --state open` scoped to the binding's repo, filters to children carrying a `## Parent` section (parent spec never mirrored), and for each match looks up Podium by `external_id = "github:<owner>/<repo>#<number>"`:

- **not found → INSERT** a new `todo` Podium issue. `auto_land` decided at insert time via `scheduler._extract_runnable_verification` (the same extractor ADR-0023 slice #120 uses for review backstop): verification present → `auto_land=true`; absent → `auto_land=false`. Bridge never fabricates a verification command. `## Blocked by` edges map to Podium `blocked_by` for dependency ordering.
- **found → skip.** Never mutates existing rows (no title/body overwrite, no state change). "Press again" is always safe even while issues are `running`/`in_review`.

The unique `external_id` index makes the upsert key idempotent. Re-running Sync picks up child issues added later without duplicating rows. A human closing the GitHub issue mid-flight does not stop Podium: the scheduler dispatches purely from local SQLite (`tracker_podium.list_candidates` reads `issue.*` only; `transition_state` runs a local `UPDATE`) — neither path shells `gh` nor reads GitHub [source: docs/adr/0042-github-podium-dispatch-bridge.md section 1; source: tracker_podium.py:319, 457; source: web/api/schema.py:67,86].

### Close-back is the ONLY Podium→GitHub write

`PodiumTrackerAdapter.transition_state` (tracker_podium.py:460) is the single seam. When the next state is `done` and the previous state was not `archived`/already-`done`, `_maybe_close_back_github` (tracker_podium.py:503) fires `gh issue close <n> --comment "Landed in <sha>."` for any issue whose `external_id` starts with `github:`. This centralized seam covers all four `STATE_DONE` call sites (`scheduler/__init__.py:1566`, `:1805`, `:2290`, `:2482`). The bridge fires close-back exactly once per real →done transition; subsequent done flips on already-closed issues no-op (`gh issue close` returns "already closed", tolerated and logged). Fail-soft: missing `gh`, unauthed `gh`, or any subprocess failure logs a warning and returns without changing the Podium `done` transition [source: tracker_podium.py:457-525; source: docs/adr/0042-github-podium-dispatch-bridge.md section 2].

## Insert-time `auto_land` provenance gate (C-0384)

The bridge decides `auto_land` by calling the existing `scheduler._extract_runnable_verification(body)` extractor (scheduler/__init__.py:396). Because the gate is at INSERT time (not at the scheduler terminal), a verification-less issue can never reach the auto-land terminal at `scheduler/__init__.py:2290` (guarded by `if not auto_land`). This is the same provenance principle as ADR-0023 (`auto_land` must be explicit, never inferred), but generalized: any issue with a runnable `## Verification` qualifies — slicer-stamped or otherwise.

**Format constraint (load-bearing, live-verified this session).** `_extract_runnable_verification` parses the `## Verification` section by splitting on backticks (`body.split("`")`) and treating the ODD-indexed parts as command text:

- **Single-backtick inline form (e.g. `` `uv run pytest -q` ``)** → recognized; multiple inline commands chained with the word `and` between them join with ` && `.
- **Triple-backtick fenced form (e.g. ```` ```bash\nuv run pytest -q\n``` ````)** → returns empty (`len(parts) % 2 == 0`).
- **Prose-only verification** → returns empty (no backticks at all).

Practical consequence for `to-tickets` output: slices (or operators) writing `## Verification` must use the inline single-backtick form to get `auto_land=true`. Fenced heredocs silently drop to `auto_land=false` even when the command is runnable. The same extractor is used by `scheduler._handle_review_terminal_done` (ADR-0023 review backstop), so the same format rule governs both gates [source: scheduler/__init__.py:396-422; source: docs/adr/0042-github-podium-dispatch-bridge.md section 1].

## `external_id` namespace and dedup (C-0385)

GitHub-mirrored Podium issues use `external_id = "github:<owner>/<repo>#<number>"` (e.g. `github:shreeve1/symphony#12`). This is the **second** documented `external_id` convention alongside `automation:<id>:loop` (ADR-0015); both are prefix-namespaced so lookups stay unambiguous and the UNIQUE index (`ix_issue_external_id`, `web/api/schema.py:86`) handles dedup structurally. The column is nullable free-form TEXT so adding more conventions (e.g. `jira:...`, `linear:...`) requires no schema change — just another prefix namespace.

**Runtime resolvability is the opt-in mechanism.** A binding whose git remote does not parse as GitHub-shaped (via `resolve_github_repo(repo_path)`, which handles both `git@host:owner/repo.git` SSH-alias remotes and HTTPS forms) simply has no Sync button — no `bindings.yml` field needed. The `github-personal` SSH-alias caveat in `CLAUDE.md` matters here: a binding whose remote uses a non-GitHub alias (the wrong account) will resolve to the wrong owner/repo [source: docs/adr/0042-github-podium-dispatch-bridge.md section 1].

## sync_from_github blocked_by sort fix (C-0386)

**Bug:** `gh issue list --label ready-for-agent` returns issues **newest-first**. When a dependent child (higher issue number) was listed before its blocker (lower number), the dependent inserted first and its `## Blocked by` edge lookup found no mirrored blocker → the edge was **silently dropped within a single sync pass**. Live smoke (2026-07-19) demonstrated this on GH #13 (blocked_by #12): both children mirrored and auto-landed (SHAs `cf7b922` and `3b95a21`), but GitHub #13 mirrored to Podium #522 carried `blocked_by=[]` instead of `[#523]`. The dispatch ordering invariant was violated but the end-to-end smoke "looked green" — classic self-masking failure mode.

**Fix (commit `430e468`, symphony `fix(#514)`, 2026-07-19):** `child_issues.sort(key=lambda item: int(item["number"]))` before insert. `to-tickets` publishes blockers before dependents (blockers carry lower numbers), so ascending sort is the right invariant. Regression test `test_sync_maps_blocked_by_within_single_pass_newest_first` in `web/cli/tests/test_podium_issues.py` reproduces the newest-first ordering (fails without the sort). Full suite green (1678 passed). Same class of bug as C-0373 (bare-provider-name trap): both surfaced only via a real end-to-end smoke, not by unit tests with stubbed data sources [source: web/cli/podium_issues.py:461,471; source: web/cli/tests/test_podium_issues.py:868; source: commit 430e468].

## Podium frontend slice requires explicit `pnpm build` + restart (C-0387)

`podium-web.service` runs `pnpm start -p 8091` (serves the prebuilt `.next` bundle) with **no `ExecStartPre` build step**. Therefore a frontend-only slice that adds UI code (e.g. #516's Sync-from-GitHub button) does **not** appear on the live Podium UI until an explicit `cd web/frontend && pnpm build && sudo systemctl restart podium-web.service` is run. The repo commit alone is not enough.

Live-observed 2026-07-19: the Sync button code shipped in commit `38501da feat(#516)` but the live UI did not render the button until an out-of-band `pnpm build` + `systemctl restart podium-web.service` ran. This gotcha is **complementary** to the existing `deploy.sh` hazard cluster (C-0347 stale `.next/cache`, C-0348 `deploy.sh` systemctl stop/start race, C-0354 `next-server` SIGTERM-ignore / 10s stop bound) — those cover hazards *during* a deploy; C-0387 covers the slice-side miss of *not invoking deploy at all* [source: /etc/systemd/system/podium-web.service; source: commit `38501da`; source: web/frontend/deploy.sh; source: wiki/analyses/podium-frontend-deploy-cosmetics.md].

## Posture: GitHub-primary, Podium-private

Humans read, comment, and triage in **GitHub** (unchanged `to-spec` / `to-tickets`). Podium is an internal execution detail — the mirror row and its Run history. The pipeline becomes `grill → to-spec → to-tickets → [click Sync from GitHub] → [scheduler runs the backlog] → finish-spec`. The `implement` skill and the two spawn automations are dropped — the scheduler **is** the implement+review loop.

**Parent spec close is `finish-spec`'s job, not the bridge's.** The bridge only closes each *child* GitHub issue on its Podium `done`. The parent spec issue is closed by `finish-spec`, which already closes the spec last — only after every child ticket is closed, the suite is green, and the acceptance criteria pass [source: skills/finish-spec/SKILL.md; source: docs/adr/0042-github-podium-dispatch-bridge.md section 3].

## Cross-repo note (DOTFILES-binding change)

The `to-tickets` `## Verification` field is a **dotfiles-binding** change (delivered via dotfiles Podium issue #520, landed dotfiles commit `b349dfd` this session), **not** part of symphony #513-517. The bridge inherits the `## Verification` discipline from `to-tickets`'s existing prompt-renderer contract — it does not add or enforce new prose at the bridge level.

## Citations

- ADR: `docs/adr/0042-github-podium-dispatch-bridge.md` (status: accepted)
- Sync CLI: `web/cli/podium_issues.py:325+` (`sync_from_github`, `_extract_blocked_by_numbers`)
- Tracker close-back seam: `tracker_podium.py:460` (`transition_state`), `:503` (`_maybe_close_back_github`)
- Schema: `web/api/schema.py:67,86` (`external_id TEXT`, `ix_issue_external_id`)
- Verifier extractor: `scheduler/__init__.py:396` (`_extract_runnable_verification`)
- Auto-land terminal guard: `scheduler/__init__.py:2290` (`if not auto_land`)
- STATE_DONE sites: `scheduler/__init__.py:1566, 1805, 2290, 2482`
- Sort fix + regression: commit `430e468` (2026-07-19); `web/cli/tests/test_podium_issues.py:868`
- Podium-web prebuild-serve: `/etc/systemd/system/podium-web.service` (`ExecStart=/usr/bin/pnpm start -p 8091`, no `ExecStartPre`)
- Smoke evidence: live Podium issues #522 (GH #12) and #523 (GH #13), SHAs `cf7b922` + `3b95a21`