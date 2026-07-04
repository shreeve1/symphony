# Wiki Log

## [2026-06-26] session-update | Issue 141 worktree gitlink tracking fix

- Actor: agent (Pi), direct investigation + repo configuration fix.
- Inputs: user question about Issue 141; `podium.db` issue 141; `/etc/systemd/system/podium-api.service`; `.gitignore`; base repo git status.
- Outputs: updated `.gitignore` to globally ignore `worktrees/`; removed tracked worktree gitlinks from the git index (`git rm --cached -r worktrees/`); updated `wiki/CLAIMS.md` (C-0342); this log entry.
- Notes: Discovered that worktrees were being tracked as `160000` gitlinks because `worktrees/` was missing from `.gitignore`. When the agent committed work in the worktree, the base repository registered a modified gitlink (` M worktrees/symphony/141`), which caused `base_repo_dirty` to return True and blocked the worktree auto-merge/land during the transition of the issue state to "done". Untracking and ignoring the directory fixed it permanently. No secrets read, no restart needed.


## [2026-06-25] session-update | Issue #137 ADR-0026 review-run transient retry

- Actor: agent (Pi), direct implementation.
- Inputs: Podium Issue #137 / ADR-0026 review retry slice; `scheduler/__init__.py`; `scheduler/transient_retry.py`; `redispatch_core.py`; `tracker_podium.py`; `web/api/schema.py`; `web/api/migrations/versions/0012_retry_verdict.py`; `tests/test_scheduler.py`; issue verification command.
- Outputs: added review-run transient retry in `_classify_terminal`, writing `retry` Run verdict plus retry/reland-pending markers and returning the Issue to `in_review`; preserved review re-entry through `candidate.review_dispatch` after the retry cooldown; added cap-exhaustion block+notify behavior; added Podium schema revision `0012_retry_verdict`; updated `wiki/analyses/adr-0026-transient-failure-retry.md`, `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0333), `wiki/eval/worktree.eval`, and this log entry.
- Notes: Verification passed as issue-specified (`uv run pytest tests/test_scheduler.py tests/test_tracker_podium.py -q`, 219 passed). Additional checks passed: `uv run pytest tests/test_alembic_baseline.py -q`, `uv run ruff check redispatch_core.py scheduler/transient_retry.py scheduler/__init__.py tracker_podium.py tests/test_scheduler.py web/api/schema.py web/api/migrations/versions/0012_retry_verdict.py`, `git diff --check`, and touched-file LSP diagnostics. No secrets/env files read; no service restart, live DB migration, or outward notification.

## [2026-06-25] session-update | Issue #135 ADR-0026 auto-land re-drive

- Actor: agent (Pi), direct implementation.
- Inputs: Podium Issue #135 / ADR-0026 auto-land slice; `scheduler/__init__.py`; `tests/test_scheduler.py`; `docs/adr/0026-transient-failure-retry-not-block.md`; issue verification command.
- Outputs: added one in-process `_land_review_worktree` retry after `asyncio.sleep(2.0)` for any review-terminal auto-land failure; added scheduler regressions for fail-then-success, fail-twice, and sleep delay; updated `wiki/analyses/adr-0026-transient-failure-retry.md`, `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0332), `wiki/eval/worktree.eval`, and this log entry.
- Notes: Verification passed as issue-specified (`uv run pytest tests/test_scheduler.py tests/test_tracker_podium.py -q`, 216 passed) after `uv sync --extra dev` installed the local dev extra. Touched-file LSP diagnostics passed. No secrets/env files read; no service restart, live DB mutation, or outward notification.

## [2026-06-24] session-update | Issue #132 ADR-0024 dirty reland redispatch

- Actor: agent (Pi), direct implementation.
- Inputs: Podium Issue #132 / ADR-0024 slice 5; `scheduler/__init__.py`; `tracker_podium.py`; `redispatch_core.py`; `tests/test_scheduler.py`; `tests/test_tracker_podium.py`; issue verification command.
- Outputs: replaced dirty-but-passing coding review instant block with capped commit-redispatch; added `auto_land=true` reland-pending marker and clean auto-land reland-done balancing; extended Podium review candidate selection for unconsumed reland markers; refined the empty-diff guard to block only clean no-op branches so dirty empty-diff worktrees reach commit-redispatch; updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`, `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0329/C-0330; C-0328 superseded), `wiki/eval/worktree.eval`, and this log entry.
- Notes: Verification passed exactly as issue-specified (`uv run pytest tests/test_scheduler.py tests/test_tracker_podium.py -q`, 215 passed) after `uv sync --extra dev` installed the local dev extra. Advisor review caught the initial empty-diff shadowing bug before finalization; fixed and re-verified. Touched-file LSP diagnostics passed. No secrets/env files read; no service restart, live DB mutation, or outward notification.

## [2026-06-24] session-update | Issue #131 ADR-0024 empty-diff guard

- Actor: agent (Pi), direct implementation.
- Inputs: Podium Issue #131 / ADR-0024 slice 4; `web/api/worktree.py`; `worktree_facade.py`; `scheduler/__init__.py`; `web/api/tests/test_worktree.py`; `tests/test_scheduler.py`; issue verification command.
- Outputs: added `worktree_diff_empty`; re-exported it via `worktree_facade`; added coding-review empty-diff blocking before backstop/dirty/auto-land/landing; added focused worktree helper tests and scheduler regression; updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0328); this log entry.
- Notes: Verification passed as issue-specified (`uv run pytest web/api/tests/test_worktree.py tests/test_scheduler.py -q`, 228 passed, 1 Starlette/httpx deprecation warning) after `uv sync --extra dev` installed the local dev extra. Ruff and touched-file LSP diagnostics passed. No secrets/env files read; no service restart, live DB mutation, or outward notification.

Append entries with this format:

## [2026-06-24] session-update | Podium flyout markdown overflow fix

- Actor: agent (Pi), direct diagnosis + deploy.
- Inputs: operator report of horizontal scroll when opening issue flyout; `podium.db` issue 66 copied for local UI probe; `web/frontend/components/Markdown.tsx`; `web/frontend/tests/flyout-tabs.spec.ts`; `web/frontend/deploy.sh`.
- Outputs: committed `24d80f4` to wrap markdown `<pre>` diagnostic blocks; added e2e regression for patrol-style fenced JSON markers; deployed via `web/frontend/deploy.sh`; updated `wiki/analyses/podium-run-log-cap-and-flyout-dedup.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0327); added `wiki/eval/podium-ui.eval`; this log entry.
- Notes: Playwright probe against a copied live DB showed `view-comments_md` horizontal overflow fell from 4003px to 0px. Verification passed: touched-file LSP diagnostics, `pnpm exec tsc --noEmit`, `PYTHONPATH=../.. pnpm exec playwright test tests/flyout-tabs.spec.ts --project=chromium`, copy-of-live-DB probe, and deploy root=200. No env file or secret read; live DB not mutated.

## 2026-06-24 — ADR-0023 deploy + live review-phase verification

- Action: update.
- Inputs: Ralph issue #122 live deploy/verification session.
- Outputs: deployed review phase to live Symphony, fixed Pi RPC worktree cwd drift, verified auto-land/operator-gate/backstop/dirty-guard live smokes, updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`, `wiki/index.md`, `wiki/CLAIMS.md` (C-0316 superseded by C-0323), and this log entry.

## [2026-06-24] session-update | Issue #130 ADR-0024 validation review branch

- Actor: agent (Pi), direct implementation.
- Inputs: Podium Issue #130 / ADR-0024 slice 3; `prompt_renderer.py`; `scheduler/__init__.py`; `tests/test_prompt_renderer.py`; `tests/test_scheduler.py`; issue verification command.
- Outputs: added `VALIDATION_REVIEW_PREAMBLE` and `render_review_prompt` branching by `review_mode`; added validation-mode review terminal handling after the `candidate.review_dispatch` provenance gate; updated coding-path scheduler fixtures; added renderer and scheduler regression tests; updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0326); updated `wiki/eval/podium-api.eval`; this log entry.
- Notes: Verification passed exactly as issue-specified (`uv run pytest tests/test_prompt_renderer.py tests/test_scheduler.py -q`, 208 passed) after installing the dev extra into the local uv venv. Ruff and LSP diagnostics passed. Wiki gate audit required normalizing pre-existing C-0324 kind from `root-cause` to `gotcha`. No secrets/env files read; no service restart, live DB mutation, or outward notification.

## [YYYY-MM-DD] type | Title

- Actor: agent or human
- Inputs: paths or prompt summary
- Outputs: changed pages
- Notes: key decisions or unresolved questions

---

## [2026-06-24] session-update | Ralph issue #120 review verification backstop

- Actor: agent (Pi), Ralph implementation + fresh review.
- Inputs: `.kanban/issues/120-review-verification-backstop.md`; `git diff ea6ddd644cf16f46fa0c33e923482e5042cfd28a HEAD`; `scheduler/__init__.py`; `tests/test_scheduler.py`; issue verification command.
- Outputs: implemented the Python runnable-verification extractor and review-terminal backstop; marked `.kanban/issues/120-review-verification-backstop.md` done; updated `.kanban/progress.md`; updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0322); updated `wiki/eval/podium-api.eval`; this log entry.
- Notes: Verification passed exactly as issue-specified (`uv run pytest tests/test_scheduler.py -q`, 195 passed after adding missing passing-backstop coverage). Ruff, py_compile, and touched-file LSP diagnostics passed; fresh review returned `RALPH_REVIEW: PASS`. No env files read; no service restart, live DB mutation, or outward notification.

## [2026-06-24] session-update | Ralph issue #116 REVIEW_PREAMBLE renderer

- Actor: agent (Pi), Ralph implementation + fresh review.
- Inputs: `.kanban/issues/116-review-preamble-renderer-constant.md`; `git diff 5fc06962b3bbc71ba22bacfb9fd6735bc574d47c HEAD`; `prompt_renderer.py`; `tests/test_prompt_renderer.py`; issue verification command.
- Outputs: implemented `REVIEW_PREAMBLE` and `render_review_prompt(issue)`; marked `.kanban/issues/116-review-preamble-renderer-constant.md` done; updated `.kanban/progress.md`; updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0321); updated `wiki/eval/podium-api.eval`; this log entry.
- Notes: Verification passed exactly as issue-specified (`uv run pytest tests/test_prompt_renderer.py -q` and `uv run python -m py_compile prompt_renderer.py`). Ruff and touched-file LSP diagnostics passed; fresh review returned `RALPH_REVIEW: PASS`. No env files read; no service restart, live DB mutation, or outward notification.

## [2026-06-24] session-update | Ralph issue #114 auto_land schema/read path

- Actor: agent (Pi), Ralph implementation + fresh review.
- Inputs: `.kanban/issues/114-issue-auto-land-column.md`; `git diff d5bd697adf9f6976ac6ae0f92461a5eb6309a023 HEAD`; `web/api/schema.py`; `web/api/migrations/versions/0011_issue_auto_land.py`; `tracker_podium.py`; `tests/test_tracker_podium.py`; issue verification command.
- Outputs: implemented `issue.auto_land` schema/Alembic/read-path slice; marked `.kanban/issues/114-issue-auto-land-column.md` done; updated `.kanban/progress.md`; updated `wiki/concepts/podium-tracker.md`; updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0320; normalized pre-existing C-0316 kind to pass audit); updated `wiki/eval/podium-api.eval`; this log entry.
- Notes: Verification passed exactly as issue-specified (`uv run pytest tests/test_alembic_baseline.py -q` and `uv run python -m py_compile web/api/schema.py tracker_podium.py`). `tests/test_tracker_podium.py` and an 0011 upgrade/downgrade smoke also passed; touched-file LSP diagnostics only reported environment-only Alembic/SQLAlchemy import noise in the migration. No secrets/env files read; no service restart, live DB migration, or outward notification.

## [2026-06-24] session-update | Ralph issue #113 FF merge rebase retry

- Actor: agent (Pi), Ralph implementation + fresh review.
- Inputs: `.kanban/issues/113-ff-merge-rebase-retry.md`; `git diff 38d2e4452016fb8b924fc70cc81858374ddfc640 HEAD`; `web/api/worktree.py`; `web/api/tests/test_worktree.py`; issue verification command.
- Outputs: implemented one local rebase+FF retry for non-conflicting diverged-base worktree merges; marked `.kanban/issues/113-ff-merge-rebase-retry.md` done; updated `.kanban/progress.md`; updated `wiki/analyses/analysis-session-worktree-done-commit-redispatch.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0319, C-0087 superseded); updated `wiki/eval/worktree.eval`; this log entry.
- Notes: Verification passed exactly as issue-specified (`uv run pytest web/api/tests/test_worktree.py -q`, 24 passed). Ruff, py_compile, and touched-file LSP diagnostics passed; fresh review returned `RALPH_REVIEW: PASS`. Initial non-login shell lacked `uv` on PATH, so verification used `PATH=/home/james/.local/bin:$PATH` while running the exact issue command. No secrets/env files read; no service restart, live DB mutation, or outward notification.

## [2026-06-24] session-update | Issue #105 remote Claude edit+commit landing smoke

- Actor: agent (Pi), direct live smoke harness.
- Inputs: `.kanban/issues/105-remote-claude-edit-commit-landing-smoke.md`; `runs/105-remote-claude-edit-smoke.log`; `claude_runner.py`; `claude_host.py`; n8n SSH verification commands.
- Outputs: marked `.kanban/issues/105-remote-claude-edit-commit-landing-smoke.md` done; updated `.kanban/progress.md`; updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0314); updated `wiki/eval/model-catalog.eval`; this log entry.
- Notes: Used the allowed direct-harness route to avoid production `bindings.yml` mutation and `symphony-host` restart while still exercising `ClaudeAgentAdapter(remote=RemotePolicy(...))` → `SshClaudeHost` → `run_claude_agent`. Remote Claude committed `7f34e32 smoke: remote claude edit commit` in disposable n8n checkout `/tmp/symphony-105-remote-claude-20260624005402-26879`; independent verification showed empty `git status --short`, no issue-specific `symphony-claude-105-remote-edit-smoke-*` temp/tmux residue, and the checkout was removed. No secrets/env files read; no temp binding was created.

## [2026-06-23] session-update | Issue #103 remote Claude scheduler/config/routing wiring

- Actor: agent (Pi), via `dev-build` workflow.
- Inputs: `.kanban/issues/103-scheduler-config-routing-wiring.md`; `plans/feature-remote-claude-dispatch.md` Group 5; `scheduler/__init__.py`; `config.py`; `agent_runner.py`; `claude_runner.py`; `main.py`; targeted pytest/ruff/py_compile verification; pi wave-audit attempt.
- Outputs: implemented remote+Claude dispatch gate/config/routing/adapter wiring; marked `.kanban/issues/103-scheduler-config-routing-wiring.md` done; updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0312); updated `wiki/eval/model-catalog.eval`; this log entry.
- Notes: Remote bindings can now use `default_agent: claude`: scheduler permits remote+Claude and skips the local Claude probe, resume prep cold-refeeds remote Claude before local transcript checks, config allows remote Claude while preserving `claude_persist`/coding guards, routing sends remote Claude to `ClaudeAgentAdapter`, and `main.build_binding_runtime` supplies `remote`/`remote_repo_path` so the adapter constructs `SshClaudeHost`. Verification passed (`291 passed, 1 skipped` for issue command; `361 passed, 1 skipped` for affected runner suite; ruff/py_compile clean). Pi wave audit retried after an initial timeout and passed with 0 critical / 0 warning / 1 note; the note was addressed with explicit remote+Claude config guard tests; logged in ignored state file `plans/.feature-remote-claude-dispatch.state.yml`. No secrets/env files read; live calibration remains #104.

## [2026-06-23] session-update | Issue 112 duplicate model-id block

- Actor: agent (Pi), via `diagnose` workflow + `symphony-restart` restart ritual.
- Inputs: operator report for symphony Issue 112; `podium.db` issue/run rows; `journalctl -u symphony-host.service` around 16:58, 21:49, and 21:59 UTC; `model_catalog.py`; `models.yml`; `wiki/analyses/podium-issue-dispatch-contract.md`.
- Outputs: restarted `symphony-host.service` from stale `code_sha=ed887e5` to `code_sha=a2e16c7`; requeued Issue 112 through `web.api.main.patch_issue(..., {"state":"todo"})`; updated `wiki/analyses/podium-issue-dispatch-contract.md`; updated `wiki/CLAIMS.md` (C-0311); updated `wiki/eval/model-catalog.eval`; this log entry.
- Notes: Root cause was deployment ordering, not bad Issue data: live scheduler loaded old global-unique-id validator but re-read the new duplicate-id `models.yml` on dispatch, producing `Dispatch blocked: model resolution failed: duplicate model id: claude-opus-4-8`. After restart, startup probes/reconcile passed, Issue 112 requeued, and Run 323 claimed/dispatched with Claude `claude-opus-4-8`. No env file or secret read; no direct Podium SQLite mutation.

## [2026-06-23] session-update | Pi CLIProxy model catalog update

- Actor: agent (Pi), via `symphony-models` skill.
- Inputs: operator request to add only Pi CLIProxy provider models; `pi --list-models cliproxy --offline`; `~/.pi/agent/settings.json` enabled model list; `models.yml`; `model_catalog.py`; `web/frontend/components/NewIssueModal.tsx`; focused pytest/tsc verification.
- Outputs: commit `0c2e167` adding Pi CLIProxy model entries and changing model catalog identity to `(agent, provider, id)`; updated `wiki/analyses/podium-028-model-catalog-searchable-dropdowns.md`; updated `wiki/analyses/podium-issue-dispatch-contract.md`; updated `wiki/analyses/symphony-skills-index.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0310); updated `wiki/eval/model-catalog.eval`; this log entry.
- Notes: Added `claude-haiku-4-5-20251001`, `claude-opus-4-8`, and `claude-sonnet-4-6` as `agent: pi`, `provider: cliproxy` without changing the existing Pi default (`gpt-5.5`). The opus/sonnet ids intentionally collide with Claude-agent entries, so validation now rejects only duplicate `(agent, provider, id)` entries; dispatch resolves duplicate bare ids by the selected agent and accepts `provider/id` for same-agent provider disambiguation. Verification passed: `_load_models(Path('models.yml'))`, 75 focused pytest tests, exact skill test, frontend `pnpm exec tsc --noEmit`, LSP diagnostics, and direct pi one-shot checks for all three CLIProxy models with Symphony's `:high` suffix (`ok`). No service restart, Plane API call, env-file read, direct DB edit, or secret print.

## [2026-06-23] session-update | Issue #102 remote Claude modal/session behavior

- Actor: agent (Pi), Ralph implementation + fresh review
- Inputs: `.kanban/issues/102-remote-modal-continuity-steering.md`; `git diff 2c085d9af2c160022d2307aff12efe51bd840391 HEAD`; `claude_runner.py`; `tests/test_claude_runner.py`; issue verification command.
- Outputs: updated `.kanban/issues/102-remote-modal-continuity-steering.md`; updated `.kanban/progress.md`; updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; this log entry.
- Notes: #102 decouples Claude permission/question modal handling from the idle gate, forces remote Claude launches to use `--session-id`, and makes remote steering delivery a no-op. Verification passed exactly as issue-specified (71 pytest tests; ruff clean), touched-file LSP diagnostics were clean, and fresh review returned `RALPH_REVIEW: PASS`. Claim row was not added; the promoted ADR analysis carries the durable fact. Wiki claim budget was set to 300 so `gate.py audit` matches the curated wiki scale (259 active claims).

---

## [2026-06-23] session-update | Issue #100 Claude runner host-mediated tmux cleanup

- Actor: agent (Pi), Ralph implementation + fresh review
- Inputs: `.kanban/issues/100-route-runner-tmux-cleanup-through-host.md`; `git diff b76db6cef32e4504cc9eb32d939f5b56d4702ad7 HEAD`; `claude_runner.py`; `claude_host.py`; `tests/test_claude_runner.py`; `tests/test_claude_persist.py`; `tests/test_claude_host.py`; issue verification command.
- Outputs: updated `.kanban/issues/100-route-runner-tmux-cleanup-through-host.md`; updated `.kanban/progress.md`; updated `docs/adr/0012-remote-binding-ssh-exec.md`; updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; this log entry.
- Notes: #100 routes Claude tmux helpers, persistent-session liveness, and cleanup through explicit `ClaudeHost` arguments. Remote fake `SshClaudeHost` tests assert `has-session`, pane capture, `kill-session`, and cleanup use SSH-wrapped tmux/rm commands. Verification passed exactly as issue-specified (82 pytest tests; ruff clean), touched-file LSP diagnostics were clean, and fresh review returned `RALPH_REVIEW: PASS`. Claim row was not added because `wiki/CLAIMS.md` is already over budget; the promoted ADR analysis carries the durable fact.


## [2026-06-23] session-update | Issue #100 Claude runner host routing actionable review

- Actor: agent (Pi), Ralph actionable review loop
- Inputs: `.kanban/issues/100-route-runner-tmux-cleanup-through-host.md`; `git diff b176dab83316e93fb55abaf978f11a429f77d6d6 HEAD`; `claude_runner.py`; `claude_host.py`; `tests/test_claude_runner.py`; `tests/test_claude_host.py`; issue verification command.
- Outputs: committed review fix `27e2394`; updated `.kanban/issues/100-route-runner-tmux-cleanup-through-host.md`; updated `.kanban/progress.md`; updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; this log entry.
- Notes: Review found #100's tmux/cleanup host routing mostly complete but fixed remaining local prompt writes for steer/nudge/question autoreply, remote socket existence checks, and stale docs that still said runner routing was deferred. Verification passed exactly as issue-specified (`.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py tests/test_claude_host.py -q && /usr/local/bin/ruff check claude_runner.py claude_host.py`, 84 passed; ruff clean) and touched-file LSP diagnostics were clean. No `wiki/CLAIMS.md` row was added because the claim table was already over budget per the prior #99 gate.


## [2026-06-23] session-update | Issue #99 ClaudeHost seam actionable review

- Actor: agent (Pi), Ralph actionable review loop
- Inputs: `.kanban/issues/099-claudehost-seam-completion.md`; `git diff 2ba032d9832d1a83db846075c5d000edc01b6e5d HEAD`; `claude_host.py`; `tests/test_claude_host.py`; issue verification command.
- Outputs: updated `.kanban/issues/099-claudehost-seam-completion.md` with `action_reviewed: 2026-06-23`; updated `.kanban/progress.md`; updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; this log entry.
- Notes: Review found #99 correct and purely additive: `ClaudeHost`/`LocalClaudeHost`/`SshClaudeHost` now expose `tmux_argv`, `is_remote`, and `rmtree`; `claude_runner.py` call-site mediation remains deferred to the next remote-Claude slice. Verification passed exactly as issue-specified (`.venv/bin/python -m pytest tests/test_claude_host.py tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_host.py`, 80 passed; ruff clean) and touched-file LSP diagnostics were clean. Claim gate check for an atomic #99 claim returned `EVICT_FIRST` because `wiki/CLAIMS.md` is already over budget (257 active > 40), so no claim row was added and broad claim demotion was deferred.


## [2026-06-23] session-update | Global run timeout default raised to 2 hours

- Actor: agent (Pi)
- Inputs: operator request after Run #258 timeout; `config.py`; `tests/test_config.py`; `runs/258.log`.
- Outputs: updated `config.py`; updated `tests/test_config.py`; updated `wiki/analyses/podium-issue-dispatch-contract.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/concepts/prompt-renderer.md`; updated `wiki/CLAIMS.md`; this log entry.
- Notes: Default `SymphonyConfig.run_timeout_ms` and `SYMPHONY_RUN_TIMEOUT_MS` fallback changed from `3_600_000` to `7_200_000` ms. Env override remains authoritative; live `symphony-host.service` needs a restart to load the code/default for new dispatches. Verified with `py_compile config.py` and `pytest tests/test_config.py -q` (55 passed).


## [2026-06-23] session-update | Run #242 summary END marker tolerance

- Actor: agent (Pi), via `/grill-me`
- Inputs: Issue #98 / Run #242 operator request; `runs/242.log`; `scheduler/markers.py`; `tests/test_schedule.py`; live `podium.db` read/backfill for Run 242 / Issue 97.
- Outputs: updated `wiki/analyses/podium-046-unified-output-contract.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; this log entry.
- Notes: Root cause was parser strictness, not missing agent output: `SYMPHONY_SUMMARY_END` was glued to trailing prose, so `_parse_summary_block` missed a valid summary and the completion comment fell back to "Agent finished without a summary." Commit `0ac7c5e` makes the summary END token close the block even with same-line trailing text and adds a regression test. Run #242 / Issue #97 was backfilled from the existing log. Claim gate was checked but no new claim was admitted because the hot claim file is over budget; no secrets or env files were read. Service restart/deploy was deferred because the working tree contains unrelated pre-existing changes.


## [2026-06-21] session-update | Issue #84 flyout staged controls decision

- Actor: agent (Pi) + operator (James), via `/grill-me`
- Inputs: Issue #84 operator request; accepted operator reply "Yes"; code inspection of `web/frontend/components/IssueFlyout.tsx`, `web/api/main.py`, and `bindings.yml`; existing ADR-0018/C-0299 schedule UI docs.
- Outputs: new raw capture `wiki/raw/sessions/2026-06-21-issue-084-flyout-staged-controls.md`; updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md`; updated `wiki/CLAIMS.md` (C-0301 added, C-0299 noted as implementation-current but target-superseded); updated `wiki/index.md`; updated `wiki/ROUTING.md`; this log entry.
- Notes: Verified Schedule=Yes currently applies immediately and moves the issue to To Do because the flyout calls `/schedule` and the backend forces `state='todo'`. Operator accepted the target behavior: Schedule and approval-affecting flyout controls should stage until Send with the comment; ordinary metadata can remain immediate-save. Approval/Approved controls should hide for homelab because `approval.enabled=false`. No code implementation, service restart, live Podium mutation, secrets, or env files.


## [2026-06-20] session-update | ADR-0015 patrol→Podium first-live-cycle verification + post-cutover fixes

- Actor: agent (Claude Code) + operator (James); operator-approved manual patrol triggers, operator fixed the pi extension
- Inputs: handoff `/tmp/handoff-3LhvCu.md`; live read-only diagnosis (worker/symphony-host journals, `podium.db` issues 62–72, bearer/token-hash probes, `temporal schedule list/describe`, `temporal workflow describe`); homelab `podium_adapter.py`/`patrol_plane.py`/`schedule_patrols.py`/`WORKFLOW.md`; symphony `prompt_renderer.py` (trailer-parse grep); `~/dotfiles/.pi/agent/extensions/ponytail/`
- Outputs: homelab commit `a716349` (`PodiumAdapter._coerce_row_id` int→str fix + 2 regression tests; `WORKFLOW.md` Plane-CLI→`SYMPHONY_RESULT` cleanup); new raw capture `wiki/raw/sessions/2026-06-20-patrol-podium-cutover-verify-and-fixes.md`; updated `wiki/analyses/adr-0015-patrol-podium-tracker-adapter.md` (first-live-cycle section + sources/frontmatter); `wiki/CLAIMS.md` (C-0271–C-0275 added; C-0270 qualified); `wiki/index.md`; `wiki/ROUTING.md`; this log entry. Live: worker restarted onto `a716349`; all 6 patrol schedules unpaused (operator-approved); issue 62 re-dispatched to verify pi.
- Notes: The first real patrol finding wedged `PatrolWorkflow` — live podium-api returns INTEGER issue ids, `TicketActivityOutcome.issue_id` is `str | None`, Temporal rejected the int at the activity-result boundary and retried forever; the Podium write itself succeeded (create/dedup/marker/`med` all correct). Mock/real divergence (in-memory transport stringifies ids; dry-run had no real id) masked it. Fixed by coercing at the adapter boundary; re-verified `COMPLETED`. Confirmed (operator-accepted) that patrol findings auto-dispatch a pi agent that remediates the live host. Retired Plane-CLI completion residue from homelab WORKFLOW.md (nothing parses the issue commit trailer). Answered "why paused": schedules are created paused by design (`schedule_patrols.py:111`); Wave C never ran the unpause — now all 6 unpaused (infra next 15:00 UTC). A freshly-installed broken `ponytail` pi extension (CJS `require` in a `type:module` package) briefly disabled ALL pi dispatch host-wide; operator fixed via `createRequire` shim, re-verified. Pre-existing stale test `test_prompt_renderer.py::...documents_medium_risk_autonomy` fails before+after (excluded-service names moved to CLAUDE.md by a prior refactor) — not touched. Pre-existing homelab `CLAUDE.md` drift left unstaged. No secret env values printed (token compared by sha256 only).


## [2026-06-20] session-update | ADR-0016 implemented — infra WORKFLOW.md retired → INFRA_PREAMBLE renderer constant

- Actor: agent (Claude Code, /dev-build) + operator (James); operator approved cross-repo edits, the homelab WORKFLOW.md deletion, and chose offline render verification over a live dispatch smoke
- Inputs: `plans/adr-0016-workflow-md-renderer-constant.md`; `docs/adr/0016-workflow-md-retired-renderer-constant.md`; symphony `prompt_renderer.py`/`main.py`/`project_scaffold.py` + tests; homelab `automation/homelab-stack/src/homelab_router/prompt_renderer.py` + test; `~/homelab/CLAUDE.md`; recovered safety policy from homelab commit `ebdc588`; service topology probes (`systemctl is-active/is-enabled symphony-host.service`, unit cat, podium-api import trace)
- Outputs: symphony commit `7e71b10` (INFRA_PREAMBLE constant; infra skips load_workflow; load_workflow/WorkflowConfig/_parse_frontmatter deleted; path vestigial; project_scaffold stops emitting WORKFLOW.md; tests rewritten; test_workflow_author.py retired). Homelab commit `2458429` (WORKFLOW.md deleted; CLAUDE.md gains "Symphony Agent Safety Policy" + scoped "Symphony Unattended Autonomy"; patrol-router repointed to bundled `default_workflow.md`). New raw capture `wiki/raw/sessions/2026-06-20-adr-0016-implementation-landed.md`; `wiki/analyses/adr-0016-workflow-md-retired-renderer-constant.md` (status→landed, consequences updated, source added); `wiki/CLAIMS.md` (C-0276/C-0277/C-0278 flipped decision→implemented; C-0026 amendment updated; C-0282 symphony-host is the live dispatcher / deploy needs a restart + C-0283 patrol-router repoint added); `wiki/index.md` (ADR-0016 row + workflow-homelab row); `wiki/ROUTING.md` (systemd + bindings routes); this log entry.
- Notes: Topology — `symphony-host.service` (the only `render_prompt` consumer via `python -m main`) is the LIVE dispatcher: `disabled` from boot but started operationally; ran 3× on 2026-06-20 (`45564c0`→`d7207f4`→`58e0e4a`, ~393k log lines, polling Podium). `podium-api.service` (always-on) does NOT run the dispatch loop. **Interim error (corrected within session):** a momentary `is-active=inactive` snapshot led to a wrong "dormant by design / deploy=commit / no restart" conclusion (recorded then reversed across C-0282/C-0276/index/ROUTING/ADR/memory). Truth: the service loads code at start, so deploy REQUIRES a restart. Deployed by operator-approved `sudo systemctl restart symphony-host.service` onto `7e71b10` (20:26Z: `symphony_started code_sha=7e71b10 bindings=5`, claude+pi probes ok, no `workflow-missing`, stable PID). [5.3] also verified offline pre-restart (real homelab binding infra+podium): INFRA_PREAMBLE + narrowed rule 11 + identifier substitution + OUTPUT_CONTRACT present, no file-sourced content, WORKFLOW.md absent. Symphony suite 965 pass / 14 pre-existing tests/skills/ failures (absent .claude/skills tree; zero new); homelab-stack 722 pass. pi wave-1 audit passed (0 critical / 1 warning, logged). Live-dispatch autonomy behavior NOT exercised (open follow-up). Per-patrol-skill work + plan/build-mode removal remain out of scope. Pre-existing homelab working-tree drift (config.py/router.py/monitor.py/worker.py + tests) left untouched/unstaged. No secrets printed (PODIUM_API_TOKEN never handled).

---


## [2026-06-18] session-update | ADR-0014 worktree commit-redispatch implemented (build)

- Actor: agent
- Inputs: `/dev-build plans/feature-worktree-done-commit-redispatch.md` build session; diff of `web/api/worktree.py`, `worktree_facade.py`, `web/api/main.py`, `docs/adr/0014-...md`, `web/api/tests/test_worktree*.py`; `plans/.feature-worktree-done-commit-redispatch.state.yml` build audit
- Outputs: new `wiki/raw/sessions/2026-06-18-worktree-done-commit-redispatch-build.md`; updated `analyses/analysis-session-worktree-done-commit-redispatch.md` (Implementation landed section, title/frontmatter accepted); `CLAIMS.md` (+C-0250, C-0247→superseded, C-0248→superseded, C-0086 gap-closed note); `index.md`, `ROUTING.md`
- Notes: ADR-0014 `proposed → accepted`. Shipped predicate is **dirty-only**, refining the ADR's "no commits ahead OR dirty" (C-0248) — clean-empty worktree falls through to no-op merge+teardown; partial commit re-dispatches. Silent-discard gap (C-0247) closed. pi wave audit: 0 critical / 1 warning (unguarded UPDATE, matches existing pattern; logged not gated). Full suite 926 passed; 1 pre-existing unrelated `agent_runner.py` failure. Deferred follow-up: optional atomic state-guard on `_redispatch_to_commit`/`_append_blocked_and_publish`.

---


## [2026-06-18] promotion | Worktree done-time commit-redispatch analysis

- Actor: agent (Claude Code), operator-requested ("promote")
- Inputs: `wiki/candidates/analysis-session-worktree-done-commit-redispatch.md` (lint: claim refs C-0246..C-0249 resolve, all cited source files exist, no broken links/secrets).
- Outputs: moved candidate → `wiki/analyses/analysis-session-worktree-done-commit-redispatch.md` (`status: promoted`); `wiki/index.md` candidate queue emptied + Analyses row added; `wiki/CLAIMS.md` C-0246..C-0249 `Page` column repointed candidates→analyses; `wiki/ROUTING.md` Architecture + Decisions Pages lists + route note updated to authoritative; this log entry.
- Notes: Promoted the analysis page as authoritative documentation of the worktree lifecycle, the silent-discard gap, and the accepted ADR-0014 design. ADR-0014 itself remains `proposed`/unbuilt; the page and C-0248 state that explicitly. No code change, no service restart, no live mutation.

## [2026-06-18] session-update | Worktree feature walkthrough + ADR-0014 done-time commit-redispatch (proposed)

- Actor: agent (Claude Code) + operator (James), via `/grill-me`
- Inputs: grill-me walkthrough of the Podium worktree feature; read-only code review of `web/api/worktree.py`, `web/api/main.py:998-1390`, `scheduler/__init__.py:1699,1772`, `worktree_facade.py`, `bindings.yml`; live `git`/`sqlite3` inspection of `/home/james/symphony`; existing claims C-0007/C-0009/C-0084..C-0088.
- Outputs: new ADR `docs/adr/0014-worktree-done-commit-redispatch.md` (`proposed`); edited `CONTEXT.md` (`Run`, `Run Worktree`, `Landing`, lifecycle bullet — worktree/landing generalized from infra-only to any binding type); new raw capture `wiki/raw/sessions/2026-06-18-worktree-done-commit-redispatch-design.md`; new candidate `wiki/candidates/analysis-session-worktree-done-commit-redispatch.md`; `wiki/CLAIMS.md` (C-0246..C-0249 added; C-0007/C-0009/C-0086 forward-noted); `wiki/index.md` candidate queue row; `wiki/ROUTING.md` Architecture + Decisions routes; this log entry.
- Notes: Verified lifecycle and surfaced the only silent-data-loss path — an uncommitted worktree marked `done` makes `merge --ff-only` a no-op and `cleanup_worktree`'s `git worktree remove --force` deletes the work behind a green `done` (C-0247). Decision (ADR-0014, James-accepted, build deferred): at done-time re-dispatch the agent to commit its own work via the existing operator-reply→`todo` path (worktree persists, `create_worktree` idempotent), capped at 2 re-dispatches, then fall back to `blocked` — never auto-commit un-agent-committed work into `main` (C-0248). Also established: merge-on-done is operator-gated (scheduler sets `in_review`, never `done`) and not binding-type-gated, so `symphony` self-binding can enable worktrees safely (base on `main`, clean, `podium.db*` gitignored) — feature currently dormant (C-0246/C-0249). **No code implemented, no service restart, no Plane/Podium/DB mutation; no `.env` or `/home/james/symphony-host.env` read.** Candidate held (not auto-promoted) pending ADR-0014 implementation; promote ADR to `accepted` and supersede C-0247 on landing. Open follow-up: implement the guard + re-dispatch + loop-cap in `web/api/worktree.py`/`web/api/main.py` with tests, then decide whether to enable `worktree_active` on `symphony`.

## [2026-06-18] session-update | Issue #51 reply send flyout auto-close

- Actor: agent (Pi)
- Inputs: Issue #51 operator report; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/tests/reply.spec.ts`; `wiki/concepts/operator-reply.md`.
- Outputs: updated `wiki/concepts/operator-reply.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0245 added); updated `wiki/log.md`.
- Notes: Captured restored UI contract: successful operator reply send closes the Issue flyout while the backend `/reply` state flip and failed-send behavior remain unchanged. Verification: focused Playwright repro failed before fix, then `npx tsc --noEmit` and `PATH="$HOME/.local/bin:$PATH" npm run test:e2e -- reply.spec.ts flyout-auto-close.spec.ts` passed (5 tests). No secrets, env files, service restarts, or live API mutations.

## [2026-06-18] session-update | Podium skills refresh to 32-row catalog

- Actor: agent (Pi)
- Inputs: `symphony-skills` workflow; `web/cli/podium_skills.py`; `tests/skills/test_catalog_maintenance_skills.py`; live refresh command outputs captured in `wiki/raw/sessions/2026-06-18-podium-skills-refresh-32-row-catalog.md`.
- Outputs: live Podium `skill` table refreshed to match the default scan (32 rows); new raw capture `wiki/raw/sessions/2026-06-18-podium-skills-refresh-32-row-catalog.md`; updated `wiki/analyses/podium-skills-catalog-refresh.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0241 added, C-0136 noted as historical row-count snapshot); updated `wiki/log.md`.
- Notes: Read-only FK preflight found no `issue.preferred_skill` blockers; live refresh added `netbird-troubleshoot` and `tralph-merge`, removed seventeen stale file-backed rows, and post-refresh diff was empty (`scanned=32 existing=32`). Verification: `uv run pytest tests/skills/test_catalog_maintenance_skills.py` passed (7 tests). No service restart, Plane API call, `.env` read, or `/home/james/symphony-host.env` read.

## [2026-06-18] session-update | Issue #086 docs glossary wiki for warm Claude sessions

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/086-docs-glossary-wiki.md`; `CONTEXT.md`; `docs/adr/0013-warm-claude-session-and-send-keys-steer.md`; `.kanban/issues/076-claude-persist-config-flag.md`–`.kanban/issues/085-frontend-claude-steer-ui.md`; `wiki/analyses/adr-0010-pi-rpc-dispatch-for-live-steering.md`; `wiki/concepts/session-resume-continuity.md`.
- Outputs: updated `CONTEXT.md` (`Steering` and new `Warm Session` term); accepted `docs/adr/0013-warm-claude-session-and-send-keys-steer.md`; ingested `wiki/raw/adr-0013-warm-claude-session-and-send-keys-steer.md`; promoted `wiki/analyses/adr-0013-warm-claude-and-send-keys-steer.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0240 added; C-0176/C-0178/C-0193/C-0239 amended); updated `wiki/log.md`.
- Notes: Captured ADR-0013 as accepted after #076–#085 implementation/review, while explicitly leaving manual canary/restart soak to issue #087. Verification: exact issue grep/test command passed; candidate citation lint passed; no secrets or `.env` contents read.

