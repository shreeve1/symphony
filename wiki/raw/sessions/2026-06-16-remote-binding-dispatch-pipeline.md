# Session Capture: ADR-0012 v1 Remote-Binding dispatch pipeline (RepoHost seam + invariants) + live n8n smoke

- Date: 2026-06-16
- Purpose: Implement the remote-aware dispatch pipeline that ADR-0012's adapter slice left incomplete, then re-run the live `n8n` smoke end-to-end. Closes the "adapter necessary but not sufficient" gap recorded in C-0214 / the adr-0012 analysis.
- Scope: code seam + config invariants + worktree/compaction/gate guards + startup reachability; live staging, restart, smoke, and the keep-live decision. Built via `/dev-build plans/remote-binding-dispatch-pipeline.md`.

## Durable Facts

- **RepoHost seam** — `repo_host.py`: `RepoHost` Protocol (`code_sha() -> str`), `LocalRepoHost(path)` (delegates to `code_version.resolve_code_sha`; `path` is the dispatch cwd so local worktree-active runs still record the worktree HEAD), `SshRepoHost(remote, repo_path, run_func)` (runs `ssh_base_args(remote) + ["git -C <shlex.quoted> rev-parse --short HEAD"]`, 5s timeout, returns `"unknown"` on non-zero/`OSError`/`TimeoutExpired`, never raises), and `repo_host_for(binding, *, cwd=None, run_func=subprocess.run)` factory (remote→`SshRepoHost` ignoring cwd; else `LocalRepoHost(cwd or repo_path)`). — Evidence: `repo_host.py`, `tests/test_repo_host.py`
- **Shared SSH helper** — `ssh_support.py` `ssh_base_args(remote, *, reverse_port=None)`, extracted from `agent_runner._ssh_base_args` (now a thin delegation), shared by the adapter and the repo host. — Evidence: `ssh_support.py`, `agent_runner.py`, `tests/test_ssh_support.py`
- **Config invariants** — `config._binding_from_mapping` raises `ConfigError` when a `remote:` binding is not `type: coding` AND `pi_mode: one-shot` AND `default_agent: pi`. This makes the infra-`WORKFLOW.md` local read, build-mode plan-file validation, and the RPC startup probe *unreachable* for remote bindings (collapsed, not per-callsite guarded). — Evidence: `config.py`, `tests/test_config.py`
- **`resolve_code_sha` hardened** — now catches `OSError` (covers `PermissionError`) → `"unknown"`, never crashes. This was the proximate cause of the original blocked smoke (`PermissionError: '/home/itadmin/itastack'` at `scheduler.py:635`). — Evidence: `code_version.py`, `tests/test_code_version.py`
- **Scheduler routed through seam** — three `resolve_code_sha` callsites (`635`, `1508`, `1603`) go through `repo_host_for(binding, cwd=...).code_sha()`, falling back to `resolve_code_sha(cwd)` when `binding is None`. `main.py:241` engine self-sha stays local. — Evidence: `scheduler.py`, `main.py`
- **Worktrees inert for remote** — API `create_binding_issue`/`patch_issue` coerce `worktree_active=False`; `_is_remote_binding` guards `_maybe_merge_worktree`/`_maybe_teardown_archived_worktree`/`_maybe_archive_worktree`/`_purge_archived_issues` (skip local worktree ops, still clear `worktree_active`); `scheduler._worktree_run_fields` returns `{}` and `_handle_archived_terminal` skips worktree teardown for remote. Remote agent runs directly in `repo_path`; its own commits are the landing. — Evidence: `web/api/main.py`, `scheduler.py`, `web/api/tests/`
- **Dispatch-gate guards** — `scheduler._apply_dispatch_gate` fail-loud blocks remote + non-pi agent (covers issue-level `agent:claude`/`preferred_agent`, which the config `default_agent: pi` invariant does NOT cover) and remote + `preferred_skill` (because `prompt_renderer._skill_directive` would still inject "invoke the skill"). `agent_runner.run_remote_agent` never appends `--skill` (logs `remote_skill_skipped`). Context compaction skipped for remote (`scheduler._maybe_compact_context` early-return; web `_compact_issue_context` → 422). — Evidence: `scheduler.py`, `agent_runner.py`, `web/api/main.py`
- **Non-fatal startup reachability** — `main._build_binding_runtime` remote branch calls `repo_host_for(binding).code_sha()` once, logs `remote_repo_reachable`/`remote_repo_unreachable`, never raises. — Evidence: `main.py`, journal `remote_repo_reachable binding=n8n host=100.95.224.218 sha=7f91558`
- **Live smoke PASSED** — `n8n` (`itadmin@100.95.224.218:/home/itadmin/itastack`, coding/one-shot, `pi`/`openai-codex`/`gpt-5.5:high`) Issue 32 → Run 56: `state=succeeded`, `verdict=done`, `exit_code=0`, `agent_session_sha=7f91558` (remote HEAD recorded over SSH via the seam), `worktree_path`/`branch_name`=null. The remote agent searched `itastack` for ADR-0012 (found none — correct, that's the n8n repo) and returned `SYMPHONY_RESULT: done` through the reverse tunnel. — Evidence: `podium.db` run id 56, `runs/56.log`, `plans/.remote-binding-dispatch-pipeline.state.yml` `live_smoke:`
- **Test status** — `uv run pytest -q` → 874 passed, 2 skipped (+32 vs the 842 baseline); ruff clean on touched files; new files `tests/test_ssh_support.py`, `tests/test_repo_host.py`. — Evidence: build run output

## Decisions

- **Keep `n8n` live as a permanent 4th binding** (homelab, symphony, dotfiles, n8n). No rollback (reverses the 2026-06-16 rollback recorded in C-0214). No extra restart needed — already loaded. — Evidence: operator answer during `/dev-build` Phase 10
- **Strategy A** (seam + config invariants), worktrees deferred — chosen in the plan; collapses four local-`repo_path` touchpoints to "unreachable" rather than guarding each. — Evidence: `plans/remote-binding-dispatch-pipeline.md`

## Evidence

- `plans/remote-binding-dispatch-pipeline.md` — the executed plan (27/27 code tasks, 28/28 tests checked).
- `plans/.remote-binding-dispatch-pipeline.state.yml` — `build_audits:` (pi wave audits) + `live_smoke:` blocks.
- `runs/56.log`, `podium.db` run id 56 / issue id 32 — smoke evidence.
- journal `symphony-host.service` 2026-06-16 07:06–07:12 — `symphony_started ... bindings=4`, `remote_repo_reachable binding=n8n ... sha=7f91558`, reconcile 4/4, smoke dispatch.

## Exclusions

- No secrets from `/home/james/symphony-host.env`.
- Per-builder agent chatter and the pi wave-audit transcripts (summarized in the state-file `build_audits:` instead).

## Open Questions And Follow-Ups

- **v2 (out of scope):** remote worktrees + over-SSH `merge_worktree`/teardown; remote context compaction (route compaction agent through the remote adapter); remote `preferred_skill` (ship the skill dir to a remote temp path, mirroring the `plane` helper); `web/api/main.py:_branches_for` degrades to `[]` for remote (non-blocking, no branch dropdown). Session resume / Session Tail / remote orphan-reaping remain v2 per ADR-0012.
- **Host badge UI** (remote-binding chip) — still pending from the ADR-0012 v1 scope; not part of this build.
- **Uncommitted tree:** these changes plus a separate file-browser feature (`web/api/files.py`, `FileBrowser.tsx`, …) and wiki edits are uncommitted on `main`; commit hygiene (path-scoped commit) is operator-owned. Running service loads the on-disk tree.
- `CLAUDE.md` "Live bindings" table lists homelab + trading (stale: trading offboarded per C-0212; n8n now live) — not corrected in this pass.
