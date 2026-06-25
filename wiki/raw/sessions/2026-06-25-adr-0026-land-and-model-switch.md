# Session Capture: ADR-0026 land resolution, model switch, and parallel-slice land friction

- Date: 2026-06-25
- Purpose: Queue ADR-0026 plan as Podium issues, then shepherd the slices through land — resolving repeated auto-land rebase failures and a hung agent run — and switch the default pi model off a flaking provider.
- Scope: Durable facts about how ADR-0026 landed, the wiki-churn/duplicate-migration land friction, the agent stall gap, the default-model switch, and the Codex transient-signature allowlist gap. No secrets.

## Durable Facts

- ADR-0026 (transient terminal-failure retry) is fully implemented and live as of restart to `code_sha=fb799be` (2026-06-25 05:09 UTC). All five Podium slices done: #133 transient-core, #134 startup-probe fail-soft, #135 auto-land re-drive, #136 implement-run retry (→todo), #137 review-run retry (→in_review reland). — Evidence: `git log --oneline`; `sudo journalctl -u symphony-host.service | grep symphony_started`; `uv run python -m web.cli.podium issues list --binding symphony`
- The default pi model was switched from `gpt-5.5`/`openai-codex` to `deepseek-v4-pro`/`deepseek` in `models.yml` (commit `96d25bb`). `load_models()` reads the working-tree catalog per-dispatch with no cache, so the switch is live without a restart. — Evidence: `models.yml`; `model_catalog.py` `load_models`; `scheduler/__init__.py:789`
- `deepseek` is NOT in pi's `models.json` provider registry (only openai-codex/cliproxy/zai/minimax) but IS authenticated in `auth.json`, and pi resolves it dynamically. Live-probed ok: `pi -p --provider deepseek --model deepseek-v4-pro:high` → `PROBE_OK_HIGH` (exit 0). — Evidence: `~/.pi/agent/models.json`; `~/.pi/agent/auth.json`; live probe in `/tmp/pi-probe`
- Codex provider failures surface as `exit_code=1, timed_out=false` with stderr like `Codex SSE response headers timed out after 20000ms` or bare `terminated`. The original ADR-0026 allowlist (`server_is_overloaded`, 5xx, 429, connection, rate-limit) did NOT match these, so they blocked. Allowlist expanded (commit `a35f327`) to add `timed out`, `timeout`, `\bsse\b`, `\bterminated\b`. — Evidence: `scheduler/transient_retry.py`; run #409 stderr; `tests/test_transient_retry.py`
- Parallel slices that each run `/wiki-update` deterministically collide at land time: every slice edits the same wiki bookkeeping files (CLAIMS.md, ROUTING.md, index.md, log.md, analyses/…), so the second slice's branch diverges and the land rebase conflicts on wiki content. Recurred on #134 and #136. This is a deterministic conflict — ADR-0026's transient-retry machinery cannot self-heal it. — Evidence: journal `merge_rebase_failed` for #134 (02:21:13) and #136; rebase conflict files were wiki-only for #134
- Parallel slices can also create the SAME Alembic migration from the same parent: #136 and #137 both created a `0012_*_retry_verdict.py` branching from `0011_issue_auto_land`, which would produce two Alembic heads. Resolved by deleting #136's duplicate at merge time (main's `0012_retry_verdict.py` covers the `retry` verdict). — Evidence: `web/api/migrations/versions/0012_retry_verdict.py`; `git show 121890b -- web/api/migrations/`
- Agent stall-detection gap: a hung agent (live `pi` process, no output, frozen mid-context-compaction, `WCHAN=ep_poll`, 0% CPU) holds its `locks` resource and the run until the 2h `run_timeout_ms` (`config.py:175` = 7,200,000ms). ADR-0026's retry handles terminated agents (nonzero exit / timed_out), NOT frozen ones — `agent_runner` is blocked in `process.communicate(timeout=run_timeout_ms)` and cannot see the stall. Observed on #136 review run #417 (frozen ~50min; killed manually, exit 143). — Evidence: `ps`/`/proc/<pid>` for PID 396551; session jsonl mtime frozen at 02:59; `config.py:175`; `agent_runner.py:406`
- `contract_gate.py` reads the LIVE `podium.db` + `runs/` logs as its scoring corpus; as runs accumulate (many with empty/non-standard logs) coverage drifts below the locked baseline (0.9314 → 0.9129). Not caused by the model switch or ADR-0026. Separately, `scheduler/markers.py:14` verdict regex is `(done|review|blocked)` — missing `retry` (no retry verdicts exist in the DB yet, so this is latent). — Evidence: `contract_gate.py:53,81`; `contract_gate_baseline.json`; `scheduler/markers.py:14`

## Decisions

- Switch the pi default model to `deepseek-v4-pro` to move off openai-codex, which was SSE-timing-out (run #409) and stalling mid-compaction (#136). — Evidence: `models.yml` commit `96d25bb`; live probes
- Expand the transient allowlist to cover `timed out`/`timeout`/`sse`/`terminated` so observed Codex failures are caught. — Evidence: commit `a35f327`
- Manually land #134 and #136 by rebasing onto main, taking main's version of wiki-churn conflicts, and (for #136) merging the two complementary `_classify_terminal` retry functions + deleting the duplicate migration. — Evidence: `git log`; commits `877a06e`/`4d65e2d` (#134), `fb799be` (#136)

## Evidence

- `models.yml` — default-model switch
- `scheduler/transient_retry.py` — allowlist expansion
- `scheduler/__init__.py` — both retry functions now on main
- `web/api/migrations/versions/0012_retry_verdict.py` — single migration (duplicate deleted)
- `config.py:175` — `run_timeout_ms = 7_200_000`
- `agent_runner.py:406` — `process.communicate(timeout=run_timeout_ms / 1000)`
- `contract_gate.py:53` — `DB_PATH = REPO / "podium.db"`
- journal `symphony_started code_sha=fb799be` — ADR-0026 live

## Exclusions

- No secrets, API keys, or env-file contents read or captured.
- Per-run session jsonl contents not archived (only mtimes used as evidence).
- Full transcript not archived.

## Open Questions And Follow-Ups

- Stall watchdog: kill an agent run if no session-jsonl write for N minutes, independent of the 2h hard timeout. Separate from ADR-0026.
- Land friction: defer `/wiki-update` until after land, or assign shared migrations to a single coordinating slice, to stop parallel-slice wiki-churn / duplicate-migration collisions.
- Contract gate: decide whether to update the baseline (locks in drift), freeze the corpus to a snapshot, or improve the parser for empty-log rows; and add `retry` to `scheduler/markers.py:14` before retry verdicts appear in the DB.