## [2026-06-17] session-update | Issue #083 Claude persist steering API

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/083-api-allow-claude-steer.md`; `web/api/main.py`; `web/api/tests/test_steer.py`; `web/api/tests/test_endpoints.py`; `.kanban/progress.md`; fresh review diff `git diff 3037ef8727e97c760197cef3b226af89719cc63b HEAD`.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0010-pi-rpc-dispatch-for-live-steering.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0239 added; C-0176/C-0178/C-0193 notes refined); updated `wiki/log.md`.
- Notes: Captured Issue #083 landing: `/api/bindings` now surfaces `claude_persist`, and `/api/issues/{id}/steer` accepts live Claude steer/abort only for bindings with `claude_persist: true` while keeping pi RPC gating and returning 409 for non-persist Claude. Verification: exact issue command passed (`uv run pytest tests/test_agent_runner.py tests/test_scheduler.py` = 183 passed, 1 skipped; `uv run python -m py_compile web/api/main.py`), focused API tests passed, ruff/format clean, touched-file LSP diagnostics clean, fresh Ralph review `RALPH_REVIEW: PASS`. No env files or live secrets read.

## [2026-06-17] session-update | Issue #081 persistent Claude reaper scheduler wiring

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/081-claude-reaper-scheduler-wiring.md`; `.kanban/progress.md`; `scheduler/__init__.py`; `config.py`; `tests/test_scheduler.py`; `tests/test_config.py`; fresh review diff `git diff f5f99c0468bc58e9b23b8b8680bf3c791c4e3842 HEAD`.
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0238 added); updated `wiki/log.md`.
- Notes: Captured Issue #081 landing: `run_loop` now sweeps persistent Claude sessions once per poll iteration only for `claude_persist` bindings, offloads the sweep through `asyncio.to_thread`, uses adapter-backed `get_issue` for real `state`/`latest_run_state`, and exposes config defaults/overrides for idle TTL and max live sessions. Verification: issue command passed (`uv run pytest tests/test_scheduler.py tests/test_claude_persist.py tests/test_config.py` = 215 passed; `uv run python -m py_compile scheduler/__init__.py config.py`), ruff clean, touched-file LSP diagnostics clean, fresh Ralph review `RALPH_REVIEW: PASS`. No env files or live secrets read.

## [2026-06-17] session-update | Pi personal harness removed

- Actor: agent (Pi)
- Inputs: operator request to remove the project-local Pi `personal-harness` extension; `.pi/extensions/personal-harness.ts`; Pi extension docs; `wiki/analyses/personal-harness-pi-profile.md`; `wiki/CLAIMS.md` C-0121/C-0122.
- Outputs: deleted `.pi/extensions/personal-harness.ts`; new raw capture `wiki/raw/sessions/2026-06-17-personal-harness-pi-removal.md`; updated `wiki/analyses/personal-harness-pi-profile.md`; updated `wiki/CLAIMS.md` (C-0121/C-0122 superseded, C-0237 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Removed only the project-local Pi extension file; no matching global personal-harness extension was found. Future Pi reloads/sessions should no longer auto-discover it; current running Pi sessions may retain it until `/reload` or restart, and already-injected guidance remains in this conversation history. Historical profile/source docs retained for restoration/reference. No secrets, `.env` contents, or `/home/james/symphony-host.env` contents read.

## [2026-06-17] session-update | Issue #075 agent callback env dual emit

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/075-agent-env-dual-emit-neutral-text.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `agent_runner.py`; `prompt_renderer.py`; `schedule.py`; `tests/test_agent_runner.py`; `tests/test_remote_agent.py`; `tests/test_prompt_renderer_podium.py`; `.kanban/progress.md`
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0236 added)
- Notes: Captured Issue #075 landing L2-02/L4-03: Plane-tracker agents now receive tracker-neutral `SYMPHONY_TRACKER_*` callback aliases alongside legacy `SYMPHONY_PLANE_*` names for one release; Podium bindings still receive no callback env/helper; agent-visible prompt/schedule wording now uses tracker-neutral issue/comment phrasing. Verification: `uv run pytest` passed (891 passed, 2 skipped); focused agent-runner/remote/prompt/schedule tests passed; ruff and touched-file LSP diagnostics clean; fresh Ralph review returned `RALPH_REVIEW: PASS`. No env files or live secrets read.

## [2026-06-17] session-update | Issue #074 tracker enum neutral names

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/074-tracker-enum-neutral-names.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `tracker_contract.py`; `tracker_adapter.py`; `tracker_podium.py`; `config.py`; `tests/test_tracker_contract.py`; `.kanban/progress.md`
- Outputs: updated `wiki/concepts/tracker-contract.md`; updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0235 added)
- Notes: Captured Issue #074 landing L3-04/L5-02 tracker-vocabulary cleanup: canonical `TrackerState`, `TrackerLabel`, and `TrackerUserMapping` names, Plane-prefixed compatibility aliases retained, and adapter/Podium/config annotations repointed to canonical names. Verification: `uv run pytest` passed (891 passed, 2 skipped); focused ruff/tests passed; touched-file LSP diagnostics clean; fresh Ralph review returned `RALPH_REVIEW: PASS`. No env files or live secrets read.

## [2026-06-17] session-update | Issue #70 run_tick decomposition

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/070-decompose-run-tick.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `scheduler.py`; `.kanban/progress.md`; `symphony-host.service` restart logs
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0233 added)
- Notes: Captured Issue #70 landing the main T4 `run_tick` decomposition increment: named selection/gate/prepare/dispatch stage helpers plus `_classify_terminal` for terminal run-record and tracker side effects. Verification: `uv run pytest -q` passed (887 passed, 2 skipped); `uv run ruff check scheduler.py` passed; `uv run python -m py_compile scheduler.py` passed; touched-file LSP diagnostics clean; fresh Ralph review returned `RALPH_REVIEW: PASS`; `symphony-host.service` restarted cleanly on code SHA `48fc0bb` with startup reconcile, run reconcile, RPC probe, and dispatch-loop evidence. No env files or live secrets read.

## [2026-06-17] session-update | Issue #68 resume fallback dedup

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/068-dedup-resume-fallback.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `scheduler.py`; `tests/test_dispatch_compaction.py`; `symphony-host.service` restart logs
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0231 added)
- Notes: Captured Issue #68 landing the first T4 scheduler-decomposition step: `_dispatch_with_resume_fallback` now owns the resumed-dispatch fallback retry sequence and is used by both resumed exception and nonzero-exit paths. Verification: `uv run ruff check scheduler.py tests/test_dispatch_compaction.py` passed; `uv run pytest tests/test_dispatch_compaction.py -q` passed (7 passed); touched-file LSP diagnostics clean; full `uv run pytest -q` passed (888 passed, 2 skipped); `symphony-host.service` restarted cleanly on code SHA `ee967e3` with reconcile and dispatch-loop evidence. No env files or live secrets read.

## [2026-06-17] session-update | Issue #67 Plane secret de-shipping for Podium agents

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/067-plane-secret-deshipping-podium.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `agent_runner.py`; `tests/test_agent_runner.py`; `tests/test_remote_agent.py`; `bindings.yml`
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0225 superseded, C-0230 added)
- Notes: Captured Issue #67 landing L6-02(a): Podium local/RPC/remote agents no longer receive Plane callback env/secrets or the `plane` helper; Plane-tracker bindings retain callback env and helper for rollback/back-compat. Verification: `uv run pytest` passed (887 passed, 2 skipped), touched-file LSP diagnostics clean, `git diff --check` clean, and changed-diff secret scan found only variable names plus fake test key `fake-plane-key-for-tests`. No env files or live secrets read.

## [2026-06-17] session-update | Issue #66 public runtime factory and web API reflection cleanup

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/066-public-build-binding-runtime-web-api-reflection.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `main.py`; `web/api/main.py`; `tests/test_main.py`; `tests/test_trading_podium_dispatch.py`
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0229 added); actionable review fix in `web/api/main.py` + `web/api/tests/test_context_compaction.py`
- Notes: Captured Issue #66 landing L0-02/L0-06: `main.build_binding_runtime(config, binding)` is now the public side-effect-free runtime factory, and Podium `_compact_issue_context` uses normal imports instead of `vars(engine_main)`/`vars(compaction)` reflection. Actionable review fixed the legacy `uvicorn main:app` from `web/api` import path where `sys.modules["main"]` points at the API module, not the scheduler entrypoint. Verification: `uv run pytest` passed (885 passed, 2 skipped), touched-file LSP diagnostics clean, `git diff --check` clean, `uv run ruff check web/api/main.py web/api/tests/test_context_compaction.py` clean, and the legacy app-dir import regression is covered. No secrets or env files read.

## [2026-06-17] session-update | Issue #65 binding probe extraction

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/065-extract-probe-binding.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `main.py`; `tests/test_main.py`
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0228 added)
- Notes: Captured Issue #65 landing L0-03: `_probe_binding(config, binding)` now owns startup probe side effects and `run_bindings_loop` calls it before `_build_binding_runtime`; `_build_binding_runtime` is pure runtime wiring. Verification: `uv run pytest -q` passed (884 passed, 2 skipped), touched-file LSP diagnostics clean, `git diff --check` clean, and fresh Ralph review returned `RALPH_REVIEW: PASS`. No secrets or env files read.

## [2026-06-17] session-update | Issue #64 tracker vocabulary home

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/064-tracker-types-vocabulary-home.md`; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `tracker_types.py`; `tracker_adapter.py`; `plane_adapter.py`; `tracker_podium.py`; `scheduler.py`; `blocked_reconciler.py`; `web/api/main.py`; `tests/test_plane_poller.py`
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0227 added)
- Notes: Captured Issue #64 landing T7 tracker vocabulary home: stdlib-only `tracker_types.py`, sole `tracker_adapter.TrackerAdapter` Protocol home, and concrete adapters importing shared vocabulary. Actionable review then preserved two Plane-path behaviours after the move: `IssuePayload` still defaults to Todo, and malformed Plane issue rows still raise `PlanePollingSchemaError`. Verification: focused `tests/test_plane_poller.py` passed (25 passed), full `uv run pytest` passed (883 passed, 2 skipped), touched-file LSP diagnostics clean, and `git diff --check` clean. No secrets or env files read.

## [2026-06-17] session-update | Issue #45 architecture-review polish batch

- Actor: agent
- Inputs: Podium Issue #45; architecture review `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`; `scheduler.py`; `main.py`; `model_catalog.py`; `config.py`; `agent_runner.py`; `schedule.py`
- Outputs: updated `wiki/analyses/root-scheduler-architecture-review.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0224 superseded, C-0226 added)
- Notes: Captured that implementation has started: L0-01 `_invoke_renderer` rename, L5-03 shared `KNOWN_AGENTS` usage, and L4-01 `_decode_entity_at` extraction. Verification: `tests/test_schedule.py` passed; full `uv run pytest` passed (878 passed, 2 skipped). `uv` was not on the default PATH for the first focused run, so verification used `/home/james/.local/bin/uv` and then `PATH=/home/james/.local/bin:$PATH uv run pytest`. No secrets or env files read.

## [2026-06-16] session-update | Issue #38 Dashboard totals omit terminal states

