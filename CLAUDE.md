# Symphony — Agent Context

This is the Symphony host-native scheduler source repo. It is live infrastructure: `symphony-host.service` runs `/usr/bin/python3 -m main` from this directory and polls Plane for Todo tickets.

## REQUIRED: Caveman Prose

**Hard rule. Every response, every turn.** Write like a smart caveman. Full technical accuracy stays. Fluff dies.

- **Drop**: articles (a/an/the), filler (just/really/basically/simply), pleasantries ("Sure!", "Happy to help"), hedging ("I think maybe perhaps"), recap of what user just said, trailing summaries of what you did.
- **Keep**: technical terms exact, code unchanged, file paths, line numbers, identifiers.
- **Form**: fragments OK. Short clauses. Pattern → `[thing] [action] [reason]. [next step].`
- **Bad**: "Sure! I'd be happy to help you with that. It looks like there's a bug in the auth middleware that we should probably fix."
- **Good**: "Bug in auth middleware. Fix:"

**Boundaries** — code, commit messages, PR descriptions, and documentation you author are written in normal prose. Caveman applies to chat output only.

**Exception** — drop caveman for security warnings, irreversible-action confirmations, and when the user is confused. Resume after.

## Key Paths

- `/home/james/symphony/` — this repo. `bindings.yml` lives at the root; auto-discovered at CWD.
- `/home/james/symphony-host.env` — secrets (`PLANE_API_KEY`, etc.). File mode `0600`; never `cat` or print contents.
- `/etc/systemd/system/symphony-host.service` — service unit. `OnFailure=telegram-alert@%n.service`.
- `/etc/systemd/system/telegram-alert@.service` — failure-alert template; shares the same env file.
- Bound repos that Symphony agents inspect and modify are listed in `bindings.yml` (`repo_path` per binding); remote bindings carry a `remote:` block and live on another host.
- `/home/james/homelab/docs/runbooks/automation/symphony.md` — project runbook.

## Git Remote

- Remote: `git@github-personal:shreeve1/symphony.git`
- Always use `github-personal` SSH host alias — default `github.com` key authenticates as `shreeve1/SSH` (wrong account). `github-personal` uses `~/.ssh/id_ed25519_github_personal` and authenticates as `shreeve1`.

## Safety

- Treat as live infrastructure.
- Do not print values from `/home/james/symphony-host.env`.
- `systemctl restart symphony-host.service` is pre-approved: restart whenever needed without asking. Still run the pre-sanity and post-restart verification from the `symphony-restart` skill.
- Ask James before `systemctl stop`, unit edits, Plane API mutations, or smoke ticket requeues unless he has already approved that exact live mutation.

## Unattended modal handling (claude_runner)

Claude runs unattended (`--permission-mode bypassPermissions`), but bypass does **not** suppress every confirmation modal — `.claude/` edits and the `rm -rf /` / `rm -rf ~` circuit breakers still prompt, and an unanswerable modal used to hang the run and surface as the misleading "Agent timed out". `_poll_claude_until_done` now drives parked modals automatically (`claude_runner.py`):

- **Permission / Yes-No modal → Enter.** Option 1 ("Yes") is pre-selected, so Enter approves and the agent continues. This is a **blanket auto-approve with no carve-out** — it also accepts the `rm -rf /` / `rm -rf ~` circuit breakers (operator decision, 2026-06-19). The unattended agent can therefore execute a destructive command it raised by mistake; the binding sandbox and WORKFLOW.md are the only remaining guardrails.
- **Multi-choice question picker → Escape, wait `MODAL_QUESTION_SETTLE_SECONDS`, then paste "proceed with your recommendations".** This is a fallback for an agent that wrongly opened an interactive picker; the correct path is the `SYMPHONY_QUESTION` park, which completes cleanly without a modal.
- If the same modal pane persists past `MODAL_STUCK_LIMIT` automated interactions (Enter / auto-reply not landing), the run aborts with a clear reason instead of looping.

Log lines: `claude_permission_modal_approved`, `claude_question_modal_autoreplied`, `claude_modal_stuck`. Detection is best-effort regex on the captured pane (`_hit_permission_modal` = Yes/No choices + hint; `_hit_question_modal` = non-Yes/No choices + selection/escape hint).

