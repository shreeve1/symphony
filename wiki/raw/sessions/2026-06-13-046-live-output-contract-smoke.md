# Session Capture: #046 unified output contract — live end-to-end smoke verification

- Date: 2026-06-13
- Purpose: First live end-to-end observation of the #046 unified output contract on the running `symphony-host.service` (commit `5be9755`, restarted 2026-06-13 04:48 UTC). Prior to this it had only unit-test coverage; no real Issue had dispatched since the restart.
- Scope: One smoke Issue filed against the `homelab` binding, watched through dispatch → Run → completion comment, then the completion comment inspected against the four observable #046 changes. Also captures a model/effort incompatibility surfaced by a first failed attempt.

## Durable Facts

- The #046 output contract behaves in production exactly as documented in claims C-0160 / C-0161 / C-0162. A successful homelab Run (Run id 2, verdict `done`, exit 0, ~37s) posted `comments_md` as `**Symphony completed:**\n\n{summary}` where `{summary}` is the agent's multi-line `SYMPHONY_SUMMARY_BEGIN`/`END` block posted **verbatim** (3 markdown bullets, newlines preserved). — Evidence: `sqlite3 /home/james/symphony/podium.db "SELECT comments_md FROM issue WHERE id=3"`; `SELECT summary FROM run WHERE id=2`.
- The completion comment carried **no `### Symphony AI Summary` header wrapper**, **no `**Timeline** —` footer line**, and the Issue's comment stream contained **no `Symphony claimed at <ts>` comment** — only the single completion block. Confirms the C-0162 removals end-to-end. — Evidence: same `comments_md` query (block ends immediately after the last bullet).
- The `run.summary` column stores the agent summary block verbatim (without the `**Symphony completed:**` prefix); `comments_md` is that block with the prefix prepended. Confirms `_extract_summary` / `_parse_summary_block` captured the multi-line block, not a collapsed single line. — Evidence: `run` row id 2 vs `issue` row id 3.
- This was the Pi/codex dispatch path (`provider=openai-codex model=gpt-5.5:low`), so the Claude-path result-file parsing (C-0154) was not exercised. — Evidence: journal `agent_runner pi_dispatch issue_id=3 provider=openai-codex model=gpt-5.5:low`.
- **Model/effort incompatibility**: `reasoning_effort=minimal` is a valid value in Symphony's `IssueCreate` (`web/api/main.py:357` Literal `minimal|low|medium|high`) but is **rejected by the default `gpt-5.5` model** at dispatch. The first attempt (Issue id 2, `reasoning_effort=minimal`) failed in 8.4s with exit code 1, transitioned to `blocked`, verdict `failed`; stderr: `Unsupported value: 'minimal' is not supported with the 'gpt-5.5' model. Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'.` Re-filing with `reasoning_effort=low` succeeded. — Evidence: `issue` id 2 `comments_md`; journal `agent_exited issue_id=2 exit_code=1`.
- The failed (`blocked`) Run's comment also showed the #046-clean format: no Timeline footer, no claim comment; the blocked branch posted the stderr summary because no `SYMPHONY_SUMMARY` block was emitted (consistent with C-0161's blocked-branch behavior). — Evidence: `issue` id 2 `comments_md`.

## Decisions

- James approved filing a low-risk smoke ticket to verify #046 live (`AskUserQuestion`: "File smoke ticket now"). — Evidence: this session.
- Smoke Issues filed via direct INSERT into the live `podium.db` (mirroring the `POST /api/bindings/{name}/issues` INSERT at `web/api/main.py:629`) because the Podium HTTP API requires a bcrypt session-password login (`PODIUM_PASSWORD_HASH`) whose plaintext is not recoverable from env. The `web.cli.podium` CLI exposes only `skills` and `set-password`, no issue-create command. — Evidence: `web/api/main.py:170` `require_auth`; `web/api/auth.py:48`; `uv run python -m web.cli.podium --help`.

## Evidence

- `/home/james/symphony/podium.db` — live DB (confirmed open by scheduler PID 731625 via `lsof`; `/var/lib/symphony` absent so `resolve_db_path` uses the repo-root fallback, `web/api/db.py:13`).
- Issue id 2 (homelab, `minimal`) → Run id 1 `failed`/`blocked`; Issue id 3 (homelab, `low`) → Run id 2 `succeeded`/`done`. Both left in Podium as audit evidence per the `symphony-binding-smoke` convention.
- journalctl markers: `issue_claimed issue_id=3`, `pi_dispatch ... model=gpt-5.5:low`, `agent_exited ... exit_code=0`, `state_transitioned issue_id=3 state=...`.

## Exclusions

- No secrets read or printed (`/home/james/symphony-host.env` untouched; `PODIUM_PASSWORD_HASH` value not retrieved).
- The two uncommitted working-tree files (`CONTEXT.md`, `.gitignore`) from a prior interrupted Ralph run were left untouched per the handoff.

## Open Questions And Follow-Ups

- Claude-path output contract still unverified live (no Claude Issue has dispatched). C-0154 result-file parsing remains unit-test-only.
- Should `IssueCreate.reasoning_effort` reject `minimal` when the resolved model is `gpt-5.5`, or should the dispatch gate translate/validate effort against the model's supported set? Currently a valid-per-Symphony value produces a fast `blocked` failure. Not fixed this session — logged as a gotcha.