- Actor: agent
- Inputs: Podium issue #38 request; `web/frontend/app/page.tsx`; `web/frontend/tests/dashboard.spec.ts`; existing dashboard wiki page
- Outputs: updated dashboard implementation and spec; updated `wiki/analyses/podium-031-board-overview-dashboard.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0222 added)
- Notes: Dashboard totals and badges now include only active states (`todo`, `running`, `in_review`, `blocked`), omitting `done` and `archived`. Verification: touched-file LSP diagnostics clean; `cd web/frontend && pnpm exec tsc --noEmit` passed; first Playwright run failed because `uv` was not on PATH, then `PATH=/home/james/.local/bin:$PATH pnpm exec playwright test dashboard.spec.ts` passed (1 test).

## [2026-06-15] session-update | Issue #25 Question Park verdict drift

- Actor: agent
- Inputs: operator request to review `symphony` binding Issue `issue max`; read-only Podium SQLite queries for Issue `25` / Run `36`; scheduler journal slice; `/home/james/symphony/runs/36.log`; `scheduler.py`; `web/api/schema.py`; `tests/test_scheduler.py`
- Outputs: new raw capture `wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md`; new promoted analysis `wiki/analyses/podium-question-park-verdict-drift.md`; updated `wiki/analyses/podium-046-unified-output-contract.md`; updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0211 added, C-0185 note updated)
- Notes: Root cause: the agent exited cleanly with a `SYMPHONY_QUESTION` block, but scheduler attempted to persist `verdict="question"` while Podium schema still restricts `run.verdict` and `issue.latest_verdict` to `done|review|blocked`. `_finish_run_record` raised SQLite CHECK failure, then stale-running fallback moved Issue `25` to `in_review` while latest Run `36` stayed `running`. No env files, secrets, DB writes, service restarts, systemd edits, or Podium state mutations were performed. Follow-up: decide schema vocabulary expansion vs mapping Question Park to an existing persisted verdict, then add Podium SQLite regression coverage and repair live row under normal approval gates.

## [2026-06-15] session-update | symphony-host NoNewPrivileges disabled

- Actor: agent + operator
- Inputs: current session decision; `systemctl show symphony-host.service --property=NoNewPrivileges,ActiveState,SubState,MainPID,ActiveEnterTimestamp`; `systemctl cat symphony-host.service`; Run #33 log evidence (`/home/james/symphony/runs/33.log`)
- Outputs: new raw capture `wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md`; updated `wiki/sources/symphony-host-service-unit.md`; updated `wiki/concepts/symphony-operations.md`; claims **C-0209** and **C-0210** added; `wiki/index.md` and `wiki/ROUTING.md` updated
- Notes: James chose the global option to remove the `NoNewPrivileges` boundary from `symphony-host.service` so scheduler-launched agents can attempt sudo-backed service/system changes if sudoers permits. Pi harness blocked direct unit-file editing; operator applied the drop-in manually. Base unit still declares `NoNewPrivileges=yes`, but the live drop-in sets `NoNewPrivileges=no`; verified active/running with `MainPID=562675`. This applies to all bindings, not just `symphony`; self-binding remains highest-risk. No secrets or env contents captured.

## [2026-06-14] session-update | #023 symphony-binding-remove skill

- Actor: agent
- Inputs: issue #023 ("remove binding skill"), `.claude/skills/symphony-binding-scaffold/SKILL.md`, `skill_migration.py` (`remove_podium_binding` already present), `tests/skills/test_binding_scaffold.py`, `web/api/schema.py`
- Outputs: new `.claude/skills/symphony-binding-remove/SKILL.md`; new `tests/skills/test_binding_remove.py` (4 cases); `analyses/symphony-skills-index.md` (sources + lifecycle map + per-skill section + date); claim **C-0206** added; `index.md` row + `ROUTING.md` keywords updated
- Notes: Inverse of `symphony-binding-scaffold`. Helper `remove_podium_binding` already existed in `skill_migration.py:114-179` (archive default `purge=False`; destructive `purge=True`); this issue authored the operator-facing SKILL.md (pre-flight Issue/Run count check, purge confirmation gate, diff-before-commit, no-Plane rules) and the missing regression test. New skill auto-discovered by `scan_skills` (appears in the Podium dropdown after `symphony-skills` refresh). Tests: `tests/skills/` 24 passed. Not committed/restarted; no `.env` read.

## [2026-06-14] session-update | #023 skill review — purge FK bug fixed

- Actor: agent
- Inputs: operator reply "review the skill for any gaps"; `skill_migration.py:remove_podium_binding`, `web/api/db.py:39-52`, `web/api/schema.py`, `.claude/skills/symphony-binding-remove/SKILL.md`
- Outputs: fix in `skill_migration.py` (purge `PRAGMA defer_foreign_keys = ON`); `tests/skills/test_binding_remove.py` (purge test now sets `latest_run_id` + asserts no `binding_settings` orphan); SKILL.md safety additions (yaml comment-stripping, self-binding caveat, archive-reversal section); claim **C-0208** added + C-0206 refined; `analyses/symphony-skills-index.md` per-skill section extended
- Notes: Real bug — `remove_podium_binding(purge=True)` raised `FOREIGN KEY constraint failed` for any binding whose issues had `latest_run_id` set (i.e. all dispatched issues), because `connect()` runs with `foreign_keys=ON` and `issue.latest_run_id`↔`run.issue_id` is a cycle no single delete order satisfies. Original test missed it (NULL `latest_run_id`). Fix defers FK checks to COMMIT. Reproduced live on a tmp DB (pre-fix fail, post-fix clean; `binding_settings` cascades). Archive path unaffected. Doc gaps also closed: comment-stripping (C-0171 parity), `symphony` self-binding removal caveat, how to reverse an archive. Tests: `tests/skills/` 26 passed. Not committed/restarted; no `.env` read.

## [2026-06-14] session-update | #023 follow-ups — offboard umbrella + catalog index

- Actor: agent
- Inputs: operator reply "proceed with the follow-ups"; `.claude/skills/symphony-onboard-project/SKILL.md` + `tests/skills/test_onboard_project.py` (mirror pattern); `~/dotfiles/.claude/skills/SYMPHONY.md` (stale Plane-era catalog)
- Outputs: new `.claude/skills/symphony-offboard-project/SKILL.md` + `tests/skills/test_offboard_project.py` (2 cases); dotfiles `SYMPHONY.md` gained a "Teardown a binding" section + corrected `bindings.yml` ownership line; `analyses/symphony-skills-index.md` (sources, lifecycle map, per-skill section); claim **C-0207** added + C-0206 note; `index.md` + `ROUTING.md` updated
- Notes: `symphony-offboard-project` chains `symphony-bindings-status` → `symphony-binding-remove` → `symphony-restart`, archive-default/purge-gated, no auto-rollback, no Plane. dotfiles `SYMPHONY.md` is otherwise still Plane-era stale (onboarding names `symphony-project-scaffold` as primary, omits binding-scaffold/skills/models); only the teardown addition + ownership line corrected — full Podium rewrite of that catalog deferred (cross-repo, separate scope). Tests: `tests/skills/` all pass. Not committed/restarted; no `.env` read.

## [2026-06-14] session-update | claude_runner idle-at-prompt stall fix (Run #23)

- Actor: agent
- Inputs: live diagnosis of Run #23/#25 (`podium.db`, `ps`/`ss`, agent transcripts, journal), `claude_runner.py`, `scheduler.py:1656`, `config.py:132`, commit `9c058b7`
- Outputs: raw `wiki/raw/sessions/2026-06-14-claude-runner-idle-completion-nudge.md`; promoted `analyses/podium-042-claude-tmux-adapter.md` (new "Idle-at-prompt detection + nudge" section, sources + date bumped); claim **C-0205** added; **C-0151** note updated (refined by C-0205); `index.md` row + `ROUTING.md` (claude-dispatch route page + idle keywords) updated
- Notes: Root cause — interactive tmux REPL has no process-exit signal, so an agent that ends its turn without writing the done file is indistinguishable from a working one and the poll loop waited out the full 1h `run_timeout_ms`. Fix detects idle via unchanged-signal counters, nudges twice, then fails fast (`-1`/`timed_out=True` + `claude_idle_no_completion`). Operator rejected headless `claude -p` (option A) → option B. Run #23 reconciled `failed`/`blocked` by restart (predates fix); Run #25 completed normally (non-instance). **Follow-up same session:** pane-only stability (`9c058b7`) was unvalidated + TUI-coupled (idle session captured an empty alt-screen pane), so `dc09e61` gates idle on BOTH pane and agent transcript mtime (`session_file_path`) — complementary signals, false-positive needs both frozen. Live on `e1bc113` (James committed `remove_podium_binding` e1bc113 atop dc09e61). Open: nudge/fail-fast not yet exercised by an organic live idle run — forcing real non-compliance is flaky, so validation is deterministic unit tests + passive monitoring of the next organic claude run for false positives.

## [2026-06-14] session-update | #058 pi RPC lifecycle hardening

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #058 implementation; commits `84f1c45`, `50ad752`, `65035b3`; `.kanban/issues/058-rpc-lifecycle-ops.md`; `.kanban/progress.md`; `agent_runner.py`; `web/api/steer_queue.py`; `tests/test_agent_runner.py`; `tests/test_scheduler.py`; existing ADR-0010 and Session Resume wiki pages.
- Outputs: updated `wiki/analyses/adr-0010-pi-rpc-dispatch-for-live-steering.md`; updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/CLAIMS.md` (C-0194 added; C-0191 note updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured per-run steer queue cleanup on pi RPC adapter exit, stale queue cleanup during RPC orphan startup sweep, `rpc_orphan_reap_done` logging of process and queue counts, and explicit semaphore-cap test coverage for live RPC dispatches. Verification passed: `uv run pytest tests/test_agent_runner*.py tests/test_scheduler*.py tests/test_main*.py -q` (179 passed, 1 skipped), full `uv run pytest -q` (776 passed, 2 skipped), `uv run ruff check`, touched-file LSP diagnostics clean, `git diff --check`, secret-pattern diff scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

---

## [2026-06-14] session-update | #057 Podium flyout Steering UI

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #057 implementation; commits `b536de5`, `92a6de7`, `0d65d6d`; `.kanban/issues/057-steer-ui-flyout.md`; `.kanban/progress.md`; `web/api/main.py`; `web/api/tests/test_endpoints.py`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/components/QueryProvider.tsx`; `web/frontend/components/SessionTailPanel.tsx`; `web/frontend/lib/api.ts`; `web/frontend/tests/fixtures.ts`; `web/frontend/tests/steer-flyout.spec.ts`; existing ADR-0010 and Session Resume wiki pages.
- Outputs: updated `wiki/analyses/adr-0010-pi-rpc-dispatch-for-live-steering.md`; updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/CLAIMS.md` (C-0193 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured the live steer flyout UI, typed frontend steer/abort clients, `/api/bindings` `pi_mode` exposure, local queued/delivered tail echoes, disabled Claude/idle/non-RPC affordances, and e2e coverage for live tail + steer + durable comments + abort. Verification passed: `uv run pytest web/api/tests/ -q`, full `uv run pytest -q` (772 passed, 2 skipped), `cd web/frontend && pnpm exec tsc --noEmit`, `cd web/frontend && npm run test:e2e -- steer-flyout.spec.ts` (3 passed), touched-file LSP diagnostics clean, `git diff --check`, secret-pattern diff scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

---

## [2026-06-13] session-update | #053 Live Session Tail

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #053 implementation; commits `967c081`, `c2a8957`, `7971cd5`; `.kanban/issues/053-live-session-tail.md`; `.kanban/progress.md`; `web/api/main.py`; `web/api/tests/test_session_tail.py`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/components/QueryProvider.tsx`; `web/frontend/components/SessionTailPanel.tsx`; `web/frontend/playwright.config.ts`; `web/frontend/tests/fixtures.ts`; `web/frontend/tests/session-tail.spec.ts`; existing ADR-0009 Session Resume wiki pages.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0009-session-resume-continuity.md`; updated `wiki/CLAIMS.md` (C-0186 added; C-0176 note updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured API-process `_SessionTailer`, read-only byte-range JSONL session reads, `run.tail` WebSocket event payloads, absent/empty/unreadable file no-op behavior, Session flyout tab, and shared `QueryProvider` tail-event filtering. Verification passed: `uv run pytest web/api/tests/ -q` (178 passed, 1 skipped), `cd web/frontend && npm run test:e2e -- session-tail.spec.ts` (2 passed), full `uv run pytest -q` (744 passed, 1 skipped), `cd web/frontend && pnpm exec tsc --noEmit`, touched-file LSP diagnostics clean, `git diff --check`, secret-pattern scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

---

## [2026-06-13] session-update | #052 Question Park

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #052 implementation; commits `a796e5a`, `ecb2c62`, `595fd34`; `.kanban/issues/052-question-park.md`; `.kanban/progress.md`; `prompt_renderer.py`; `scheduler.py`; `claude_runner.py`; `tests/test_scheduler.py`; `tests/test_prompt_renderer.py`; `tests/test_prompt_renderer_podium.py`; `tests/test_claude_runner.py`; existing ADR-0009 Session Resume and #046 output-contract wiki pages.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0009-session-resume-continuity.md`; updated `wiki/analyses/podium-046-unified-output-contract.md`; updated `wiki/CLAIMS.md` (C-0185 added; C-0176 note updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` as a third terminal output outcome, scheduler verdict `question`, `**Symphony question:**` comment posting, `in_review` parking for the existing operator-reply redispatch/resume path, Claude wrapper permission for Question Park, and unchanged blocked-on-error mapping. Verification passed: issue command `uv run pytest tests/test_scheduler*.py tests/test_prompt_renderer*.py web/api/tests/test_reply.py -q`, full `uv run pytest -q` (741 passed, 1 skipped), touched-file LSP diagnostics clean, `git diff --check`, secret-pattern diff scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

---

## [2026-06-13] session-update | #051 Claude resume end-to-end

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #051 implementation; commits `ca23cc3`, `2afed5a`, `6aa223b`; `.kanban/issues/051-claude-resume-end-to-end.md`; `.kanban/progress.md`; `claude_runner.py`; `scheduler.py`; `tests/test_claude_runner.py`; `tests/test_dispatch_compaction.py`; existing ADR-0009 Session Resume wiki pages.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0009-session-resume-continuity.md`; updated `wiki/CLAIMS.md` (C-0184 added; C-0175/C-0176/C-0177/C-0180/C-0183 notes updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured Claude tmux `--session-id`/`--resume` launch branching, `--continue`/`-c` ban, scheduler resume eligibility extended to Claude, delta-only resume prompts, compaction skip, run-row `agent_session_sha`/`resumed`, and in-tick fresh re-feed fallback on resume failure. Verification passed: issue command `uv run pytest tests/test_claude_runner.py tests/test_session_continuity.py -q`, broader dispatch tests, full `uv run pytest -q` (740 passed, 1 skipped), touched-file LSP diagnostics clean, `git diff --check`, secret-pattern diff scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

---

## [2026-06-13] session-update | #050 pi RPC dispatch + resume wiring

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #050 implementation; commits `831e9f3`, `09f904f`, `9177bf1`; `.kanban/issues/050-pi-resume-end-to-end.md`; `.kanban/progress.md`; `agent_runner.py`; `scheduler.py`; `config.py`; `main.py`; `plane_adapter.py`; `tracker_podium.py`; `prompt_renderer.py`; `tests/test_agent_runner.py`; `tests/test_dispatch_compaction.py`; existing ADR-0009/ADR-0010 Session Resume wiki pages.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0009-session-resume-continuity.md`; updated `wiki/analyses/adr-0010-pi-rpc-dispatch-for-live-steering.md`; updated `wiki/CLAIMS.md` (C-0181..C-0183 added; C-0175/C-0178 notes updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured `PiRpcAgentAdapter`, per-binding `pi_mode: rpc` opt-in, scheduler resume eligibility/rendering/fallback/run-row wiring, and context-compaction skip on resume. Verification passed: issue command `uv run pytest tests/test_dispatch_compaction.py tests/test_scheduler*.py tests/test_session_continuity.py tests/test_agent_runner*.py -q` (166 passed), full `uv run pytest -q` passed on retry after one transient SQLite busy-test failure was green in isolation, touched-file LSP diagnostics clean, `git diff --check`, secret-pattern diff scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

---

## [2026-06-13] session-update | #049 delta-only resume prompt rendering

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #049 implementation; commits `ce6e7c5`, `915525e`, `3a523c7`; `.kanban/issues/049-delta-only-resume-prompt.md`; `.kanban/progress.md`; `prompt_renderer.py`; `tests/test_prompt_renderer_podium.py`; existing ADR-0009/session-resume wiki pages.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0009-session-resume-continuity.md`; updated `wiki/CLAIMS.md` (C-0180 added; C-0175..C-0177 notes updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured `render_prompt(..., resume=True)` emitting `OUTPUT_CONTRACT` plus only the newest `### Operator Reply`, omitting WORKFLOW.md/issue/full comments/context, preserving Podium `preferred_skill` directive, and leaving live dispatch on re-feed until #050/#051 adapter wiring. Verification passed: `uv run pytest tests/test_prompt_renderer.py tests/test_prompt_renderer_podium.py -q`, full `uv run pytest -q` (733 passed, 1 skipped), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents.

---

## [2026-06-13] session-update | Claude dispatch path — first live #046 E2E + three tmux fixes (C-0154 closed)

- Actor: agent (Claude Code)
- Inputs: James asked for a handoff to verify #046 on the Claude path and to run a live Claude E2E. Wrote `/tmp/handoff-claude-046-contract.md`, filed Claude-routed homelab smokes (issues 6-10), reproduced manually, root-caused three bugs, implemented fixes + tests, and re-verified live after James restarted `symphony-host`.
- Outputs: code — `claude_runner.py` `_paste_and_submit` (settle + re-send Enter while `_paste_pending`), `_read_result_with_grace` (done-but-empty grace re-poll), pane capture on the 137 branch, and `_wrap_prompt` completion-protocol hardening (Write tool not heredoc + create done only after non-empty result); constants `PASTE_SETTLE_SECONDS`/`SUBMIT_RETRY_ATTEMPTS`/`RESULT_GRACE_SECONDS`; 4 new/updated tests in `tests/test_claude_runner.py`. Wiki — new raw capture `wiki/raw/sessions/2026-06-13-claude-path-046-e2e-and-fixes.md`; C-0174 added; section added to `wiki/analyses/podium-042-claude-tmux-adapter.md`; `wiki/index.md` #042 row + `wiki/ROUTING.md` Executor route updated; this log entry.
- Notes: Three bugs across issues 6-9 — paste/Enter race (prompt never submitted → 60-min idle), done-but-empty instant-137 with no diagnostics, and the real blocker: claude's Bash-heredoc result write broke on shell-special content (`command not found: bat`) yet it touched done anyway. The pane-capture fix surfaced bug 3. **Live + verified 2026-06-13 ~06:54 UTC** after a `symphony-host` restart (`2e8ff42`): Claude smoke issue 10 → Run 8 `succeeded`/`done`/exit 0, verbatim `**Symphony completed:**` block (backtick-heavy content literal, no header/Timeline/claim comment), `provider=''`/bare `claude-opus-4-8` — **C-0154 confirmed on a successful scheduler Claude run**. `symphony-host.service` `PrivateTmp=yes` (sockets in private /tmp; nsenter to observe). `uv run pytest` 716 passed, 1 skipped; ruff clean. Fix uncommitted — James to merge. No secrets read.

---

## [2026-06-13] session-update | Per-model reasoning-effort validation (fix for C-0167)

- Actor: agent (Claude Code)
- Inputs: troubleshooting the #046 live-smoke failure (Issue 2: `reasoning_effort=minimal` rejected by default `gpt-5.5`); James approved fix approach "per-model efforts + gate validate" and "edit now, you merge" alongside his concurrent consume-on-dispatch WIP.
- Outputs: code — `model_catalog.validate_models` parses optional `efforts:`; `models.yml` gpt-5.5 `efforts: [none, low, medium, high, xhigh]`; `scheduler._apply_dispatch_gate` pi-branch effort validation (fail-loud); `web/api/main.py` `reasoning_effort` Literal widened to `none|minimal|low|medium|high|xhigh`; `web/frontend/lib/api.ts` `ModelOption.efforts`; `NewIssueModal` per-model effort dropdown + clear-on-invalid; `IssueFlyout` union list; tests in `tests/test_dispatch_gate.py`, `tests/test_model_catalog.py`, `web/api/tests/test_issue_create.py`. Wiki — C-0169 added, C-0167 note updated (follow-up resolved), section added to `wiki/analyses/podium-issue-dispatch-contract.md`, ROUTING dispatch route extended, this log entry.
- Notes: `uv run pytest` 713 passed, 1 skipped; ruff + frontend tsc clean. Made live 2026-06-13 ~05:48 UTC at James's request: restarted `podium-api` + `symphony-host` (working tree, uncommitted) and ran the frontend `deploy.sh` atomic swap. Verified end-to-end — `minimal` smoke (issue 4) blocked at the gate with no run row + loud comment; `xhigh` smoke (issue 5) dispatched `gpt-5.5:xhigh` → `done`/exit 0. Still uncommitted — James to merge. consume-on-dispatch is now committed (`06cff0f`). No secrets read.

---

## [2026-06-13] session-update | #046 unified output contract — live end-to-end smoke verification

- Actor: agent (Claude Code)
- Inputs: James-approved low-risk homelab smoke Issue against the running `symphony-host.service` (commit `5be9755`, restarted 2026-06-13 04:48 UTC); live `podium.db` inspection of `issue.comments_md` / `run.summary`; journalctl dispatch markers. Issue id 2 (`reasoning_effort=minimal`) → Run id 1 `failed`/`blocked`; Issue id 3 (`low`) → Run id 2 `succeeded`/`done`.
- Outputs: new raw capture `wiki/raw/sessions/2026-06-13-046-live-output-contract-smoke.md`; `wiki/analyses/podium-046-unified-output-contract.md` updated (live-status paragraph corrected to pushed+live, new "Live verification (2026-06-13)" section, source added); `wiki/CLAIMS.md` C-0166 + C-0167 added, C-0163 and C-0165 "not yet live" notes corrected to live-confirmed; `wiki/index.md` #046 row updated; `wiki/ROUTING.md` Output-contract + Dispatch-contract routes extended; this log entry.
- Notes: #046 output contract confirmed in production exactly as documented (verbatim multi-line summary, no `### Symphony AI Summary` header, no Timeline footer, no `Symphony claimed at` comment) — C-0166. Surfaced one durable gotcha: `reasoning_effort=minimal` is valid in `IssueCreate` but rejected by the default `gpt-5.5` model → fast `blocked` failure (C-0167); open follow-up to gate/translate effort per model. Claude dispatch path (C-0154) still unverified live. Smoke Issues left in Podium as audit evidence. No secrets read, no `.env` contents, no transcript. Smoke Issues filed by direct INSERT into live `podium.db` (HTTP API needs a session password not recoverable from env).

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #044 implementation; commits `2e5439a`, `e61ace5`, `ea7aa82`; `.kanban/issues/044-claude-startup-probe-and-socket-reaper.md`; `.kanban/progress.md`; `claude_runner.py`; `scheduler.py`; `main.py`; `tests/test_claude_runner.py`; `tests/test_dispatch_gate.py`; `tests/test_main.py`; `tests/conftest.py`; existing #042/#043 wiki pages.
- Outputs: new `wiki/analyses/podium-044-claude-startup-probe-reaper.md`; updated `wiki/CLAIMS.md` (C-0156..C-0158 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured fail-soft Claude startup probing, Claude-only dispatch blocking on probe failure, Pi unaffected behavior, and one-time global reaping of `/tmp/symphony-claude-*.sock` tmux servers before per-binding reconcile. Verification passed: `git diff --check`, secret-pattern diff scan, `uv run pytest` and `uv run pytest -q` (690 passed, 1 skipped), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-13] session-update | #043 Claude dispatch routing

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #043 implementation; commits `56fd314`, `2dc4be4`, `235fda7`; `.kanban/issues/043-wire-claude-dispatch.md`; `.kanban/progress.md`; `agent_runner.py`; `main.py`; `scheduler.py`; `tests/test_agent_runner.py`; `tests/test_dispatch_compaction.py`; `tests/test_dispatch_gate.py`; `tests/test_trading_podium_dispatch.py`; existing #042 and dispatch-contract wiki pages.
- Outputs: new `wiki/analyses/podium-043-claude-dispatch-routing.md`; updated `wiki/analyses/podium-issue-dispatch-contract.md`; updated `wiki/analyses/podium-026-context-compaction.md`; updated `wiki/analyses/podium-042-claude-tmux-adapter.md`; updated `wiki/CLAIMS.md` (C-0146 superseded, C-0148 note, C-0152..C-0155 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured #043 opening the Claude dispatch gate, `RoutingAgentAdapter` Pi/Claude branching, honest Claude Run rows (`provider=""`, bare model id), stdout-only Claude post-run parsing, and Pi-only context compaction. Verification passed: `git diff --check`, `uv run pytest -q` (681 passed, 1 skipped), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-13] session-update | #042 Claude tmux adapter component

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #042 implementation; commits `e45759d`, `b17f405`, `bdde507`; `.kanban/issues/042-claude-tmux-adapter.md`; `.kanban/progress.md`; `claude_runner.py`; `tests/test_claude_runner.py`; `docs/adr/0001-claude-via-tmux-send-keys.md`.
- Outputs: new `wiki/analyses/podium-042-claude-tmux-adapter.md`; updated `wiki/CLAIMS.md` (C-0148..C-0151); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured Python-native `ClaudeAgentAdapter` component, `symphony-claude-<issue>-<nonce>` artifact namespace, allowlisted env, ready poll, file result/done gate, lifecycle mappings, cleanup, and #043 routing handoff. Verification passed: `uv run pytest -q` (679 passed, 1 skipped), `uv run ruff check claude_runner.py tests/test_claude_runner.py`, `git diff --check`, touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #038 Podium Inbox dismissal and resurface

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #038 implementation; commits `e7b0bd6`, `a0c3ebb`, `0344e78`; `.kanban/issues/038-podium-inbox-dismiss-resurface.md`; `.kanban/progress.md`; `web/api/main.py`; `tracker_podium.py`; `web/api/tests/test_inbox.py`; `tests/test_tracker_podium.py`; `web/frontend/components/Sidebar.tsx`; `web/frontend/lib/api.ts`; `web/frontend/tests/inbox.spec.ts`.
- Outputs: new `wiki/analyses/podium-038-inbox-dismiss-resurface.md`; updated `wiki/CLAIMS.md` (C-0137..C-0139); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured state-preserving Inbox dismissal, guarded dismiss endpoint, WebSocket publish, resurface clearing on transitions into `in_review`/`blocked`, optimistic Sidebar dismiss UX, and follow-up that #039 can remove the dashboard attention list. Verification passed: `PATH=/home/james/.local/bin:$PATH uv run pytest -q` (652 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (37 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | Podium password rotation helper

- Actor: agent (Pi)
- Inputs: operator request to make the successful Podium password-change workflow easier; `web/README.md`; `web/cli/podium.py`; `scripts/podium-change-password.sh`.
- Outputs: added `scripts/podium-change-password.sh`; updated `web/README.md`; updated `wiki/analyses/podium-018-auth.md`; updated `wiki/CLAIMS.md` (C-0132); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured the low-risk helper/runbook path: generate the bcrypt hash via the existing CLI, leave env editing and `podium-api.service` restart as explicit operator steps, and document `PODIUM_SESSION_SECRET` rotation only for force-logout. Verification passed: `bash -n scripts/podium-change-password.sh` and `git diff --check`. No secrets, no `.env` contents, no live service restart.

## [2026-06-12] session-update | Claude Code hook harness personalization (re-applied)

- Actor: agent (Claude, `personalize-harness` skill + wiki update)
- Inputs: current session; `pyproject.toml`, `uv.lock`, `.venv`, `CLAUDE.md`; generated `.claude/settings.json` + `.claude/hooks/{validate-syntax,block-bash-pattern,pre-git-checks,reinject-rules}.sh`; ruff/pytest baseline measurements; `~/.claude/skills/personalize-harness/SKILL.md` (global skill edit, outside repo).
- Outputs: `wiki/raw/sessions/2026-06-12-claude-code-harness.md`; `wiki/analyses/claude-code-harness-profile.md`; `wiki/CLAIMS.md` C-0130..C-0131; `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`; corrected `CLAUDE.md` "Quick Checks" (`python3 -m pytest` → `uv run pytest`).
- Notes: Team-layer Claude Code harness — 4 hooks (blocking syntax-validate afterWrite, blocking bash guard, blocking pre-git ruff-on-staged + `uv run pytest`, advisory compact reinject). Decisions: ruff at commit-time/changed-files-only (no `[tool.ruff]` config → repo-wide baseline red 38/82 + 5 lint); test gate is `uv run pytest` not bare `python3 -m pytest` (system python3 lacks alembic, .venv has it, 615 passed/1 skip/53s) — drove the `CLAUDE.md` quick-check correction; alembic stays project-only (declared dep, locked, in `.venv` 1.18.4), do not install system-wide. Path guard + Stop self-review skipped by operator choice. Live bug caught + fixed: rm guard matched safe `/tmp` deletes, re-anchored to root/home boundaries. Skill hardened with mandatory baseline-verification/runner-resolution step. **This update was first written then wiped by concurrent Ralph #033–#036 archive work (which reclaimed claim IDs C-0126/C-0127); re-applied here with claims renumbered to C-0130/C-0131.** Sibling of the Pi harness (C-0121/C-0122). No secrets, no env contents, no transcript.

## [2026-06-12] session-update | repo-local Symphony operational skills

- Actor: agent (Pi)
- Inputs: operator request to reconcile Symphony skills into `/home/james/symphony/.claude/`; dotfiles copies of `symphony-restart` and `symphony-troubleshooter`; repo-local `.claude/skills/symphony-*`; `tests/skills/`.
- Outputs: added `.claude/skills/symphony-restart/SKILL.md`; added `.claude/skills/symphony-troubleshooter/SKILL.md`; added `tests/skills/test_restart_troubleshooter.py`; updated `wiki/analyses/symphony-skills-index.md`; updated `wiki/CLAIMS.md` (C-0129); updated `wiki/log.md`.
- Notes: Project-local consolidation kept existing Podium-era skills canonical, did not overwrite them with stale dotfiles copies, and did not copy non-Symphony `debug-hermes`. Follow-up dotfiles commit `06fa9a6` removed the stale global `symphony-*` copies so project-local skills no longer collide. Verification covered skill tests and stale Plane scaffold strings; no secrets or `.env` contents read.

## [2026-06-12] session-update | #035 archived engine-terminal contract

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #035 implementation; commits `c8118c1`, `32c16d3`, `65cd128`; `.kanban/issues/035-podium-archive-engine-terminal-contract.md`; `.kanban/progress.md`; `tracker_podium.py`; `web/api/main.py`; `scheduler.py`; `tests/test_tracker_podium.py`; `web/api/tests/test_worktree_api.py`; `tests/test_trading_podium_dispatch.py`.
- Outputs: updated `wiki/analyses/podium-issue-archive-design.md`; updated `wiki/CLAIMS.md` (C-0123/C-0124 superseded, C-0126..C-0127 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured #035 landing the archived terminal engine contract: guarded `transition_state`, idle archive PATCH worktree teardown, active-run deferral, explicit scheduler `archived_terminal` skip after run-row finalization, and #036 purge still pending. Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (622 passed, 1 skipped), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #023c Podium homelab cutover + infra role projection

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #023c implementation; commits `037d78e`, `89ae1af`, `811e5e8`; `bindings.yml`; `tracker_podium.py`; `web/api/schema.py`; `web/api/migrations/versions/0003_infra_role_columns.py`; `web/api/main.py`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/components/NewIssueModal.tsx`; `web/README.md`; `CONTEXT.md`; `tests/test_tracker_podium_infra.py`; `tests/test_main.py`; `.kanban/issues/023c-podium-homelab-cutover.md`; `.kanban/progress.md`.
- Outputs: new `wiki/analyses/podium-023c-homelab-cutover.md`; updated `wiki/concepts/podium-tracker.md`; updated `wiki/analyses/adr-0005-replace-plane-with-podium.md`; updated `wiki/CLAIMS.md` (C-0104..C-0106, C-0080 superseded, C-0083 note); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured homelab now live on Podium, both active bindings on Podium, infra role columns/projection, infra-only UI chips, live migration/restart/smoke evidence, rollback docs, and stale e2e issue parking. Verification passed: `uv run pytest` (586 passed, 1 skipped), `pnpm exec tsc --noEmit`, live `alembic upgrade head`, `symphony-host.service` restart, touched-file LSP diagnostics with no critical errors, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no raw transcript.

## [2026-06-11] session-update | #023a Podium systemd units actionable review

- Actor: agent (Pi, Ralph actionable review)
- Inputs: issue #023a actionable review; commit `9a9b30d`; `.kanban/issues/023a-podium-systemd-units.md`; `.kanban/progress.md`; live unit snapshots `/etc/systemd/system/podium-api.service`, `/etc/systemd/system/podium-web.service`, `/etc/systemd/system/telegram-alert@.service`, `/usr/local/sbin/send-telegram-systemd-alert`.
- Outputs: new `wiki/raw/podium-api.service`; `wiki/raw/podium-web.service`; `wiki/raw/telegram-alert@.service`; `wiki/raw/send-telegram-systemd-alert`; new `wiki/sources/podium-systemd-units.md`; updated `wiki/analyses/adr-0005-replace-plane-with-podium.md`; `wiki/CLAIMS.md` (C-0103 and C-0065 note); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured landed Podium sibling units, API `--workers 1`, web loopback `HOST=127.0.0.1`, `OnFailure=telegram-alert@%n.service` wiring, and the unattended verification rule to check external-notification wiring without firing live Telegram alerts. Verification passed: `sudo systemctl status podium-api.service podium-web.service --no-pager && ss -tlnp | grep -E '8090|8091'`; env variable presence checked without printing secrets.

## [2026-06-11] session-update | #027 Podium skill-suite migration

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #027 implementation; commits `07b0c36`, `628ea08`, `73ce14c`; `.claude/skills/symphony-binding-scaffold/SKILL.md`; `.claude/skills/symphony-binding-smoke/SKILL.md`; `.claude/skills/symphony-bindings-status/SKILL.md`; `.claude/skills/symphony-onboard-project/SKILL.md`; `.claude/skills/symphony-plane-recover/SKILL.md`; `.claude/skills/symphony-project-scaffold/SKILL.md`; `.claude/skills/symphony-workflow-author/SKILL.md`; `skill_migration.py`; `tests/skills/`; `.kanban/issues/027-podium-skill-suite-migration.md`; `.kanban/progress.md`.
- Outputs: updated `wiki/analyses/symphony-skills-index.md`; `wiki/CLAIMS.md` (C-0099..C-0102, C-0049 Podium supersession note); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured Podium-era `symphony-*` skill paths, new `symphony-binding-scaffold`, smoke/status Podium endpoint migration, Plane-only scaffold/recover split, tracker-agnostic workflow-author posture, and test coverage. Verification passed: `uv run pytest` (572 passed, 1 skipped), touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #026 Podium Issue Context compaction

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #026 implementation; commits `db4a559`, `c24cd5b`; `context_compaction.py`; `scheduler.py`; `tracker_podium.py`; `web/api/main.py`; `web/api/schema.py`; `web/api/migrations/versions/0002_context_compaction_settings.py`; `tests/test_context_compaction.py`; `tests/test_dispatch_compaction.py`; `web/api/tests/test_context_compaction.py`; `.kanban/issues/026-podium-engine-context-compaction.md`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-026-context-compaction.md`; `wiki/CLAIMS.md` (C-0095..C-0098, C-0068 supersession note); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured engine-owned context compaction, `binding_settings` threshold/keep settings, pre-Run configured-agent invocation, `replace_context(...)`, no-Run-row invariant, manual compact endpoint, and ADR-0005 zero-schema-impact correction. Verification passed: `uv run pytest` (563 passed, 1 skipped), touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #023b Podium Alembic baseline + SQLite backup wiring

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #023b implementation; commits `5df8784`, `e633be7`, `849898f`; `tests/test_alembic_baseline.py`; `web/api/migrations/env.py`; `web/api/migrations/README.md`; `scripts/podium-backup.sh`; `/etc/cron.d/podium-backup`; `web/README.md`; `.kanban/issues/023b-podium-alembic-and-backup.md`; `.kanban/progress.md`.
- Outputs: `wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md`; `wiki/raw/podium-backup.cron`; `wiki/analyses/podium-023b-alembic-backup.md`; `wiki/CLAIMS.md` (C-0092..C-0094); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured Alembic/runtime schema parity testing, logger-preserving Alembic config, migration rule docs, cron-based SQLite `.backup` with 14-day retention, restore-drill evidence, and pytest 8.x dev-tooling pin. Verification passed: `uv run pytest` (554 passed, 1 skipped) plus backup file check. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #022 Podium restart Run reconciliation + run-log retention

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #022 implementation; commits `3bd8957`, `0667480`, `9686183`; `scheduler.py`; `tracker_podium.py`; `tests/test_run_reconcile.py`; `tests/test_log_retention.py`; `.kanban/issues/022-podium-restart-reconcile-and-log-retention.md`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-022-run-reconcile-log-retention.md`; `wiki/CLAIMS.md` (C-0089..C-0091); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured landed startup Run reaping, parent-Issue blocked transition, preserved worktrees, run-log retention semantics (90 days or newest 100 per Issue), startup + 24h scheduler wiring, and structured `run_reconcile_*` / `log_retention_*` pairs. Verification passed: `uv run pytest` (552 passed, 1 skipped). No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #021 Podium worktree opt-in + FF-only auto-merge

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #021 implementation; commits `74b024d`, `b59f193`, `f0c5d37`; `web/api/worktree.py`; `agent_runner.py`; `plane_adapter.py`; `tracker_podium.py`; `web/api/main.py`; `tests/test_agent_runner.py`; `web/api/tests/test_worktree.py`; `web/api/tests/test_worktree_api.py`; `web/frontend/tests/worktree.spec.ts`; `.kanban/issues/021-podium-worktree-auto-merge.md`; session wiki query of `wiki/index.md` and `wiki/ROUTING.md` before implementation.
- Outputs: `wiki/analyses/podium-021-worktree-auto-merge.md`; `wiki/CLAIMS.md` (C-0084..C-0088); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured deterministic Podium worktree path/branch, dispatch cwd switching, FF-only Done merge and teardown, blocked abort comments, archive toggle behavior, frontend chip lifecycle, and dotenv masking fix for the auth missing-secret test. Verification passed: `uv run pytest` (545 passed, 1 skipped) and `pnpm test:e2e` (15 passed). No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #021 dev-review fixes

- Actor: agent (Pi after dev-review-claude)
- Inputs: dev-review findings for commits `5858e7c..97f9ae6`; `web/api/main.py`; `scheduler.py`; `agent_runner.py`; `web/api/worktree.py`; `tests/test_trading_podium_dispatch.py`; `web/api/tests/test_worktree.py`; `web/api/tests/test_worktree_api.py`; `web/frontend/lib/api.ts`; `web/frontend/components/IssueFlyout.tsx`; `.kanban/issues/021-podium-worktree-auto-merge.md`; `.kanban/progress.md`.
- Outputs: updated `wiki/analyses/podium-021-worktree-auto-merge.md`; updated `wiki/CLAIMS.md` (C-0086..C-0088); updated `wiki/log.md`.
- Notes: Captured final blocked-row WebSocket publish after merge aborts, async `to_thread` git work, Run-row worktree metadata, server-derived Issue worktree path/branch fields, combined done+worktree-off PATCH precedence, and review-fix verification: `uv run pytest` (547 passed, 1 skipped), `pnpm exec tsc --noEmit`, and `pnpm test:e2e` (15 passed). No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #020 trading→Podium cutover smoke + run-log finalization bug

- Actor: agent (Claude, cutover smoke + wiki update)
- Inputs: session performing the #020 operator smoke; commits `12289da`, `8eb4aa6`, `eb1a706`; `tracker_podium.py`; `scheduler.py:438-478`; `web/api/db.py:8-22`; `main.py:75-81`; `tests/test_trading_podium_dispatch.py`; live `podium.db` (issue 17 / run 6) and `journalctl` traceback.
- Outputs: new `wiki/raw/sessions/2026-06-11-podium-020-cutover-smoke.md`; promoted `wiki/analyses/analysis-session-020-cutover-smoke.md`; `wiki/CLAIMS.md` (added C-0082, C-0083; refinement notes on C-0062, C-0067); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured the production-only run-log crash (`adapter.db_path=None` → unwritable `/var/lib/symphony/runs` → `PermissionError` in `_write_run_log`), the `__post_init__` fix, the run-log co-location convention, the masked-test lesson, and the trading-live-on-Podium milestone. Refines (does not supersede) C-0062/C-0067. Follow-up: consider making `RUN_LOG_ROOT` follow `resolve_db_path` fallback (#024). No secrets, no `.env` contents, no transcript.

---

## [2026-06-09] setup | Initial wiki scaffold

- Actor: agent (Claude Code, llm-wiki-setup skill)
- Inputs: James interview answers — domain: Symphony scheduler internals + runbook; sources: CLAUDE.md, CONTEXT.md, ~/homelab/docs/runbooks/automation/symphony.md, docs/, Plans/, with expanded coverage; commit wiki to git; auto-promote candidates (no James gate); inline citation style.
- Outputs: created wiki/ tree (raw/, raw/sessions/, candidates/, sources/, entities/, concepts/, analyses/, assets/); created wiki/README.md, wiki/index.md, wiki/log.md, wiki/ROUTING.md, wiki/CLAIMS.md; queued CLAUDE.md refactor and first ingest.
- Notes: Raw-source git policy not explicitly confirmed for binaries — .gitignore left untouched; will warn before committing large binaries. Auto-promotion overrides default candidate gate.

## [2026-06-09] ingest | all-three-tiers (Tier 1 + 2 + 3)

- Actor: agent (Claude Code, llm-wiki-setup skill, Ingest workflow, batch at James' request "all three")
- Inputs:
  - **Tier 1**: copied to `wiki/raw/`: `workflow-homelab.md` (from `~/homelab/WORKFLOW.md`), `workflow-trading.md` (from `~/trading/crypto-trading-agents/WORKFLOW.md`), `symphony-host.service` (from `/etc/systemd/system/`), `brainstorm-pi-swap.md` (from `artifacts/brainstorming/`), 4 spec PRDs (from `artifacts/specs/*/PRD.md`).
  - **Tier 2**: read in-tree for behavioural extraction: `schedule.py`, `blocked_reconciler.py`, `scheduler.py`, `agent_runner.py`, `run_worktree.py`, `prompt_renderer.py` (no raw copy — code on disk is the canonical source).
  - **Tier 3**: read 8 `symphony-*` SKILL.md frontmatter+intros from `~/.claude/skills/`; counted tests in `tests/*.py`.
- Outputs:
  - **Tier 1**: `sources/symphony-host-service-unit.md`; `entities/workflow-homelab.md`, `entities/workflow-trading.md`; `analyses/brainstorm-pi-swap.md`, `analyses/pi-swap-review-specs.md`.
  - **Tier 2**: `concepts/schedule-comment-grammar.md`, `concepts/blocked-reconciler-implementation.md`, `concepts/scheduler-loop.md`, `concepts/agent-runner-and-worktree.md`, `concepts/prompt-renderer.md`.
  - **Tier 3**: `analyses/symphony-skills-index.md`, `analyses/symphony-tests-index.md`.
  - Claims: C-0026..C-0049 added to `wiki/CLAIMS.md`.
  - Index Sources/Entities/Concepts/Analyses expanded across all four buckets.
  - ROUTING.md expanded: Architecture, Operations, Bindings & Repos, Scheduling, Plan/Build/Approve, Blocked Reconciler, Executor/Agent, Decisions, Plan History, Skills & Tooling all updated; new **Tests** branch added.
- Notes:
  - Tier 2 module pages document behaviour contracts that aren't derivable from CONTEXT.md or the ADRs — constants, regexes, naming schemes, sort precedence, fail-fast guardrails. They are deliberately not full code transcripts; code on disk remains canonical.
  - Discovered divergence (C-0045): `prompt_renderer.py` defaults `IssueData.mode = "conversation"` and emits a Conversation Mode block — but CONTEXT.md's Mode entry lists only plan/build/execute. Either CONTEXT.md needs a Conversation Mode entry or the renderer's conversation block is a deliberately-undocumented runtime extension. Flag for grill-me.
  - scheduler.py (2633 LOC) is intentionally summarised, not transcribed. `concepts/scheduler-loop.md` lists constants, semaphore/cooldown model, and the top-level async surface; deeper sections (sanitisation, dirty-base approval protocol, mode-resolution algorithm) should be ingested as separate concept pages when questions surface.
  - 4 spec PRDs in `artifacts/specs/` consolidated into one `pi-swap-review-specs.md` rather than 4 separate pages — they share a single target and reviewer format.
  - 8 `symphony-*` SKILL.md files documented as an index page rather than per-skill pages — SKILL.md is the source of truth and lives in a separate dotfiles repo.
  - 14 test files documented as a coverage map; test bodies not transcribed.
  - Auto-promoted all new pages.

## [2026-06-09] ingest | batch — runbook, ADRs, plans, bindings, tracker_contract

- Actor: agent (Claude Code, llm-wiki-setup skill, Ingest workflow, batch mode at James' request "batch all")
- Inputs: copied to `wiki/raw/`: `runbook-symphony.md` (from `~/homelab/docs/runbooks/automation/symphony.md`), `adr-0001-claude-tmux.md` through `adr-0004-tracker-contract.md` (from `docs/adr/`), `plan-refactor-move-symphony-to-home.md` through `plan-ticket-scheduling.md` (5 plans from `plans/`), `bindings.yml`, `tracker_contract.py`.
- Outputs:
  - sources/: `runbook-symphony.md`
  - concepts/: `symphony-operations.md`, `tracker-contract.md`
  - analyses/: `adr-0001-claude-tmux.md`, `adr-0002-generalize-symphony.md`, `adr-0003-worktree-per-run.md`, `adr-0004-tracker-contract.md`, `symphony-plan-history.md`
  - entities/: `binding-homelab.md`, `binding-trading.md`
  - claims: C-0011..C-0025 added to `wiki/CLAIMS.md`
  - index Sources/Entities/Concepts/Analyses populated
  - ROUTING.md expanded with Scheduling, Plan/Build/Approve, Blocked Reconciler, Telegram, Executor/Agent, Plan History branches
- Notes:
  - Plan landed-status verified against `git log`: `refactor-move-symphony-to-home` (98c6359), `symphony-pi-executor-swap` (8af5dab), `symphony-ticket-scheduling` (36352f9); `symphony-plan-approve-workflow` landed pre-ADR-0004 (homelab-router-era); `symphony-operational-improvements` partial — flagged for verification (`plane comments`, stderr surfacing).
  - C-0010 note refined: `approval.enabled: false` in bindings.yml is the **engine gate** flag; the label-driven plan/approve flow (mode:plan → approval-required → mode:build) is a separate mechanism. CONTEXT.md says homelab opts in — that wording refers to the label flow, not the engine flag.
  - Deferred per-entity breakouts for Mode/Agent/Workflow/Done Marker/Verdict/Run/Run Worktree/Landing/Project Scaffold/Tracker Adapter/Agent Adapter — `concepts/symphony-engine.md` covers each in dedicated section. Create on demand when routing pressure justifies it.
  - Auto-promoted all new pages.

## [2026-06-09] ingest | CONTEXT.md (Symphony glossary)

- Actor: agent (Claude Code, llm-wiki-setup skill, Ingest workflow)
- Inputs: `CONTEXT.md` (copied to `wiki/raw/symphony-context.md`)
- Outputs: `wiki/sources/symphony-context.md` (source summary, promoted), `wiki/concepts/symphony-engine.md` (engine concept, promoted), C-0001..C-0010 added to `wiki/CLAIMS.md`, index Sources/Concepts updated, ROUTING.md Project Overview + Architecture branches populated.
- Notes: Source touches multiple potential entity pages (Project Binding, Mode, Agent, Workflow, Tracker Adapter, Tracker Contract, Agent Adapter, Done Marker, Verdict, Run, Run Worktree, Landing, Project Scaffold). Held off on a fan-out into 13 entity pages — single overview concept page captures the engine model. Recommend per-entity pages on demand or as part of next ingest pass. Auto-promoted both new pages (no James gate).

## [2026-06-09] session-update | trading smoke rate-limit debugging

- Actor: agent (Pi, wiki-update skill, SessionUpdate workflow)
- Inputs: current debugging session; `scheduler.py`; `tests/test_scheduler.py`; `prompt_renderer.py`; `wiki/raw/workflow-trading.md`; journal evidence for trading smoke issues `6fbfd86a-36b2-4548-9b41-2a80fb66506c` and `0ab7f64c-3ad4-468d-8c2e-4d408c35f076`; commits `a269e32`, `fbff782`, `c4944be`.
- Outputs: `wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md`; `wiki/analyses/trading-smoke-rate-limit-debugging.md`; updates to `wiki/concepts/scheduler-loop.md`, `wiki/concepts/prompt-renderer.md`, `wiki/entities/workflow-trading.md`, `wiki/CLAIMS.md` (C-0050..C-0053), `wiki/index.md`, `wiki/ROUTING.md`, and `wiki/log.md`.
- Notes: Captured root causes and fixes for post-agent Plane 429 recovery, shared Plane cooldown, optional-label scan pressure, and the remaining dirty-worktree proof blocker: unlabeled issues render as conversation mode and should not edit files. No secrets, `.env` contents, or full transcript stored.

## [2026-06-09] session-update | thin engine E2E test + service restart

- Actor: agent (Pi, wiki-update skill, SessionUpdate workflow)
- Inputs: current session; `agent_runner.py`; `scheduler.py`; `config.py`; `main.py`; journalctl evidence for smoke issue `b0b79316`; commit `e73e924`; `symphony-host.service` unit config.
- Outputs: `wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md`; `wiki/candidates/analysis-thin-engine-e2e-test.md`; `wiki/candidates/concept-thin-engine-v2.md`; CLAIMS.md updates (C-0007, C-0009, C-0016, C-0018, C-0019, C-0020, C-0040, C-0041, C-0042, C-0044 — supersession/historical notes); `wiki/index.md` (2 candidate rows); `wiki/ROUTING.md` (Thin Engine + Service Restart branches); `wiki/log.md` (this entry).
- Notes: Thin engine E2E smoke test verified full dispatch lifecycle. Root cause for worktree behavior was code drift (service never restarted after thin engine commit). Service restarted successfully. Stale worktree cleaned. Promoted concept page `agent-runner-and-worktree.md` substantially stale — new candidate supersedes it. 10 claims annotated with thin-engine context. No secrets stored.

## [2026-06-10] session-update | Podium #014 new-issue flow + review + modal evolution

- Actor: agent (Claude Code, wiki-update skill, SessionUpdate workflow)
- Inputs: current session; commits `a68cccf`, `f0de67b`, `4aab377`, `a6157f3`, `bf7cfd0`; `web/api/main.py`; `web/api/seed.py`; `web/api/tests/test_issue_create.py`; `web/frontend/components/NewIssueModal.tsx`; `web/README.md`; `.kanban/issues/014/015/020`.
- Outputs: `wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md`; `wiki/analyses/podium-014-new-issue-flow.md` (auto-promoted after lint); `wiki/CLAIMS.md` (C-0054..C-0058); `wiki/index.md` (analyses row + removed two stale candidate-queue rows for already-promoted thin-engine pages); `wiki/ROUTING.md` (Podium Web UI branch); `wiki/log.md` (this entry).
- Notes: Captured #014 endpoint contract, INSERT OR IGNORE seeding pivot and its #015 resurrection constraint, /options dropdown endpoint design (static agents mirror scheduler validation; KNOWN_MODELS placeholder; live git branches), close-on-success modal UX deviation accepted by James, flyout chip removals, and free-text agent/model constraint for #020. Index candidate-queue cleanup was low-risk maintenance (files no longer exist; promoted versions indexed). No secrets, no transcript.

## [2026-06-10] ingest | ADR-0005 (replace Plane with Podium) + Podium tracker concept page

- Actor: agent (Claude Code, Ingest workflow; AI-consumption optimized at James's request)
- Inputs: `docs/adr/0005-replace-plane-with-podium.md` (copied to `wiki/raw/adr-0005-replace-plane-with-podium.md`); live code grounding `web/api/schema.py`, `web/api/db.py`, `web/api/main.py`, `web/api/seed.py`, `web/api/migrations/versions/0001_initial.py`; `scheduler.py:488`. Reviewed done slices #012a–#013 against existing wiki coverage; two gaps found (ADR-0005 never ingested; Podium impl had no concept page).
- Outputs: `wiki/raw/adr-0005-replace-plane-with-podium.md` (raw copy); `wiki/analyses/adr-0005-replace-plane-with-podium.md` (decision page, auto-promoted); `wiki/concepts/podium-tracker.md` (impl concept page, auto-promoted); `wiki/CLAIMS.md` (C-0059..C-0068 added; C-0004 supersession note for Podium); `wiki/index.md` (concepts + analyses rows); `wiki/ROUTING.md` (Podium Web UI + Decisions branches expanded); `wiki/log.md` (this entry).
- Notes: Pages written dense/fact-first for future AI sessions, not human narrative. Verified live: `scheduler.py:488` is_coding-off-bindings[0] bug (C-0066); two distinct enums issue.state vs run.state (C-0067); db-path chain + check_same_thread rationale (web/api/db.py). ADR-0005 reconciliation captured: ADR-0002 "stay on Plane" superseded; ADR-0001/0003 already inert via thin engine v2, worktree posture reversed to opt-in. podium-api/web systemd units not yet created at ingest time (C-0065 reflects design). `.kanban/` gitignored — claims cite code paths + commits primarily. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #017 WebSocket live updates

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #017 implementation; commit `0a50bc7`; `web/api/main.py`; `web/api/seed.py`; `web/api/tests/test_websocket.py`; `web/frontend/components/QueryProvider.tsx`; `web/frontend/components/NewIssueModal.tsx`; `web/frontend/tests/live-sync.spec.ts`; `web/frontend/playwright.config.ts`.
- Outputs: `wiki/analyses/podium-017-live-updates.md`; `wiki/CLAIMS.md` (C-0069..C-0072); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured WS `/api/ws` in-process fanout, issue/run event contract, frontend TanStack Query live cache strategy, reconnect/disconnect pill behavior, optimistic-create race fix, `websockets` runtime dependency, and last-write-wins concurrency decision. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #018 shared-password auth

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #018 implementation; commit `b8a50f0`; `web/api/auth.py`; `web/api/main.py`; `web/api/tests/test_auth.py`; `web/cli/podium.py`; `web/frontend/components/AppShell.tsx`; `web/frontend/app/login/page.tsx`; `web/frontend/tests/auth.spec.ts`.
- Outputs: `wiki/analyses/podium-018-auth.md`; `wiki/CLAIMS.md` (C-0073..C-0076); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured bcrypt shared-password auth, required env contract, signed `podium_session` cookie, HTTP and WebSocket auth gates, frontend login/logout redirect contract, set-password stdout-only helper, and test-auth convention. No production secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #025 prompt renderer Podium path

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #025 implementation; commit `36a7cd4`; `prompt_renderer.py`; `skill_mode_map.py`; `tests/test_prompt_renderer_podium.py`.
- Outputs: updated `wiki/concepts/prompt-renderer.md`; `wiki/CLAIMS.md` (C-0077..C-0078); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured `tracker_kind="podium"`, direct `comments_md`/`context_md` rendering, non-truncating Podium comments, `skill_mode_map.SKILL_TO_MODE`, and the transitional Skill→Mode bridge. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #019 tracker adapter

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #019 implementation; commits `9e84869`, `37c5170`, `1eff632`; `config.py`; `main.py`; `scheduler.py`; `tracker_adapter.py`; `tracker_podium.py`; `web/api/db.py`; `tests/test_tracker_podium.py`; `tests/test_podium_sqlite_concurrent.py`; `tests/test_engine_against_podium.py`.
- Outputs: updated `wiki/concepts/podium-tracker.md`; `wiki/CLAIMS.md` (C-0079..C-0081); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured `tracker: plane|podium` binding validation, runtime tracker protocol, SQLite Podium adapter, WAL/busy-timeout concurrency posture, no direct `plane_adapter` import in `tracker_podium.py`, and scheduler `stores_context` path for Podium `context_md`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #023d trading Plane archive + reverse-proxy docs

- Actor: agent (Claude, interactive session + wiki update)
- Inputs: issue #023d execution (descoped to trading-only); `symphony-plane-recover archive` run; `bindings.yml`; `CONTEXT.md`; `web/README.md`; `config.py:345,391`; `tests/test_trading_podium_dispatch.py`; `.kanban/issues/023d-podium-plane-archive.md`.
- Outputs: `wiki/raw/sessions/2026-06-11-podium-023d-trading-plane-archive.md`; `wiki/analyses/podium-023d-trading-plane-archive.md`; `wiki/CLAIMS.md` (C-0107, C-0108; supersession notes on C-0023→superseded, C-0059, C-0104); updated `wiki/entities/binding-trading.md` (retire banner, historical Tracker Contract section); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured the operator-waived soak gate, the irreversible trading Plane archive (HTTP 204, `archived_at: 2026-06-11T22:42:15Z`), the live `tracker_contract` removal → `DEFAULT_CONTRACT` fallback, the README Authelia reverse-proxy snippet, and the deferred homelab archive. No secrets, no `.env` contents (PLANE_API_KEY only echoed as char-count during env sourcing), no transcript.
- Unresolved: homelab Plane archive follow-up issue (e.g. 023e) not yet created; Authelia/proxy live edit + Podium reachability confirmation operator-pending; no git commit yet.
- Addendum: added a non-destructive drift banner to `wiki/raw/bindings.yml` (immutable snapshot) flagging it predates #023c/#023d; body preserved verbatim, still valid YAML. Raw immutability honored — flag, never silently rewrite.

## [2026-06-12] session-update | #023d reverse-proxy bring-up (podium-web LAN bind)

- Actor: agent (Claude, interactive session + wiki update)
- Inputs: operator-chosen FQDN `podium.testytech.net` + proxy upstream `10.20.20.16:8091`; `podium-web.service` unit edit (`HOST=127.0.0.1`→`HOST=10.20.20.16`, backup `.bak.2026-06-12`, daemon-reload + restart); reachability verification (`10.20.20.16:8091`→200, loopback→000); `symphony-host.service` restart onto sha `82462e6`; `web/frontend/package.json` start script.
- Outputs: updated `web/README.md` (FQDN + LAN upstream + bind requirement, commit `82462e6`); `wiki/CLAIMS.md` (added C-0109; annotated C-0065, C-0103; C-0109 marked applied/verified); `wiki/sources/podium-systemd-units.md`; `wiki/raw/podium-web.service` (drift banner, immutable body); `wiki/analyses/podium-023d-trading-plane-archive.md` (bring-up section); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Frontend `start` is `next start -H ${HOST:-0.0.0.0}`, so the unit `HOST` env selects the bind interface; loopback-only was why the LAN proxy 404'd. LAN bind exposes the unauthenticated port 8091 — Authelia stays the gate, firewall optional. No secrets, no `.env` contents, no transcript.
- Unresolved: end-to-end `https://podium.testytech.net` via Authelia not yet confirmed (last #023d acceptance box); homelab archive follow-up issue (023e) not created; commits `a24d229`/`82462e6` unpushed.

## [2026-06-12] session-update | Podium frontend deploy hazard + atomic deploy script + UI cosmetics

- Actor: agent (Claude, interactive session + wiki update)
- Inputs: cosmetic frontend request (collapsible sidebar, card quick-view); live MIME/400 console errors after in-place `next build`; root-cause + recovery via `podium-web.service` restart; `web/frontend/deploy.sh` (new); `web/frontend/next.config.mjs` (`distDir` env override); `web/frontend/components/AppShell.tsx`; `web/frontend/components/IssueCard.tsx`; `web/frontend/.gitignore`; `systemctl cat podium-web.service`; `web/frontend/package.json`.
- Outputs: `wiki/raw/sessions/2026-06-12-podium-frontend-deploy-and-ui-cosmetics.md`; `wiki/analyses/podium-frontend-deploy-cosmetics.md` (promoted); `wiki/CLAIMS.md` (C-0110 deploy hazard + atomic deploy, C-0111 UI cosmetics); `wiki/index.md`; `wiki/ROUTING.md` (Operations, Podium Web UI, Service Restart & Deployment routes); `wiki/log.md`.
- Notes: Root cause — `next start` serves prebuilt `.next` with no hot reload; `next build` overwrites `.next` in place, so the live server served old HTML against new chunk hashes (400/`text/html` MIME, app stuck at "Checking session…"). Fix is atomic staging-swap `deploy.sh` (build to `.next.staging`, stop→swap→start). Build-only validated; stop/swap/start untested on a real deploy. No secrets, no `.env` contents, no transcript.
- Unresolved: five frontend changes uncommitted (latest commit `eef75d1`); first real `deploy.sh` run will exercise the live swap path; card shows pinned `preferred_agent`/`preferred_model`, not last Run's actual agent/model (would need a new issue-list field).

## [2026-06-12] grill-me + decision | Podium UX/observability tuning plan + ADR-0006

- Actor: agent (Claude, /grill-me session) + James (operator decisions)
- Inputs: `.kanban/archive/2026-06-11/progress.md`; wiki (`index.md`, `ROUTING.md`, `analyses/podium-017-live-updates.md`, `analyses/podium-frontend-deploy-cosmetics.md`, `CLAIMS.md`); code reads `web/api/main.py`, `web/frontend/components/{NewIssueModal,RunDetailPanel,Sidebar}.tsx`, `web/frontend/app/page.tsx`, `config.py`, `agent_runner.py`, `scheduler.py`, `tracker_podium.py`.
- Decisions (plan, not yet implemented): (1) searchable zero-dep comboboxes replacing native FieldSelect; model dropdown auto-populates from a new git-tracked `models.yml` (agent-tagged), filtered by selected agent; maintained by two manually-run skills `symphony-skills` (wraps `podium skills refresh`) + `symphony-models` (edits models.yml). (2) Run liveness = frontend elapsed timer + refresh-on-exit, no live log tail. (3) Live bridge = gated TanStack `refetchInterval` (~3s while queued/running, slow/off idle), WS kept for optimistic operator-action UI. (4) Board overview at `/` (replaces placeholder): per-binding + global state counts, cross-binding attention list, per-binding last activity — all client-side from existing payload; failure-trend chart deferred (needs new run-history endpoint).
- Outputs: `docs/adr/0006-engine-state-surfaced-by-polling-not-websocket.md` (new ADR, accepted); `wiki/raw/adr-0006-engine-state-polling.md` (immutable copy); `wiki/analyses/adr-0006-engine-state-polling.md` (promoted); `wiki/CLAIMS.md` (C-0112 engine writes bypass in-process WS hub → gated polling; C-0113 run log written once at `communicate()` exit; annotated C-0070 as closed/unachievable-as-written); `wiki/index.md`; `wiki/ROUTING.md` (Decisions route); `wiki/log.md`.
- Verified facts: `grep -c "run.updated" scheduler.py tracker_podium.py` = 0/0; only publish is API-startup seed at `main.py:126`. `agent_runner.py:272` `process.communicate(timeout=...)` blocks until exit (no incremental log). Landing `/` is a placeholder; no aggregate view exists.
- Notes: No secrets, no `.env` contents, no transcript. Plan implementation (models.yml, skills, frontend comboboxes/timer/overview, polling) is future work — only the live-bridge architecture decision was promoted to an ADR.
- Unresolved: none of the four plan items implemented yet; ADR-0006 + claims uncommitted (local working tree).

## [2026-06-12] session-update | #028 models.yml catalog + searchable dropdowns

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #028 implementation; commits `99bd541`, `1773db9`, `8bda239`; `models.yml`; `web/api/main.py`; `web/api/tests/test_issue_create.py`; `web/frontend/lib/api.ts`; `web/frontend/components/NewIssueModal.tsx`; `web/frontend/tests/new-issue.spec.ts`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-028-model-catalog-searchable-dropdowns.md`; updated `wiki/analyses/adr-0006-engine-state-polling.md`; updated `wiki/CLAIMS.md` (C-0114, C-0115; C-0056 superseded); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured model catalog source-of-truth move from `KNOWN_MODELS` to `models.yml`, shared `_validate_models()` contract, `/options` model-object shape, graceful invalid-catalog fallback, agent-filtered searchable comboboxes, free-text Agent/Model preservation, and #032 validator reuse note. Verification passed: `uv run pytest` (591 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (16 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES` due an unrelated live-sync flake in the reviewer run. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #031 board overview dashboard

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #031 implementation; commits `e95a394`, `c93500a`, `8387e6a`; `web/frontend/app/page.tsx`; `web/frontend/app/[binding]/page.tsx`; `web/frontend/components/KanbanBoard.tsx`; `web/frontend/tests/dashboard.spec.ts`; `.kanban/issues/031-podium-board-overview-dashboard.md`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-031-board-overview-dashboard.md`; updated `wiki/CLAIMS.md` (C-0116); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured root `/` cross-binding dashboard, client-side aggregation from existing issue-list payloads, global and per-binding `issue.state` roll-ups, last-activity timestamps, blocked/failed attention rows, and `/<binding>?issue=<id>` flyout deep-link behavior. Verification passed: `uv run pytest` (591 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (21 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #032 catalog maintenance skills

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #032 implementation; commits `e1744bc`, `6325bc1`, `4e83e1a`; `.claude/skills/symphony-skills/SKILL.md`; `.claude/skills/symphony-models/SKILL.md`; `tests/skills/test_catalog_maintenance_skills.py`; `.kanban/issues/032-symphony-skills-and-models-maintenance-skills.md`; `.kanban/progress.md`.
- Outputs: updated `wiki/analyses/symphony-skills-index.md`; updated `wiki/CLAIMS.md` (C-0117); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured manual Skill-table refresh flow, direct `models.yml` list/add/remove maintenance, shared `_load_models()` / `_validate_models()` lint gate, no bespoke model helper, and safety rules forbidding service restarts, Plane calls, env-file reads, direct DB model edits, and secret printing. Verification passed: `uv run pytest tests/skills/` (15 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | operator-reply comments

- Actor: agent (Claude, `/dev-build` of `plans/feature-operator-reply-comments.md` + wiki update)
- Inputs: implementation across `web/api/main.py` (`ReplyCreate`, `ALLOWED_REPLY_STATES`/`ACTIVE_RUN_STATES`, `reply_to_issue` endpoint + `ctx`-strip 422 fix), `prompt_renderer.py` (`flag_operator_replies`), `web/frontend/lib/api.ts` (`postReply`), `web/frontend/components/IssueFlyout.tsx` (`ReplyComposer`); new tests `web/api/tests/test_reply.py`, `tests/test_prompt_renderer_podium.py` additions, `web/frontend/tests/reply.spec.ts`; fixtures lifted into `web/api/tests/conftest.py`.
- Outputs: new raw capture `wiki/raw/sessions/2026-06-12-operator-reply-comments.md`; new promoted concept `wiki/concepts/operator-reply.md`; cited edit to `wiki/concepts/prompt-renderer.md` (`render_previous_comments_block` directive flag, updated 2026-06-12); `wiki/CLAIMS.md` C-0118, C-0119; updated `wiki/index.md`, `wiki/ROUTING.md`, `wiki/log.md`.
- Notes: Durable new fact — posting an operator reply carries a `todo` state-flip side effect that re-dispatches the agent (single atomic conditional `UPDATE` with `COALESCE(comments_md,'')`, state + `latest_run_state` guard; 409/422/400/404 contract). Continuity is transcript re-feed (`comments_md` + `context_md`), not pi session resume. Closes the bidirectional Issue Comments gap (C-0068); extends Podium render_prompt (C-0077). Verification: `pytest web/api/tests` 72 passed/1 skipped, `pytest tests/ --ignore=alembic` 471 passed (one flaky concurrency test passes in isolation; fails only under concurrent CPU/SQLite load), `playwright reply.spec.ts` 3 passed, `tsc --noEmit` clean, sample Podium prompt eyeballed showing directive + reply. No secrets, no `.env` contents, no transcript. Pre-existing unrelated `tests/test_alembic_baseline.py` collection error (`alembic` not installed) ignored.

## [2026-06-12] session-update | frontend e2e clobbers live .next (crash-loop + deploy.sh recovery)

- Actor: agent (Claude, post-restart frontend incident)
- Inputs: live diagnosis of "Checking session…" hang after `podium-web.service` restart — `.next` had no `BUILD_ID` (dev build written at 05:04 by `playwright test` during the operator-reply `/dev-build`); `next start` crash-looped (NRestarts=13); referenced chunks 400ing with `text/html`. Evidence: `journalctl -u podium-web.service`, `web/frontend/playwright.config.ts:39-44`, `web/frontend/package.json`, `web/frontend/deploy.sh`, port/listener + curl probes.
- Outputs: updated `wiki/analyses/podium-frontend-deploy-cosmetics.md` (new "Second trigger: Playwright e2e clobbers the live `.next`" section, deploy.sh first-real-run validation, isolation follow-up, frontmatter sources); `wiki/CLAIMS.md` C-0120; updated `wiki/ROUTING.md`, `wiki/log.md`.
- Notes: Durable fact — `pnpm test:e2e` runs `next dev` into the shared `web/frontend/.next` with no `NEXT_DIST_DIR`, silently overwriting the production build `podium-web` serves; damage is masked until the next restart, then crash-loops on a missing `BUILD_ID`. Recovery is `deploy.sh` (staging-swap rebuild), not a bare restart — also confirmed deploy.sh's stop/swap/start path end-to-end for the first time (chunks 200 with correct MIME, tree clean, root 200). Prevention follow-up: isolate e2e webServer via throwaway `NEXT_DIST_DIR` or keep `test:e2e` out of live-dir automated builds. No code change this pass; no secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | Pi personal harness profile

- Actor: agent (Pi, personalize-harness-pi + wiki update)
- Inputs: current session; `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`; `.pi/extensions/personal-harness.ts`; `CLAUDE.md`; `web/README.md`; `web/frontend/playwright.config.ts`; `wiki/analyses/podium-frontend-deploy-cosmetics.md`; `wiki/analyses/symphony-tests-index.md`.
- Outputs: `wiki/raw/sessions/2026-06-12-personal-harness-pi.md`; `wiki/analyses/personal-harness-pi-profile.md`; `wiki/CLAIMS.md` (C-0121..C-0122); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured the generated project-local Pi harness, advisory/deferred project-check posture, manual-only Playwright posture, reference-only guidance decision, selected safety blockers, and verification results. No secrets, no `.env` contents, no `/home/james/symphony-host.env` contents, no full transcript.

## [2026-06-12] session-update | Issue archive ("delete button") design grilling

- Actor: agent (Claude, grill-me design session + wiki update)
- Inputs: current conversation (grill-me on delete-vs-done); codebase facts from `web/api/schema.py`, `web/api/main.py`, `web/api/db.py`, `web/api/worktree.py`, `tracker_podium.py`, `web/frontend/lib/issues.ts`, `web/frontend/components/KanbanBoard.tsx`, `web/frontend/components/IssueFlyout.tsx`; `CONTEXT.md` (Tracker Contract entry edited twice this session).
- Outputs: `wiki/raw/sessions/2026-06-12-issue-archive-state-design.md`; `wiki/analyses/podium-issue-archive-design.md` (auto-promoted after lint); `wiki/CLAIMS.md` C-0123..C-0125; `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Design accepted, not implemented — sixth `archived` state (no new column), engine-terminal contract (no verdict transition post-run, deferred worktree teardown via `remove_worktree`), mid-run archive allowed, per-column board minimize with localStorage persistence, Archive button in flyout, 14-day opportunistic purge on `updated_at` with FK-safe delete order. Hazards recorded: `transition_state` resurrection bug, worktree-vs-issue "archive" terminology collision. C-0021/C-0064 (five states) left active — supersession deferred to the implementation pass. ADR offered, declined. No secrets, no env contents, no transcript.

## [2026-06-12] session-update | #034 archived issue state core

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #034 implementation; commits `11a1ff3`, `efc8c67`, `0b90159`, `a97e186`, `0569271`; `.kanban/issues/034-podium-archived-state-core.md`; `.kanban/progress.md`; `web/api/main.py`; `web/api/schema.py`; `web/api/migrations/versions/0004_archived_state.py`; `web/api/tests/test_issue_patch.py`; `web/api/tests/test_reply.py`; `web/frontend/lib/issues.ts`; `web/frontend/components/KanbanBoard.tsx`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/tests/archive.spec.ts`; `web/frontend/tests/board.spec.ts`.
- Outputs: updated `wiki/analyses/podium-issue-archive-design.md`; updated `wiki/CLAIMS.md` (C-0067, C-0123..C-0125); updated `wiki/index.md`; updated `wiki/log.md`.
- Notes: Captured #034 landing the sixth `archived` Issue state through migration/runtime schema, PATCH and list filtering, reply 409 guard coverage, rightmost default-collapsed Archived board column, and no-confirm flyout Archive action. Engine-terminal teardown (#035) and 14-day purge (#036) remain pending. Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (618 passed, 1 skipped), `pnpm exec tsc --noEmit`, `PATH="$HOME/.local/bin:$PATH" pnpm test:e2e` (32 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES` with only minor notes addressed by follow-up commits. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #036 archived retention purge

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #036 implementation; commits `b589cef`, `cb079c4`, `6cf44b9`; `.kanban/issues/036-podium-archived-retention-purge.md`; `.kanban/progress.md`; `web/api/main.py`; `web/api/tests/test_archive_purge.py`.
- Outputs: updated `wiki/analyses/podium-issue-archive-design.md`; updated `wiki/CLAIMS.md` (C-0127 superseded, C-0128 added); updated `wiki/index.md`; updated `wiki/log.md`.
- Notes: Captured #036 landing the archived retention purge: API startup + post-archive PATCH sweeps, hardcoded 14-day `updated_at` window, FK-safe per-issue delete order, best-effort run-log unlink, rollback behavior, and filesystem-based defensive worktree cleanup even when `worktree_active` is stale. Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (633 passed, 1 skipped), touched-file LSP diagnostics clean, `git diff --check` clean, secret scan clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | First live Podium skill catalog refresh

- Actor: agent (Claude Code, symphony-skills + wiki-update)
- Inputs: live `python -m web.cli.podium skills refresh` run (dry-run → FK failure → repoint → success); `web/cli/podium_skills.py`; `web/cli/podium.py`; `web/api/seed.py`; `.claude/skills/symphony-skills/SKILL.md`; in-session DB inspections of `podium.db`.
- Outputs: new `wiki/raw/sessions/2026-06-12-podium-skills-catalog-refresh.md`; new `wiki/analyses/podium-skills-catalog-refresh.md` (candidate created, linted, auto-promoted); `wiki/CLAIMS.md` C-0133..C-0136 added, C-0055 marked superseded (by C-0136); `wiki/index.md` and `wiki/ROUTING.md` updated.
- Notes: Captured three durable refresh-CLI behaviors: dry-run prints catalog TSV not a diff (SKILL.md step 2 wrong — follow-up to fix wording); single-source scan contract (default `~/.claude/skills` dotfiles symlink; repo-local `symphony-*` skills not cataloged; two `--source` runs clobber); `issue.preferred_skill` FK blocks stale-row delete with clean whole-run rollback, and manual-row protection is deletion-only (manual `diagnose` row converted to file-backed by upsert). James approved live refresh and repointing 12 e2e issues from `/diagnose` to `diagnose`. Result: 50-row catalog, zero pending diff, catalog maintenance skill tests 6 passed. Skill seeding confirmed retired in `web/api/seed.py` → C-0055 superseded. No secrets, no env contents, no transcript.

## [2026-06-12] session-update | catalog-alpha/bravo fixture leak cleanup

- Actor: agent (Claude Code)
- Inputs: James report of phantom dropdown entries; `podium.db` skill rows; `web/frontend/tests/skill-catalog.spec.ts`; `web/frontend/tests/fixtures.ts`; git history (`6d9f1c6`).
- Outputs: deleted `catalog-alpha`/`catalog-bravo` rows from live `podium.db` (48 rows remain, zero manual rows); updated `wiki/analyses/podium-skills-catalog-refresh.md` resulting-state section; updated C-0136 note in `wiki/CLAIMS.md`.
- Notes: Rows were leaked Playwright e2e fixtures — an older `seedSkills` wrote `source=''` into the live DB, which refresh's manual-row protection then preserved. Current `fixtures.ts` isolates via `PODIUM_DB_PATH` → `web/test-results/podium-e2e.db` and tags `source='e2e'` (self-healing: refresh deletes leaked `'e2e'` rows). No FK or code references existed at deletion. No secrets, no env contents.
## [2026-06-12] session-update | Pi personal harness hardening pass

- Actor: agent (Pi follow-up)
- Inputs: `.pi/extensions/personal-harness.ts`; `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`; `wiki/raw/sessions/2026-06-12-personal-harness-pi.md`; post-generation setup review findings.
- Outputs: tracked `wiki/raw/personal-harness-pi-profile.md`; updated `.pi/extensions/personal-harness.ts`; updated `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`; updated `wiki/analyses/personal-harness-pi-profile.md`; updated `wiki/CLAIMS.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Hardened bash secret-read blocking for `/home/james/symphony-host.env` and `.env`-like files, switched runtime roots to `PROFILE.targetRepo`, moved the durable profile reference into tracked wiki raw storage, changed automatic pytest beforeGit into a manual `uv run pytest -q` reminder, and replaced source-only dry checks with mocked-event verification coverage. No secrets or `.env` contents captured.

## [2026-06-12] session-update | #039 dashboard attention list removal

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #039 implementation; commits `1ca6fe2`, `5d6918f`, `c91bdcc`; `.kanban/issues/039-podium-remove-dashboard-attention-list.md`; `.kanban/progress.md`; `web/frontend/app/page.tsx`; `web/frontend/tests/dashboard.spec.ts`.
- Outputs: updated `wiki/analyses/podium-031-board-overview-dashboard.md`; updated `wiki/CLAIMS.md` (C-0116 note, C-0140 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured #039 removal of the Dashboard Needs attention list after Sidebar Inbox became canonical. Verification passed: `PATH=/home/james/.local/bin:$PATH pnpm test:e2e` (37 passed), `pnpm exec tsc --noEmit`, touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | Issue-field dispatch contract (grill-me → deploy → smoke)

- Actor: agent (Claude Code, grill-me session with James)
- Inputs: grill-me decisions Q1–Q8; commits `0912016`, `2343bf2`, `ea449b5`; smoke issue 20 / run 13; journalctl drift tracebacks; pi v0.78.1 `--help` and package `docs/skills.md`.
- Outputs: new `wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md`; promoted `wiki/analyses/podium-issue-dispatch-contract.md` (lint passed, auto-promotion); supersession notes on `analyses/podium-014-new-issue-flow.md`, `analyses/podium-028-model-catalog-searchable-dropdowns.md`, `concepts/prompt-renderer.md`, `concepts/thin-engine-v2.md`, `sources/symphony-host-service-unit.md`; `wiki/CLAIMS.md` C-0141..C-0146 added, C-0058 marked superseded, C-0114 drift note; `wiki/index.md` + `wiki/ROUTING.md` updated.
- Notes: Six dispatch-contract decisions implemented and live-verified same session. Root cause captured: live podium.db alembic stamp-vs-run drift (0005 stamped, column missing) broke transition_state post Ralph #037/#038 merge; fixed manually + pragma parity check. Follow-up: kanban #040 (claude adapter), startup schema-parity check idea, stale glm reference in new-issue.spec.ts. No secrets, no transcript.

## [2026-06-12] session-update | ensure_schema stamp-drift root cause + boot guard

- Actor: agent (Claude Code, follow-up to dispatch-contract session)
- Inputs: forensics on `web/api/main.py` `ensure_schema` (blind `UPDATE alembic_version` on boot); commit `772e7ba`; `web/api/tests/test_ensure_schema.py` (4 regression tests); e2e suite 37 passed, python suite 659 passed.
- Outputs: refined `wiki/analyses/podium-issue-dispatch-contract.md` root-cause paragraph; `wiki/CLAIMS.md` C-0147 added, C-0145 note refined; `wiki/ROUTING.md` keywords extended.
- Notes: Confirmed mechanism for the 2026-06-12 stamp-vs-run drift. Boot now fails loud on missing columns instead of serving against a drifted schema. Stale glm reference in new-issue.spec.ts found already fixed by the Ralph batch; remaining glm string is decorative run-history fixture data. No secrets.

## [2026-06-12] session-update | Unit env cleanup, #040 archived, CLI ensure_schema parity

- Actor: agent (Claude Code)
- Inputs: James request (archive claude-adapter ticket, unit cleanup, CLI ensure_schema parity); unit + override.conf edits with `*.bak.2026-06-12` backups; restart verification markers.
- Outputs: `.kanban/issues/040` → `.kanban/archive/2026-06-12c/` (status blocked, deferral note; Ralph attempt had blocked on missing verification command); symphony-host unit cleaned of `OPENCODE_*` and `SYMPHONY_PI_*` env (drop-in keeps `PI_BIN`); `web/cli/podium_skills.py` `ensure_schema` now fresh-only (never touches existing DBs); CLAUDE.md env/dead-config sections rewritten; `wiki/sources/symphony-host-service-unit.md` note updated.
- Notes: Post-cleanup restart clean on code_sha=81bfd8d — startup pi probe passed using the models.yml default (gpt-5.5/openai-codex), proving env removal safe. No secrets.

## [2026-06-13] lint | Resolve committed git stash-pop conflict markers in wiki

- Actor: agent (Claude Code)
- Inputs: `wiki/index.md`, `wiki/ROUTING.md`, `wiki/log.md` each carrying committed `<<<<<<< Updated upstream` / `=======` / `>>>>>>> Stashed changes` markers from a prior `git stash pop` (stashes `ralph-preserve-unrelated-*` still present).
- Outputs: `wiki/index.md` (superset of 4 analysis rows — kept stashed's fuller `personal-harness-pi-profile` sources incl. `wiki/raw/personal-harness-pi-profile.md`, kept upstream's "#034/#035/#036 implemented" `podium-issue-archive-design` row over the stale "not yet implemented" side); `wiki/ROUTING.md` (Skills & Tooling union — upstream page set + `tracked harness profile`/`targetRepo root resolution`/`secret-env-bash-read` keywords merged in); `wiki/log.md` (kept both append-only entry sets — #034/#036/skills-catalog/fixture-leak from upstream and the Pi-harness-hardening entry from stashed).
- Notes: All referenced pages verified on disk (no dangling links). No content lost — markers were a merge artifact, both sides were legitimate. Leftover stashes `stash@{0}`/`stash@{1}` not dropped. Unrelated working-tree WIP (output-contract refactor across claude_runner/prompt_renderer/scheduler/tracker_podium) left untouched and excluded from this commit.

## [2026-06-13] session-update | #046 unify agent output contract and clean comment stream

- Actor: agent (Claude Code)
- Inputs: in-flight uncommitted refactor across `prompt_renderer.py`, `scheduler.py`, `tracker_podium.py`, `claude_runner.py` + tests (the working-tree WIP excluded from the prior wiki-lint commit); finished, verified (`uv run pytest`: 694 passed, 1 skipped), and committed this session as `82f81fd` (symphony), `f1b7e57` (homelab WORKFLOW.md), `9a29dfb` (trading WORKFLOW.md).
- Outputs: raw capture `wiki/raw/sessions/2026-06-13-unified-output-contract.md`; promoted analysis `wiki/analyses/podium-046-unified-output-contract.md`; claims C-0159..C-0163 added; C-0039 marked superseded (→C-0162); C-0006 annotated with C-0160 companion; `index.md` analysis row + `ROUTING.md` new "Output contract" route.
- Notes: Durable knowledge — new engine-owned output contract (single `OUTPUT_CONTRACT`, multi-line `SYMPHONY_SUMMARY_BEGIN/END` block bounded 4000c with single-line fallback, summary posted verbatim, Timeline footer + `Symphony claimed at` comment removed, claim time from Run `started_at`). Code committed locally, NOT pushed and NOT live — `symphony-host.service` runs prior code until a James-approved restart; new comment format takes effect only after restart. No secrets read. Open follow-up: verify on first live run post-restart; homelab Plane archive would need another WORKFLOW pass.

## [2026-06-13] session-update | Remove the IssueFlyout archive button

- Actor: agent (Claude Code)
- Inputs: James request to remove the flyout Archive button; working-tree edits to `web/frontend/components/IssueFlyout.tsx` (deleted the `data-testid="archive-issue"` button block between `MetadataChips` and the tab strip) and `web/frontend/tests/archive.spec.ts` (retargeted "archive button moves issue…" to the `edit-state` state chip, deleted the now-obsolete "archive button hidden on already archived issue" test); confirmed `archived` is in `STATES`/`STATE_KEYS` (`web/frontend/lib/issues.ts:11`) so the state chip already offers it.
- Outputs: raw capture `wiki/raw/sessions/2026-06-13-remove-flyout-archive-button.md`; promoted-page maintenance edit to `wiki/analyses/podium-issue-archive-design.md` (line-25 prose softened to "originally carried", Button decision row struck through with removal note, follow-up added, `updated` 2026-06-13, new source); `wiki/CLAIMS.md` C-0164 added, C-0125 annotated (Archive-button clause superseded by C-0164, other clauses remain active); `wiki/ROUTING.md` Podium Web UI keywords extended.
- Notes: UI affordance removal only — no API/schema/engine change; #033/#034 column-minimize, #035 engine-terminal, #036 retention purge all unaffected. Change is in the working tree, NOT committed and NOT deployed — `podium-web` serves the prior build until a frontend rebuild + `deploy.sh` staging swap. No secrets.

## [2026-06-13] session-update | #046 review-hardening follow-up

- Actor: agent (Claude Code)
- Inputs: independent Opus review (dev-review-claude) of the committed #046 change (`82f81fd`); applied five fixes in the working tree — secret redaction before bounding (W2), column-0 `_SUMMARY_BLOCK_RE` + unindented OUTPUT_CONTRACT (W3), `_run_started_at` gated on `stores_context` (W1), completion summary on its own line (N3), `NOTIFY_REASON_MAX_CHARS=2000` notifier cap (N4); added two regression tests (straddle redaction, indented-block non-match); `uv run pytest` 696 passed, 1 skipped; ruff clean.
- Outputs: review-hardening section added to `wiki/analyses/podium-046-unified-output-contract.md`; claim C-0165 added (refines C-0160, C-0162); this log entry. Code changes in `scheduler.py`, `prompt_renderer.py`, `tests/test_scheduler.py`.
- Notes: Durable refinement of the #046 output contract (security: secret-straddle redaction; correctness: contract self-match guard). Separate symphony commit on top of `82f81fd`; NOT pushed and NOT live — `symphony-host.service` runs prior code until a James-approved restart. No secrets read. Working tree also contains an unrelated archive-button-removal stream (frontend + its wiki) left uncommitted.

## [2026-06-13] session-update | symphony-* skills audit + troubleshooter SQL fix

- Actor: agent (Claude Code)
- Inputs: full review of all 11 repo-local `symphony-*` skills against current source after #042–#046/Podium churn; verified referenced functions, API endpoints (loopback 8090), test files, and SQLite column names.
- Outputs: fixed two stale SQLite fallback queries in `.claude/skills/symphony-troubleshooter/SKILL.md` (binding `repo_path`/`default_agent` → `name, display_name, archived`; run `updated_at` → `started_at`/`ended_at`, order by `id desc`); raw capture `wiki/raw/sessions/2026-06-13-symphony-skills-audit.md`; claim C-0168 (refines C-0129); maintenance edit + date bump on `wiki/analyses/symphony-skills-index.md`; this log entry.
- Notes: Doc-only fix; no code or service change. Other 10 skills verified clean. James approved the edit. No secrets read; review read-only except the single skill-doc edit. Follow-up: when ADR-0008 `preferred_skill` consume-on-dispatch is committed, decide whether any operator skill should mention it.

## [2026-06-13] session-update | symphony-binding-scaffold accuracy review + live symphony self-binding

- Actor: agent (Claude Code)
- Inputs: accuracy review of `.claude/skills/symphony-binding-scaffold/SKILL.md` against `skill_migration.py` / `web/api/db.py` / `scheduler.py`; ran `uv run pytest tests/skills/test_binding_scaffold.py` (2 passed); James approved binding the Symphony repo itself live.
- Outputs: hardened SKILL.md (exact `PodiumBindingScaffoldRequest` call, `db_path`/`bindings_path` resolution, `default_agent`/`binding_type` enums, live DB+yaml verification block, `plane_project_id`/restart notes); created live `symphony` binding (DB row + `binding_settings` in `/home/james/symphony/podium.db`, appended to `bindings.yml`); raw capture `wiki/raw/sessions/2026-06-13-symphony-self-binding-scaffold.md`; promoted `wiki/entities/binding-symphony.md` + `wiki/analyses/analysis-session-symphony-self-binding-scaffold.md`; claims C-0170 (binding live), C-0171 (comment-stripping side effect), C-0172 (is_coding per-binding); marked C-0066 superseded; refined C-0099 note; index/routing updates.
- Notes: Verified side effect — `scaffold_podium_binding` strips all `bindings.yml` comments via `yaml.safe_load`/`safe_dump` round-trip (deleted 77 lines of Plane rollback comment blocks; data-identical, recoverable from git); James chose to leave them removed. Self-binding is highest-risk (agents can edit scheduler source). Binding NOT live until a James-approved `symphony-host.service` restart; no real `WORKFLOW.md` authored yet. No secrets read; `symphony-host.env` untouched.
- Unresolved: restart to activate binding; author symphony `WORKFLOW.md` before smoke; consider hardening `_append_binding` against comment loss.

## [2026-06-13] session-update | symphony binding WORKFLOW.md authored + restart-activated

- Actor: agent (Claude Code)
- Inputs: continuation of the symphony self-binding session; activated the binding via `symphony-restart` (James-approved) and authored its `WORKFLOW.md` via `symphony-workflow-author`. Operator chose edit-and-commit-to-`main` autonomy for the self-binding.
- Outputs: restart verified (new pid 944137, code_sha d24921a, `bindings=3`, all three reconcile_startup_done, dispatch loop alive, 0 errors); authored + committed `WORKFLOW.md` (`2e8ff42`, target-repo-only commit); render-tested against `prompt_renderer.py`; `uv run pytest tests/skills/test_workflow_author.py` passed; claim C-0173 added; C-0170 follow-ups marked resolved; `wiki/entities/binding-symphony.md` updated (WORKFLOW section + live status).
- Notes: `WORKFLOW.md` is read per-dispatch, so effective without a further restart. Live-Infrastructure Safety Boundary keeps restart/unit/bindings.yml/podium.db/Plane/worktree mutations operator-gated despite commit freedom. Unrelated working-tree changes (`claude_runner.py`, `tests/test_claude_runner.py`, `wiki/analyses/podium-042-claude-tmux-adapter.md`) are James working in a parallel session — left untouched; the WORKFLOW.md commit was surgical (1 file). No secrets read.
- Unresolved: optional `_append_binding` comment-preservation hardening (C-0171). `symphony-binding-smoke` now available to exercise the binding end-to-end if desired.

## [2026-06-13] session-update | Session Resume continuity design (grill + ADR-0009 + issues 047–055)

- Actor: operator (James) + agent (Claude Code)
- Inputs: `/grill-me` on "track agent session files per issue and resume on operator reply" → universal continuity design; verified pi/Claude session flags (`pi --help`, `claude --help`) and the Claude Agent SDK + pi sessions docs (conversation-not-filesystem; capture is an SDK feature; Anthropic recommends re-feed for ephemeral). Then `/to-issues`, then ADR creation, then this wiki pass.
- Outputs: ADR-0009 `docs/adr/0009-session-resume-continuity.md` (+ raw copy `wiki/raw/adr-0009-session-resume-continuity.md`); raw session capture `wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md`; promoted `wiki/analyses/adr-0009-session-resume-continuity.md` + `wiki/concepts/session-resume-continuity.md`; CONTEXT.md glossary terms Continuity/Re-feed/Session Resume/Question Park/Session Tail; kanban issues 047–055 (board 027–046 archived to `.kanban/archive/2026-06-13/`); claims C-0175 (ADR-0009 decision) + C-0176 (glossary + issue board); forward-pointer note added to `wiki/concepts/operator-reply.md`; index/routing updates (new Continuity & Session Resume routing branch).
- Notes: DESIGN/PLANNING only — no code shipped; live continuity is still pure re-feed, which stays the guaranteed floor. ADR `accepted` but unimplemented. operator-reply "transcript re-feed, not session resume" is NOT marked superseded (re-feed remains the floor; supersede only when Session Resume ships). All working-tree changes uncommitted (live-infra repo — operator to review/commit). No secrets read; `symphony-host.env` untouched.
- Unresolved: implement issues 047–055; ADR-0009 currently on hold→now created; stale CONTEXT.md "Agent" glossary term ("pi only / claude removed") recorded but NOT fixed per operator hold; Question Park reverses the unattended "never ask questions" contract once 052 lands.

## [2026-06-13] maintenance | CONTEXT.md stale-glossary fix

- Actor: operator (James) + agent (Claude Code)
- Inputs: operator asked to fix the stale records flagged in C-0176 (CONTEXT.md "Agent" term contradicting live Claude).
- Outputs: CONTEXT.md — **Agent** term rewritten (pi + claude both live, per-issue routing, claude via tmux; was "pi only / claude removed"); **Project Binding** `default_agent` now `pi`/`claude` and coding bindings = `trading` + `symphony` (was pi-only / trading-only); **Tracker Adapter** lists `homelab`/`trading`/`symphony` on Podium (was "both homelab and trading"). C-0176 note updated to record the fix.
- Notes: Aligns the glossary with C-0153 (RoutingAgentAdapter), C-0170 (symphony binding live), C-0174 (live Claude). Analyses pages referencing the pi-only era are accurate history and were left intact (mark-superseded-not-delete). Working tree uncommitted (live-infra repo — operator to review/commit). No secrets read.

## [2026-06-13] session-update | Ralph #048 Session Resume decision core

- Actor: Ralph (Pi)
- Inputs: `.kanban/issues/048-continuity-decision-core.md` from ADR-0009 backlog; implementation base `838ff66e46562cbf38ac28b0cf91fa2f8c9e9147`.
- Outputs: Added `session_continuity.py` and `tests/test_session_continuity.py`; marked #048 done; updated `.kanban/progress.md`; promoted wiki status from design-stage/unimplemented to partially implemented for Session Resume; added claim C-0177 and updated C-0176 status note.
- Notes: Live dispatch still uses re-feed until #049–#051 wire delta prompt rendering and pi/Claude adapters. Verification: `uv run pytest tests/test_session_continuity.py -q` (11 passed), full `uv run pytest -q` (727 passed, 1 skipped), critical LSP diagnostics clean for touched Python files. No secrets read; no service restart or external notification fired.

## [2026-06-13] grill-me + decision | ADR-0010 — dispatch pi via RPC for live mid-run Steering

- Actor: Claude (grill-me session with operator).
- Inputs: `docs/handoffs/2026-06-13-pi-tmux-standardization-grill.md`; `agent_runner.py`, `claude_runner.py`, `scheduler.py`, `web/api/main.py`; pi bundled docs `docs/rpc.md`/`json.md`; ADR-0001/0002/0006/0009; kanban 047-055; `C-0016`/`C-0174`/`C-0176`.
- Decision: reject "pi -> tmux" and "one dispatch mechanism" (unreachable — `claude -p`/`stream-json` removed for this account, C-0016). Standardize the **Agent Adapter capability interface, not the transport**: dispatch **pi via `pi --mode rpc`** to enable **live mid-run Steering** (RPC `steer`, race-free) over a web->scheduler payload channel (extends #054 sentinel; extends ADR-0006 with an inward input path). **Claude stays tmux park-and-reply**; live Steering is **pi-only**.
- Outputs: created `docs/adr/0010-pi-rpc-dispatch-for-live-steering.md` (status `proposed`); added **Steering** term to `CONTEXT.md`; re-sequenced kanban — rewrote #050 onto RPC (Slice A: dispatch parity + resume), amended #052 (pi park parses `SYMPHONY_QUESTION` from RPC final text) and #053 (tail stands; pi RPC persists session jsonl), added #056 (steer channel), #057 (steer UI), #058 (RPC lifecycle); added claim C-0178; marked the live-steer-deferred clause of C-0176 superseded; updated `wiki/concepts/session-resume-continuity.md`.
- Parity spike: PASSED (throwaway `/tmp`, `--no-session`, no infra touched) — `pi --mode rpc --skill <dir>` loaded the skill, resolved `openai-codex`/`gpt-5.4-mini`, loaded CLAUDE.md context (answered "caveman"), streamed `message_update` deltas, completed on `agent_end`.
- Notes: NO production code shipped; only the spike ran. Loop already stopped (2 iterations, #047 done/committed, #048 attempted); #047/#048/#049 are RPC-agnostic, kept. Do NOT restart any loop until the re-sequenced issues are reviewed. Working tree uncommitted (live-infra repo — operator to review/commit). No secrets read; no service restart. ROUTING/index update for the Steering term deferred to a follow-up.

## [2026-06-13] grill-me + decision | Comments/Context post-Resume role reframe

- Actor: Claude (grill-me session with operator).
- Inputs: `docs/handoffs/2026-06-13-comments-context-rework-grill.md`; `CONTEXT.md`; ADR-0009/0010; `prompt_renderer.py:217-225`; `.kanban/issues/049,050,052,056`; C-0175–C-0178; `wiki/concepts/operator-reply.md`.
- Decision: the headline hypothesis "rework Comments/Context" resolves to **terminology rework only** — #049/#050 already encode the right data model and injection plan. Operator confirmed: re-feed floor permanent & authoritative; Issue Comments = human-facing record + operator input channel (agent never consumes the blob as memory; resume injects only the newest operator-reply delta; full blob re-injected only on the floor); Issue Context = floor substrate + UI observability (not injected on resume); compaction orthogonal (#026 owns `context_md` fresh/fallback-only, native session auto-compacts itself, no reconciliation — closes the ADR-0009 deferral); live Steering appends to Comments as a distinct entry (no state flip, not re-injected).
- Outputs: reworded `CONTEXT.md` **Issue Comments** + **Issue Context** (clean ownership split — Comments = human surface, Context = AI surface), added **Steering** term + a source-of-truth relationship line; amended `docs/adr/0009-session-resume-continuity.md` with a "Resolved 2026-06-13" note closing the deferred compaction question and stating the human/AI ownership split; added claim **C-0179**; added a role-reframe note to `wiki/concepts/operator-reply.md`; added ROUTING keywords.
- Issue edits (the only spec the grill produced that the backlog lacked — Steering's durable record): **#056** + acceptance criterion: accepting a steer appends a distinct `### Operator Steer (<ISO>)` block to `comments_md`, NO state flip, NOT re-injected (transient queue is not the record). **#057**: note the steer shows in the comments thread (durable) vs the live tail (transient). **#050**: note that the RPC session owns its own context window on a long resume loop (native auto-compaction), orthogonal to #026. #049/#052/#058 unchanged — already correct.
- Full gap pass over #047–#058 (operator-requested, before commit). Two real gaps fixed: **(A) skill-invoke on resume** — a `preferred_skill` named on an operator reply was silently dropped on the resume path; #049 now keeps the skill-invoke prepend on resume and #050 re-passes `--skill <dir>` on the resume launch. **(B) #056↔#054 sequencing** — #056 extends #054's wake-sentinel seam to a payload queue but was not blocked by it; #056 `blocked_by` now `[050, 054]`. Minor #054 `blocked_by:[047]` loose dependency left as-is (harmless). All other issues consistent with the resolved design.
- Notes: NO code shipped; terminology/decision only. No new ADR (amendment chosen over ADR-0011). Working tree uncommitted (live-infra repo — operator to review/commit). No secrets read; no service restart. ROUTING/index update for the Steering term still deferred (carried from the prior entry).

## [2026-06-13] session-update | #054 Fast re-dispatch on operator reply

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #054 implementation; commits `2ab4a47`, `06ecc6b`, `acfdf3e`; `.kanban/issues/054-fast-redispatch-on-reply.md`; `.kanban/progress.md`; `web/api/wake_signal.py`; `web/api/main.py`; `scheduler.py`; `web/api/tests/test_reply.py`; `tests/test_scheduler.py`; `tests/test_log_retention.py`; existing ADR-0009 Session Resume and operator-reply wiki pages.
- Outputs: updated `wiki/concepts/session-resume-continuity.md`; updated `wiki/analyses/adr-0009-session-resume-continuity.md`; updated `wiki/concepts/operator-reply.md`; updated `wiki/CLAIMS.md` (C-0187 added; C-0176 note updated); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured the filesystem wake-sentinel seam (`SYMPHONY_WAKE_SENTINEL_PATH` / `SYMPHONY_RUNTIME_DIR/reply-wake` / `/tmp/symphony/reply-wake`), API touches after successful reply and state-to-`todo` PATCH, failed replies not waking, scheduler one-second sentinel checks during poll sleeps, stale sentinel consumption, and no-busy-loop behavior. Verification passed: issue command `uv run pytest tests/test_scheduler*.py web/api/tests/test_reply.py -q` (155 passed), full `uv run pytest -q` (749 passed, 1 skipped), `uv run ruff check` on touched Python files, touched-file LSP diagnostics clean, `git diff --check`, secret-pattern diff scan, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-13] in-app verification | #050 pi RPC dispatch — ADR-0010 Slice A FAILED

- Actor: Claude (operator-requested in-app verification of #050, after the tralph batch auto-merged the full #049–#054 chain).
- Method: drove Symphony's own `run_pi_rpc_agent` against real pi 0.78.1 (`openai-codex`/`gpt-5.4-mini`) in a throwaway cwd via a `/tmp` harness — no service, no Podium, no binding — plus a raw protocol-compliant capture of `pi --mode rpc` events.
- Finding: **FAIL.** Both fresh + resume calls returned `timed_out=True` at full `run_timeout_ms`, though the model completed and resume recalled the prior token. A compliant blocking reader saw `agent_end` in 9.7s for the same prompt → pi is fine, the adapter is broken. Root causes: (1) `_read_rpc_line` uses `selectors` on the raw fd + buffered `readline()`; pi RPC stays alive idle after `agent_end` (no EOF), so the buffered terminal line is never read → timeout; (2) `_event_text` over-scrapes (extension `setStatus`/`notify` banners, echoed prompt, cumulative partials) → polluted assistant text. Faked-stdio unit tests (C-0181) masked both.
- Outputs: reopened `.kanban/issues/050` (`status: reopened`) with both defects + fix guidance; added claim **C-0188**; appended superseding caveats to **C-0181**/**C-0183**; annotated ADR-0010 on disk (gitignored). ADR-0010 stays `proposed`. Confirmed `pi_mode: rpc` is set on NO binding (one-shot default) → broken adapter dormant, production unaffected. Throwaway pi sessions cleaned.
- Guardrails: do NOT flip ADR-0010 → accepted and do NOT enable `pi_mode: rpc` until #050 is re-verified in-app. No `symphony-restart` warranted. No secrets / `.env` / transcript.

## [2026-06-13] fix | #050 pi RPC adapter — both defects fixed, Slice A re-verified PASS

- Actor: Claude (operator: "fix #050 now"), following the C-0188 in-app failure.
- Change (`agent_runner.py`): replaced `_read_rpc_line` with `_rpc_line_reader` (raw-fd `os.read` + drain-buffer-before-repoll, StringIO `readline` fallback, completion via `agent_end` not EOF); replaced `_event_text`/`_stringify_event_text`/`_rpc_text_from_raw` with `_assistant_delta` (only `message_update` text_delta, excludes thinking/tool-call/banners/echoes). Rewrote the `run_pi_rpc_agent` event loop accordingly.
- Tests: added `test_run_pi_rpc_agent_extracts_only_assistant_text_deltas` (real pi event shape + exclusion) and env-gated `test_run_pi_rpc_agent_real_pi_completion_parity` (`SYMPHONY_RPC_PARITY=1`). `tests/test_agent_runner.py` 20 passed/1 skipped; #050 suite (`test_dispatch_compaction`/`test_scheduler`/`test_session_continuity`/`test_agent_runner`) 173 passed/1 skipped.
- In-app verification (real pi 0.78.1, `openai-codex`/`gpt-5.4-mini`): run-to-completion ~15s (`timed_out=False`, `exit=0`, `stdout=='PARITY_OK'`); resume across two processes recalled the token — `OVERALL=PASS` (was 120s timeout pre-fix).
- Outputs: `#050` → `done` (fix notes + soak caveat); claim **C-0189**; **C-0188** marked RESOLVED→C-0189; ADR-0010 disk annotation updated FAILED→FIXED. ADR-0010 stays `proposed`.
- Guardrails: adapter-level Slice A only — a throwaway-binding soak (scheduler→adapter→verdict) is still required before enabling `pi_mode: rpc` on any real binding or flipping ADR-0010 → accepted. No service/Podium touched; throwaway pi sessions cleaned. No secrets / `.env` / transcript.

## [2026-06-13] soak + cutover | rpcsoak throwaway binding — ADR-0010 Slice A full-path PASS → accepted

- Actor: Claude (operator-driven, step-gated).
- Setup: created isolated repo `/home/james/rpc-soak` (real WORKFLOW.md); scaffolded `rpcsoak` coding binding via `symphony-binding-scaffold` (Podium DB row + `bindings.yml`, committed `5943420`); added `pi_mode: rpc`.
- Cutover: operator approved a full restart. `sudo systemctl restart symphony-host.service` → code_sha `2e8ff42`→`5943420`, 4 bindings, all reconciled clean, dispatch loop alive, 0 errors. This activated the whole merged #047–#054 batch + the #050 RPC fix for ALL bindings (pi one-shot bindings unaffected on dispatch; #052 question-park prompt + #054 wake sentinel now live everywhere; Claude resume reachable).
- Finding 1 (deploy gap, FIXED): live `podium.db` was at alembic `0006`; cutover code needs #047's `0007` run columns. Every dispatch failed `table run has no column named agent_session_sha`. Backed up DB, `alembic upgrade head` (0006→0007), dispatch recovered. Lesson: a cutover with a migration MUST run `alembic upgrade head` — the systemd restart does not.
- Soak: filed a real Podium smoke issue (#12) on rpcsoak. Dispatch → `pi_rpc_dispatch ... cwd=/home/james/rpc-soak` → completed ~34s, `timed_out=false`, `exit=0`, `verdict=done`, clean summary, `agent_session_sha` recorded, agent committed `notes/rpc-soak-check.md` (`8c0dd2e`). Full path scheduler→RPC adapter→verdict PROVEN.
- Finding 2 (by-design, NOT a bug): `verdict=done` parks the issue in `in_review` ("awaiting review", `scheduler.py:1907-1994`), not terminal `done`; agent never auto-closes (coding-binding model). `reason=agent-marker-review` = "a result marker was emitted", `in-review` is the destination for both done and review. Investigated per operator request; no fix needed.
- Outputs: ADR-0010 `proposed`→`accepted` (disk; slice-a-soak note); claim **C-0190**; updated C-0189 + the #050-landed claim + C-0178-adjacent pointers. Live `podium.db` migrated 0006→0007 (backup kept).
- Teardown (operator chose): rpcsoak binding removed from `bindings.yml` + Podium DB, repo + smoke issue removed, restart to unload. `pi_mode: rpc` NOT enabled on any real binding (separate operator decision). No secrets / `.env` read.

## [2026-06-14] feat + flip | #058 orphan-reaper/probe; all bindings → pi_mode: rpc

- Actor: Claude (operator: "flip now, finish issues later" → chose land-reaper-then-flip, then all-three-at-once).
- Reaper/probe (commit `44e72c9`): `reap_orphan_rpc_processes()` (boot sweep, SIGKILLs leftover `pi --mode rpc` whose `/proc` start-time matches the launch-recorded pidfile) + `verify_pi_rpc_support()` (boot `get_state` probe, only when a binding is rpc). `run_pi_rpc_agent` writes/removes `<runtime>/rpc/<pid>.pid`. Wired into `run_bindings_loop`.
- Two real-pi facts faked tests missed (verified live, mirrors the #050 lesson): pi masks argv (cmdline = `pi`) → start-time guard not cmdline; pi `--mode rpc` ignores SIGTERM → reaper uses SIGKILL (orphan died `returncode -9`).
- Tests: `tests/test_agent_runner.py` +reaper/probe/pidfile (29 tests, 1 skipped real-pi); #050 suite 173 passed. ruff clean.
- Flip: `bindings.yml` homelab/trading/symphony all `pi_mode: rpc`; config validated; restart healthy (`code_sha 44e72c9`, 3 bindings, `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, reconciles clean, 0 errors). All pi dispatch is now RPC; Claude-routed issues still tmux.
- Outputs: claim **C-0191**; #058 note (reaper+probe slice done). Pending for operator: #055, #056/#057 (live steer), #058 remainder.
- Guardrails: per-run timeout already in #050; steer-queue cleanup deferred to #056. No secrets / `.env` read.

## [2026-06-14] ingest | #055 checkpointed exploration mode

- Source: Ralph #055 implementation (`.kanban/issues/055-checkpointed-exploration.md`) plus changed skill/prompt/test files.
- Change: added repo-local `checkpointed-exploration` Skill; `prompt_renderer` now prepends a bounded-step/Question-Park directive only when that Skill is selected, including resume prompts; `symphony-workflow-author` now tells future Workflow authors to document the Skill for incremental investigation.
- Verification: issue command `uv run pytest tests/test_prompt_renderer*.py tests/skills/ -q` passed; full `uv run pytest -q` passed (762 passed, 2 skipped); `uv run ruff check` passed on touched Python files; touched-file LSP diagnostics clean; fresh review returned `RALPH_REVIEW: PASS`.
- Wiki updates: `concepts/session-resume-continuity.md`, `analyses/adr-0009-session-resume-continuity.md`, `index.md`, `ROUTING.md`, and claim **C-0192** updated.
- No secrets / `.env` read.

## 2026-06-14 — session-update: run-log size decouple + fly-out comments/context/run-summary dedup
- Source: this session (grill → implement → restart → wiki). Raw capture `wiki/raw/sessions/2026-06-14-flyout-dedup-and-run-log-cap.md`; scheduler commit `e0c02b4` (live `code_sha=e0c02b4`); frontend changes uncommitted at capture.
- Inputs: operator report that the issue fly-out comments tab ≈ context tab and the run-detail summary row is a third copy, plus the run-log pane showing only `## stdout … [output truncated]`.
- Findings: for `pi_mode: rpc` bindings the agent's stdout is assistant `text_delta` prose only (`_assistant_delta`, `agent_runner.py:888`) = the `SYMPHONY_SUMMARY` block, fanned into `comments_md`/`context_md`/`run.summary`; the run log shared the 2 KB `_sanitize_report` bound with `context_md`, so it only kept a 2 KB tail (write-time truncation).
- Change: (1) frontend display-only — `IssueFlyout.tsx` dropped the context tab + orphaned `MarkdownEditor`, `RunDetailPanel.tsx` dropped the run-summary row; (2) `scheduler.py` decoupled the run-log cap — `LOG_MAX_BYTES=1_048_576`, `_sanitize_report(..., max_bytes=…)`, `_finish_run_record` takes `secrets` and logs raw `result` streams; comment/context stay at 2 KB. `context_md` store untouched (re-feed floor + compaction).
- Verification: `uv run pytest` 776 passed / 2 skipped; restart verified `reconcile_startup_*` ×3, `dispatch_completed`, `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, zero errors.
- Wiki updates: new `analyses/podium-run-log-cap-and-flyout-dedup.md`, claims **C-0195** + **C-0196**, `CONTEXT.md` Issue Context glossary amended, `index.md`, `ROUTING.md`.
- Unresolved: frontend uncommitted (needs `next build` + restart / hot-reload); `npm run test:e2e` not yet run; ADR-0007 has no promoted wiki analysis page (candidate opportunity).
- No secrets / `.env` read.

## 2026-06-14 — session-update: pre-git pytest gate OOM-killed concurrent live agents (#14/#15) + harden hook
- Source: this session (review two failed `symphony`-binding issues → diagnose → fix hazard #3 → wiki). Raw capture `wiki/raw/sessions/2026-06-14-pre-git-pytest-gate-agent-oom.md`.
- Inputs: operator report that two `symphony`-binding issues failed (#14 "Column changing", #15 "Inbox"); both Runs recorded `error connecting to /tmp/symphony-claude-*.sock`.
- Findings: that socket string is a `capture-pane`-after-death artifact (C-0197), not the cause. Both claude/opus agents (cwd = live repo) were SIGKILL'd (exit 137) within 1s at 14:09:08 UTC, `timed_out=false`, mid-work — no restart (`NRestarts=0`), no reap. Trigger: issue #15's agent committed a frontend-only change; the pre-git hook ran full `uv run pytest` but `uv` was off the dispatch PATH, so the agent hand-rolled an unbounded suite run in its live tmux session → resource exhaustion killed both agents (C-0198). Separately found issue #14's real bug: live `podium.db` `issue.state` CHECK omits `'archived'` despite `alembic_version=0007` — a new stamp-vs-run drift extending C-0145, undetected because C-0147's guard only checks missing columns not CHECK diffs (C-0199, unfixed).
- Change: hook-only fix to `.claude/hooks/pre-git-checks.sh` (James chose surgical over worktree/MemoryMax) — (1) prepend `~/.local/bin` to PATH so `uv` resolves in-hook; (2) gate pytest on `changed_py` = staged `*.py` (commit) ∪ `*.py` in `@{u}..HEAD` (push). Live immediately (PreToolUse re-reads script); no service/DB change.
- Verification: `bash -n` clean; gate decision verified across frontend-only commit (skip), Python staged (run), Python in unpushed commits (run), non-Python push (skip); `uv` resolves under simulated systemd default PATH.
- Wiki updates: new raw capture + `analyses/pre-git-pytest-gate-agent-oom.md`, claims **C-0197/C-0198/C-0199**, pre-git bullet in `analyses/claude-code-harness-profile.md` updated (cited), `index.md`, `ROUTING.md`.
- Unresolved: #1 archive CHECK drift (rebuild `issue` per 0004 DDL) not applied; #2 issue #15's completed frontend edits sit uncommitted in the live tree; detection gap in C-0147 (CHECK drift); residual RAM risk from two concurrent Python commits (worktree/MemoryMax descoped).
- No secrets / `.env` read.

## 2026-06-14 — session-update: real root cause of Claude agent socket deaths (corrects OOM) + fixes landed
- Source: this session (a third failure, #17 "Archive", triggered re-investigation → root cause → fixes → wiki). Raw capture `wiki/raw/sessions/2026-06-14-claude-agent-socket-reap-root-cause.md`.
- Inputs: operator reported #17 also failed with `error connecting to ...sock`. Single agent, no concurrency, ~20 GiB free.
- Findings: OOM hypothesis (C-0198) DISPROVEN. Real cause (C-0200): `main.run_bindings_loop`→`run_dispatcher` calls the real `reap_orphan_claude_sockets()`/`reap_orphan_rpc_processes()`; three `tests/test_main.py` tests drive `run_bindings_loop` without stubbing them, so any `uv run pytest -q` reaps live `/tmp/symphony-claude-*.sock` → kills the running Claude agent's own socket. Proven via a sentinel tmux socket killed by the full suite (777 passed) and bisected to those tests; pi (#16, RPC) and subset runs unaffected. Also: #17's agent had authored the correct archive fix (migration 0008) before dying.
- Change: (1) `tests/conftest.py` autouse `_no_real_orphan_reap` fixture neutralising both reapers — commit `f096476`, sentinel survives full suite after fix; (2) committed #17's archive fix (migration `0008_fix_issue_archived_check` + `INITIAL_REVISION`→0008 + `test_upgrade_repairs_stale_archived_check`) — commit `b26f31f`. Pre-git hook change (`c2c6187`) kept as hygiene only.
- Verification: `uv run pytest -q` 777 passed / 2 skipped twice (pre/post fix); targeted `tests/test_alembic_baseline.py` 3 passed; sentinel-socket experiment before/after.
- Wiki updates: new raw capture; analysis `pre-git-pytest-gate-agent-oom.md` corrected (OOM marked disproven, real cause appended); claim **C-0200** added, **C-0198** corrected, **C-0199** marked fix-landed; `index.md`, `ROUTING.md`.
- Apply (done, same session, James-approved): stopped `podium-api` → backed up `podium.db.bak.pre-0008.20260614-151731` → `uv run alembic upgrade head` (0007→0008) → started `podium-api` clean. Verified live `alembic_version=0008`, `issue.state` CHECK includes `'archived'`, BEGIN/ROLLBACK archive UPDATE accepted, 5 rows intact, API healthy (401). Archive bug resolved live.
- Unresolved: C-0147 CHECK-drift detection gap (ensure_schema compares revision + columns, not CHECK DDL); defence-in-depth: scope `reap_orphan_claude_sockets` to the current run/PID or a service-only guard; #2 issue #15's frontend edits + `web/frontend/tests/inbox.spec.ts` working-tree change still uncommitted.
- No secrets / `.env` read.

## 2026-06-14 — session-update: board drag-to-column issue moves (#18 follow-up)

- Inputs: this session implemented drag-to-column on the Podium Kanban board (commit `2e75d83`), the unimplemented half of issue #18. Started from `a4ea162` (handoff `/tmp/handoff-TNpd15.md`).
- Findings: `KanbanBoard` previously wrapped a placeholder `<DndContext>` with no handlers. Board cards come from the `["issues", binding]` React Query cache (polling + `issue.updated` WS upsert). Server `patch_issue` applies no run-state gating for `state` (only archive teardown / done FF-merge are state-conditional), so no card needs to be drag-disabled. `@dnd-kit/utilities`/`sortable` not hoisted/installed → used the DragOverlay pattern (no transform helper).
- Change: `IssueCard` gained optional drag props (renders plain when omitted); `KanbanBoard` got `PointerSensor` (5px activation preserves click-to-open), `useDroppable` columns (expanded + collapsed rail), `DragOverlay`, and an optimistic `patchIssue(id,{state})` mutation against `["issues",binding]` with rollback. New e2e `web/frontend/tests/board-dnd.spec.ts`.
- Verification: `npx tsc --noEmit` clean; `npx playwright test board-dnd.spec.ts` 2 passed; related board specs green except pre-existing `board.spec.ts:4` backdrop-click failure (reproduced with changes stashed → unrelated, not fixed).
- Wiki updates: new raw capture `wiki/raw/sessions/2026-06-14-board-drag-to-column.md`; promoted `analyses/podium-issue-archive-design.md` follow-up marked gap RESOLVED + frontmatter sources/date bumped; claim **C-0201** added; `index.md` row + `ROUTING.md` Podium Web UI keywords updated.
- Outdated-source check: the 2026-06-14 #18 follow-up bullet on the archive-design page (which flagged the gap) is now superseded by the resolution bullet directly beneath it; both retained per provenance rule. No other cited sources drifted.
- Not deployed: frontend committed only; podium-web needs `deploy.sh` rebuild + restart (ask James). Unrelated `claude_runner.py` working-tree change left untouched.
- No secrets / `.env` read.

## 2026-06-14 — session-update: PID/start-time ownership guard for the Claude socket reaper (C-0200 follow-up)

- Inputs: this session implemented the defence-in-depth follow-up flagged in C-0200. Started from `a4ea162` (handoff `/tmp/handoff-6c1CNA.md`). Goal: make `reap_orphan_claude_sockets` itself refuse to kill a live-run socket regardless of caller, on top of the already-landed `tests/conftest.py` fix (`f096476`).
- Change (`claude_runner.py`): dispatch now records a sidecar pidfile `<runtime>/claude/<namespace>.pid` = `"<server_pid> <start_time>"` (`_register_claude_run` → `_claude_server_pid` via `display-message -p '#{pid}'`, `start_time` from `agent_runner._pid_start_time`); removed on teardown via new `ClaudeRunCleanup.pidfile_path`. The reaper skips any globbed socket whose sidecar names a live, start-time-matching pid (`claude_socket_skipped_live`) and reaps only true orphans (missing/dead/mismatch). Mirrors `reap_orphan_rpc_processes` (#058) and its injection surface (`pidfile_dir`/`environ`/`is_alive`/`read_start_time`), but inverts the keep/kill decision to protect alive+match. Boot-sweep purpose preserved (dead-server sockets still cleaned).
- Tests (`tests/test_claude_runner.py`): added live-owned-skip, dead-owner-reap, start-time-mismatch-reap, `_register_claude_run` write/omit, and cleanup-removes-pidfile cases. `uv run pytest tests/test_claude_runner.py tests/test_main.py -q` → 41 passed; `tests/test_agent_runner.py` 33 passed/1 skipped; full suite 782 passed/2 skipped, only the known-flaky `test_two_sqlite_writers_succeed_without_busy_errors` failed in the batch (passes in isolation, unrelated). `ruff check`/`format` clean.
- Wiki updates: analysis `analyses/pre-git-pytest-gate-agent-oom.md` gained a "Defence-in-depth" section; claim **C-0202** added; C-0200 follow-up marked RESOLVED (pointer to C-0202); `index.md` row + `ROUTING.md` keywords updated.
- Outdated-source check: C-0200's follow-up note (which flagged the gap) is now superseded by the resolution pointer; retained per provenance rule. No other cited sources drifted.
- Not restarted/committed at time of writing: live scheduler runs old code until a human-approved `symphony-restart`. No secrets / `.env` read.

## 2026-06-14 — session-update: ADR-0011 WORKFLOW.md is infra-only autonomy policy
- Inputs: `/grill-me` design pass on the cli-vs-infra split James perceived (Symphony grew from homelab infra ticketing into a cli-first issue tracker). Resolved the split onto the existing `binding_type` axis and produced ADR-0011, then implemented it. Raw capture: `wiki/raw/sessions/2026-06-14-workflow-md-infra-only.md`.
- Decisions: `WORKFLOW.md` is infra-only autonomy policy — mandatory for `infra`, *ignored* (not optional) for `coding`. It is autonomy instruction, not safety; safety/repo conventions are the bound repo's responsibility via native `CLAUDE.md`/`AGENTS.md`, and Symphony stays narrow (at most a bind-time *flag*). `binding_type` value names stay `coding`/`infra`; "cli" is product framing only.
- Code (`prompt_renderer.py`): `render_prompt` skips `load_workflow` for `binding_type=="coding"` (`body=""`) and assembles a clean prompt with no leading blank when the body is empty. `WORKFLOW.md` deleted from the `symphony` and `trading` repos (code change landed first to avoid `workflow-missing`).
- Tests: added `test_coding_binding_ignores_workflow_md` + `test_coding_binding_renders_without_workflow_file` (`tests/test_prompt_renderer_podium.py`); flipped coding-prompt assertions in `tests/test_trading_podium_dispatch.py`, `tests/test_engine_against_podium.py`, `tests/test_dispatch_compaction.py` to "WORKFLOW body absent". Full suite `uv run pytest -q` → 786 passed, 2 skipped.
- Skills: `symphony-onboard-project` branches on `binding_type` (infra → `symphony-workflow-author`; coding → skip + flag missing native config); `symphony-workflow-author` now infra-only, refuses coding bindings (description + body updated). `symphony-binding-scaffold` unchanged. `tests/skills/test_onboard_project.py` + `tests/skills/test_workflow_author.py` pass.
- Docs/wiki: ADR `docs/adr/0011-workflow-md-infra-only.md`; `CONTEXT.md` Workflow term rewritten inline; analysis `analyses/adr-0011-workflow-md-infra-only.md` (promoted); claims **C-0203**, **C-0204** added; **C-0005** superseded (mandatory-for-every-binding), **C-0029/C-0030** superseded (trading WORKFLOW.md deleted); `entities/workflow-trading.md` marked SUPERSEDED (file deleted), `entities/workflow-homelab.md` noted infra-only-but-active; `index.md` + `ROUTING.md` updated.
- Outdated-source check: `wiki/raw/workflow-trading.md` is now an orphaned pre-deletion snapshot of a deleted file; retained per provenance rule (cited by superseded claims). `wiki/raw/symphony-context.md#24` (source of C-0005) predates the infra-only split.
- Not restarted/committed at time of writing: live scheduler runs old code until a human-approved `symphony-restart`. No secrets / `.env` read.

## 2026-06-15 — session-update: trading binding offboard (purge)

- Inputs: `/symphony-offboard-project trading` session (this conversation) + live command outputs (pre-flight SQL, `remove_podium_binding` result, restart journal).
- Action: offboarded the `trading` Podium binding in **purge** mode (James chose purge over default archive; 1 issue + 1 run history disposable). `remove_podium_binding("trading", purge=True)` → `db_action='deleted'`, `deleted_issue_count=1`, `deleted_run_count=1`, `removed_from_bindings_yml=True`. James-approved `symphony-restart` (PID 988767, `code_sha=48ca8c2`, 05:17:20 UTC) → live binding set now **2: homelab, symphony**; restart healthy (reconcile pair per binding, `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, dispatch loop alive, 0 errors).
- Outputs: raw capture `wiki/raw/sessions/2026-06-15-trading-binding-offboard.md`; claim **C-0212** added; `entities/binding-trading.md` given an OFFBOARDED banner (frontmatter `updated`→2026-06-15, source + `offboarded`/`removed` tags added); `index.md` trading row + `ROUTING.md` Bindings keywords updated.
- Reconcile: complements C-0207 (offboard umbrella) and C-0206/C-0208 (purge path + FK-defer fix) with the first live purge exercise. No claim superseded (binding-trading was already historical post-#023d). `wiki/raw/bindings.yml` snapshot remains a pre-removal historical source.
- Unresolved: `CLAUDE.md` "Live bindings" table still lists `trading` (stale; not corrected in this wiki-only pass — James scoped to "update wiki"). No secrets / `.env` read.

---

## [2026-06-15] session-update | Podium web "client-side exception" = C-0110 hazard recurrence

- Actor: agent
- Inputs: operator report "Application error: a client-side exception has occurred"; diagnosis via `systemctl show podium-web.service`, `.next` mtimes, per-chunk `curl` status; James-approved `sudo systemctl restart podium-web.service`.
- Outputs: raw capture `wiki/raw/sessions/2026-06-15-podium-web-stale-build-client-exception.md`; claim **C-0213** added (extends C-0110); `analyses/podium-frontend-deploy-cosmetics.md` got a "Live recurrence 2026-06-15" note + source + `updated`→2026-06-15; `index.md` analysis row + `ROUTING.md` Operations keywords updated.
- Notes: Root cause already documented (C-0110 + analysis) — this is a live production recurrence (bare `next build` bypassed `deploy.sh`) with a NEW symptom string (client-side exception / app-router-chunk-400 hydration failure vs prior "Checking session…" hang) and confirmation that restart-alone fixes it when a valid on-disk `.next` exists. No claim superseded. No secrets read.
- Unresolved: `deploy.sh` not consistently used for frontend rebuilds (recurrence proof) — consider a guard against bare `next build` on the live dir. File-browser feature (`FileBrowser`/`FileEditor`/Monaco/`/[binding]/files`) went live via the restart but is still uncommitted — confirm intended.

## [2026-06-15] session-update | ADR-0012 Remote Bindings (SSH-exec) + first config slice — Issue #27

- Actor: agent (grill-me design dialog, unattended Symphony run on Issue #27)
- Inputs: Issue #27 "add other LAN systems to Podium"; operator approvals ("proceed with SSH exec remote binding", "include a host badge in proceed"); offered test host `itadmin@100.95.224.218`; read-only probe of that host; codebase reads (`agent_runner.py`, `config.py`, `web/api/schema.py`, `bindings.yml`); live `systemctl show` of `podium-api` + `symphony-host` env + `ss -tlnp`.
- Outputs: new `docs/adr/0012-remote-binding-ssh-exec.md` (status `accepted`); new `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` (promoted); claim **C-0214** added; `index.md` analysis row + `ROUTING.md` Design/ADR Pages+Keywords updated. Code: `config.py` gained `RemotePolicy`, `ProjectBinding.remote`/`is_remote`, `_remote_from_mapping` (additive `remote:` schema, no dispatch wiring); 3 new tests in `tests/test_config.py`; `tests/test_config.py` green (42 passed).
- Notes: Decision = SSH-exec Remote Binding behind the `AgentAdapter` seam, NOT a deployed daemon (rejected the operator's "symphony-remote copied onto device" framing). Load-bearing finding = Podium API is loopback-only (`127.0.0.1:8000`), so remote agent callback uses an SSH `-R` reverse tunnel rather than LAN-exposing the API (probe from `n8n` to the API timed out, confirming). Host probe: SSH key auth already works; pi/claude/git/tmux all present on `n8n`. No live behavior change, no service restart, no tracker mutations.
- Unresolved: build remaining slices — `RemoteAgentAdapter` (ssh-exec + `-R` tunnel + env forward), dispatch wiring (`main.py`/`RoutingAgentAdapter`), host-badge UI (likely a `binding` column + chip in the card/fly-out), and a smoke test against `n8n`. `bindings.yml` not yet given a `remote:` entry. `CLAUDE.md` "Live bindings" table still lists only homelab/symphony (no remote binding registered yet).

## [2026-06-16] session-update | offboard skill seed-dependent test cleanup

- Actor: agent
- Inputs: operator reply to continue Run #51 with permission; `.claude/skills/symphony-binding-remove/SKILL.md`; `.claude/skills/symphony-offboard-project/SKILL.md`; `web/api/seed.py`; seed-dependent tests retargeted from removed `trading` binding to surviving `symphony` binding.
- Outputs: updated `wiki/analyses/symphony-skills-index.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0215 added).
- Notes: Captured new teardown process checkpoint: after a `bindings.yml` removal, scan for removed-binding references and retarget only seed-dependent tests to a surviving same-type binding, leaving self-contained tmp-DB/`_bindings_override` tests alone. Verification: focused skill/API tests passed (12 passed) and full `uv run pytest -q` passed (828 passed, 2 skipped). No secrets, no env files, no DB writes, and no service restart.

## [2026-06-16] update | Issue #27 — RemoteAgentAdapter implemented (ADR-0012 dispatch slice)

- Actor: agent
- Inputs: Podium issue #27 ("Other systems") thread; `docs/adr/0012-remote-binding-ssh-exec.md`; `agent_runner.py` dispatch path (`run_agent`, `AgentAdapter`/`RoutingAgentAdapter`, `_agent_env`); `main.py` `_build_binding_runtime`; existing `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` + C-0214.
- Outputs: updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` (Status of the build + sources + date); updated `wiki/CLAIMS.md` (C-0214 → two slices landed, v1 helper-shipping gap).
- Notes: Cleared #27 commit blocker (full suite already green — `web/api/tests/conftest.py` fixture had been repointed `trading`→`symphony`). Committed config slice `80c5bb4` and dispatch adapter slice `ca01062` (`run_remote_agent` + `RemoteAgentAdapter`: ships `plane` helper to remote `/tmp/symphony-remote-<issue>`, `ssh -R <port>:127.0.0.1:<port>` reverse tunnel, pi by basename, pi-only routing; 12 new tests). Full `uv run pytest -q` green (840 passed, 2 skipped). v1 gap surfaced: `run_agent`'s `plane` helper rides a local temp-dir PATH, so the remote adapter must ship it per run for the callback to resolve. Remaining slices (host badge UI, `n8n` smoke) are gated on adding the `n8n` `remote:` entry to `bindings.yml` + a James-approved `symphony-restart`; not done. No secrets, no DB writes, no Plane/Podium mutation, no service restart.

## [2026-06-16] update | Issue #27 — live remote-binding validation + rollback (ADR-0012)

- Actor: agent
- Inputs: staged `n8n` remote binding (`itadmin@100.95.224.218`, `repo_path=/home/itadmin/itastack`) in `bindings.yml` + Podium `binding` row; `symphony-restart`; `symphony-binding-smoke n8n`; live journal for pid 2810668/2813435/2815352/2836504; `main.py`, `scheduler.py:635`, `prompt_renderer.py`.
- Outputs: updated `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` (Live validation section); updated `wiki/CLAIMS.md` (C-0214: live-validation finding + startup fix + open pipeline gap).
- Notes: End-to-end smoke against the live scheduler proved the `RemoteAgentAdapter` is necessary but not sufficient. (1) Startup crash-loop fixed (commit `dab2b45`): `_build_binding_runtime` ran the LOCAL `verify_pi_support` with a remote `repo_path` → `PermissionError` → crash; guarded behind `not binding.is_remote`. (2) Dispatch still blocked: issue #31 → `reason=workflow-missing` wrapping `PermissionError: /home/itadmin/itastack` from `_prepare_resume_candidate`→`resolve_code_sha`; the local-`repo_path` assumption recurs in worktree/compaction/landing. Root: `/home/itadmin` is mode 750 on aidev so `james` can't traverse it. Operator chose to roll back the live binding: removed `bindings.yml` `n8n` entry, deleted the Podium `n8n` `binding` row, archived smoke issue #31, restarted to known-good 3-binding state (code_sha `dab2b45`, all reconciled, dispatch alive, no errors). Committed code (config + adapter + startup guard) retained as foundation. Remaining pipeline work (remote-aware `resolve_code_sha`/worktree/compaction/landing) is a tracked follow-up on Issue #27 — NOT auto-dispatched. No secrets read; the only live mutations were the approved restart cycle and the binding/issue rollback rows.

## [2026-06-16] session-update | Claude refeed session-id collision (issue 27 runs 54/55)

- Actor: agent
- Inputs: `podium.db` run/issue rows for issue 27; `runs/54.log`, `runs/55.log`; journal `resume_skipped reason=sha-drift` + `claude_dispatch`/`agent_exited`; `claude_runner.py`, `session_continuity.py`, `scheduler.py`; live claude-CLI repro (`--session-id` collide vs `--resume`).
- Outputs: raw session capture `wiki/raw/sessions/2026-06-16-claude-refeed-session-id-collision.md`; promoted analysis `wiki/analyses/analysis-session-claude-refeed-session-id-collision.md`; claim C-0216; index Analyses row + ROUTING entries (Continuity & Session Resume, Executor / Agent). Code: commit `4521730` (`claude_runner.py` session_arg keyed on `transcript_file.exists()` + regression test).
- Notes: Runs 54/55 failed `claude_ready_timeout` because the deterministic per-issue transcript (from resumed runs 45-49) collided with the refeed's `--session-id` create (`Session ID already in use`, exit 1 → tmux server dies). Fix selects `--resume` vs `--session-id` by transcript existence, not the `resumed` flag; `resumed` still governs prompt content upstream. Non-destructive. Live in the running service (fixed file on disk before the 02:40 restart) but not yet exercised by a real refeed. Full `uv run pytest` 841 passed, 2 skipped. No secrets, no DB/Plane/service mutation in the wiki pass; issue 27 recovery de-scoped per operator. Open: push decision for 8 unpushed commits on `main` (operator-owned).

## [2026-06-16] session-update | ADR-0012 v1 remote-binding dispatch pipeline (RepoHost seam) + live n8n smoke passed

- Actor: agent
- Inputs: plan `plans/remote-binding-dispatch-pipeline.md` + sidecar `plans/.remote-binding-dispatch-pipeline.state.yml` (build_audits + live_smoke); new code `repo_host.py`, `ssh_support.py` + edits to `code_version.py`, `config.py`, `scheduler.py`, `agent_runner.py`, `main.py`, `web/api/main.py`; `runs/56.log` + `podium.db` Issue 32/Run 56; journal `symphony-host.service` 2026-06-16 07:06–07:12 (`symphony_started bindings=4`, `remote_repo_reachable binding=n8n sha=7f91558`).
- Outputs: raw session capture `wiki/raw/sessions/2026-06-16-remote-binding-dispatch-pipeline.md`; promoted-page maintenance edit `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` (new "Resolution 2026-06-16" section + frontmatter sources/tags); claim **C-0217** (supersedes the pipeline-deferred/rolled-back portion of **C-0214**, which got a supersession note); `wiki/index.md` adr-0012 row refreshed (date 2026-06-16); `wiki/ROUTING.md` ADR branch keywords expanded (RepoHost seam, repo_host_for, ssh_support, remote invariants, n8n live, C-0217).
- Notes: Built via `/dev-build` (Strategy A: seam + config invariants, not scattered guards). Closes the "adapter necessary but not sufficient" gap. n8n kept as a permanent 4th live binding (homelab, symphony, dotfiles, n8n) per operator. pi wave audits: wave 1 passed, wave 2 `audit_skipped` (reviewer_timeout — pi/gpt-5.5 hung; builder self-validated), wave 3 passed (0 critical / 0 warning / 2 note via inlined-diff + `--no-tools` retry). `uv run pytest -q` → 874 passed, 2 skipped (+32; new `tests/test_repo_host.py`, `tests/test_ssh_support.py`); ruff clean. No secrets written; no DB/Plane mutation in the wiki pass. Open: changes uncommitted on `main` (operator commit pending, mixed with an unrelated file-browser feature); v2 follow-ups (remote worktrees/compaction/skill, host badge UI); stale `CLAUDE.md` "Live bindings" table (lists homelab+trading; trading offboarded per C-0212, n8n now live).

## [2026-06-16] session-update | ADR-0012 remote-binding host label (Issue 34) landed + deployed live

- Actor: agent
- Inputs: Issue 34 ("host binging name" — show "n8n — itastack" not bare "n8n") + operator replies (name+repo only, no IP, skip flyout v1; then "still not showing" after restarting wrong service); committed code `ad00b0b`; live systemd state (`podium-api.service` 8090, `podium-web.service` 8091 both stale at 2026-06-15 start); `web/frontend/deploy.sh`.
- Outputs: claim **C-0218** (Issue 34 host label landed + deploy topology lesson); promoted-page edit `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` (new "Host label landed 2026-06-16 (Issue 34)" section + frontmatter sources/tags issue-34/host-label/deploy); `wiki/index.md` adr-0012 row summary refreshed; this log entry.
- Notes: Root cause of "names haven't changed" = the change spans `podium-api` (serves new `/api/bindings` `is_remote`/`repo_name` JSON) + `podium-web` (Next.js prebuilt bundle, needs `deploy.sh` rebuild+atomic-swap), but the operator restarted `symphony-host.service` (the scheduler), which serves neither. Fixed by `systemctl restart podium-api.service` (now 15:49 UTC) + `web/frontend/deploy.sh` (build then stop/swap/start podium-web, now 15:52 UTC, root=200). Live helpers confirm `is_remote(n8n)=True`/`repo_name=itastack`; full visual confirm (hard-refresh) pending operator. Code path: `web/api/main.py` `list_bindings` enrichment + `web/frontend/{lib/api.ts,components/Sidebar.tsx,app/page.tsx}` " — {repo_name}" when `is_remote`. Test `test_bindings_endpoint_surfaces_remote_repo_name`. Styled host chip still deferred (operator dropped IP for v1). No secrets read; podium-api/web restart + frontend deploy were the only live mutations (deploy.sh does a ~3s atomic podium-web stop/swap/start with `.next.prev` rollback). Git tree clean after deploy.

## [2026-06-16] session-update | Binding scaffold writes `remote:` block (Issue 34 follow-up)

- Actor: agent
- Inputs: operator question "is there a remote binding skill? can we make sure that this happens on future remote bindings when setup?"; `.claude/skills/symphony-binding-scaffold/SKILL.md`, `skill_migration.py` (`scaffold_podium_binding`), `config.py` (`_remote_from_mapping` + remote v1 constraints), `.claude/skills/symphony-onboard-project/SKILL.md`.
- Outputs: claim **C-0219**; code commit `60f5475` (`skill_migration.py` remote params + `bindings.yml` `remote:` block write + v1 validation; `tests/skills/test_binding_scaffold.py` 2 new tests; SKILL.md doc); promoted-page edit `wiki/analyses/adr-0012-remote-binding-ssh-exec.md` (new "Scaffold writes the `remote:` block" subsection); this log entry.
- Notes: No dedicated remote-binding skill exists — remote bindings are made via `symphony-binding-scaffold` (umbrella `symphony-onboard-project`). The C-0218 "name — repo" label is data-driven (`/api/bindings` reads `bindings.yml` live), so display was already automatic; the only gap was that scaffold had no remote inputs (live `n8n` block was hand-added). Now `PodiumBindingScaffoldRequest` takes `remote_host`/`remote_user`/`remote_identity`; scaffold writes `remote: {host, user, identity?}` and enforces C-0217 v1 invariants (`coding`/`pi`/`one-shot`) with early `ValueError`. `symphony-onboard-project` inherits it (delegates to scaffold step 1, no edit). 28 skill tests pass. No live mutations: pure repo code/skill/test/wiki edits; `bindings.yml` untouched.

## [2026-06-16] session-update | Flyout comment ordering → oldest-first single-blob render

- Actor: agent
- Inputs: operator grill session "can we talk about the issue flyout comment display and ordering?" → decisions to (1) flip newest-first to oldest-first, (2) remove the per-entry split (option A — single markdown blob), (3) auto-scroll to bottom keyed on `issueId`. Source files: `web/frontend/components/IssueFlyout.tsx` (`CommentsThread`), `web/frontend/tests/{flyout-tabs,steer-flyout}.spec.ts`, `web/frontend/tests/{global-setup.mjs,fixtures.ts}`.
- Outputs: raw session capture `wiki/raw/sessions/2026-06-16-flyout-comment-ordering.md`; claims **C-0220** (oldest-first single-blob render + issueId-keyed auto-scroll; removes `splitCommentEntries`/`#{1,6}` shredding) and **C-0221** (trading-bound e2e specs broken by trading offboarding); promoted-page follow-on section + frontmatter/source bump on `wiki/analyses/podium-run-log-cap-and-flyout-dedup.md`; index row + ROUTING keyword updates; this log entry.
- Notes: Display-only frontend change — `comments_md` storage/append-order/API untouched. Verified `tsc --noEmit` clean and `steer-flyout` specs pass (cover `view-comments_md`). `flyout-tabs:3` failed but is PRE-EXISTING and unrelated: confirmed identical on clean HEAD (stash + re-run). Root cause = `global-setup.mjs` mirrors the live `bindings.yml`, which no longer has `trading` after the 2026-06-15 offboarding (C-0212), so the `/trading` board + seed card never render. Change uncommitted; live UI needs `web/frontend/deploy.sh` (prebuilt bundle), not a plain restart (cf. C-0218). Open follow-up: reseed the trading-bound e2e specs against a live binding or add a fixture-only trading binding.
- Unresolved: trading-bound e2e specs (`flyout-tabs`/`board`/`run-detail`) remain red until reseeded; flyout change not yet deployed/committed.

## [2026-06-16] session-update | e2e binding fixture decoupled from live bindings.yml (C-0221 resolved)

- Actor: agent
- Inputs: operator "reseed against the live binding now"; full e2e run (17 failed/31 passed) → root cause = `global-setup.mjs` mirrors live `bindings.yml`, `trading` offboarded. Files: `web/frontend/tests/global-setup.mjs`, `web/api/seed.py`, `web/api/schema.py`, `web/frontend/components/IssueFlyout.tsx`, `web/api/main.py`.
- Outputs: code commit `b3e0f58` (synthesize fixture-only `trading` binding in `global-setup.mjs`); updated claim **C-0221** to `resolved`; updated `wiki/analyses/podium-run-log-cap-and-flyout-dedup.md` (e2e-drift section + follow-up); same-session addendum on `wiki/raw/sessions/2026-06-16-flyout-comment-ordering.md`; ROUTING keywords; this log entry.
- Notes: Decision **decouple over migrate** — operator picked the fixture-binding option after I surfaced that the breakage was 16 specs (not 3) and that migrating mutating specs (dnd/archive/dashboard) to a shared homelab board would break `fullyParallel` isolation. Fix clones a local binding, forces `type=coding` (flyout 7-chip coding layout; infra adds 3 chips), drops `remote:`. No spec edits. Full suite 47 passed; lone miss = unrelated `new-issue` combobox keyboard flake (green in isolation).
- Unresolved: `new-issue.spec.ts:124` combobox keyboard-nav flake under full-suite parallelism (not investigated; passes alone). Flyout render change (C-0220) + this fix still uncommitted-to-remote / not deployed to live UI (needs `web/frontend/deploy.sh`).

## [2026-06-17] session-update | Root scheduler architecture review + Pi meta-review

- Actor: agent
- Inputs: `/architecture-review` over the root scheduler module (24 top-level `*.py`, ~11.6k LOC), per-finding operator triage; then `/dev-review-pi` (reviewer `openai-codex/gpt-5.5`, read-only verified) over the resulting artifact; operator "all five" (apply Pi corrections) + "update wiki". Evidence: `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`, `scheduler.py`, `main.py`, `agent_runner.py`, `plane_adapter.py`, `tracker_podium.py`, `tracker_adapter.py`, `web/api/main.py`, `bindings.yml`.
- Outputs: raw capture `wiki/raw/sessions/2026-06-17-root-scheduler-architecture-review.md`; promoted analysis `wiki/analyses/root-scheduler-architecture-review.md`; claims **C-0223** (all live bindings podium → Plane dormant), **C-0224** (review artifact/plan exists, not implemented), **C-0225** (Plane secret/helper shipped to Podium agents — near-term security cleanup); `index.md` Analyses row; new `ROUTING.md` section "Architecture review & refactor plan"; this log entry. Artifact itself revised per Pi review (L0-01 corrected → rename, L0-06 added, L6-02 split into Phase 5 + Phase 7, L3-01 reworded; tallies 40→41 / 28→29 accepted).
- Notes: **No source code modified** — the product is a proposal/plan artifact (`.rpiv/`, git-ignored). Two methodology principles recorded (M1 keep tested zero-consumer primitives that pair with an existing flow; M2 verify an unusual coupling's reason before fixing). Wise-decision keeps: engine→`web.api.db` (Podium is the web DB), `SymphonyConfig.__repr__` deny-by-omission, tuple returns, single-file `schedule.py`, standalone `plane_cli` Telegram. Pi meta-review caught one wrong finding (L0-01), one missed reflection cluster (`web/api` 4× `vars()`), and one security re-prioritization (Plane secret shipped to all-Podium agents) — all verified against source before applying.
- Unresolved: implementation not started (next: `/blueprint` per phase, Phase 1 first). Near-term security cleanup L6-02(a)/Phase 5: stop shipping `SYMPHONY_PLANE_API_KEY` + `plane` helper to Podium agents. Operator-gated: Phase 6 vocabulary migration touches the live `symphony-host.service` env contract; Phase 7 Plane-path removal needs a confirmed Plane sunset.

## [2026-06-17] session-update | Issue #069 scoped Plane cooldown to `_DispatchState`

- Actor: Ralph worker
- Inputs: `.kanban/issues/069-scope-cooldown-dispatchstate.md`; prior implementation commits `8fa5537`, `1fd292f`, `4b86fd9`; live restart verification on `symphony-host.service`; `scheduler.py`; `tests/test_scheduler.py`.
- Outputs: updated promoted analysis `wiki/analyses/root-scheduler-architecture-review.md`; updated index/routing entries; claim **C-0232** and supersession note on **C-0051**; this log entry.
- Notes: Issue #069 landed T5 per-binding isolation. `_PLANE_COOLDOWN_UNTIL` and test-only scheduler globals were removed; cooldown helpers now read/write only `_DispatchState.cooldown_until`; tests assert a Plane 429 recorded on one `_DispatchState` does not cool down another. Verification: `uv run pytest` passed (887 passed, 2 skipped); touched-file LSP diagnostics clean; fresh Ralph review passed; live restart verified `symphony_started code_sha=877438f`, `rpc_orphan_reap_done`, `pi_rpc_probe_ok`, `reconcile_startup_*`, `run_reconcile_*`, and `dispatch_completed` with no matched errors.

## [2026-06-17] session-update | Issue #073 tracker-neutral config env dual-read

- Actor: Ralph worker
- Inputs: `.kanban/issues/073-config-tracker-neutral-dual-read.md`; `config.py`; `tests/test_config.py`; implementation base `6ab45266bce534f3ea3023d44e316ade5982ad91`.
- Outputs: code commit `2da1986` (`config.py` tracker-neutral env aliases/accessors + config tests + issue/progress updates); updated promoted analysis `wiki/analyses/root-scheduler-architecture-review.md`; updated index/routing entries; claim **C-0234**; this log entry.
- Notes: Initial review diff from the supplied base to `HEAD` was empty, so the actionable review loop implemented the missing slice. `SYMPHONY_TRACKER_*` values win when both neutral and legacy names are set; legacy `PLANE_*` names remain supported for live unit/env back-compat. No `/home/james/symphony-host.env` or systemd unit edit occurred. Verification: `uv run pytest -q` passed (889 passed, 2 skipped); `uv run ruff check config.py tests/test_config.py` passed; touched-file LSP diagnostics clean; `git diff --check HEAD^ HEAD` clean; secret scan found no non-allowlisted added secret patterns.

## [2026-06-17] session-update | Issue #082 lock-gated Claude boot reaping

- Actor: Ralph worker
- Inputs: `.kanban/issues/082-claude-boot-reaper-lock-gated.md`; `claude_runner.py`; `main.py`; `tests/test_claude_runner.py`; `tests/test_main.py`; implementation base `918f74172335c3a0de3b33905891da47fbfc343c`.
- Outputs: implementation commit `e17c0ce`; review status commit `70df9c0`; done/progress commit `03901b0`; updated promoted analysis `wiki/analyses/root-scheduler-architecture-review.md`; updated index/routing entries; claim **C-0237**; this log entry.
- Notes: Persistent Claude sockets are now scheduler-lifetime warm sessions only. `run_bindings_loop` acquires and holds the configured lock when possible, passes `lock_confirmed` to `reap_orphan_claude_sockets`, and the reaper bypasses the pid/start-time live guard only for persistent sockets with confirmed lock ownership. Without lock confirmation, persistent sockets keep the guard; nonce sockets are guarded in both modes. Verification: `uv run pytest tests/test_claude_runner.py tests/test_claude_persist.py` passed (58 passed); `uv run python -m py_compile claude_runner.py main.py` passed; `uv run pytest tests/test_main.py -q` passed (15 passed); ruff and touched-file LSP diagnostics clean; fresh review returned `RALPH_REVIEW: PASS`.

---

## [2026-06-18] session-update | claude_persist canary soak (#087) + steer-queue PrivateTmp fix

- Actor: Claude Code (operator-driven soak)
- Inputs: `.kanban/issues/087-MANUAL-canary-restart-soak.md`; live `symphony-host.service` + `podium-api.service`; Podium smoke Issue #45 (runs 81/82/83); `claude_runner.py`, `web/api/steer_queue.py`, `web/api/main.py`, `scheduler/__init__.py`; journal evidence.
- Outputs: new raw session capture `wiki/raw/sessions/2026-06-18-claude-persist-canary-soak-087.md`; updated promoted page `wiki/analyses/adr-0013-warm-claude-and-send-keys-steer.md` (Soak status now PASSED + deployment bug); claim **C-0242** added; **C-0240** soak-pending note amended; `wiki/index.md` ADR-0013 row + `wiki/ROUTING.md` Continuity keywords updated; this log entry. Non-wiki: `docs/adr/0013-...md` `soak:` line + consequence bullet, `.kanban/issues/087` (status done, ACs ticked, soak result) + `.kanban/issues/086` soak note, `CLAUDE.md` "Env locations" `SYMPHONY_RUNTIME_DIR`, `~/homelab/docs/runbooks/automation/symphony.md` failure pointer, two `runtime-dir.conf` drop-ins (+ `.bak.2026-06-18`).
- Notes: Soak PASSED on the live `symphony` binding — warm reattach (no 2nd ready-wait), steer landing next turn, reap on close all observed. Surfaced a real deployment bug: live steer/abort was accepted (HTTP 200) but never delivered because the steer queue (`$SYMPHONY_RUNTIME_DIR/steer`) was not shared between the `PrivateTmp=no` writer (`podium-api.service`) and the `PrivateTmp=yes` reader (`symphony-host.service`); affected pi RPC too. Fixed by `SYMPHONY_RUNTIME_DIR=/run/symphony` drop-in on both units. ADR-0013 stays `accepted`. Open follow-up: consider a code-side startup check for steer-queue visibility (invariant is currently unit-config-only). No `/home/james/symphony-host.env` values read.

---

## [2026-06-18] session-update | Issue #44 remote binding local coding parity

- Actor: Pi agent (Podium issue #44)
- Inputs: operator grill-me decision to make remote bindings match local coding binding parity; `agent_runner.py`; `scheduler/__init__.py`; `config.py`; `bindings.yml`; `skill_migration.py`; `docs/adr/0012-remote-binding-ssh-exec.md`; `CONTEXT.md`; remote/scaffold/config/scheduler tests.
- Outputs: remote bindings now require `pi_mode: rpc`; `n8n` binding changed from one-shot to rpc; remote dispatch runs SSH-piped `pi --mode rpc`, forwards Steering records, registers the local SSH process in the RPC pidfile registry, and ships selected preferred-skill directories to the remote temp dir before passing a remote `--skill` path; scaffold docs and validation updated; ADR-0012 and glossary updated; promoted analysis/index/routing updated; claim **C-0243** added; this log entry.
- Notes: Target is local coding binding parity, not a separate remote workflow. Remaining deferred parity gaps: remote Session Tail over SSH if needed for live remote session-file viewing, remote worktrees/merge/teardown, remote context compaction, branch dropdowns, and remote orphan sweeps beyond killing the local SSH process group. Verification: `uv run pytest tests/test_remote_agent.py tests/test_config.py tests/test_scheduler.py tests/test_dispatch_gate.py tests/skills/test_binding_scaffold.py -q` passed (231 passed); `uv run pytest tests/test_agent_runner.py tests/test_remote_agent.py -q` passed (51 passed, 1 skipped); full `uv run pytest` passed (926 passed, 2 skipped). No `/home/james/symphony-host.env` read.

---

## [2026-06-18] onboard | ai-web-chat local coding binding

- Actor: Claude Code (operator-driven `/symphony-onboard-project`)
- Inputs: `/home/james/ai-web-chat` (web chat app: chat-api, packages, has `CLAUDE.md`, no `AGENTS.md`); `bindings.yml`; `skill_migration.scaffold_podium_binding`; live `symphony-host.service`; smoke Issue #49 / Run 102.
- Outputs: new `ai-web-chat` binding row in `binding`/`binding_settings` (Podium SQLite) + `bindings.yml` entry (`type: coding`, `default_agent: pi`, `pi_mode: rpc`, `base_branch: main`, landing local). No entity page (routine local coding binding; follows `dotfiles`/`n8n` no-page precedent). Live set now 5 bindings. This log entry.
- Notes: `coding` type → skipped `symphony-workflow-author` (no `WORKFLOW.md`); repo has `CLAUDE.md` so no convention flag. Restart loaded `code_sha=12405d8 bindings=5`, all 5 `reconcile_startup_done`, `pi_rpc_probe_ok`, 0 errors. Smoke Run 102 succeeded (verdict `done`, exit 0, agent `pi` / provider `openai-codex` / model `gpt-5.5:high` from `models.yml`; ran `pwd`+`git status`, no code changes). Onboard restart also flushed concurrent-session Issue #44 WIP (remote coding parity: agent_runner/scheduler/config/skill_migration + n8n one-shot→rpc) live as commit `12405d8` after full suite passed (926 passed, 2 skipped). Note: `scaffold_podium_binding` re-serializes the whole `bindings.yml`, so the post-scaffold diff folds in any unrelated working-tree edits (here the in-flight n8n rpc change) — inspect carefully, do not assume a scaffold bug. No `/home/james/symphony-host.env` read.

---

## [2026-06-18] session-update | retire context_md re-feed floor + context compaction

- Actor: Claude Code (`/dev-build plans/retire-context-md-refeed-floor.md` → `/wiki-update`)
- Inputs: executed plan `plans/retire-context-md-refeed-floor.md` (27/27 impl, 12/12 tests); build state `plans/.retire-context-md-refeed-floor.state.yml`; code diff (10 files, +40/−692); `uv run pytest` → 917 passed, 2 skipped.
- Outputs: raw session capture `wiki/raw/sessions/2026-06-18-retire-context-md-refeed-floor.md`; new claim **C-0244**; superseded **C-0095/C-0096/C-0097/C-0098** (status→superseded, pointers to C-0244); drift note added to **C-0229** (web/api/main.py no longer imports build_binding_runtime/SymphonyConfig/maybe_compact/estimate_tokens; `_compact_issue_context` removed); `analyses/podium-026-context-compaction.md` status→`superseded` with RETIRED banner + Retirement section; `concepts/prompt-renderer.md` updated (context block removed, comments_md sole continuity surface); `index.md` podium-026 row marked RETIRED; `ROUTING.md` retirement keywords added; this entry.
- Notes: Durable contract change — `context_md` no longer injected into Podium prompts; automatic scheduler compaction + manual `/compact` endpoint + `context_compaction.py` removed; tracker `replace_context`/`context_compaction_settings` removed; `context_md` column/`IssueData` field/`append_context` + `binding_settings.context_compact_*` columns + revision `0002` kept dormant (no schema-destructive migration). Code NOT yet committed; no service restart. Wave-1 pi audit clean; wave-2 pi audit skipped (reviewer_timeout — pi-hang) mitigated by in-skill compatibility audit + full suite. No `/home/james/symphony-host.env` read.

## [2026-06-19] session-update | Remote binding gap walkthrough (grill-me) + SSH keepalive

- Actor: Claude Code (`/grill-me` "walk through the remote binding ... work through any gaps" → `/wiki-update`)
- Inputs: code reading of `config.py`, `main.py`, `scheduler/__init__.py`, `agent_runner.py`, `ssh_support.py`, `repo_host.py`, `session_continuity.py`, `bindings.yml`, live `systemctl show ... Environment` (`SYMPHONY_RUN_CAP=3`); ADR-0012 + `wiki/analyses/adr-0012-remote-binding-ssh-exec.md`.
- Change made: `ssh_support.ssh_base_args` now emits `-o ServerAliveInterval=15 -o ServerAliveCountMax=4` (idle-drop protection for the remote pi RPC channel); `tests/test_ssh_support.py` exact-argv assertions updated. `uv run pytest tests/test_ssh_support.py tests/test_repo_host.py tests/test_remote_agent.py -q` → 27 passed. **Uncommitted.**
- Outputs: raw session capture `wiki/raw/sessions/2026-06-19-remote-binding-gap-walkthrough.md`; new claims **C-0251** (serialize-per-remote-binding decision, shared-tree hazard, NOT implemented), **C-0252** (native resume can't engage for remote → cold re-dispatch; resume-over-SSH v2), **C-0253** (SSH keepalive implemented), **C-0254** (remote env is the host's job, contract reaffirmed); ADR `docs/adr/0012-remote-binding-ssh-exec.md` "Amendment 2026-06-19" section; `analyses/adr-0012-remote-binding-ssh-exec.md` gap-walkthrough section + `updated: 2026-06-19`; `index.md` ADR-0012 row updated; `ROUTING.md` keywords added; this entry.
- Notes: Scope decision — remote bindings are a growing capability, not a solo `n8n` demonstrator. **Open live hazard:** C-0251 (serialize per remote binding) is a decision only, not yet implemented; `n8n` `run_cap=3` can still put 3 `pi` processes in one remote working tree. Recommended next action. No `/home/james/symphony-host.env` read.

## 2026-06-19 — Issue 53: homelab WORKFLOW.md autonomy/safety scoping migration
- Actor: Claude Code (Symphony unattended run, issue 53; grill-me → audit → approved → execute).
- Inputs: `bindings.yml` (homelab is the only `infra` binding), `/home/james/homelab/WORKFLOW.md`, `/home/james/homelab/CLAUDE.md` + subsystem `AGENTS.md`, `docs/adr/0011-workflow-md-infra-only.md`, `.claude/skills/symphony-workflow-author/SKILL.md`, `wiki/entities/workflow-homelab.md`.
- Finding: WORKFLOW.md rules 12/16/17 parked safety enumerations inline (the ADR-0011 anti-pattern) and rule 12 cited "safety rules from CLAUDE.md" that grep confirmed were absent from homelab CLAUDE.md/AGENTS.md — a dangling reference.
- Change made (homelab repo commit `ebdc588`, local, NOT pushed; only `CLAUDE.md` + `WORKFLOW.md` staged out of a dirty tree): added "Symphony Agent Safety Policy" section to homelab `CLAUDE.md` (baseline prohibitions, excluded services, approval-required categories); rewrote WORKFLOW.md rules 12/16/17 to pointer-reference CLAUDE.md, retaining only the autonomy posture. Render-tested via `prompt_renderer.load_workflow` (frontmatter OK, enumerations gone, pointers present).
- Outputs: new claim **C-0255**; **C-0027** note annotated (source relocated to CLAUDE.md); `wiki/entities/workflow-homelab.md` 2026-06-19 update banner; this entry.
- Notes: no `/home/james/symphony-host.env` read; no Plane/Podium mutation; no push; no service restart. Symphony self-binding untouched.

## [2026-06-19] session-update | Approval-gate output-contract false positive

- Actor: agent (Pi)
- Inputs: operator request on issue #55 to patch issue #53 (`Homelab workflow`) repeatedly blocking; read-only evidence from `podium.db`, `/home/james/symphony/runs/111.log`, `/home/james/symphony/runs/113.log`; `scheduler/__init__.py`; `scheduler/markers.py`; `tests/test_scheduler.py`.
- Outputs: new raw capture `wiki/raw/sessions/2026-06-19-approval-gate-output-contract-false-positive.md`; updated `wiki/analyses/podium-046-unified-output-contract.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0256 added); this log entry.
- Notes: Fixed approval-gate precedence so explicit `SYMPHONY_RESULT` / `SYMPHONY_QUESTION` markers are authoritative for approval-gate classification; markerless approval-needed exits still block. Verification: focused approval-gate tests passed (5), ruff passed. Full `tests/test_scheduler.py` timed out at 180s after partial progress; rerun later if a full green scheduler module is needed. No secrets, env files, DB mutations, service restarts, or pushes.

---

## [2026-06-19] update | C-0251 implemented — serialize dispatch per remote binding

- Actor: agent (/dev-build of plans/fix-serialize-remote-binding-dispatch.md)
- Inputs: plans/fix-serialize-remote-binding-dispatch.md; scheduler/__init__.py; tests/test_scheduler.py; docs/adr/0012-remote-binding-ssh-exec.md; wiki/CLAIMS.md (C-0251); wiki/analyses/adr-0012-remote-binding-ssh-exec.md; wiki/index.md.
- Outputs: scheduler/__init__.py (`_effective_run_cap` helper, `_new_dispatch_state` binding kwarg, run_loop semaphore via factory + slots clamp, docstring); tests/test_scheduler.py (5 new tests); docs/adr/0012 amendment rewritten; wiki/CLAIMS.md C-0251 body rewritten (status active, implemented 2026-06-19); wiki/analyses/adr-0012 C-0251 bullet rewritten; wiki/index.md C-0251 phrasing flipped; this log entry.
- Notes: Implemented as a per-binding dispatch semaphore sized to 1 for `binding.is_remote` via `_effective_run_cap` + `_new_dispatch_state`; the reserve-function gate originally proposed in C-0251 was rejected as redundant under the semaphore — all wiki/ADR text updated to describe the implemented design, no remaining reference to a reserve-function gate the code does not implement. Verification: new tests pass; full scheduler module green (153). Wave-end pi audit (gpt-5.5) on the scheduler+test diff returned no findings. Restart of symphony-host.service still required for the change to take effect (deploy step, not yet run). No secrets, DB mutations, or pushes.

---

## 2026-06-19 session-update: approval-gate report-truncation marker drop (C-0257)

- Actor: agent (/wiki-update SessionUpdate)
- Inputs: diagnostic handoff (issues #53/#55/#57, run 120, sha 53b31ac); scheduler/__init__.py; scheduler/markers.py; scheduler/sanitize.py; tests/test_scheduler.py; runs/120.log; runs/122.log; existing C-0256 + wiki/raw/sessions/2026-06-19-approval-gate-output-contract-false-positive.md; wiki/analyses/podium-046-unified-output-contract.md.
- Outputs: scheduler/__init__.py (`_classify_terminal` verdict+gates read raw `result.stdout`/`result.stderr` via `class_stdout`/`class_stderr`); scheduler/markers.py (`_parse_result_marker`/`_hit_permission_gate`/`_hit_approval_gate` ANSI-strip internally); tests/test_scheduler.py (`test_verdict_marker_honored_when_summary_exceeds_report_truncation`); commit `2cf2eb2`; wiki/raw/sessions/2026-06-19-approval-gate-report-truncation-marker-drop.md; wiki/CLAIMS.md (C-0257); wiki/index.md (podium-046 row); wiki/ROUTING.md (output-contract route keywords + C-0257); this log entry.
- Notes: Distinct follow-on to C-0256 — C-0256 made markers authoritative (gate precedence), but the marker was still parsed from the 2 KB tail-truncated `_format_report` output, so a >2 KB summary dropped the head `SYMPHONY_RESULT` marker → verdict None → tail approval prose re-tripped the gate. Fixed by classifying from raw streams (mirrors `_extract_summary`). Verified: full `uv run pytest -q` 936 passed/2 skipped; revert-probe confirmed the new test catches the bug. Deployed live (restart to `2cf2eb2`, all 5 bindings reconciled, dispatch alive, 0 errors). Live-reproduced on smoke Issue 58/Run 122 (succeeded verdict=done) with offline `runs/122.log` proof that the old path would block. Recovered stuck issues 53/55/57 via `PATCH state=todo` → re-ran clean to `in_review` (runs 123/124/125); 53 was `archived` (flagged for re-archive decision). Optional `_APPROVAL_GATE_RE` tightening deliberately deferred. No secrets captured; no pushes.

---

## [2026-06-19] session-update | Claude unattended modal auto-drive (Run #128 review + fix)

- Actor: agent (James-directed; AskUserQuestion on the security carve-out)
- Inputs: `runs/128.log`, `podium.db` (run 128 / issue 57), `claude_runner.py`, `tests/test_claude_runner.py`, `.claude/settings.json`, `CLAUDE.md`, claude-code-guide over Claude Code permission docs, two headless `claude` edit probes; commits `b18c943` + `c434c59`
- Outputs: `wiki/raw/sessions/2026-06-19-claude-modal-autodrive.md`; `wiki/analyses/analysis-session-claude-modal-autodrive.md` (candidate→promoted); CLAIMS C-0258/C-0259/C-0260 added, C-0205 note updated (open follow-up resolved); `index.md` (Analyses), `ROUTING.md` (Executor / Agent pages + keywords)
- Notes: Run #128 "Agent timed out" was a mislabelled non-bypassable `.claude/` permission modal (old binary; 2.1.170 now auto-approves). Fix: `_poll_claude_until_done` drives parked modals — Enter to approve Yes/No, Escape+"proceed with your recommendations" for question pickers, abort after `MODAL_STUCK_LIMIT=3`. Operator chose blanket auto-approve, NO carve-out (accepts rm -rf circuit breakers). Added `additionalDirectories: [/home/james/homelab]` grant. Verified: full suite 939 passed/2 skipped; deployed `code_sha=c434c59` PID 2958104, healthy. Open: question-modal regex is best-effort (no real `ask_user_question` pane reproduced); issue #57 still `blocked` (SKILL.md/wiki wiring outstanding). No secrets captured; commits local, not pushed.

## 2026-06-19 — Query: homelab issue 59 "Temporal" Build loop ("no readable plan file was found")
- Actor: agent (symphony-binding persist run, issue 60 — review homelab issue 59)
- Inputs: `podium.db` (issue 59 / run 131, comments_md), `scheduler/__init__.py` (`_issue_slug`, `_expected_plan_path`, `_validate_issue_plan_path`, `_validated_fallback_plan_path`, build branch ~L1234-1288), `tracker_podium.py:95,155`, `config.py:288,331-344`, `/home/james/homelab/plans/`
- Outputs: CLAIMS C-0261 added (refines C-0030 for Podium era); homelab commit `f6b9002` renaming `plans/59-temporal.md`→`plans/59.md`
- Notes: Root cause — Podium adapter sets issue identifier to the numeric id ("59"), so Build's plan-path validator expects `plans/59.md`, but the Plan run wrote the old `{id}-{title}` name `plans/59-temporal.md`. Validation failed every poll → Build posted "no readable plan file was found", flipped build→plan, returned issue to Todo, looping (60+ identical comments). Immediate unblock applied (rename, landing=local so no push). Issue 59 currently Todo; James must re-set the Build skill on it to retry. Open design question for James logged in C-0261: fix Plan author to emit `plans/{id}.md` vs relax validator to accept `{id}-*.md`.

## 2026-06-19 — Fix: Build accepts id-prefixed plan filenames (deeper bug from issue 59)
- Actor: agent (symphony-binding persist run, issue 60); operator directive "let's fix the deeper bug"
- Inputs: `scheduler/__init__.py` (`_expected_plan_path`, `_validate_issue_plan_path`, `_validated_fallback_plan_path`), `tests/test_scheduler.py`
- Outputs: symphony commit `98c5561` (scheduler fix + 5 new tests); CLAIMS C-0262 added, C-0261 marked superseded
- Notes: Operator chose to relax discovery rather than change the Plan author. `_validated_fallback_plan_path` now prefers exact `plans/{id}.md`, else a single `plans/{id}-*.md` match (requires `-` so `591`≠`59`); ambiguous/zero → None → returns to Plan mode. `_validate_issue_plan_path` matches stem == slug or `slug-` prefix, retaining path-safety checks. `tests/test_scheduler.py` 160 passed; full suite 946 passed/2 skipped — the only 2 failures were pre-existing `uv`-not-on-PATH subprocess tests (`web/api`/`web/cli`), confirmed green when `uv` is on PATH. No live service touched; commit local, not pushed.

## [2026-06-20] session-update | grill-me: wire Temporal patrols → Podium (ADR-0015)

- Actor: agent (`/grill-me` over homelab `plans/59.md`; James settled 3 open forks)
- Inputs: `/home/james/homelab/plans/59.md`, `/tmp/handoff-HDgnMi.md`, `blocked_reconciler.py`, `web/api/main.py:807`, `tracker_podium.py:245`, homelab `ticket_writer.py`/`patrol_plane.py`/`worker.py`/`patrol_models.py`/`plane_adapter.py`; existing ADR-0011/0014 + CLAIMS C-0014/C-0035
- Outputs: `docs/adr/0015-patrol-podium-tracker-adapter.md` (status `proposed`); `wiki/raw/sessions/2026-06-20-patrol-podium-adapter-grill.md`; `wiki/analyses/adr-0015-patrol-podium-tracker-adapter.md` (candidate→promoted); CLAIMS C-0263/C-0264/C-0265 added, C-0014 + C-0035 annotated Plane-scoped (reversed for Podium, not superseded); `index.md` (Analyses row), `ROUTING.md` (Decisions + Blocked Reconciler pages/keywords); homelab `plans/59.md` updated (settled-decisions block, Waves re-sequenced A→B→C, approval checklist resolved — homelab repo, commit pending)
- Notes: No patrol→Podium code exists — design only. Settled forks: full lifecycle parity incl. auto-cure (not just posting); `external_id` global-unique nullable index (double duty: adapter dedup + reconciler rule selection); sequencing A→B→C batching both excluded-service changes (migration + reconciler rule) into one gated `podium-api` window. Linchpin: Plane `consecutive_passes`-reset-to-1 is an editor-strip bug (`patrol_plane.py:65-71`), so trusting the marker on Podium markdown is sound — new Podium-only `patrol-passes-marker` rule fires on `consecutive_passes>=2 AND last_pass_at>last_fail_at`; marker gains those timestamps (homelab). Gap caught: plan 59's original Wave 2 omitted the reconciler change. Next: `/dev-build` Wave A (homelab, no service impact). No secrets; no live service touched.

## [2026-06-20] build | /dev-build plan 59 Waves A+B (patrol→Podium adapter)

- Actor: agent (`/dev-build`; two builder subagents + pi wave-end audits + operator handoff at each wave)
- Inputs: `docs/adr/0015-patrol-podium-tracker-adapter.md`, homelab `automation/homelab-stack` (ticket_writer/plane_adapter/plane_contract/patrol_plane/patrol_models + tests), symphony `web/api/{schema,main}.py`, `blocked_reconciler.py`, `scheduler/__init__.py:1117`, migrations 0008 head
- Outputs: homelab commit `e86d69d` (Wave A: `ticket_types.py`, `podium_adapter.py`, `podium_http.py`, patrol_plane marker timestamps, plane_adapter re-export, tests); symphony commit `44d6b5f` (Wave B: migration `0009_issue_external_id`, schema parity, `external_id` API + `?external_id=` filter + UNIQUE→409, marker-first reconciler cure, tests); `plans/.59.state.yml` build_audits (homelab); ADR-0015 + `wiki/analyses/adr-0015-*` implementation-status sections; CLAIMS C-0266 added, C-0265 annotated built
- Notes: Waves A+B built/tested/committed but **INERT** — nothing applied or restarted. pi audits: Wave A clean; Wave B 0 critical / 2 warnings (migration index-skip + PATCH-409) auto-fixed + covered. Full suites green (homelab 172 targeted, symphony 966 passed/2 skipped). PodiumAdapter verified to import only `ticket_types` (decoupled from Plane). §4 revised during build: cure shipped as a unified marker-first-with-comment-fallback in the existing patrol rule (not a separate DEFAULT_RULES entry) since the reconcile call site passes no per-tracker rules; Plane comment path byte-for-byte preserved. Migration idempotency required (SCHEMA_SQL-at-head vs stamp-at-0008 drift). One pre-existing unrelated homelab `test_prompt_renderer` failure (WORKFLOW.md drift, C-0255) noted, not introduced. **Remaining:** Wave C (worker.py cutover + `PATROL_TRACKER` toggle + dry-run + patrol-worker restart) + gated `podium-api` window (apply migration 0009, create `homelab-patrol` binding, restart). No secrets printed; no live service touched; commits local, not pushed.

## [2026-06-20] session-update | ADR-0015 gated podium-api window applied live (full parity)

- Actor: agent (operator-gated execution from handoff; James confirmed window + chose full-parity scope)
- Inputs: `/tmp/handoff-IG4RNe.md`, `docs/adr/0015-patrol-podium-tracker-adapter.md`, `/home/james/homelab/plans/59.md`, CLAIMS C-0266/C-0267, `web/api/migrations/versions/0009_issue_external_id.py`, `alembic.ini`, `web/api/{main,schema}.py`, `scripts/podium-backup.sh`, live `podium.db` (rev 0008)
- Outputs: live migration `0008`→`0009_issue_external_id (head)` on `podium.db` (`external_id` col + `ix_issue_external_id` index); `podium-api.service` + `symphony-host.service` restarted onto Wave B / new code (full parity); backup `/backup/podium-2026-06-20.db`; `wiki/raw/sessions/2026-06-20-patrol-podium-gated-window.md`; CLAIMS C-0268 added; `wiki/analyses/adr-0015-*` status section updated; ROUTING keyword + C-0268 added
- Notes: Verified — `?external_id=zzz`→200 `[]` (Wave B endpoint live); `symphony_started code_sha=d7207f4 bindings=5`, `reconcile_startup_completed cleaned=0`×5, `dispatch_completed`; marker-first cure live (`blocked_reconcile_skipped issue_id=61 external_id= reason=no-matching-rule`); `homelab` binding `{blocked:1,archived:1}` unchanged before+after. Ops corrections: alembic config is repo-ROOT `alembic.ini` (handoff's `web/api/alembic.ini` is wrong — errors "No 'script_location' key"); migration MUST precede the podium-api restart or Wave B startup crashes on `_schema_drift` missing-column (`web/api/main.py:464-470`). Benign nit found: `INITIAL_REVISION` left at 0008 (`web/api/schema.py:3`) → per-startup `podium_schema_revision_mismatch db=0009 code=0008` warning (non-fatal; bump to silence). Working tree had unrelated dirty docs (`CLAUDE.md`, `CLAUDE_1.md`) from a concurrent session — docs-only, left untouched. **Wave C NOT done** (deferred per handoff). No secrets read/printed; `symphony-host.env` never opened. **Open:** Wave C (`worker.py` cutover); INITIAL_REVISION bump follow-up.

## [2026-06-20] session-update | ADR-0015 Wave C — patrol cutover (auth gap fixed, dry-run passed, cutover deferred)

- Actor: agent (operator-gated; James authorized Wave C, chose service-token auth, then chose "dry-run only, then pause")
- Inputs: `/home/james/homelab/plans/59.md` (Wave C), `docs/adr/0015-*`, CLAIMS C-0266/C-0267/C-0268, homelab `automation/homelab-stack` (worker.py/config.py/podium_adapter.py/podium_http.py/ticket_types.py), symphony `web/api/{auth,main}.py`, `scheduler/__init__.py` (dispatch eligibility), live podium-api `127.0.0.1:8090`
- Outputs: symphony `69bf3f3` (podium-api Bearer `PODIUM_API_TOKEN` auth + tests); 2nd gated podium-api window (token in `symphony-host.env`, restarted, bearer verified); homelab `d160955` (Wave C `worker.py` cutover wiring + `WorkerConfig` podium fields + tests), `2e4fad6` (podium_adapter bare-list response fix + regression test); live dry-run 10/10 (test issue 62 created→archived→DB-deleted, no dispatch); CLAIMS C-0269 + C-0270 added; `wiki/raw/sessions/2026-06-20-wave-c-patrol-cutover.md`; ADR-0015 analysis status + ROUTING updated
- Notes: **Auth gap (C-0269):** podium-api was cookie-only (`require_auth` middleware never read `Authorization`); Wave A's `PodiumHttpTransport` speaks only Bearer (its "unauthenticated create endpoint" docstring was wrong) → cutover would 401. Operator chose token-on-podium-api (excluded service) over transport cookie-login. Added optional `PODIUM_API_TOKEN` (constant-time, cookie-fallback, unset→cookie-only). **Dry-run found a real bug (C-0270):** `find_by_external_id` only parsed the mock's `{"results":[...]}`, but live API returns a bare list → `AttributeError` in prod; fixed both-shapes + regression test. Dry-run also live-confirmed the `<!-- patrol-status -->` marker round-trips in Podium markdown (C-0265) and that a plain `todo` is dispatch-eligible in any binding (`scheduler/__init__.py:1201-1230`) → archived sub-second to avoid claiming. **DEFERRED per operator:** worker env (`PODIUM_API_TOKEN`+`PATROL_TRACKER=podium` in `/etc/homelab-stack/temporal-worker.env`) + `homelab-temporal-patrol-worker.service` restart; patrols stay on Plane until then. **Working-tree alert (unrelated):** a concurrent process deleted all of `.claude/` + 142 lines of `CLAUDE.md` mid-session (recoverable from HEAD; caused 15 environmental `tests/skills/` failures); surfaced to James, left untouched. Token value / secrets never printed; commit hooks bypassed only because the hook script was among the concurrently-deleted files. **Open:** finish Wave C cutover on go; decide `.claude` restore; INITIAL_REVISION bump.

## [2026-06-20] session-update | ADR-0015 Wave C cutover COMPLETE — patrols live on Podium

- Actor: agent (operator "proceed with cutover")
- Inputs: C-0269/C-0270, `/etc/homelab-stack/temporal-worker.env`, `/home/james/symphony-host.env` (token source), `homelab-temporal-patrol-worker.service`
- Outputs: worker env gained `PATROL_TRACKER=podium` + `PODIUM_API_TOKEN` (hash-verified == podium-api token; value never printed); patrol worker restarted; C-0270 + ADR-0015 analysis flipped deferred→complete
- Notes: Verified `patrol_tracker=podium binding=homelab base_url=http://127.0.0.1:8090`, `worker_started code_sha=2e4fad6`, clean Temporal connect, no 401/errors. **ADR-0015 fully landed** — patrols write to the `homelab` Podium binding; first live write on next Temporal-scheduled cycle (dry-run already proved the path). Plane retained via `PATROL_TRACKER=plane`. Operator confirmed the `.claude/`+`CLAUDE.md` working-tree changes were his own intentional edits (not a rogue process) — no recovery; 15 `tests/skills/` failures are from the deleted SKILL.md files (operator's call). No secrets printed.

## [2026-06-20] review | dev-review-claude on Wave C diff — findings applied

- Actor: agent (independent reviewer: Claude Opus via dev-review-claude/tmux) + primary applied agreed fixes
- Inputs: symphony `69bf3f3` (bearer auth), homelab `d160955`/`2e4fad6` (Wave C wiring + adapter fix)
- Findings: 0 Critical, 3 Warning, 7 Note; no working-tree drift; no false positives (verified .env gitignored, whoami cookie-only, from_stack_config sets 0 patrol fields, 1 patrol-worker deployment)
- Outputs (applied): symphony `49971ed` — harden `verify_bearer_token` header parsing (strip + edge tests + mutating-endpoint capability test). homelab `dcd8c16` — W1: `from_stack_config` resolves patrol fields via shared `_patrol_fields_from_env` + enforces Podium-token guard (was: defaults podium/no-token → runtime 401); N6: URL-encode `external_id` dedup query; N7: transport return types `dict|list`; N8: fix stale/wrong `podium_http` docstrings (`:8090` not `:8200`; Bearer required, not "unauthenticated" — the claim that caused the Wave A gap); runbook §"Patrol → Podium" adds PATROL_TRACKER rollback pin (W3), token-rotation restart (N4), accepted unscoped-token risk (W2). Tests: symphony auth 22 passed; homelab 72 passed; ruff clean both.
- Accepted-as-is: W2 (unscoped token — documented), N5 (no bearer rate-limit; negligible at 256-bit), N11 (whoami cookie-only; harmless). N10 (.env) verified gitignored — no action.
- Notes: refines C-0269 (auth hardening) and C-0270 (from_stack_config guard). Live services still run pre-fix code (podium-api `69bf3f3`, worker `d160955`/`2e4fad6`); the fixes are latent-safety (prod sends clean `Bearer`, external_ids are slug-safe, worker uses from_env) so no restart is required — optional pickup on next restart. No secrets printed.

## 2026-06-20 — ADR-0016: retire infra WORKFLOW.md → renderer constant (grill-me design pass)
- Actor: agent (grill-me session with James)
- Type: decision record (ADR + wiki); **no code/file change — implementation deferred**
- Inputs: `~/homelab/WORKFLOW.md`, `WORKFLOW.infra.md` template (in `.claude.2` Trash), `prompt_renderer.py`, `project_scaffold.py:50-66`, `skill_mode_map.py`, `bindings.yml`, ADR-0011, CONTEXT.md Workflow glossary
- Decision (4 parts): (1) infra `WORKFLOW.md` retired — generic body → renderer constant in `prompt_renderer.py`, `render_prompt` skips `load_workflow` for infra, delete homelab file + scaffold stub + template; infra+coding converge. (2) medium-risk autonomy grant → `~/homelab/CLAUDE.md` scoped to unattended Symphony dispatch (no interactive-session leak). (3) rule 11 narrowed (Option A): body is trusted operator instruction, quoted machine output is data — unblocks per-patrol-skill design. (4) plan/build kept in the constant for now; removal deferred to the separate patrol-skill work.
- Principle: `WORKFLOW.md` = portable Symphony harness contract (ships with engine); host-specific policy (safety + autonomy) lives in host `CLAUDE.md`. Install on a new host → author `CLAUDE.md`, touch nothing else.
- Outputs: `docs/adr/0016-workflow-md-retired-renderer-constant.md` (accepted, impl pending); `wiki/analyses/adr-0016-workflow-md-retired-renderer-constant.md` (promoted); CONTEXT.md Workflow term rewritten; CLAIMS C-0276/C-0277/C-0278 added; C-0203/C-0204 → superseded, C-0026 amended; index.md + ROUTING.md updated; workflow-homelab entity annotated.
- Follow-ups (NOT done): `prompt_renderer.py` INFRA constant + skip-load-for-infra, file deletions, `CLAUDE.md` autonomy migration, tests, James-approved `symphony-restart`; retire `symphony-workflow-author` + scaffold infra-WORKFLOW emission; the separate per-patrol-skill build (incl. plan/build removal decision). Order: renderer change must land before deleting `~/homelab/WORKFLOW.md` (else `workflow-missing`).
- Notes: supersedes the file-based half of ADR-0011 only; ADR-0011's `binding_type` coding-ignore split + "safety is the repo's job" stance remain. No secrets read.

## [2026-06-20] session-update | Patrol→Podium soak: reply-409 self-heal regression + auto-cure close stickiness

- Actor: agent
- Inputs: live monitoring of the first scheduled patrol→Podium cycles (ADR-0015 post-cutover soak); `journalctl`/`sqlite3`/`temporal` read-only diagnosis; `diagnose` skill; operator-gated fix + deploy.
- Root cause: `/reply` (`web/api/main.py:1135-1158`) is the operator-reopen endpoint (appends comment AND flips `state='todo'`, gated to in_review/blocked/done with no active run). `record_failure` flipped to TODO then commented via `/reply` → deterministic 409 → workflow FAILED (C-0279). Sibling: `record_pass` close set DONE then commented → `/reply` reopened it to todo → auto-cure never stuck (C-0280). Both masked by the permissive `InMemoryPodiumTransport` reply fake (same mock/real divergence class as C-0270/C-0271).
- Fix (homelab `0e163be` + `219424e`): comment BEFORE the caller's state flip; shared `_post_comment_tolerating_409` helper (409 = active run, non-fatal); mock enforces the real state+run-state guard; `TestPatrolPodiumReplyContract` regression tests (proven to fail against old orderings); 732 suite pass. Worker restarted → `code_sha=219424e`; two manual `infra` cycles COMPLETED, dedup held (59 issues), 409s on 70/71 tolerated, issue 63 closed→stayed done.
- Outputs: `wiki/raw/sessions/2026-06-20-patrol-podium-reply-409-and-close-stickiness.md` (raw capture); `wiki/analyses/adr-0015-patrol-podium-tracker-adapter.md` new "First scheduled-cycle soak" section + Related/sources; CLAIMS C-0279/C-0280/C-0281; ROUTING ADR-0015 route keywords extended; index.md ADR-0015 row annotated.
- Follow-ups (deferred, C-0281): `/reply` reopens to todo on every comment → pass-recorded issues re-dispatch pi each cycle and a close can be clobbered back to in_review by an in-flight pi run (issue 62 observed done→in_review). Durable fix = non-reopening comment endpoint on podium-api (excluded service, operator-gated). Confirm the scheduled 03:00 UTC infra cycle + other domains' first self-heal cycles COMPLETE on `219424e`.
- Notes: in-flight operator working-tree files (`hosts/aidev.md`, `services/agent-zero-stack.md`, runbook docs) left uncommitted. No secrets read; tokens never printed.

## [2026-06-20] session-update | SYMPHONY_RUN_CAP reduced 3 → 2 (per-binding pi concurrency)

- Actor: agent (Claude Code), operator-requested
- Inputs: operator asked to reduce simultaneous pi agents to 2 per binding; `bindings.yml`, `config.py:176,294`, `scheduler/__init__.py:161-193`, live `systemctl`/`journalctl` verification.
- Change applied (not wiki): `/etc/systemd/system/symphony-host.service.d/override.conf` `SYMPHONY_RUN_CAP` 3→2; `daemon-reload` + `restart`; verified `SYMPHONY_RUN_CAP=2` live and `symphony_started ... bindings=5` on new PID.
- Outputs: `wiki/raw/sessions/2026-06-20-run-cap-reduced-to-2.md` (raw capture); `wiki/sources/symphony-host-service-unit.md` (new override.conf RUN_CAP row + dated note); CLAIMS C-0284 (live value now 2; supersedes C-0251 live-value sub-fact, which got a drift note); ROUTING ops route keywords extended.
- Notes: architecture (per-binding cap, remote clamp, host-wide ≈ run_cap × num_bindings) already documented in C-0251 / ADR-0012 — unchanged. Only durable new fact is the live value. Operator confirmed intent is "2 per binding," NOT host-wide 2 (would need a shared global semaphore — deferred, not requested). No secrets read/written; env file untouched (cap lives in the drop-in).

## [2026-06-20] session-update | ADR-0017 `/comment` endpoint built, deployed, live-verified (resolves C-0281)

- Actor: agent (Claude Code), `/dev-build plans/adr-0017-comment-endpoint.md` + operator-gated deploy
- Inputs: `web/api/main.py`, `web/api/tests/test_comment.py`, `web/frontend/components/IssueFlyout.tsx`, `web/frontend/tests/comments-collapse.spec.ts` (symphony `09c852c`); `automation/homelab-stack/src/homelab_router/podium_adapter.py`, `src/homelab_worker/patrol_plane.py`, `tests/test_podium_adapter.py`, `tests/test_patrol_plane.py` (homelab `8a101eb`); `docs/adr/0017-...md`; live podium-api + patrol-worker journals.
- Durable knowledge: `POST /api/issues/{id}/comment` is the append-only Comment primitive (no state flip, no run-state gate, never 409s, verbatim append, caller-owned header); homelab `add_comment` repointed `_reply_path`→`_comment_path` + worker-stamped `### Patrol (<ts>)`; `patrol_plane.py` unchanged so the C-0279/C-0280 409-tolerance + comment-before-flip ordering are now dead insurance; reopen/close owned by explicit `update_issue`. Deploy order podium-api→podium-web→worker; live docker patrol confirmed `/comment` 200 (no `/reply`, no 409) with comment+reopen decoupled.
- Outputs: raw `wiki/raw/sessions/2026-06-20-adr-0017-comment-endpoint-landed.md`; CLAIMS C-0285 (new, high, supersedes C-0281; C-0281 marked `superseded`); promoted-page maintenance on `wiki/concepts/operator-reply.md` (new `/comment` sibling section + frontmatter), `wiki/analyses/adr-0015-patrol-podium-tracker-adapter.md` (soak "Resolved (C-0285)" entry + related); index.md operator-reply + adr-0015 rows; ROUTING.md ADR route keywords extended (ADR-0017/comment/C-0285).
- Unresolved: live pass-no-reopen + close-stays-done not yet observed in prod (test-covered only; needs a passing/closing docker check); pre-existing `podium_schema_revision_mismatch` (db 0009 vs code 0008) at podium-api startup, unrelated to ADR-0017; `_post_comment_tolerating_409` + comment-before-flip ordering are removable once `/comment` soaks; `podium-web` needs a host-only pnpm `verify-deps-before-run=false` drop-in to restart (captured in agent memory, not wiki).
- Notes: no secrets read/written (`PODIUM_API_TOKEN` sourced, never printed). Two `/dev-build` wave diffs each passed an independent pi audit.

## [2026-06-20] session-update | ADR-0017 open items: live pass/close observed + INITIAL_REVISION 0009 fix

- Actor: agent (Claude Code), handoff `/tmp/handoff-XTILeb.md` (items 1 & 2)
- Inputs: triggered `schedule-patrol-infra` cycle + `journalctl -u homelab-temporal-patrol-worker.service` (22:19); live `podium.db` issues #62/#63/#64; `web/api/schema.py`, `web/api/main.py:429-475`, `web/api/db.py`, `web/api/migrations/versions/0009_issue_external_id.py`; `tests/test_alembic_baseline.py`, `web/api/tests/test_ensure_schema.py`, `web/api/tests/test_endpoints.py`.
- Durable knowledge: (item 1) ADR-0017 **pass-no-reopen** (#64 pve1 `in_review` stayed in_review after a `/comment` pass) and **close-stays-done** (#62 aidev `in_review`→`done`, "closed after 5 consecutive passes", DONE flip stuck) now confirmed LIVE; whole cycle used `/comment` only (zero `/reply`, zero 409); #63 done→running was a legitimate reopen (wazuh disk genuinely 81%>80%). (item 2) the `podium_schema_revision_mismatch db=0009 code=0008` warning is a one-line code lag — live DB is legitimately at head 0009, no migration/stamp needed; fix = bump `INITIAL_REVISION` to `0009_issue_external_id`.
- Outputs: raw `wiki/raw/sessions/2026-06-20-adr-0017-live-pass-close-observed-and-initial-revision-fix.md`; CLAIMS C-0286 (live pass/close obs), C-0287 (INITIAL_REVISION fix); C-0285 caveat updated to point at C-0286; code commit symphony `188fadb` (`web/api/schema.py` only); index.md + ROUTING.md adr-0015/0017 rows extended.
- Unresolved: handoff item 3 (dead-insurance cleanup) now UNBLOCKED but deferred (let `/comment` soak a few more natural cycles); item 4 (uncommitted wiki/CONTEXT) still operator-batched; podium-api will keep logging the benign warning until its next restart picks up `188fadb`.
- Notes: no secrets read/written (`PODIUM_API_TOKEN` sourced, never printed). No infra forced; no smoke comments injected — observed a natural pass after aidev disk fell to 76%.

## [2026-06-20] session-update | ADR-0017 item 3: dead-insurance cleanup landed (homelab 086487d)

- Actor: agent (Claude Code), handoff `/tmp/handoff-XTILeb.md` (item 3), unblocked by C-0286
- Inputs: `automation/homelab-stack/src/homelab_worker/patrol_plane.py`, `tests/test_patrol_plane.py::TestPatrolPodiumReplyContract`.
- Durable knowledge: removed `_post_comment_tolerating_409` + the orphaned `import httpx`; inlined `adapter.add_comment` at the three call sites (record_failure reopen/update, record_pass close, record_pass below-threshold). `/comment` is append-only (never reopens, never 409s — C-0285) and the contract is live-confirmed (C-0286), so the 409 wrapper + "comment-before-flip avoids the reply 409" rationale were dead. Behavior unchanged; comment-first kept only so a comment failure aborts before a state change. Full homelab-stack suite 723 passed.
- Outputs: CLAIMS C-0288 (cleanup landed); C-0285/C-0286 notes updated to point at C-0288 (dead-insurance sub-facts superseded); index.md + ROUTING.md adr-0015 rows extended. Code commit homelab `086487d` (patrol_plane.py only).
- Unresolved: no worker restart forced (behavior-identical; next natural restart picks it up). Handoff item 4 (uncommitted wiki/CONTEXT) still operator-batched.
- Notes: no secrets. Other modified files in the homelab working tree (config/router/monitor/worker + their tests) are unrelated pre-existing changes, left untouched.

## [2026-06-20] grill+ingest | ADR-0018: patrol medium-risk updates self-schedule into the maintenance window (proposed)

- Actor: agent (Claude Code), `/grill-me` "review anything outstanding between Temporal patrols and Podium".
- Inputs: live `podium.db` (issues 62–76), patrol/symphony journals, `patrol_config.py`, `scheduler/__init__.py`, `schedule.py`, `tracker_podium.py`, `web/api/{schema,main}.py`; three operator decision answers.
- Durable knowledge: patrols→Podium is live + healthy (auto-cure proven on 62/69); medium-risk findings (package/image updates, reboots, prunes) correctly BLOCK awaiting a maintenance window that Podium can't grant. Verified the detection cron never runs in-window (infra `0 3,15` UTC = 8pm/8am LA vs 12am–6am LA window) and that Podium's dormant scheduling machinery already requires the `Symphony-Schedule` comment (column=flag, comment=time). Operator chose hands-off agent self-scheduling reusing the grammar + a first-class infra-only Schedule control in the Podium UI.
- Outputs: ADR `docs/adr/0018-patrol-medium-risk-window-scheduling.md` (`proposed`); raw session `wiki/raw/sessions/2026-06-20-patrol-window-scheduling-grill.md`; analysis `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md` (promoted); CLAIMS C-0289/C-0290/C-0291; index.md + ROUTING.md (Scheduling + Decisions) rows added.
- Unresolved: no code yet — implementation plan/issues to follow (symphony: `SYMPHONY_SCHEDULE` marker + scheduler handling + UI + window constant + dedup-don't-clobber guard; homelab: INFRA_PREAMBLE block→schedule rule). Recommend verifying the apply path on one real finding before flipping INFRA_PREAMBLE.
- Notes: no secrets read/written; live board observed, not mutated. Carried-over chores (stale `test_default_workflow_documents_medium_risk_autonomy`, ponytail pi-extension ESM bug, homelab Plane-CLI doc debt) noted, not addressed.

## 2026-06-21 — Close out ADR-0016 kanban issues 088–092 (board reconciliation)
- Actor: agent (Claude Code), "review .kanban/issues — may have been built in other sessions".
- Inputs: `.kanban/issues/088–092`, `prompt_renderer.py`, `project_scaffold.py`, git log (`7e71b10`), `~/homelab/{CLAUDE.md,WORKFLOW.md}`, patrol-router `prompt_renderer.py`, ADR-0016, CLAIMS C-0276/C-0277/C-0278.
- Finding: all five ADR-0016 issues were already implemented in prior sessions (symphony `7e71b10`, homelab `2458429`; `~/homelab/WORKFLOW.md` deleted; restart-deployed) but the board still marked them `pending`. Only residual gap: 092 acceptance — `wiki/entities/workflow-homelab.md` still read "decision only, NOT yet implemented / file still exists".
- Outputs: fixed `wiki/entities/workflow-homelab.md` (file now described as deleted; prompt renders from `INFRA_PREAMBLE`; `updated: 2026-06-20`); flipped issues 088–092 to `status: done` and archived to `.kanban/archive/2026-06-21/`. No new claims (C-0276/0277/0278 already implemented-marked).
- Notes: no code changed; no secrets touched. Verified against each issue's own acceptance criteria before closing.

## [2026-06-21] session-update | Issue #93 schedule foundations landed

- Actor: agent (Ralph actionable review loop)
- Inputs: `.kanban/issues/093-schedule-foundations-next-window-prefer-last.md`; `schedule.py`; `scheduler/__init__.py`; `tests/test_schedule.py`; `tests/test_scheduler.py`; diff from base `9ca6989c8820e31211e15c2ff4f13c080614d7ce` to `HEAD`.
- Outputs: symphony commit `14d2e41` (`next_maintenance_window`, `not_before=next_window`, Podium `prefer_last` latest-control-line handling); updated `wiki/concepts/schedule-comment-grammar.md`; updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0291 qualified; C-0292/C-0293 added); this log entry.
- Notes: Captured the first ADR-0018 backend foundation slice. Remaining ADR-0018 work is still unbuilt: `SYMPHONY_SCHEDULE` marker handling, INFRA_PREAMBLE schedule authorization, dedup-don't-clobber behavior, and the Podium UI Schedule control. Verification: `uv run pytest tests/test_schedule.py tests/test_scheduler.py -q` passed (226 tests); touched-file LSP diagnostics clean. No secrets, env files, service restarts, live alerts, or live DB mutations.

## [2026-06-21] session-update | Issue #94 SYMPHONY_SCHEDULE output marker mechanism landed

- Actor: agent (Ralph one-issue loop)
- Inputs: `.kanban/issues/094-symphony-schedule-marker.md`; `scheduler/markers.py`; `scheduler/__init__.py`; `prompt_renderer.py`; `tests/test_schedule.py`; `tests/test_prompt_renderer.py`; implementation base `d3cb5d85598b3d02a629a87ca715c402af5e6524`.
- Outputs: symphony commits `0b2ab00` (implementation), `45905a7` (review status), `459e0f2` (done/progress); updated `wiki/concepts/schedule-comment-grammar.md`; updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md`; updated `wiki/analyses/podium-046-unified-output-contract.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0291 qualified; C-0294 added); this log entry.
- Notes: Captured the second ADR-0018 mechanism slice: `SYMPHONY_SCHEDULE` stdout marker parsing, schedule marker stripping from summary/question blocks, scheduler re-export, and output-contract/INFRA_PREAMBLE mechanism wording. Remaining ADR-0018 work is still unbuilt: scheduler terminal handling for valid/malformed schedule markers (#95), schedule-authorization policy, dedup-don't-clobber behavior, and the Podium UI Schedule control. Verification: `uv run pytest tests/test_schedule.py tests/test_prompt_renderer.py tests/test_prompt_renderer_podium.py -q` passed (90 tests); touched-file LSP diagnostics clean; fresh Ralph review PASS. No secrets, env files, service restarts, live alerts, or live DB mutations.

## [2026-06-21] session-update | Issue #095 scheduler terminal schedule handler

- Actor: agent (Ralph/Pi)
- Inputs: `.kanban/issues/095-scheduler-terminal-schedule-handler.md`; implementation diff `git diff 6d8eefc6b6105068791719d83abf8dab749df429 HEAD`; `scheduler/__init__.py`; `tests/test_scheduler.py`; `.kanban/progress.md`; fresh review session.
- Outputs: updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md`; updated `wiki/concepts/schedule-comment-grammar.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0295 added, C-0291/C-0294 refined); this log entry.
- Notes: Captured Issue #95 landing: valid infra `SYMPHONY_SCHEDULE` markers become scheduled TODO issues via schedule comment → scheduled label → TODO, Run `succeeded`/`verdict=None`, `agent-marker-scheduled`; malformed/past/reasonless infra markers block; coding bindings ignore the marker. Actionable review fixed approval-gate precedence, malformed-marker coding ignore, run-record/order test coverage, and added `action_reviewed`. Verification: `uv run pytest tests/test_scheduler.py -q` passed (172 tests), touched-file LSP diagnostics clean. No secrets, env files, service restarts, or live alert/paging notifications.

---


## [2026-06-21] session-update | Issue #096 manual schedule API

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/096-manual-schedule-api-endpoint.md`; `web/api/main.py`; `web/api/tests/test_schedule_endpoint.py`; `web/api/tests/test_endpoints.py`; `.kanban/progress.md`; fresh review diff `git diff 6a10ced23e07f59faf0ec130712aa16141402ec3 HEAD`.
- Outputs: updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0291 refined, C-0296 added); updated `wiki/log.md`.
- Notes: Captured Issue #096 landing the backend manual schedule API: infra-only `POST`/`DELETE /api/issues/{id}/schedule`, `/api/bindings` `binding_type`, and `IssueCreate.schedule` for atomic create-time holds. Verification: exact issue command passed (`uv run pytest web/api/tests/test_schedule_endpoint.py web/api/tests/test_endpoints.py -q` = 9 passed), ruff passed for touched Python files, touched-file LSP diagnostics clean, fresh Ralph review `RALPH_REVIEW: PASS`. No env files or live secrets read.

## [2026-06-21] session-update | Issue #097 frontend schedule controls

- Actor: agent (Ralph)
- Inputs: `.kanban/issues/097-frontend-schedule-control-infra-only.md`; `web/frontend/components/ScheduleControl.tsx`; `web/frontend/components/NewIssueModal.tsx`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/components/IssueCard.tsx`; `web/frontend/lib/api.ts`; `web/frontend/tests/schedule.spec.ts`; fresh review diff `git diff 06553cf3ba1065233de712d5a1207a3d04b2284e HEAD`.
- Outputs: symphony commits `47ca35b` (implementation), `a8a5072` (review status), `a645af8` (done/progress); updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0291 refined, C-0297 added); updated `wiki/log.md`.
- Notes: Captured Issue #097 landing the infra-only frontend Schedule control, create-time `IssueCreate.schedule` payload, flyout `POST`/`DELETE /schedule` path, and board-card Scheduled chip. Verification: exact issue command passed (`cd web/frontend && pnpm test:e2e schedule.spec.ts && pnpm build` = 3 Playwright tests passed + Next build passed), touched-file LSP diagnostics had no critical errors, fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES`. No env files or live secrets read; Playwright browser/dependency setup was local verification prep only.

## [2026-06-21] session-update | #098 landing, schedule-UI Yes/No refinement, window deploy-verify

- Actor: agent (interactive session, not Ralph)
- Inputs: `.kanban/issues/098-MANUAL-homelab-block-to-schedule-policy-and-dedup.md`; homelab `automation/homelab-stack/src/homelab_router/{podium_adapter,ticket_writer,plane_adapter}.py`, `.../homelab_worker/patrol_plane.py`, `.../tests/test_patrol_plane.py`, `/home/james/homelab/CLAUDE.md`; symphony `web/frontend/components/{ScheduleControl,IssueFlyout}.tsx`, `web/frontend/lib/api.ts`, `web/frontend/tests/schedule.spec.ts`; live `journalctl -u symphony-host` (07:00–07:35Z), read-only `podium.db`, `systemctl show … ExecMainStartTimestamp`.
- Outputs: homelab commit `f76f7ab` (#098, pushed); symphony commits `002b25f`/`9c21520`/`4047704`/`7e4a319` (schedule-UI refinement + e2e, pushed); new raw session `wiki/raw/sessions/2026-06-21-adr-0018-098-deploy-verify.md`; updated `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md` (deploy-verify section + status); updated `wiki/index.md`, `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0298/C-0299/C-0300 added, C-0297 marked partially superseded); updated `wiki/log.md`.
- Notes: #098 landed the homelab policy half of ADR-0018 (block→schedule in homelab `CLAUDE.md`, dedup-don't-clobber, close-clears-schedule; `uv run pytest` 732 passed). Schedule UI simplified to Yes/No apply-on-change + held-issue `/comment` path (`tsc`+`next build` clean, `schedule.spec.ts` 4 Playwright tests pass). **Deploy-verify on the 2026-06-21 00:00–06:00 PT window did NOT cleanly verify:** path is live and an agent attempted to self-schedule, but issue 76 emitted a computed past timestamp (`not_before=2026-06-21T07:00:00+00:00`) instead of symbolic `next_window` → #95 classified `agent-scheduled-malformed` → blocked; no issue ever held. Suspected (unverified) cause: resumed pre-policy session not getting the `next_window` preamble. Unresolved: confirm preamble injection on resumed sessions; re-verify item 5 with a fresh dispatch; #098 item 6 (re-open backlog 63/66/71/74/75/76) deferred until a clean verify. No env files or live secrets read; observation phase mutated nothing.

## [2026-06-21] session-update | Run #212 triage → remote session tail (ADR-0019 built) + tracker-port design

- Actor: agent (interactive session, not Ralph)
- Inputs: operator report "Run #212 in binding n8n doesn't look like it's running correctly"; read-only `podium.db`, `journalctl -u symphony-host.service`, live `ps`/`ss`, `runs/212.log`; code reads of `agent_runner.py`, `web/api/main.py`, `session_continuity.py`, `proc_runtime.py`, `ssh_support.py`, `config.py`, `bindings.yml`, `web/frontend/components/SessionTailPanel.tsx`; a `/grill-me` session on remote session tail + dead Plane code.
- Outputs: new ADR `docs/adr/0019-orchestrator-owns-agent-io-tracker-port-and-remote-tail.md`; **built (working tree) remote session tail** — `proc_runtime.tail_spool_path`, `_drain_rpc_events(spool_path=…)`, `run_remote_agent` spool wiring+cleanup, `_SessionTailer` remote spool branch (`r.id AS run_id`), plus tests `test_drain_rpc_events_spools_assistant_deltas` + `test_tailer_reads_spool_for_remote_binding`; new raw session `wiki/raw/sessions/2026-06-21-remote-tail-and-tracker-port.md`; new promoted analysis `wiki/analyses/adr-0019-orchestrator-owns-agent-io.md`; updated `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0302/C-0303/C-0304 added), `wiki/log.md`.
- Notes: Run #212 was healthy (issue #89, pi/openai-codex gpt-5.5:high, succeeded/review in ~6m39s) — it only looked stuck because remote runs had no live tail. Built Thread B of ADR-0019: scheduler spools the SSH-piped pi RPC stream to `<runtime>/tail/<run_id>.log` for the web tailer (no `ssh tail -f`); `uv run pytest` 59 passed/1 skipped, `ruff` clean. **Not committed, not deployed (deploy = restart symphony-host + journal verify), not live-verified on a real remote run.** Thread A (tracker port: two-half adapter, agent-during-run canonical, Halo roadmap, registry, opaque `tracker_config:`, tunnel-as-inference) is **proposed/design-only** — pairs with the Halo adapter. Also surfaced the dead `-R 8000` Plane tunnel (C-0304). Unresolved: commit+deploy+live-verify the remote tail; build the tracker port for Halo.

## [2026-06-23] session-update | Run #234 review → resume-mode dropped Schedule Context (C-0300 root cause confirmed + fixed)
- Actor: agent (Symphony unattended, issue #95).
- Inputs: operator question on Run #234 + reply "Proceed with fix you outline"; reads of `runs/234.log`, `prompt_renderer.py`, `session_continuity.py`, `scheduler/__init__.py` (`_with_schedule_context`/`_invoke_renderer`/`_prepare_resume_candidate`), homelab `CLAUDE.md` + `tickets/74.md`, `wiki/analyses/adr-0018-...md`.
- Outputs: fix in `prompt_renderer.py` resume branch (re-append `_render_schedule_context` for non-coding bindings); 2 regression tests in `tests/test_prompt_renderer_podium.py`; CLAIMS C-0305; updated ADR-0018 analysis ("Resume-mode dropped the Schedule Context" section); this log entry.
- Notes: Run #234 blocked an image prune because the resume-mode prompt discarded the `## Schedule Context` block (the homelab policy apply-now signal) — the structural cause behind C-0300 resumed-session hypothesis. Verified: `pytest test_prompt_renderer_podium.py test_prompt_renderer.py test_scheduler.py test_session_continuity.py` → 205 passed. NOT committed or deployed; item 5 clean schedule-and-apply verify still required before #098 item 6 (re-open blocked backlog 63/66/71/74/75/76).

## [2026-06-23] session-update | Issue #97 disable issue Telegram notifications
- Actor: agent (Symphony unattended, issue #97).
- Inputs: issue request to disable Telegram notifications for issues; code reads of `main.py`, `agent_runner.py`, `plane_cli.py`, `config.py`, `scheduler/__init__.py`, `notifier.py`; wiki Telegram operations pages.
- Outputs: issue Telegram opt-in flag `SYMPHONY_ISSUE_TELEGRAM_NOTIFICATIONS`; default scheduler notifier disabled; agent Telegram credentials withheld unless opted in; `plane_cli` Telegram guarded by the same flag; updated tests; updated `wiki/concepts/symphony-operations.md`, `wiki/sources/runbook-symphony.md`, `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0015 superseded, C-0306 added), and this log entry.
- Notes: Systemd failure Telegram alerts (`telegram-alert@%n.service` / `send-telegram-systemd-alert`) remain unchanged. Verification recorded in the issue summary.

## [2026-06-23] decision | Issue #102 "Tralph" → ADR-0021 board-grind-is-Symphony-dispatch

- Actor: agent (Symphony unattended, Podium Issue #102)
- Inputs: tralph alias lookup (`~/.zshrc` → `~/.claude/skills/ralph/ralph-loop.sh`, ralph SKILL.md, supervise/service); scheduler/tracker reads (`scheduler.py` run_loop, `tracker_podium.list_candidates`/`list_issues`, `web/api/schema.py` binding/binding_settings, `bindings.yml`); operator reply "go with option b"
- Outputs: `docs/adr/0021-board-grind-is-symphony-dispatch-per-binding-pause.md` (proposed); kanban slices `.kanban/issues/105`–`109`; this log entry
- Notes: Decision — Symphony's scheduler already grinds each binding's `todo` column continuously (FIFO by created_at); the gap vs tralph is start/stop, delivered as a runtime `dispatch_paused` flag in `binding_settings` (pause = stop starting new work, not abort) + a UI toggle; status reuses existing board/run surfaces. Deferred tralph-fidelity gaps: priority-ordered selection, dependency model (no Podium `blocked_by` column), fresh-session review-after-DONE. **SUPERSEDED same day by the entry below — operator dropped start/stop/control; the pause ADR + slices 105-109 were deleted (never built) and replaced with the dependency/parallelization design.**

## [2026-06-23] decision | Issue #102 "Tralph" pivot → ADR-0021 issue dependencies + parallel dispatch

- Actor: agent (Symphony unattended, Podium Issue #102)
- Inputs: operator reply "no more need for start/stop/control... we do need some sort of dependency and parallelization"; code reads — `scheduler/__init__.py` `_effective_run_cap`/`config.run_cap` (default 2, env `SYMPHONY_RUN_CAP`), `tracker_podium.list_candidates`/`list_issues`, `web/api/schema.py` issue table, `web/cli/podium_issues.py` (line 17: blocked_by is advisory-only), `web/api/main.py` IssueCreate
- Outputs: rewrote `docs/adr/0021-podium-issue-dependencies-and-parallel-dispatch.md` (proposed; replaces the deleted pause-design ADR); replaced kanban slices `.kanban/issues/105`–`109` with dependency slices; this log entry. Deleted: the pause ADR + the 5 pause slices (never built).
- Notes: Key finding — parallelization ALREADY exists (per-binding `run_cap` semaphore, default 2); the real gap is ENFORCED dependencies. Decision: add `issue.blocked_by` (JSON id array, mirrors `.kanban` frontmatter) via Alembic 0010; gate candidate selection so a `todo` issue dispatches only when all blockers are `done`/`archived` (gated issue STAYS `todo`, NOT flipped to `blocked` state); unknown blocker id → treated satisfied + warn; cycles rejected at write time; carry `blocked_by` through the mirror (kanban-id→podium-id) + create/patch API; read-only "waiting on #N" UI chip; parallelism knob stays `run_cap`. **CORRECTED by the entry below — dependency-gating is necessary but not sufficient.** Pending wiki promotion: `analyses/adr-0021-*.md` page + `index.md`/`ROUTING.md`/`CLAIMS.md` — defer until ADR accepted or build lands.

## [2026-06-23] decision | Issue #102 corrected root cause — shared-tree co-run conflict (ADR-0021 Update section)

- Actor: agent (Symphony unattended, Podium Issue #102)
- Inputs: operator reply "which ones can run at the same time without conflicting with each other's work in the same tree"; code read `scheduler/__init__.py` `_dispatch_cwd` (runs in shared `repo_path` unless `worktree_active`, opt-in/off by default) + `_effective_run_cap` (local coding = run_cap=2)
- Outputs: appended "Update 2026-06-23 — corrected constraint" section to `docs/adr/0021-podium-issue-dependencies-and-parallel-dispatch.md`; this log entry. Kanban slices 105-109 unchanged (still valid).
- Notes: Root cause — `run_cap=2` + no default worktree means two agents `cd` into the SAME live checkout and stomp uncommitted edits/index; ANY two concurrent shared-tree coding runs conflict (independent or not). Safe parallelism needs 3 layers: (1) isolation enabler [worktree-per-run, exists opt-in], (2) dependency ordering [ADR-0021], (3) mutual-exclusion/resource key so isolated parallel runs don't collide at merge [NEW, unspecified]. Open fork awaiting operator: P1 safe floor = `_effective_run_cap` returns 1 when not worktree-isolated (tiny, kills all conflicts, no parallelism); P2 = worktree-per-run default + mutex/resource layer (real conflict-free parallel). Recommended P1 now → then dependency + P2. Mutex model to be a follow-up ADR once parallelism target chosen.

## [2026-06-23] decision | Issue #102 — operator chose P2; ADR-0021 converged on 3-layer conflict-free parallelism

- Actor: agent (Symphony unattended, Podium Issue #102)
- Inputs: operator reply "P2 — Real conflict-free parallelism"; code reads — `worktree_facade.py` (API: `branch_name`, `create_worktree`, `remove_worktree`, `worktree_dir`, `worktree_exists`, `worktree_is_dirty`), `scheduler/__init__.py` `_worktree_run_fields` (line 385, opt-in `worktree_active` gate) + `_dispatch_cwd` (line 427) + `_effective_run_cap`, `config.py` `worktrees_root`
- Outputs: appended "Update 2026-06-23 (2) — operator chose P2" section to `docs/adr/0021-podium-issue-dependencies-and-parallel-dispatch.md` (fork resolved to P2; mutex model folded in, no follow-up ADR); restructured kanban slices — 105 schema now adds BOTH `blocked_by` + `locks` columns (Alembic 0010), 106 dependency gate, 107 write-paths carry both, NEW 108 worktree-per-run default-ON for local bindings, NEW 109 mutual-exclusion lock gate, renumbered 110 UI chip (waiting + locked), 111 MANUAL deploy+verify; this log entry
- Notes: Decision — P2 ships three layers together. (1) ISOLATION: invert `_worktree_run_fields` so local (non-remote) runs get a worktree by default; deterministic `worktree_dir(repo,binding,issue_id)` so warm/resumed sessions re-enter same path; remote unchanged (cap 1). (2) DEPENDENCY: `blocked_by` gate (unchanged). (3) MUTUAL EXCLUSION: `locks` JSON label-set per issue; a `todo` candidate is eligible only if its locks are disjoint from in-flight locks AND from locks claimed earlier in the same tick — both lock-gated and dep-gated issues STAY `todo` (no new state). Chose label-SET over single mutex-group key (correct on multi-area edge case, same code size, ponytail rule). JSON columns over join table (single-user scale, mirrors kanban frontmatter). Locks are operator-authored advisory hints, not path-derived (YAGNI). Slices dogfood the feature: 106/108/109 all `locks: [scheduler]` so they serialize. Calibration risks flagged for MANUAL slice 111: warm-session worktree re-entry, worktree cleanup/disk, self-binding dogfood. **Design only — no live code; slices 105-111 are grindable but the live Alembic 0010 + scheduler change is hard-to-reverse and needs an explicit "build it" (slice 111 is operator-gated MANUAL).** Pending wiki promotion: `analyses/adr-0021-*.md` + index/ROUTING/CLAIMS — defer until ADR accepted or build lands.

## [2026-06-23] decision | Issue #102 — authoring path: /podium-issues becomes a plan→Podium slicer (one skill)

- Actor: agent (Symphony unattended, Podium Issue #102)
- Inputs: operator reply wanting chain `grill-me → dev-plan → podium-issues` with issues "created similarly to how to-issues slices up plans but adapted for podium", and NOT a folder scan / second skill; reads — `~/.claude/skills/to-issues/SKILL.md` (vertical-slice slicing rules), `~/.claude/skills/podium-issues/SKILL.md` (current behavior = DB-direct kanban→Podium mirror via `web.cli.podium issues import-kanban`)
- Outputs: appended "Update 2026-06-23 (3) — authoring path" section to `docs/adr/0021-...md`; reframed slice 107 (API-only `blocked_by`+`locks`+cycle-reject; mirror demoted to optional Ralph bridge — drop kanban-id→Podium-id translation from critical path); NEW slice 112 (repurpose `/podium-issues` into a plan slicer; rename old mirror to `/podium-mirror-kanban`); this log entry
- Notes: Key clarification — `/podium-issues` ALREADY EXISTS today as a folder mirror (operator thought it'd be new). Decision: repurpose it into a plan slicer that writes straight to Podium (reuse to-issues slicing rules, sink=Podium not `.kanban`), creating issues in dependency order so `blocked_by` uses real Podium ids inline (no kanban-id translation) and setting `locks` per slice. `.kanban` bypassed for the Podium path; it stays source-of-truth only for the Ralph local-coding loop (still `/to-issues`); old mirror kept solely as Ralph→Podium bridge under a new name. Tradeoff flagged (operator may reverse): direct-to-Podium issues live in SQLite, not git — no version-controlled diff of what a plan produced; slicer could optionally also emit `.kanban` byproduct if git-traceability wanted. Still design only — no code; needs "build it".

## [2026-06-23] decision | Issue #102 — operator confirmed: no folder mirroring, direct-to-Podium; mirror retired

- Actor: agent (Symphony unattended, Podium Issue #102)
- Inputs: operator reply "This looks good except for no folder mirroring right directly to the podium path" — approval of the slicer design with the tightening that there is to be NO folder mirroring at all
- Outputs: edited ADR Update (3) (mirror RETIRED, not renamed/kept; tradeoff marked accepted not "may reverse"); slice 107 dropped the legacy-mirror bullet (API-only, no kanban-id translation anywhere); slice 112 changed from "rename mirror to /podium-mirror-kanban" to "retire the old folder-mirror skill"; ADR slice-list updated; this log entry
- Notes: Resolves both open calls from the prior turn — (1) naming moot: `/podium-issues` is simply the slicer, the old folder-mirror is removed; (2) no-`.kanban`-for-Podium-path tradeoff ACCEPTED (issues live in Podium SQLite, not git). `.kanban` + `/to-issues` survive only for the unrelated Ralph local-coding loop. Design now locked. Still no code — slices 105-110 + 112 are grindable; live deploy 111 stays operator-gated MANUAL; awaiting "build it".

## [2026-06-23] session-update | Issue #108 wiki-update — nothing to capture; gate.py schema-incompatible with this CLAIMS.md

- Actor: agent (Symphony unattended, Podium Issue #108)
- Inputs: issue "use llm-wiki-setup and wiki-update to update this repo's wiki"; ran llm-wiki-setup (wiki already initialized/healthy — no setup work), wiki-update SessionUpdate workflow; `gate.py audit`; reads of `gate.py:39-44,229-307` (BUDGET=40, COLD_HITS=1, COLD_AGE_DAYS=120, cmd_demote), `wiki/CLAIMS.md` header
- Outputs: NO wiki content change (no durable session knowledge — #108 is a meta "go update the wiki" task with no engineering session). This log entry only.
- Notes: **GOTCHA for future wiki-update runs — do NOT run `gate.py demote` (no `--force`) against this wiki.** `gate.py` expects `Created`/`Hits` columns; this `CLAIMS.md` header is `ID|Claim|Source|Page|Confidence|Status|Notes` (neither column). So `age_days`→∞ and `Hits`→0 for every row, making the hits≤1 AND age>120d auto-demote criteria match ALL 257 active claims. A verification `demote` I expected to be a no-op drained 248 claims to `CLAIMS-cold.md`; reverted via `git checkout -- wiki/CLAIMS.md && rm CLAIMS-cold.md` (proved lossless: arrival audit 257 active == post-revert 257). Consequences of the schema mismatch: (1) `gate.py audit` permanently reports `over budget: 257 > 40` (exit 5) — config drift, not a content problem; budget 40 is a stale default never tuned to this wiki's real scale. (2) consolidate refuses (no `wiki/eval/*.eval` slice exists). Operator decision needed: raise BUDGET to match real scale, OR teach `gate.py`/`CLAIMS.md` a `Created`/`Hits` schema, OR seed an eval slice before any consolidation. Working tree also holds a large uncommitted Issue #102 session (agent_runner.py, frontend, `.kanban/105-110`, ADR-0021 log entries) — left untouched.

## [2026-06-23] decision | ADR-0022 — post the agent's captured turn, not a forced SYMPHONY_SUMMARY block

- Actor: agent (grill-me session with James) + James (decisions)
- Inputs: dotfiles Issue #105 / Run #310 review (operator asked for a reusable prompt; agent narrated it but the artifact never reached the comment); reads of `prompt_renderer.py` (`OUTPUT_CONTRACT`), `claude_runner.py` (`_wrap_prompt` result-file protocol), `agent_runner.py` (`_drain_rpc_events`/`assistant_parts`/`run_pi_rpc_agent`), `config.py` (`claude_persist` default + caps), `bindings.yml`; existing `#046`/ADR-0007/ADR-0019 wiki pages
- Outputs: new `docs/adr/0022-post-the-agents-captured-turn-not-a-forced-summary.md` (`proposed`); new promoted analysis `wiki/analyses/adr-0022-post-captured-turn-not-forced-summary.md`; superseded-banner on `wiki/analyses/podium-046-unified-output-contract.md`; planned-change note on `wiki/concepts/prompt-renderer.md`; index row; ROUTING Decisions + output-contract route updates; CLAIMS C-0308 (decision) + C-0309 (engine already captures the turn) added; C-0160/C-0161 forward-pointed (still `active`, current code)
- Notes: Decision is PROPOSED — not built, not deployed. Key finding: the engine already captures the agent's natural turn (pi `assistant_parts`; claude transcript JSONL) and discards it by sub-extracting only the summary block, so the fix is a re-route, not new machinery; pi needs no `OUTPUT_CONTRACT` wording crutch. Partially supersedes ADR-0007/#046 comment-stream design; companion to ADR-0019 (same principle, return path). Related-but-separate parked item: flip `claude_persist` default `False→True` for local bindings (`config.py:101`), own soak (8-slot cap / 45-min TTL), remote excluded by config; does not fix this bug.

- 2026-06-23 — manual wiki-update: promoted ADR-0012 remote-Claude v2 calibration evidence from Issue #104 / Runs #324-#325; added raw session `wiki/raw/sessions/2026-06-23-remote-claude-live-calibration.md`; updated docs ADR, wiki analysis/index/ROUTING, and CLAIMS C-0313.

## [2026-06-24] session-update | Podium API stale model validator emptied Model dropdown

- Actor: agent (Pi), via `symphony-models` skill.
- Inputs: operator report that adding same Claude/Pi models made both new-Issue Model dropdowns empty; `models.yml`; `model_catalog.py`; `web/api/main.py`; `web/api/tests/test_issue_create.py`; `systemctl show podium-api.service -p MainPID -p ExecMainStartTimestamp -p ActiveState -p FragmentPath --value`; focused pytest validation.
- Outputs: new raw capture `wiki/raw/sessions/2026-06-24-podium-api-model-dropdown-stale-validator.md`; updated `wiki/analyses/podium-issue-dispatch-contract.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0315); updated `wiki/eval/model-catalog.eval`; this log entry.
- Notes: Current repo catalog is valid (`_load_models(Path('models.yml'))` → 13 models; skill tests 7 passed; model/options tests 20 passed). Live `podium-api.service` was started before the tuple-identity validator landed, so its old validator can raise on duplicate bare ids; `/options` catches that `ValueError` and returns `models: []`, making both agent dropdowns empty. No `models.yml` edit needed. No service lifecycle action was taken because `symphony-models` forbids restarts; remediation is restarting `podium-api.service` through an appropriate ops path and refreshing the browser. No env file, secret, or Podium SQLite row was read.

## [2026-06-24] grill-me + manual wiki-update | ADR-0023 native per-issue review phase + provenance-gated auto-land

- Actor: agent (Claude), grill-me design session on Podium Issue #102 "Tralph" follow-up.
- Inputs: operator question ("in tralph after each issue there are review follow-up runs... how can we add this to podium issues"); `~/.claude/skills/ralph/SKILL.md`, `~/.claude/skills/dev-review-pi/SKILL.md`; `docs/adr/0021-...md`, `docs/handoffs/2026-06-23-p2-conflict-free-dispatch-review-test.md`; `scheduler/__init__.py`, `prompt_renderer.py` (INFRA_PREAMBLE/ADR-0016), `web/api/main.py` (`_maybe_merge_worktree`, `MAX_COMMIT_REDISPATCH`), `web/api/schema.py` (issue table, `IssueCreate`); `.kanban/issues/105-113`, `bindings.yml`.
- Outputs: new ADR `docs/adr/0023-native-per-issue-review-phase-and-auto-land.md` (proposed); raw session `wiki/raw/sessions/2026-06-24-native-per-issue-review-phase-grill.md`; analysis `wiki/analyses/adr-0023-native-per-issue-review-phase.md` (promoted); updated `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0316); this log entry.
- Notes: Decision reverses ADR-0014's operator-merge invariant for the slicer-authored (auto_land) subset only. New work past the locked ADR-0021 slice set — needs its own slices (schema+migration, scheduler review-phase dispatch+marker+terminal, REVIEW_PREAMBLE constant, slicer auto_land stamp, MANUAL deploy). Not built, not deployed. Auto-promoted (single-author design capture, no broken links/duplicate concepts introduced).

## [2026-06-24] dev-review-claude + slice rework | ADR-0023 trigger/merge mechanics corrected

- Actor: agent (Claude); independent dev-review-claude (opus) pass over the first ADR-0023 slice draft, then rework.
- Inputs: `docs/adr/0023-...md` + draft slices 114-120; verified against `scheduler/__init__.py` (candidate selection STATE_TODO gate ~1263, `_classify_terminal` ~1627, terminal handler ~2037), `web/api/main.py` (`_maybe_merge_worktree` 1561, `patch_issue` merge trigger ~1141, `MAX_COMMIT_REDISPATCH`/`_redispatch_to_commit`), `worktree_facade.py` (__all__ lacks merge_worktree), `web/api/worktree.py`.
- Findings: 4 Critical (scheduler can't trigger merge via transition; cross-process `_maybe_merge_worktree` call; nothing re-dispatches a `running` issue; dirty-worktree redispatch-to-`todo` breaks the never-todo invariant), 5 Warning, 6 Note. No working-tree drift.
- Outputs: deleted old slices 117-120; wrote reworked slices `.kanban/issues/117-122` (117 land_worktree extraction, 118 in_review-driven review selection, 119 provenance-gated terminal, 120 driver backstop, 121 slicer stamp, 122 MANUAL); patched `docs/adr/0023-...md` (trigger model, land_worktree, dirty-worktree guard, no-retry, slice plan, ADR-0021 105 path note); updated `wiki/index.md`, `wiki/analyses/adr-0023-native-per-issue-review-phase.md`, `wiki/CLAIMS.md` (C-0316 rewritten), `wiki/ROUTING.md`, raw session revision note, this log entry.
- Notes: Design still PROPOSED, not built. Schema/API/preamble/slicer slices (114/115/116/121) unchanged in intent; rework concentrated in trigger (in_review selection) + merge seam (land_worktree).

## [2026-06-24] session-update | Issue #107 blocked_by/locks API write path

- Actor: agent (Pi), Ralph implementation + fresh review.
- Inputs: `.kanban/issues/107-blocked-by-write-paths.md`; `web/api/main.py`; `web/api/tests/test_issue_create.py`; `web/api/tests/test_issue_patch.py`; issue verification command.
- Outputs: marked `.kanban/issues/107-blocked-by-write-paths.md` done; updated `.kanban/progress.md`; updated `wiki/concepts/podium-tracker.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0317); added `wiki/eval/podium-api.eval`; this log entry.
- Notes: #107 carries `blocked_by` and `locks` through Podium create/patch API as JSON-backed typed lists, returns omitted values as `[]`, and rejects `blocked_by` cycles with HTTP 400. Verification passed exactly as issue-specified (`uv run pytest web/api/tests/test_issue_create.py web/api/tests/test_issue_patch.py -q`, 90 passed); touched-file LSP diagnostics were clean; fresh review returned `RALPH_REVIEW: PASS`.

## [2026-06-24] session-update | Issue #108 local coding worktree default

- Actor: agent (Pi), Ralph implementation + fresh review.
- Inputs: `.kanban/issues/108-worktree-per-run-default.md`; `config.py`; `scheduler/__init__.py`; `tests/test_config.py`; `tests/test_scheduler.py`; issue verification command.
- Outputs: marked `.kanban/issues/108-worktree-per-run-default.md` done; updated `.kanban/progress.md`; updated `wiki/analyses/analysis-session-worktree-done-commit-redispatch.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/CLAIMS.md` (C-0318, C-0249 dormant subfact superseded); this log entry.
- Notes: #108 makes local coding bindings default to deterministic per-issue worktrees via `SymphonyConfig.worktree_default` / `SYMPHONY_WORKTREE_DEFAULT` while remote bindings remain shared-repo. Dispatch marks Podium rows `worktree_active=True` so existing merge/cleanup handles terminal removal. Verification passed exactly as issue-specified (`uv run pytest tests/test_scheduler.py web/api/tests/test_worktree.py -q`, 203 passed); touched-file LSP diagnostics were clean; fresh review returned `RALPH_REVIEW: PASS`.

## [2026-06-25] session-update | ADR-0023 review-terminal provenance fix

- Actor: agent (Claude), /symphony-troubleshooter → fix → /symphony-restart.
- Inputs: handoff `/tmp/handoff-w7PtsT.md`; live journal `symphony-host.service` 2026-06-24 12:00-12:07; Podium DB issue #120 (runs 346/348/352); `scheduler/__init__.py` `_handle_review_terminal_done`; `tracker_podium.py` `review_dispatch`; ADR-0023 analysis page + C-0316/C-0323.
- Outputs: fix `scheduler/__init__.py` (commit `56302b9`) gating review terminal on `candidate.review_dispatch` not the persistent marker; regression test `test_review_terminal_skips_non_review_dispatch_run`; restarted `symphony-host` to code `56302b9` (live); updated `wiki/analyses/adr-0023-native-per-issue-review-phase.md`, `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0324 added, C-0323 subfact corrected); this log entry.
- Notes: root cause — `_handle_review_terminal_done` keyed provenance off the persistent `### Symphony Review` marker in comments_md instead of `review_dispatch`, so an operator `/reply` (in_review→todo reopen) re-dispatched a normal implement run that wrongly re-ran the review terminal (issue #120 run 352 = second `review-passed-awaiting-operator-merge`); for `auto_land=true` issues this could re-merge to `main`. Verification `uv run pytest tests/test_scheduler.py web/api/tests/test_worktree.py -q` (221 passed); touched-file LSP clean. Restart saw two transient `pi` probe-timeout crashes that self-healed via systemd auto-restart (unrelated; `main._probe_binding` untouched).

## [2026-06-24] bugfix + wiki-update | reply/comment flyout crash (undecorated gate fields, C-0325)

- Actor: agent (Claude); operator reported "Application error: a client-side exception" when sending a message in an issue.
- Inputs: `web/api/main.py` (`_decorate_issue_gates` 692, `/reply` 1428, `/comment` 1497, bare `_row` returns), `web/frontend/components/IssueFlyout.tsx` (`GateHints`), `web/frontend/components/QueryProvider.tsx` (websocket issue.updated → setQueryData), `web/frontend/components/IssueCard.tsx` (already-defensive `GateTags`).
- Root cause: `/reply`+`/comment` returned/published bare issue rows missing `unsatisfied_blocked_by`/`lock_conflicts`/`dependencies_satisfied`; `/reply` flips state to `todo` where the #110 chip's `GateHints` read them unguarded → undefined.length on the post-mutation re-render.
- Fix (commits 76d5d0d, 06fbe2b): decorate both endpoints via `_decorate_issue_gates`; harden `GateHints` to default fields to []; regression `test_reply_response_carries_gate_fields`. Deployed: `podium-api` restart + `web/frontend/deploy.sh` (NOT symphony-host).
- Outputs: raw session `wiki/raw/sessions/2026-06-24-reply-comment-undecorated-gate-fields-crash.md`; new section in `wiki/analyses/podium-issue-dispatch-contract.md` (Issue-payload gate-field decoration contract); `wiki/CLAIMS.md` C-0325; `wiki/index.md`, `wiki/ROUTING.md`, this log.
- Note: C-0324 was already taken by the ralph loop (ADR-0023 review-terminal provenance bug, 2026-06-25); this claim is C-0325.

## [2026-06-24] session-update | ADR-0024 landed + ADR-0026 retry follow-up

- Actor: agent (Pi/Claude), observing and manually recovering Podium issues #128-#132 after ADR-0024 slicing.
- Inputs: Podium issues #128-#132, run rows #389-#401, `podium.db`, issue comments, worktrees `worktrees/symphony/{130,131}`, `docs/adr/0024-review-mode-gate-and-dirty-commit-redispatch.md`, `docs/adr/0026-transient-failure-retry-not-block.md`.
- Outputs: committed `2450d83` adding ADR-0024 and ADR-0026 docs; added raw session `wiki/raw/sessions/2026-06-24-adr-0024-babysitting-roadblocks.md`; created `wiki/analyses/adr-0026-transient-failure-retry.md`; updated `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md` (C-0331), and this log entry.
- Notes: All ADR-0024 slices #128-#132 landed through `712469c`, but multiple recoveries were manual: Codex `server_is_overloaded` blocked #128/#129/#131; #130/#131 passed review but blocked during auto-land after `main` advanced and needed rebase/land re-drive; #131 hit a C-0327 claim-ID collision and was renumbered to C-0328. ADR-0026 captures the proposed retry/re-drive follow-up. Live restart was performed after cleaning unrelated dirty checkout files; startup then exposed two transient `verify_pi_support` timeouts that caused systemd restarts before the service stabilized on `0ca14fe`, so startup probe retry/fail-soft was folded into ADR-0026 as well.

## [2026-06-25] session-update | ADR-0026 fully landed + live, default model switch, parallel-slice land friction

- Actor: agent (Pi), shepherding ADR-0026 Podium slices #133-#137 through land and switching the default pi model.
- Inputs: Podium issues #133-#137, runs #405-#421, `podium.db`, worktrees `worktrees/symphony/{134,136,137}`, `models.yml`, `scheduler/transient_retry.py`, journal `symphony-host.service`, `~/.pi/agent/{models,auth}.json`.
- Outputs: raw session `wiki/raw/sessions/2026-06-25-adr-0026-land-and-model-switch.md`; updated `wiki/analyses/adr-0026-transient-failure-retry.md` (now fully implemented + live, allowlist expansion section); updated `wiki/index.md`, `wiki/ROUTING.md`; added claims C-0334 (default model = deepseek-v4-pro; supersedes C-0142), C-0335 (wiki-churn-on-parallel-land + duplicate-migration collision), C-0336 (agent stall-detection gap); raised claim budget 280→320 in `.gate-state.json`.
- Notes: All five ADR-0026 slices done and live after restart to `code_sha=fb799be`. #134 and #136 required manual land (auto-land failed on deterministic rebase conflicts: #134 wiki-churn only; #136 a real `_classify_terminal` code merge + a duplicate `0012_*_retry_verdict` migration deleted). Default pi model switched gpt-5.5/openai-codex → deepseek-v4-pro/deepseek (commit 96d25bb) to move off a flaking/stalling provider; live per-dispatch, no restart. Transient allowlist expanded (commit a35f327) to cover Codex `timed out`/`SSE`/`terminated` signatures that were escaping the retry path. A hung agent (frozen mid-compaction) held its lock ~50min until the 2h `run_timeout_ms` — killed manually; stall-detection gap recorded as C-0336. Contract gate `test_gate_passes_at_head` is red from live-DB corpus drift (0.9129 < 0.9314) — NOT caused by the model switch or ADR-0026; `scheduler/markers.py:14` verdict regex still missing `retry` (latent). Separate follow-ups: stall watchdog, defer-/wiki-update-to-post-land, contract-gate baseline/corpus decision.

## [2026-06-25] grill-me | ADR-0026 follow-ups resolved → ADR-0027/0028/0029

- Actor: agent (Pi), running /grill-me over the three open ADR-0026 follow-ups (C-0335, C-0336, contract-gate/markers).
- Inputs: `wiki/raw/sessions/2026-06-25-adr-0026-land-and-model-switch.md`; claims C-0335/C-0336; `wiki/analyses/adr-0026-transient-failure-retry.md`; code `agent_runner.py:406`, `config.py:175`, `scheduler/__init__.py` (reconcile_stale_running, in_flight_locks, _classify_terminal retry verdicts), `contract_gate.py`, `scheduler/markers.py:14`, `web/api/worktree.py:238`, `session_continuity.py`.
- Outputs: three accepted ADRs — `docs/adr/0027-agent-stall-watchdog.md`, `docs/adr/0028-slice-runs-exempt-from-wiki-obligation.md`, `docs/adr/0029-contract-gate-frozen-corpus.md`; CLAUDE.md Maintenance-Trigger carve-out (slices exempt from wiki obligation); `~/.claude/skills/podium-issues/SKILL.md` migration-lock rule (`locks: [migrations]`); claims C-0337/C-0338/C-0339; updated C-0335/C-0336 Notes to RESOLVED with ADR pointers.
- Notes: Stall watchdog (C-0336→ADR-0027): session-jsonl mtime signal, runner poll loop owns the kill, NEW stall retry class (sentinel-routed, `(stall · N)` marker, cap=1, reuses verdict=retry), N=`stall_timeout_ms` 15min global. Land friction (C-0335) split in two: wiki-churn→ADR-0028 (slices don't wiki-update; one consolidated operator-driven post-land pass; cause was CLAUDE.md, fixed there, no Symphony code change; staging+replay a1 rejected as degenerate); migrations→slicer emits `locks: [migrations]`, reusing existing dispatch lock enforcement (no Symphony code change). Contract gate→ADR-0029: freeze corpus to checked-in fixture (drift was DB hygiene not parser regression), seed from honest pre-drift 175-run corpus, baseline untouched; markers.py `retry` gap REJECTED by design (retry is machine-set, never agent-declared, never parsed). Implementations (watchdog, corpus freeze) pending /dev-plan. No secrets read. Service unchanged (`code_sha=fb799be`, healthy).

## [2026-06-25] dev-review-pi | validated the three follow-up ADRs (deepseek reviewer)

- Actor: agent (Pi), running /dev-review-pi (reviewer model deepseek/deepseek-v4-pro, read-only verified) over ADR-0027/0028/0029 + the CLAUDE.md carve-out + the podium-issues migration-lock rule.
- Inputs: docs/adr/0027,0028,0029; agent_runner.py (run_pi_rpc_agent, _drain_rpc_events, run_agent communicate path); bindings.yml; redispatch_core.py count_retries; contract_gate.py; scheduler/markers.py; scheduler/__init__.py.
- Outputs: reviewer findings cross-checked against code; ADR-0027 REWRITTEN (production path correction); ADR-0028 + ADR-0029 patched; claims C-0337/C-0338/C-0339 updated.
- Notes: CRITICAL finding (verified): ADR-0027's original premise was wrong — all bindings are pi_mode:rpc, so dispatch runs through `_drain_rpc_events` (agent_runner.py:1177, 0.5s line-poll), NOT the one-shot `process.communicate()` at agent_runner.py:406 the handoff/C-0336 assumed. ADR-0027 reworked: signal = RPC-event silence (richer than session-jsonl mtime, works for remote too); placement = a second silence deadline inside the existing drain loop reusing its abort+kill path (no communicate() surgery); added stall-aware counter + combined retry ceiling (count_retries only matches the transient prefix). Retry-class/sentinel/cap/N decisions survived intact. WARNINGS actioned: ADR-0028 gains a "wiki pass needed" land-finalizer marker to close the forgotten-consolidated-pass hole; ADR-0029 drift narrative softened (drift is a mix — some mid-line SYMPHONY_RESULT markers the ^-anchored regex correctly rejects, not purely empty logs) + fixture must include locked runs 30/39/120 + a mid-line example. CONFIRMED sound: markers.py retry rejection (reviewer traced an independent failure mode), slicer migration-lock, frozen-corpus core decision. Out of scope (pre-existing): reconcile_stale_running transitions tracker state but never SIGKILLs a lingering process — separate follow-up. No secrets read; reviewer modified nothing (git status before==after).
### session-update 2026-06-26
- **Inputs**: dev-build + dev-test for ADR-0029 contract gate frozen corpus; raw session capture 
- **Outputs**: C-0340 (ADR-0029 implemented), C-0341 (mid-line detection gap), C-0339 marked superseded, ROUTING updated
- **Unresolved**: CI not wired for contract gate tests; mid-line run 9999 detection gap (gate only catches regressions, not false-positives)


## 2026-06-26 — ADR-0022 implementation landed

- **C-0308 promoted from `proposed` to `accepted`**: implementation complete per `plans/adr-0022-post-captured-turn.md`.
- **10 implementation tasks** across 4 phases complete:
  - Phase 1: `DISPLAY_MAX_CHARS` + `_bound_display` (pre-existing), `_redact_stream` extracted from `_extract_summary`
  - Phase 2: `_capture_natural_turn` in scheduler; `_extract_summary` as fallback; placeholder removed
  - Phase 3: `_extract_last_assistant_turn` in claude_runner; wired into `_poll_claude_until_done`; separator handling
  - Phase 4: `OUTPUT_CONTRACT` updated; `tests/test_captured_turn.py` (13 new tests); wiki updated
- **896 tests pass** (13 new captured-turn tests + 883 existing, 0 regressions).
- **C-0161 marked `superseded`** (verbatim-summary posting walked back); C-0160 updated (summary block now fallback).
- Files changed: `scheduler/sanitize.py`, `scheduler/__init__.py`, `claude_runner.py`, `prompt_renderer.py`, `tests/test_captured_turn.py`, `tests/test_scheduler.py`, `tests/test_dispatch_compaction.py`, `tests/test_trading_podium_dispatch.py`, `wiki/CLAIMS.md`, `wiki/analyses/adr-0022-post-captured-turn-not-forced-summary.md`

## session-update 2026-06-27 — land-on-done hardening (done means landed)
- **Inputs**: `/dev-build` of `plans/land-on-done-harden.md` (5 Pi-review findings folded; converged round 3), commit `67d5921`, symphony-host restart, live #126 clean-path land validation (`67d5921..129f109`); raw session `wiki/raw/sessions/2026-06-27-land-on-done-harden.md`.
- **Outputs**: candidate promoted to `analyses/analysis-session-land-on-done-harden.md` (extends ADR-0014 page); claims C-0344 (`done means landed` deferred persistence), C-0345 (operator-reland marker distinct from review RELAND), C-0346 (`_handle_operator_reland` closes dirty-loop dead-end) admitted via gate; index.md Analyses row added; ROUTING.md Architecture keywords extended.
- **Notes**: Distinct operator-reland marker is the single load-bearing constraint (reusing review RELAND_PENDING triggers review-run reselection loops in `tracker_podium.list_candidates`). Split-land dispatch race is mitigated (merge_worktree→re-check→abort/finalize) NOT closed — cross-process landing lease is a documented deferred follow-up. Wave-end pi audit 0 critical/1 warning (remote mid-merge abort untested → closed inline). Same session also caught up live DB Alembic 0011→0012 (unrelated routine migration; no new claim). No secrets read (live PATCH used the auth-free TestClient pattern, test password hash). Possible new ADR for "done means landed" trade-off deferred to James.
- **Unresolved**: ADR decision (author `0030-done-means-landed`?); cross-process landing lease to fully close the dispatch race.

## session-update 2026-06-29 — GFM table renderer + deploy.sh stale-cache/restart-cancel traps
- **Inputs**: Issue 146 GFM table rendered as literal pipes in Podium web UI; diagnosis (missing `remark-gfm`), fix, deploy, two `deploy.sh` defects hit while shipping; raw session `wiki/raw/sessions/2026-06-29-gfm-table-renderer-and-deploy-stale-cache.md`.
- **Outputs**: Promoted page `analyses/podium-frontend-deploy-cosmetics.md` extended with two new sections (third deploy hazard: stale `.next/cache` → byte-identical bundle; `deploy.sh` stop→start restart-cancel race) + 3 follow-ups; claims C-0347 (stale-cache deploy trap), C-0348 (restart-cancel race), C-0349 (react-markdown v9 needs remark-gfm for GFM tables) admitted via gate; index.md Analyses row updated (3 hazards catalogued); ROUTING.md Operations keywords extended (stale webpack cache, systemctl cancel race, remark-gfm).
- **Notes**: Renderer fix is correct and standard (react-markdown v9+ split GFM to `remark-gfm` plugin; `Markdown.tsx` now passes `remarkPlugins={[remarkGfm]}` + minimal Tailwind table styling; retroactive to all existing rows — markdown rendered at view time, comments append verbatim per ADR-0017). Distinct from the two deploy hazards already on the page — this is a *third* trigger where a "successful" deploy ships old code. Proven server-side (served chunk md5 == on-disk; identical md5 across `.next`/`.next.prev` pre-bust). `sw.js` returned 200 but was Next HTML — not a real service worker (red herring, not captured). The restart-cancel race is timing-dependent (clean second deploy didn't reproduce). No secrets involved.
- **Unresolved (operator-gated, deferred)**: patch `deploy.sh` to `rm -rf .next/cache` before build (C-0347 prevention); patch `deploy.sh` restart to be self-healing (poll `is-active` through `deactivating` before `start` / retry on cancel, C-0348 prevention); add Playwright regression lock for GFM table → `<table>`; commit the 3 frontend working-tree changes (`Markdown.tsx`, `package.json`, `pnpm-lock.yaml`).

## session-update 2026-06-30 — onboard `agency` binding; fix smoke-skill two-run claim, `_append_binding` comment-stripping, onboard stale-sha note
- **Inputs**: Onboarded `/home/james/agency` (coding, pi, rpc) via `symphony-onboard-project` — scaffold + restart (code_sha 88a0e70→8874f71, bindings=6) + smoke (issue #153, run #549 succeeded, deepseek/deepseek-v4-pro:high, no diff, parked `in_review`). Three friction points surfaced and fixed. Interactive session (not a Podium slice).
- **Outputs**: (1) `symphony-binding-smoke` SKILL.md step 5 + safety rule corrected — review phase is `auto_land`-gated (`tracker_podium.list_candidates`, issue #149 / ADR-0023 #3), so an operator smoke (`auto_land=false`) is ONE run → `in_review`, not two; `poll_podium_issue_run`-stops-at-first-run note added. (2) `skill_migration._append_binding` switched from safe_load→dump→rewrite to read-only-parse + text-append matching detected indent; existing entries/comments/blank-lines preserved byte-for-byte (new test `test_append_binding_preserves_existing_formatting_and_comments`); append to live `bindings.yml` now a 12-line diff vs prior 60-line whole-file rewrite. (3) `symphony-onboard-project` SKILL.md step 3 note: chained restart reflects disk head, so a stale running `code_sha` lands every commit since last boot. Claim C-0350; C-0171 open follow-up annotated RESOLVED; `entities/binding-symphony.md` + `analyses/symphony-skills-index.md` updated.
- **Notes**: #1 and #3 are doc-only; #2 is the live-code change done test-first (red→green), 28 skill tests pass. Auto-restart-on-push for the stale-sha drift was rejected — it would kill in-flight agent runs (advisor); manual restart + existing pre-sanity stale-sha detection is correct for a long-running scheduler. The earlier 2026-06-30 `agency` scaffold had already re-dumped `bindings.yml` (cosmetic, all fields preserved) — left as-is; the fix only governs future scaffolds. `_remove_binding` still round-trips by design (must rewrite the list to delete a block). No secrets; `.env` untouched.
- **Unresolved**: none.

## session-update 2026-06-30 — prompt-bloat cleanup + plan/build mode removal (ADR-0031, C-0351)
- **Inputs**: Interactive grill-me session. Operator asked to identify dispatch prompt bloat (after confirming the comment-stream change was ADR-0022 working as designed), then chose to remove engine-owned plan/build entirely (surgical option A) and control plan-vs-build via the issue body. Working tree on `af7ccbd`; not committed/deployed. Raw session `wiki/raw/sessions/2026-06-30-prompt-bloat-cleanup-plan-build-removal.md`.
- **Outputs**: ADR `docs/adr/0031-operator-driven-plan-build-not-engine-modes.md`; promoted analysis `analyses/adr-0031-operator-driven-plan-build.md`; claim C-0351 (decision) admitted via gate; C-0276 Notes forward-pointed (its `INFRA_PREAMBLE` plan/build sections now removed); index.md Analyses row added; ROUTING.md Plan/Build/Approve + Output-contract + Decisions branches extended; CONTEXT.md Mode + Tracker Contract glossary entries corrected.
- **Four findings fixed**: (1) double comment injection on the Podium path — `render_prompt` embeds `comments_md` AND `_render_for_dispatch` re-appended it; gated the append on `not stores_context` (Plane-only); regression `test_podium_dispatch_injects_comments_once`. (2) removed the `mode == "build"` scheduler gate (~105 lines), constants, orphaned plan-path helpers, `mode_for_skill` import, and Plan/Build sections of `INFRA_PREAMBLE`. (3) duplicate rule 17 resolved. (4) trimmed OUTPUT_CONTRACT summary-override block + rewrote preamble rules 12/14/15 to the ADR-0022 captured-turn model. Also removed two pre-existing dead helpers (`_state_path_for_plan`, `_final_non_empty_line`).
- **Notes**: Surgical/reversible — kept `_resolve_mode`, `gate.mode` (logging), `mode_for_skill`/`SKILL_TO_MODE`, the `preferred_skill`→`plan`/`build` label projection, Plane `MODE_PLAN`/`MODE_BUILD` enums, and `dev-plan`/`dev-build` skills all INERT (no engine branch acts on them). Full rip-out rejected (churn, Plane dormant, no behavioral gain). 1224 passed / 2 skipped; ruff + LSP clean. ~84 ins / 613 del across 6 source/test files. No secrets touched.
- **Unresolved (operator-gated)**: deploy = `symphony-host.service` restart (live dispatcher) — NOT done; changes not committed. Deferred cleanup: vestigial `render_prompt` `path` param, dormant `context_md` plumbing, the inert plan/build vocabulary, and the dead `WORKFLOW.infra.md` template (ADR-0016 residue).

## session-update 2026-06-30 — worktree opt-out + dispatch hold gate (C-0352, C-0353; C-0318 superseded)
- **Inputs**: Interactive `/dev-build` rebuild of `plans/feature-manual-issue-worktree-optout-and-hold.md`. A prior dev-build run had marked the plan `converged`/`outcome: passed` ("Build: complete"), but verification showed NONE of the 21 tasks landed — clean `main`, no `0013` migration, `_worktree_enabled` fallback still present, slicer still stamping `worktree_active=0`, and the live `symphony-host.service` (cwd == this checkout) running without the feature. The prior `plans/.feature-...state.yml` `build_audits` entry was stale/aspirational. Rebuilt from scratch inline (tightly-coupled schema→API→tracker→frontend chain; one orchestrator, one full-diff pi audit).
- **Outputs**: (1) `scheduler._worktree_enabled` binding_type=="coding" fallback removed → worktree only when `worktree_default AND worktree_active` (restores C-0063 opt-in; manual issues run in main checkout). Slicer `_insert_issue` now stamps `worktree_active=1`. (2) New `issue.hold` column (Alembic `0013_issue_hold`, last column in `CREATE TABLE issue`, `INITIAL_REVISION` bumped to `0013_issue_hold`); `list_candidates` skips held `todo` issues; threaded through API create/patch/coercion/non-null-guard/INSERT/SELECTs + frontend types, NewIssueModal checkbox, IssueFlyout ChipToggle. New claims C-0352 (worktree fallback removed) + C-0353 (hold gate); C-0318 marked superseded by C-0352. Stale `build_audits` entry in the plan state YAML replaced with the fresh `outcome: passed` rebuild record.
- **Verification**: full `uv run pytest -q` = 1230 passed/2 skipped; `pnpm tsc --noEmit` clean; `test_alembic_baseline.py` (migration head fingerprint == SCHEMA_SQL) passes; wave-end pi review `[NOTE] No findings`. Fixed 4 fallback-dependent suites beyond the plan's named two (test_review_terminal_remote_auto_land_uses_remote_worktree; two test_dispatch_compaction claude-resume tests via the `_seed_db` worktree_active stamp) by setting `worktree_active=True` to match the slicer stamp.
- **Notes**: Not committed/deployed — deploy = `symphony-host.service` restart (live dispatcher) + `podium-api`/frontend for the UI bits; left for the operator. Deferred wiki enrichment (optional): a dedicated `concepts/` page for the dispatch-hold + worktree-opt-out could be promoted later; for now the two claims point at the existing worktree analysis page + podium-tracker concept page.
- **Unresolved**: none (build complete + audited; deploy/commit operator-gated).

## maintenance 2026-06-30 — podium-web stop.conf drop-in (next-server SIGTERM-hang; C-0354)
- **Inputs**: Interactive follow-up to the hold/worktree deploy. The flagged issue: `web/frontend/deploy.sh`'s `systemctl stop` aborted mid-swap ("Job for podium-web.service canceled") during the earlier deploy, flapping the unit onto the old build. Diagnosed before fixing.
- **Diagnosis (reproduced)**: instrumented `systemctl restart podium-web` took exactly 90.16s = full `TimeoutStopUSec`. Cgroup probe showed `main=0` (pnpm gone) while `next-server` stayed alive in the unit cgroup in `deactivating` until SIGKILL. `next-server` (Next.js 15.1.3) ignores BOTH SIGTERM and SIGINT — deterministic, not intermittent (an earlier "fast stop" was a misread; that unit's next-server had already been SIGKILLed by the prior timed-out stop).
- **Fix**: drop-in `/etc/systemd/system/podium-web.service.d/stop.conf` = `KillSignal=SIGINT` + `TimeoutStopSec=10s`. The bounded timeout makes `systemctl stop` return rc=0 in ~10s (unit → `failed`/Result=timeout, but a manual stop suppresses `Restart=on-failure`, so no flap); `deploy.sh` stop→swap→start then proceeds. SIGINT is inert today (kept for the day next-server handles it); the 10s bound is the active fix. ~10s web downtime per deploy accepted (internal ops UI). Note: unit-file directive is `TimeoutStopSec=`, NOT `TimeoutStopUSec=` (that's the D-Bus property name — first attempt used the wrong name, silently ignored).
- **Verification**: real `bash deploy.sh` → exit 0, swap applied (BUILD_ID advanced), HTTP 200; `systemctl stop` rc=0 in 10s, port freed, no Restart flap.
- **Outputs**: new raw `wiki/raw/podium-web.service.d-stop.conf`; C-0354 (gotcha) admitted; `wiki/sources/podium-systemd-units.md` Live-update note added; runbook `~/homelab/docs/runbooks/automation/symphony.md` Overview pointer added (load-bearing for reinstall). Drop-in is a system file in `/etc`, not in any repo.
- **Unresolved**: the `~/homelab` runbook edit is uncommitted (separate repo) — operator to land.

## session-update 2026-07-01 — pi turn truncated at Markdown `---` (C-0355; ADR-0022 follow-up)
- **Inputs**: Interactive investigation of why Podium issue 168's AI comment was truncated to a one-sentence preamble (binding `symphony`, agent `pi`, model `glm-5.2`, run 620). The full run-history analysis was present in `runs/620.log` but not in `comments_md`.
- **Root cause**: `scheduler/sanitize.py` `_capture_natural_turn` strips claude's `<natural_turn>\n\n---\n<result_file>` separator by cutting stdout at the first `\n\n---\n`. That strip ran unconditionally for EVERY binding. A pi/glm agent that used `---` as an ordinary Markdown section divider had everything after the rule silently dropped — only the preamble reached the comment. Claude-only wiring misapplied to pi.
- **Fix**: added `is_claude` param to `_capture_natural_turn`; the separator strip now runs only when `is_claude`. Caller `_classify_terminal` (`scheduler/__init__.py`) resolves `agent = binding.resolve_agent(candidate.labels)` and passes `is_claude=agent == "claude"`. Regression tests `test_pi_markdown_hr_not_treated_as_separator` + `test_claude_turn_separator_still_strips_result_file` (`tests/test_captured_turn.py`).
- **Verification**: `pytest tests/test_captured_turn.py` 15 passed; `tests/test_scheduler.py` 213 passed.
- **Deploy**: `symphony-host.service` (live dispatcher, imports scheduler at process start) restarted onto `code_sha=16fafde` 2026-07-01; verified `symphony_started`, claude/pi RPC probes ok, remote binding reachable, dispatch loops ticking clean.
- **Outputs**: C-0355 (gotcha) admitted; ADR-0022 analysis page gained a "Follow-up bug" section + `updated: 2026-07-01`; index.md ADR-0022 row + ROUTING Output-Contract keywords updated.
- **Unresolved**: none. (Note: not committed at capture time — separate git commit step follows.)

## [2026-07-02] session-update | ADR-0032 landed + homelab flip live (5a) + #188 verified

- **Task**: complete the ADR-0032 flip from the symphony side — apply the `bindings.yml` homelab capability flip (5a), restart the live dispatcher, and capture the decomposition now that engine (#178–#181) + #188 have landed.
- **Landed/verified this session**: engine decomposition (#178–#181) confirmed on `main` (`config.py` per-binding `scheduling`/`blocked_reconciler`/`worktree_default`/`preamble`; scheduler + `dispatch_state.py` gate on flags not `is_coding`; `main.py` resolves `repo_path / preamble`; `OUTPUT_CONTRACT` always appended). #188 already fixed by `3c4138b` (both schedule-context sites gate on `scheduling`) — 32 renderer tests pass, no residual `binding_type != "coding"` schedule gate; nothing to implement.
- **5a flip**: `bindings.yml` homelab entry → `preamble: SYMPHONY.md`, `scheduling: true`, `blocked_reconciler: true`, `worktree_default: false` (commits `55cad43` + whitespace `84304c3`). Behavior-neutral — three flags equal the `type: infra` defaults; only `preamble` is a real change (verified: config parses, all 6 bindings load, 61 config tests pass).
- **Deploy**: `symphony-host.service` restarted onto `code_sha=84304c3` (PID 904584, 2026-07-02 03:43 UTC); verified `symphony_started bindings=6`, homelab binding `reconcile_startup_done` clean, `pi_rpc_probe_ok`, `rpc_orphan_reap_done count=0`, zero errors.
- **Outputs**: `wiki/analyses/adr-0032-project-defined-agent-reaction.md` (new, promoted); `wiki/entities/workflow-homelab.md` (ADR-0032 update note — `INFRA_PREAMBLE`-is-current statement marked historical); `wiki/CLAIMS.md` C-0356 (decision, supersedes the `INFRA_PREAMBLE`-current half of C-0276); `index.md` Analyses row; `ROUTING.md` Bindings route page + ADR-0032 keywords.
- **Cross-repo**: homelab-side worker marker fields (5b) + patrol-response/patrol-tune skills are project content captured in the homelab wiki (`d83230c`, candidate `concept-patrol-status-marker` + C-0025), not duplicated here.
- **Unresolved**: `binding_type` enum removal deferred (flagged inert-vestige). Both repos have local commits ahead of origin (unpushed). ADR-0032 ADR file still reads `proposed` — operator may want to flip it to `accepted` given the flip is live.

## [2026-07-04] session-update | patrol issues default to deepseek-v4-flash (C-0357)

- **Task**: operator request (issue #194) — Temporal patrol-posted issues should dispatch as `deepseek-v4-flash`. Preceded by two read-only Q&A turns (homelab default agent/model; whether flash can be set for homelab).
- **Change**: `web/api/main.py` `create_binding_issue` — added module constant `PATROL_DEFAULT_MODEL = "deepseek-v4-flash"`; after `origin` resolution, a null `issue.preferred_model` on an `origin == "patrol"` issue is defaulted to it before INSERT. Operator issues + explicit caller models untouched. Origin-scoped (all bindings), not binding-scoped — no per-binding `default_model` field exists; that was the surgical fit vs. adding config.
- **Tests**: 3 new in `web/api/tests/test_issue_create.py` (patrol default / explicit-wins / operator-unset). `web/api/tests/` = 315 passed, 1 skipped. Code committed `8fc4a80`.
- **Wiki**: C-0357 (config-fact) admitted; `analyses/podium-issue-dispatch-contract.md` gained a "Patrol-origin default model" section + `updated: 2026-07-04` + new source paths; `index.md` dispatch-contract row appended + date; `ROUTING.md` dispatch/model keyword line extended (PATROL_DEFAULT_MODEL, patrol default model, etc.).
- **Deploy**: NOT deployed at capture — change ships in `podium-api.service` (create endpoint), needs a restart to take effect. Scheduler unaffected.
- **Unresolved**: none. (Interactive operator-driven wiki pass — not a slice run, so ADR-0028 exemption N/A.)
