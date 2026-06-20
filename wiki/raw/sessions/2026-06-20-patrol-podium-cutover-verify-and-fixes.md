# Session Capture: ADR-0015 patrol→Podium first-live-cycle verification + post-cutover fixes

- Date: 2026-06-20
- Purpose: Watch the first real patrol cycle write to the live `homelab` Podium binding after the Wave C cutover; diagnose and fix anything that misbehaved.
- Scope: Live read-only diagnosis, then operator-approved manual patrol triggers, a code fix + WORKFLOW.md cleanup (homelab `a716349`), a host-global pi-harness fix (operator), and unpausing all patrol schedules.

## Durable Facts

- **Auth precondition is sound.** Bearer with the live token → HTTP 200; no-auth → 401; bad-token → 401. Worker `PODIUM_API_TOKEN` (`/etc/homelab-stack/temporal-worker.env`) hash == podium-api token (`/home/james/symphony-host.env`), sha256[0:16] `af3ea5d2282adeec` (values never printed). The C-0269 bearer path works end-to-end. — Evidence: `curl` http-code probes + `sha256sum` compare.
- **The first REAL patrol finding wedged PatrolWorkflow** (int-vs-str id). Live podium-api returns INTEGER issue ids; `TicketActivityOutcome.issue_id` is typed `str | None`; Temporal rejected the int at the activity-result boundary (`TypeError: Failed converting to str | None from 62` → `RuntimeError: Failed decoding arguments`) and retried the workflow task forever. The Podium write itself SUCCEEDED — issue 62 created in `homelab` binding (`external_id=homelab-patrol-infra-0e68960a`, priority `med`, `<!-- patrol-status -->` marker with `last_fail_at`/`consecutive_passes`), dedup single. — Evidence: `journalctl -u homelab-temporal-patrol-worker.service`; `podium.db` issue 62.
- **Root cause = mock/real divergence.** The in-memory `InMemoryPodiumTransport` stringifies ids (`podium_adapter.py:117` `str(self._next_id)`); the dry-run returned no real id (intent only) — so unit tests + the C-0270 dry-run never saw the int. Same class as the C-0270 bare-list bug and the analysis-session-020 masked-test lesson.
- **Fix (homelab `a716349`): `PodiumAdapter._coerce_row_id` coerces a response row's `id` to `str`** at the `find_by_external_id` and `upsert_issue` boundaries, honoring the string-typed `TicketWriter` contract (Plane returns string ids). Two regression tests added (bare-list find path; create path with int id). — Evidence: `automation/homelab-stack/src/homelab_router/podium_adapter.py`, `tests/test_podium_adapter.py`.
- **Post-fix live verification PASSED.** Worker restarted onto the fix; manual `infra` patrol → workflow `Status COMPLETED`, `findings_count:10`, all ids round-trip as strings (`"62"`, `"63"`…), dedup GETs 200, creates POST 201, no 401s, no decode errors. Issue 62 (`host-disk-usage`, disk now 79%) → `pass-recorded consecutive_passes:1` (auto-cure progressing). — Evidence: `temporal workflow describe` result JSON; worker journal.
- **Patrol findings auto-dispatch into live-host remediation (designed, operator-accepted).** The `homelab` binding auto-claims each patrol finding and dispatches a pi agent (`provider=openai-codex model=gpt-5.5:high cwd=/home/james/homelab`). Issue 62's agent autonomously remediated the host: vacuumed journal to 500M, truncated `/var/log/syslog{,.1}`, pruned docker builder cache, cleared `~/.cache`, apt cache — `/` 86%→79%, no service restarts. Operator confirmed acceptable. — Evidence: symphony-host journal (`pi_rpc_dispatch`/`agent_exited exit_code=0`), issue 62 `comments_md`.
- **Blast radius:** one `infra` patrol alone produced 10 failures → issues 63–72 (1 disk + 8 `os-package-update-plan` + 1 `lxc-package-update-plan`), each auto-dispatch-eligible.
- **Plane-CLI completion residue lived in homelab `WORKFLOW.md`.** Steps 18/19/20 + scattered lines told the agent to call `plane done|review|blocked` and post "Plane comments". The issue-62 agent tried the nonexistent `plane` CLI ("Symphony Plane API env vars were not injected"), then fell back to the `SYMPHONY_RESULT` marker. Cleaned (homelab `a716349`): completion now routes solely via `SYMPHONY_RESULT: done|review|blocked` (rule 21 / `prompt_renderer.OUTPUT_CONTRACT`); "Plane comment"→"summary"; `Plane-Issue:`→`Symphony-Issue:` trailer (confirmed nothing in symphony parses any issue trailer). — Evidence: `WORKFLOW.md` diff; `grep` for trailer parsing in symphony.
- **Patrol schedules are created PAUSED by design.** `schedule_patrols.py:111` `build_schedule` sets `ScheduleState(paused=True)`; module docstring: "creates schedules in the paused state so cutover still requires an explicit unpause step." Wave C wired the worker but never ran the unpause — this (not a cutover regression) is why no scheduled cycle had fired (`Notes: "paused by patrol schedule bootstrap"`, last run ~1 week prior). — Evidence: `schedule_patrols.py`; `temporal schedule describe schedule-patrol-infra`.
- **All 6 patrol schedules UNPAUSED 2026-06-20** via `python -m homelab_worker.schedule_patrols unpause --live --worker-deployed` (note "unpaused by approved patrol cutover"). Crons: infra `0 3,15`, media `0 6,18`, storage `30 7,19`, network/security/docker (each twice daily), `OverlapPolicy=SKIP`. `Paused: false` confirmed for all six. — Evidence: `temporal schedule list`.
- **A host-global pi-harness break briefly disabled ALL pi dispatch.** The freshly-installed `ponytail` pi extension (`~/.pi/agent/extensions/ponytail/index.js`, files timestamped 14:00) used CommonJS `require()` while its `package.json` declared `"type": "module"` → `require is not defined in ES module scope` → pi aborted at startup → every pi RPC dispatch exited 1 in ~8s → issues 62–72 all went `blocked`. NOT related to the patrol cutover. Operator fixed it via the `import { createRequire } from "node:module"; const require = createRequire(import.meta.url);` shim; re-verified: issue 62 re-dispatched → pi resumed its session → `exit_code=0` after 55s → `in-review`. — Evidence: issue 63 run 137 `comments_md` stderr; `~/dotfiles/.pi/agent/extensions/ponytail/index.js:1-13`.

