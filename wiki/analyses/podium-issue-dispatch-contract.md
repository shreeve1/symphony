---
title: "Podium issue-field dispatch contract (model catalog, effort, skill, claude gate)"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-07-11
sources:
  - wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md
  - wiki/raw/sessions/2026-06-24-podium-api-model-dropdown-stale-validator.md
  - model_catalog.py
  - models.yml
  - scheduler.py
  - agent_runner.py
  - prompt_renderer.py
  - skill_mode_map.py
  - web/frontend/components/NewIssueModal.tsx
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/components/QueryProvider.tsx
  - wiki/raw/sessions/2026-06-24-reply-comment-undecorated-gate-fields-crash.md
  - tests/test_dispatch_gate.py
  - tests/test_model_catalog.py
  - web/api/main.py
  - web/api/tests/test_issue_create.py
confidence: high
tags: [podium, dispatch, models, skills, reasoning-effort, claude]
---

# Podium issue-field dispatch contract

Every operator-settable Issue field now has a real dispatch effect, enforced by a fail-loud gate. Before 2026-06-12, `preferred_model`, `reasoning_effort`, and `max_duration_seconds` were stored-but-dead, and `preferred_agent: claude` silently ran pi while the Run row claimed claude [source: wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md#durable-facts].

## Dispatch gate

`scheduler._apply_dispatch_gate` runs after a candidate is reserved and before any state transition or context-compaction spend [source: scheduler.py]. It blocks the Issue (state `blocked` + comment) when:

- `preferred_model` is absent from `models.yml`, or the catalog itself fails validation;
- the resolved model entry belongs to a different agent (e.g. a claude model on a pi dispatch);
- `preferred_skill` has no skill-table row, or the row's `source` SKILL.md no longer exists on disk.

As of #043, Claude is wired: a matching Claude entry annotates the candidate with `resolved_provider=""` and a bare `resolved_model`, while Pi keeps `resolved_provider=str(entry["provider"])` and `resolved_model = "{id}:{reasoning_effort}"` [source: scheduler.py; source: wiki/analyses/podium-043-claude-dispatch-routing.md]. `_start_run_record` and the agent adapters use these, so Run rows record what actually ran [source: scheduler.py; agent_runner.py]. Gate cases are covered in `tests/test_dispatch_gate.py`.

## Model catalog is the contract

`model_catalog.py` (shared by `web.api.main` `/options` and the scheduler) requires: entries unique by `(agent, provider, id)`, `agent` in `pi|claude`, `provider` on every pi entry, and at most one `default: true` entry per agent [source: model_catalog.py; models.yml]. Duplicate bare ids are allowed across agent/provider boundaries; dispatch resolves a bare `preferred_model` by the already-resolved agent, and `provider/id` is accepted for same-agent provider disambiguation [source: model_catalog.py; tests/test_model_catalog.py; tests/test_dispatch_gate.py]. The per-agent default dispatches when `preferred_model` is unset; the new-issue modal preselects by selected agent and uses `provider/id` values only when duplicate ids need disambiguation [source: web/frontend/components/NewIssueModal.tsx]. `SYMPHONY_PI_MODEL`/`SYMPHONY_PI_PROVIDER` are a legacy Plane-path fallback only; the podium startup pi probe exercises the Pi catalog default [source: main.py].

2026-06-23 catalog update: Pi now exposes the CLIProxy provider models `claude-haiku-4-5-20251001`, `claude-opus-4-8`, and `claude-sonnet-4-6`; the latter two intentionally share ids with Claude-agent entries and resolve to `provider=cliproxy` only when the Issue resolves to `agent=pi` [source: models.yml; model_catalog.py; tests/test_dispatch_gate.py]. Deploy lesson from Issue 112: because `models.yml` is re-read on every dispatch but `model_catalog.py` is loaded only at `symphony-host` process start, catalog changes that require validator changes must be followed by `symphony-host.service` restart before requeueing issues. The stale `ed887e5` process read the new duplicate-id catalog and blocked Issue 112 with the old `duplicate model id: claude-opus-4-8` validator until restart onto `a2e16c7`; after requeue, Run 323 dispatched via Claude `claude-opus-4-8` [source: journalctl -u symphony-host.service 2026-06-23 21:49-21:59; source: model_catalog.py; source: models.yml]. The same process-freshness rule applies to the Podium API dropdown: `/api/bindings/{name}/options` catches catalog `ValueError` and degrades to `models: []`, so a stale `podium-api.service` can show an empty Model list for both agents even when repo `models.yml` validates under current code; fix is restarting `podium-api.service` onto the tuple-identity validator and refreshing the browser query cache [source: web/api/main.py; web/api/tests/test_issue_create.py; wiki/raw/sessions/2026-06-24-podium-api-model-dropdown-stale-validator.md#durable-facts].

## Skill application

pi does not discover `~/.claude/skills`; the scheduler passes `--skill <SKILL.md parent dir>` resolved from the skill table `source` column, and `prompt_renderer` prepends "First, invoke the `{skill}` skill…" to the rendered prompt [source: agent_runner.py; prompt_renderer.py]. `mode_for_skill` normalizes slash-less catalog names so `dev-plan`/`dev-build` project plan/build mode again [source: skill_mode_map.py].

## Timeout

Global run timeout is 2 hours (`config.py` default `7_200_000`, env `SYMPHONY_RUN_TIMEOUT_MS` override). This supersedes the original 60-minute default (`3_600_000`) after Run #258 timed out during a long `dev-plan` audit loop. Historical binding `WORKFLOW.md` frontmatter remains decorative for the actual subprocess kill. Per-issue `max_duration_seconds` was dropped — schema, API, UI, and migration `0006_drop_max_duration_seconds` [source: web/api/migrations/versions/0006_drop_max_duration_seconds.py].

## Live verification

Smoke issue 20 / run 13 (homelab): run row `pi / openai-codex / gpt-5.5:low / skill_invoked=question`, exit 0, verdict `done` in 67s; summary echoed the new 3600000 timeout [source: wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md#evidence]. The post-run transition initially failed on live-DB drift — `alembic_version` was stamped `0005` but `inbox_dismissed_at` never existed; fixed with the 0005 DDL manually plus a pragma diff parity check [source: wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md#durable-facts]. Root cause (confirmed post-session): `web/api/main.py` `ensure_schema` UPDATEd `alembic_version` to the code's `INITIAL_REVISION` on every boot, recording migrations that never ran. Fixed in commit `772e7ba`: existing databases are never re-stamped; startup runs a pragma drift check — missing columns raise before the API serves, extra columns (pending drop migration) warn [source: web/api/main.py; web/api/tests/test_ensure_schema.py].

## Per-model reasoning-effort validation (2026-06-13)

Reasoning-effort vocabulary is model-specific, and the dispatch gate originally appended `:{effort}` to the model id with no validation, so an effort the model rejected only failed at the provider ~8s into the run. The live smoke that verified #046 hit this: `reasoning_effort=minimal` against the default `gpt-5.5` produced `gpt-5.5:minimal`, which the codex provider rejected (`'minimal' is not supported … Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'`) → Issue `blocked`/`failed` (C-0167) [source: wiki/raw/sessions/2026-06-13-046-live-output-contract-smoke.md].

Fix (C-0169, live + verified 2026-06-13): `models.yml` entries may declare an optional `efforts:` list (gpt-5.5 = `[none, low, medium, high, xhigh]`); `model_catalog.validate_models` parses and validates it. The `agent == "pi"` branch of `_apply_dispatch_gate` rejects an effort absent from a declared `efforts` set with a loud `Dispatch blocked: reasoning_effort '…' is not supported by model '…'` before forming the suffix; entries without `efforts` are unvalidated (back-compat). The API `reasoning_effort` Literal widened to `none|minimal|low|medium|high|xhigh` so model-specific values aren't rejected at create/patch (per-model validity is the gate's job). The new-issue modal derives its effort dropdown from the selected model's `efforts` (full set as fallback) and clears an effort the model doesn't support; `IssueFlyout` offers the union (its model chip is free-text, so the gate is the enforcement point there) [source: model_catalog.py; source: scheduler.py; source: web/api/main.py; source: web/frontend/components/NewIssueModal.tsx]. Made live 2026-06-13 ~05:48 UTC by restarting `podium-api` + `symphony-host` (working tree, uncommitted) and an atomic frontend `deploy.sh` swap. Verified end-to-end: a `minimal` homelab smoke (issue 4) was blocked at the gate (`dispatch_completed reason=dispatch-gate-blocked`, the loud comment, **no run row**), while an `xhigh` smoke (issue 5) dispatched as `gpt-5.5:xhigh` and completed `done`/exit 0.

## Issue-payload gate-field decoration contract (2026-06-24)

The board/flyout render dependency/lock gating (ADR-0021 #110 chip) from three fields
that are NOT base `issue` columns: `unsatisfied_blocked_by`, `lock_conflicts`,
`dependencies_satisfied`. They are added by `_decorate_issue_gates` (`web/api/main.py:692`),
which runs on `GET /api/bindings/{name}/issues`, `GET /api/issues/{id}`, the create
path, and `patch_issue` — but originally NOT on the mutation endpoints. `/reply` and
`/comment` returned + websocket-published a bare `_row(...)` lacking those fields; since
`/reply` flips state to `todo` (where `GateHints` in `IssueFlyout.tsx` read
`issue.unsatisfied_blocked_by.length` unguarded) and the websocket `issue.updated`
payload is written straight into the React Query cache (`QueryProvider.tsx`), the
post-reply re-render threw `undefined.length` → "Application error: a client-side
exception" (C-0325).

Fix (commit `76d5d0d`): `/reply` and `/comment` now decorate via
`_decorate_issue_gates`; `GateHints` defaults the fields to `[]` (matching the already
defensive `IssueCard`/`GateTags`); regression `test_reply_response_carries_gate_fields`.
**Standing rule:** any endpoint that returns or publishes an issue row the board/flyout
consumes must run `_decorate_issue_gates`, OR the frontend must default the decorated
fields. The remaining bare `_row` mutation returns (steer/abort/schedule/dismiss/merge,
`web/api/main.py:1683/1740/1782/1807/1833/1865/1902`) are safe only because of the
frontend guard — decorate them too if a component ever reads a decorated field as
required. Deploy split: backend fix = `podium-api` restart, frontend = `web/frontend/deploy.sh`;
NOT `symphony-host`/`symphony-restart`, which is the scheduler, not the API/UI
[source: wiki/raw/sessions/2026-06-24-reply-comment-undecorated-gate-fields-crash.md].

## Patrol-origin default model (2026-07-04)

Temporal patrol-created issues default `preferred_model` to **`pi-duo`** unless the caller pins a model explicitly (C-0368, 2026-07-14; supersedes C-0366's `Fusion Fast` value and C-0357's `deepseek-v4-flash` value). The default is applied at the Podium create endpoint (`create_binding_issue`, `web/api/main.py`), not in the patrol worker: after origin is resolved (`origin == "patrol"` — explicit `origin` field, or the `external_id`-backstop for un-migrated callers), `issue.preferred_model` is replaced with the module constant `PATROL_DEFAULT_MODEL = "pi-duo"` before the INSERT, **forcing** it over any caller-pinned value [source: web/api/main.py]. Operator-origin issues are untouched (their `preferred_model` stays null → per-agent catalog default applies, `Duo` for pi via C-0368). This is origin-scoped, not binding-scoped — it applies to every patrol issue across all bindings, not homelab only (there is no per-binding `default_model` field); the operator's "patrol home lab infra runs issues" request resolved to `PATROL_DEFAULT_MODEL` (and additionally flipped the per-agent `pi` default `deepseek-v4-pro`→`Duo`, 2026-07-14), and operator-opened issues on any binding stay on the catalog default. `Duo` is registered as a `pi`/`pi-duo` entry in `models.yml`; `resolve_model` disambiguates via `provider/id`, dispatch builds `pi --provider pi-duo --model "Duo":<effort>`; the `pi-duo` entry has no `efforts:` list so the effort gate skips it (back-compat). The `Fusion` and `Fusion Fast` `pi-moa` entries were removed from `models.yml` on 2026-07-14 alongside this change; the `pi-moa` MoA extension in `~/dotfiles/.pi/agent/extensions/pi-moa` is unchanged but no longer dispatched through Symphony. The value is a plain string that the scheduler still validates against `models.yml` at dispatch via the fail-loud gate above, so removing the `pi-duo`/`Duo` catalog entry would block patrol issues loudly rather than silently mis-dispatch. Tests: `test_patrol_origin_defaults_preferred_model_to_pi_duo`, `test_patrol_origin_forces_pi_duo_over_pinned_model`, `test_operator_origin_leaves_preferred_model_unset` (`web/api/tests/test_issue_create.py`). Deploy = `podium-api.service` restart (the create endpoint lives in the API, not the scheduler).

## Supersedes

- [analyses/podium-014-new-issue-flow.md](podium-014-new-issue-flow.md) — "preferred_model free text, unlisted models still dispatch" no longer true.
- [analyses/podium-028-model-catalog-searchable-dropdowns.md](podium-028-model-catalog-searchable-dropdowns.md) — catalog promoted from dropdown aid to dispatch contract.
- [concepts/prompt-renderer.md](../concepts/prompt-renderer.md) — renderer now prepends the skill directive; timeout default is owned by `SymphonyConfig`.
- [concepts/thin-engine-v2.md](../concepts/thin-engine-v2.md) — provider/model no longer fixed per-host by env for Podium bindings.
- [sources/symphony-host-service-unit.md](../sources/symphony-host-service-unit.md) — `SYMPHONY_PI_*` env demoted to legacy fallback.
