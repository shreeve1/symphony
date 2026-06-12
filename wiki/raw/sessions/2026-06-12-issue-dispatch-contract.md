# Session Capture: Issue-field dispatch contract (grill-me → implement → deploy → smoke)

- Date: 2026-06-12
- Purpose: Grill-me walkthrough of "what happens when an Issue is created" exposed four dead/lying fields and a paused claude path; James approved six decisions, implemented and deployed same session.
- Scope: dispatch-contract decisions, implementation evidence, live-DB drift root cause, smoke evidence. No secrets, no transcript.

## Durable Facts

- `preferred_model`, `reasoning_effort`, `max_duration_seconds` were stored but never read by dispatch; `preferred_agent: claude` silently ran pi while the Run row recorded `agent="claude"` — Evidence: pre-change `scheduler.py` `_start_run_record` (config.pi_model recorded unconditionally), `agent_runner.py:316-323` `RoutingAgentAdapter` ("claude paused for v2").
- pi CLI supports `--model <id>:<thinking>` (off/minimal/low/medium/high/xhigh) and does NOT discover `~/.claude/skills`; skills load only via `--skill <path>`, settings opt-in, or `.pi/skills`/`.agents/skills` — Evidence: `pi --help` (v0.78.1), pi package `docs/skills.md`.
- Podium skill catalog rows store slash-less names (`dev-build`) while `SKILL_TO_MODE` keys are slashed (`/dev-build`), so plan/build mode projection never fired for catalog skills until normalization — Evidence: `sqlite3 podium.db "select name from skill"`, `skill_mode_map.py`.
- Live `podium.db` had `alembic_version=0005_inbox_dismissed_at` but the `inbox_dismissed_at` column did not exist (stamp recorded without the migration running). After the Ralph #037/#038 merge landed code that writes the column, every `transition_state` raised `sqlite3.OperationalError`, leaving issue 20 stuck `running` post-success — Evidence: journalctl symphony-host 21:34-21:35Z tracebacks; pragma diff script (missing_in_live: ['inbox_dismissed_at']).
- Fix: manual `ALTER TABLE issue ADD COLUMN inbox_dismissed_at TIMESTAMP NULL` (the exact 0005 upgrade DDL), verified by pragma diff against `SCHEMA_SQL` and error-free journal afterwards.
- A concurrently running `ralph-loop.service` (systemd user unit) stash-resets the symphony repo (`ralph-halt-preserve` stashes) when it relaunches; uncommitted session work must be committed early when coexisting — Evidence: `git reflog` 19:47:48 reset entry, `stash@{0}` with 13-file WIP, `~/.cache/ralph-supervise-ralph-loop.log`.

## Decisions

- `agent:claude` dispatch fails loud (blocked + comment) until a real adapter lands; kanban `#040` tracks wiring `claude -p` — James Q1/Q7.
- `preferred_model` resolves against `models.yml` at dispatch; unknown model blocks; `default: true` entry (exactly one, currently `gpt-5.5`) dispatches when unset; UI preselects it — James Q2/Q3.
- `reasoning_effort` appends as `:{effort}` to the pi `--model` argument — James Q4.
- `preferred_skill` is a directive: dispatch passes `--skill <SKILL.md parent dir>` from the skill table `source` column and the renderer prepends "First, invoke the `{skill}` skill…" to the prompt; missing catalog row or missing file on disk blocks — James Q5.
- `max_duration_seconds` dropped (schema, API, UI, migration `0006_drop_max_duration_seconds`); per-issue timeout rejected in favor of one global failsafe — James Q6.
- Global run timeout 30min → 60min (`config.py` default `3_600_000`, both binding WORKFLOW.md frontmatters, `prompt_renderer.py` defaults) — James Q6b.
- `SYMPHONY_PI_MODEL`/`SYMPHONY_PI_PROVIDER` demoted to legacy Plane-path fallback; podium startup pi probe exercises the catalog default — Q3 follow-through.
- Coexist with the running ralph-loop by committing early instead of stopping the service — James mid-session.

## Evidence

- Commits `0912016`, `2343bf2` (symphony main; later merged under `59a68c3` ralph batch merge, kanban queue commit `ea449b5`).
- `model_catalog.py`, `scheduler.py` `_apply_dispatch_gate`, `agent_runner.py` argv block, `prompt_renderer.py` directive, `skill_mode_map.py` normalization, `web/api/migrations/versions/0006_drop_max_duration_seconds.py`, `tests/test_dispatch_gate.py` (7 cases).
- Smoke: Podium issue 20 / run 13 on binding homelab — run row `agent=pi provider=openai-codex model=gpt-5.5:low skill_invoked=question`, exit 0, verdict `done`, duration 66.7s; agent summary echoed `run_timeout_ms=3600000`; issue settled `in_review` after the drift fix.
- Rollout: `/backup/podium-2026-06-12.db`, `alembic upgrade head` (0005→0006), podium-api + podium-web (deploy.sh staging swap) + symphony-host restarts 21:27-21:28Z, restart markers clean.

## Exclusions

- No values from `/home/james/symphony-host.env` or `.env` (PODIUM_* names referenced, values never read into the session).
- Session cookie minted in-memory for the authenticated smoke POST; not stored.

## Open Questions And Follow-Ups

- Kanban `#040`: real ClaudeAgentAdapter behind the gate (claude models in `models.yml` unusable until then).
- Why live `podium.db` carried a 0005 stamp without the column: forensics not completed; suspicion is `ensure_schema`'s stamp-on-fresh-`alembic_version` path combined with `CREATE TABLE IF NOT EXISTS` no-ops. Worth a parity check (pragma diff) in CI or at podium-api startup.
- `web/frontend/tests/new-issue.spec.ts` still references `glm-5.1:high`, absent from the trimmed catalog — pre-existing drift, untouched.
- homelab/trading WORKFLOW.md frontmatter `run_timeout_ms` is decorative for the actual kill (config env/default governs); comment in homelab WORKFLOW.md already says env wins.