## Decisions

- Auto-remediation of patrol findings on the live host is acceptable — operator confirmed. — Evidence: this session.
- Unpause all 6 patrol schedules now (operator chose "unpause all" despite the 10-findings-per-cycle blast radius). — Evidence: this session.
- Fix the int-id bug in the `PodiumAdapter` (string-coerce at the boundary), not by widening the activity field type — keeps the `TicketWriter` contract string-typed like Plane. — Evidence: `podium_adapter.py` diff.
- Retire the Plane-CLI completion path from `WORKFLOW.md` rather than re-add a tracker CLI — `SYMPHONY_RESULT` (rule 21) already governs. — Evidence: `WORKFLOW.md` diff.
- The 10 blocked findings (63–72) are left to self-heal on the next scheduled infra cycle (dedup reopens each to `todo`, pi now remediates); no manual cleanup. — Evidence: `record_failure` reopen path in `patrol_plane.py`.

## Evidence

- `automation/homelab-stack/src/homelab_router/podium_adapter.py` — `_coerce_row_id` fix.
- `automation/homelab-stack/tests/test_podium_adapter.py` — int-id regression tests (find + create).
- `/home/james/homelab/WORKFLOW.md` — Plane-CLI → `SYMPHONY_RESULT` cleanup.
- homelab commit `a716349` — both changes.
- `automation/homelab-stack/src/homelab_worker/schedule_patrols.py` — create-paused-by-design + unpause op.
- `~/dotfiles/.pi/agent/extensions/ponytail/index.js` — ponytail ESM fix (operator).
- `podium.db` issues 62–72; symphony-host + patrol-worker journals.

## Exclusions

- Secret env values (`PODIUM_API_TOKEN`, `/home/james/symphony-host.env`, `/etc/homelab-stack/temporal-worker.env`) — compared by hash only, never printed.
- Pre-existing uncommitted `homelab/CLAUDE.md` drift (98-line trim, not made this session) — left unstaged.

## Open Questions And Follow-Ups

- The committed homelab review fixes (`dcd8c16`) and symphony `49971ed` remain latent until the next restart of those services (pre-existing, from the dev-review log entry); the worker now also carries `a716349` (live after this session's restart).
- Pre-existing stale test `tests/test_prompt_renderer.py::TestDefaultWorkflowPolicy::test_default_workflow_documents_medium_risk_autonomy` asserts excluded-service names that a prior refactor moved into `CLAUDE.md`; failing before and after this session's edits (not a regression). Update or retire it.
- homelab runbooks (`runbooks/{alerts,mediaops,secops}/runbook.md`) still reference Plane labels/CLI as human-triage guidance — lower-priority doc debt, not agent-behavioral.
- The `ponytail` pi extension ESM packaging bug is host-global tooling debt; if it ships again on reinstall it will re-break all pi dispatch.