## Env locations

- `/home/james/symphony-host.env` — secret values (`PLANE_API_KEY`, etc.).
- `symphony-host.service` `Environment=` — non-secret config (`PLANE_API_URL`, `PLANE_WORKSPACE_SLUG`, `SYMPHONY_LOCK_PATH`, `PYTHONPATH`, `PYTHONUNBUFFERED`; `PI_BIN` lives in the `override.conf` drop-in). Inspect with `systemctl show symphony-host.service --property=Environment`.
- Dispatch model/provider for Podium bindings comes from repo-root `models.yml` (issue `preferred_model`, else the single `default: true` entry; `reasoning_effort` appends as a `:suffix`). `SYMPHONY_PI_PROVIDER`/`SYMPHONY_PI_MODEL` were removed from the unit at the 2026-06-12 cleanup; if ever set again they act only as the legacy Plane-path fallback.
- `WorkingDirectory=/home/james/symphony` — `bindings.yml` auto-discovered at cwd; `SYMPHONY_BINDINGS_PATH` not required.
- `SYMPHONY_LOCK_PATH` — optional; if set, `config.py` uses it as the single-instance lock file path. Currently `/run/symphony/symphony.lock` on the unit.
- `SYMPHONY_RUNTIME_DIR` — root for the live steer/abort queue (`$SYMPHONY_RUNTIME_DIR/steer`, `web/api/steer_queue.py`); default `/tmp/symphony`. **Must resolve to the same path for BOTH `podium-api.service` (the queue writer) and `symphony-host.service` (the queue reader), or live steer/abort silently no-ops** (HTTP 200, never delivered). symphony-host has `PrivateTmp=yes`, so the default `/tmp/symphony` is namespaced per-service and the two units never share it. Set to `/run/symphony` (shared, not namespaced by `PrivateTmp`, already holds the lock) via a `runtime-dir.conf` drop-in on each unit. Added 2026-06-18 (issue #087 soak found steer broken without it). Affects pi RPC steer too.

## Required env vars (bindings mode)

- `PLANE_API_URL`
- `PLANE_API_KEY`
- `PLANE_WORKSPACE_SLUG`
- `PI_BIN`

`PLANE_PROJECT_ID` and `HOMELAB_REPO_PATH` are a legacy single-project fallback (`config.py:289,293`); bindings mode bypasses them. Safe to leave on the unit; not required.

## Dead config

Resolved 2026-06-12: the dead `OPENCODE_BIN`/`SYMPHONY_OPENCODE_AGENT` lines and the legacy `SYMPHONY_PI_PROVIDER`/`SYMPHONY_PI_MODEL` overrides were removed from the unit and its `override.conf` drop-in (backups: `*.bak.2026-06-12`). No dead env remains on the unit.

## Live bindings

Do not enumerate live bindings here — the list drifts. Source of truth is `/home/james/symphony/bindings.yml` (auto-discovered at CWD); the Podium `binding` table mirrors it. For the current set and live status run the `symphony-bindings-status` skill or `GET /api/bindings`. For narrative/history of each binding see the wiki (`wiki/entities/binding-*.md`, `wiki/index.md`).

## Common log queries

```bash
# Reconcile lifecycle (one pair per binding)
journalctl -u symphony-host.service --since=5m -n 200 --no-pager \
  | grep -E 'reconcile_startup_(begin|done|failed)'

# Dispatch loop liveness
journalctl -u symphony-host.service --since=2m -n 100 --no-pager \
  | grep 'dispatch_completed'

# Filter by binding (replace <name> with a binding from bindings.yml)
journalctl -u symphony-host.service --since=10m --no-pager | grep 'binding=<name>'

# Errors only
journalctl -u symphony-host.service --since=15m --no-pager \
  | grep -E 'ERROR|Traceback|ConfigError'
```

## Service unit

Path: `/etc/systemd/system/symphony-host.service`. If editing, back up first (`sudo cp <unit> <unit>.bak.<date>`) and `systemctl daemon-reload` before restart. Ask James before any unit edit.

## Restart ritual

Use the `symphony-restart` skill — wraps pre-sanity, ask-then-restart, and post-restart log verification (`symphony_started`, `reconcile_startup_*`, `dispatch_completed`).

Manual fallback:

```bash
# pre-sanity
git -C /home/james/symphony log --oneline -1
git -C /home/james/symphony status --porcelain
systemctl show symphony-host.service --property=ActiveState,MainPID,ActiveEnterTimestamp

# restart (ask James first)
sudo systemctl restart symphony-host.service
sleep 5 && systemctl is-active symphony-host.service
sleep 35
journalctl -u symphony-host.service --since="1 minute ago" --no-pager \
  | grep -E 'symphony_started|reconcile_startup_(begin|done)|dispatch_completed'
```

## Quick Checks

Run from `/home/james/symphony`:

```bash
git status --porcelain
uv run pytest
```

Use `uv run pytest` (or activate `.venv` first), not bare `python3 -m pytest`: the system interpreter lacks `alembic` and other deps, so a bare run fails at collection. The deps live in the uv-managed `.venv`.

Run for the host-native Symphony service:

```bash
systemctl show symphony-host.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
journalctl -u symphony-host.service --since=5m --no-pager -n 100
```

## Pre-commit testing (agent obligation)

There is no git pre-commit hook — the agent runs tests before committing. This is a standing obligation, not optional.

Before any `git commit` of code changes:

1. Run a **fast subset**: the test modules covering the code you changed, e.g. `uv run pytest tests/test_scheduler.py tests/test_config.py -q`. Map changed source files to their `tests/test_<area>.py` counterpart.
2. If the change is cross-cutting, touches `config.py`/`main.py`/dispatch/reconcile, or you cannot confidently scope the affected tests, run the **full suite**: `uv run pytest -q`.
3. Commit only when the selected tests pass. If a test fails, fix it or surface the failure — do not commit over a red suite.
4. `test_podium_sqlite_concurrent` is known-flaky under parallel load (`database is locked`); re-run it in isolation before treating a failure as a regression.

Always use `uv run pytest`, never bare `python3 -m pytest` (system interpreter lacks `alembic` and other deps).

## Skill suite

- `symphony-project-scaffold` — create a Plane project + binding entry.
- `symphony-workflow-author` — replace a binding's stub WORKFLOW.md with a real one.
- `symphony-restart` — pre-sanity → ask → restart → verify.
- `symphony-bindings-status` — read-only "what's running" table.
- `symphony-binding-smoke` — file a low-risk smoke ticket, watch one Run.
- `symphony-plane-recover` — archive / state-fill for half-built projects.
- `symphony-onboard-project` — umbrella that chains the above.

## LLM Wiki

This project uses `wiki/` as an LLM-maintained knowledge base for Symphony scheduler internals, runbook content, decisions, and operational patterns. Citation style is inline: `[source: path/to/file.md#section]`. **Auto-promotion is enabled** — the agent self-promotes candidates after lint passes; James gate is off.

### Directories

- `wiki/raw/` — immutable source material; read, never rewrite.
- `wiki/raw/sessions/` — curated session captures created by `/wiki-update` when conversation evidence needs citation.
- `wiki/candidates/` — transient holding for generated pages awaiting lint and auto-promotion.
- `wiki/sources/` — promoted source summaries.
- `wiki/entities/` — promoted entity pages (services, bindings, agents, projects).
- `wiki/concepts/` — promoted concept pages (dispatch loop, reconcile lifecycle, etc.).
- `wiki/analyses/` — promoted query outputs and syntheses.
- `wiki/raw/assets/` — source attachments clipped with raw material.
- `wiki/assets/` — generated or wiki-native images and attachments.

### Required Files

- Read `wiki/index.md` first when answering wiki-backed questions.
- Use `wiki/ROUTING.md` after `wiki/index.md` to narrow large searches.
- Append every ingest, query, lint, promotion, and discard to `wiki/log.md`.
- Track important factual claims in `wiki/CLAIMS.md` with inline citations.

### Wiki-First Project Search

For any Symphony-specific question, investigation, design task, bug hunt, or code search that requires project context, check the wiki first.

1. Read `wiki/index.md` before searching broadly.
2. Use `wiki/ROUTING.md` to identify relevant promoted pages, candidates, and claim entries.
3. Read relevant wiki pages and `wiki/CLAIMS.md` entries before using general repository search.
4. If the wiki does not contain enough information, search the codebase, docs (`CONTEXT.md`, `~/homelab/docs/runbooks/automation/symphony.md`), or external sources as needed.
5. When non-wiki search reveals durable project knowledge, propose ingesting the source into `wiki/raw/`, creating a `wiki/candidates/` page (auto-promoted after lint), or updating an existing promoted page with a cited change.
6. If external or codebase search was needed to answer a wiki-backed question, mention the wiki gap and the ingest or update path taken in the final answer.

### Session Update Workflow

Use `/wiki-update` during or after meaningful sessions to capture durable decisions, verified facts, root causes, follow-ups, and reusable context. Create curated raw session captures under `wiki/raw/sessions/` when conversation evidence is needed. Do not archive full transcripts, secrets from `/home/james/symphony-host.env`, private material, or raw pasted user content without explicit approval. New session-derived knowledge transits `wiki/candidates/`, gets linted, then auto-promotes; updates to `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md`, and `wiki/log.md` are required.

### Maintenance Trigger

The wiki is a standing obligation, not an opt-in step. Before reporting any task complete, run the end-of-session wiki check. This is mandatory, not advisory.

A task produces durable project knowledge — and therefore requires a `/wiki-update` pass before it is reported done — when it includes any of:

- A decision that sets or reverses project direction, scope, or ownership.
- Accepted or changed terminology, naming, or domain concepts.
- A new or revised architecture, process, or contract that future sessions must honor.
- A verified fact, root cause, or fix that contradicts or supersedes existing wiki knowledge.

End-of-session check, every task:

1. Decide whether the task hit any trigger above.
2. If yes, run `/wiki-update` before reporting completion. If a full pass must be deferred, state the wiki gap and the proposed ingest, candidate, or promotion path in the final answer.
3. If no, state one line in the final answer confirming the wiki check ran and nothing qualified.

Mark superseded knowledge `superseded` in `wiki/CLAIMS.md` with a pointer to the newer claim; never delete it to clean up history. Routine or already-documented work does not trigger a pass.

### Ingest Workflow

1. Place new source under `wiki/raw/` (copy or symlink for in-tree files; preserve original path in citation).
2. Summarize the source with citations to the raw path.
3. Discuss key takeaways with James when the source is substantial, ambiguous, or likely to touch multiple pages.
4. Extract entities, concepts, contradictions, and atomic claims.
5. Create page in `wiki/candidates/`.
6. Run lint checks against the candidate (broken links, citation drift, duplicate concepts).
7. Auto-promote to the appropriate directory (`sources/`, `entities/`, `concepts/`, `analyses/`), set `status: promoted`, update timestamps.
8. Update `wiki/index.md`, `wiki/ROUTING.md`, and `wiki/CLAIMS.md`.
9. Append an entry to `wiki/log.md`.

### Query Workflow

1. Read `wiki/index.md` to identify relevant promoted pages and candidates.
2. Use `wiki/ROUTING.md` to narrow branches when the index is too broad.
3. Read only the relevant promoted pages and claim entries.
4. Answer with inline citations (`[source: wiki/concepts/page.md]` or `[source: wiki/raw/file.md#section]`).
5. If the answer produces durable synthesis, save as `wiki/candidates/<slug>.md`, lint, auto-promote to `wiki/analyses/`.

### Promotion Workflow

Auto-promotion: agent self-promotes after lint. No James gate.

1. Lint the candidate page for citations, confidence, and duplicates.
2. Move it to `sources/`, `entities/`, `concepts/`, or `analyses/`.
3. Set `status: promoted` and update timestamps.
4. Update `index.md`, `ROUTING.md`, `CLAIMS.md`, and `log.md`.

### Discard Workflow

When a candidate is rejected during lint, remove its candidate index row, candidate-only routes, and candidate claim page references before deleting the candidate file. Append a discard entry to `wiki/log.md`.

### Lint Workflow

Check broken wikilinks, orphan pages, duplicate concepts, uncited claims, stale claims, claim content drift against cited sources, contradictions, missing concept pages, data gaps, stale candidate references, and missing index/routing entries. Report findings before making broad changes.
