---
title: ADR-0012 — Remote Bindings dispatch over SSH-exec
type: analysis
status: promoted
created: 2026-06-15
updated: 2026-06-16
sources:
  - docs/adr/0012-remote-binding-ssh-exec.md
  - config.py (RemotePolicy, ProjectBinding.remote, _remote_from_mapping, remote invariants)
  - agent_runner.py (run_remote_agent, RemoteAgentAdapter, RoutingAgentAdapter, --skill skip)
  - main.py (_build_binding_runtime remote wiring + reachability)
  - repo_host.py (RepoHost, LocalRepoHost, SshRepoHost, repo_host_for)
  - ssh_support.py (ssh_base_args)
  - code_version.py (resolve_code_sha OSError hardening)
  - scheduler.py (code_sha seam, worktree/compaction/gate guards)
  - web/api/main.py (worktree force-off + _is_remote_binding guards + compaction 422)
  - tests/test_remote_agent.py, tests/test_repo_host.py, tests/test_ssh_support.py
  - web/api/schema.py (binding table)
  - plans/remote-binding-dispatch-pipeline.md
  - web/api/main.py (list_bindings is_remote/repo_name enrichment, Issue 34)
  - web/frontend/lib/api.ts, web/frontend/components/Sidebar.tsx, web/frontend/app/page.tsx (host label)
  - web/frontend/deploy.sh (podium-web atomic deploy)
confidence: high
tags: [adr, remote-binding, ssh, dispatch, podium, issue-27, issue-34, repo-host, seam, n8n, host-label, deploy]
---

# ADR-0012 — Remote Bindings dispatch over SSH-exec, not a remote daemon

Decision (status `accepted`, Issue #27): a **Remote Binding** is an ordinary Project Binding carrying an optional `remote:` block (`host`, `user`, `identity?`); its `repo_path` then denotes the checkout on that host. Dispatch runs the same agent command (`pi`/`claude`) over `ssh user@host ...` behind the existing `AgentAdapter` Protocol / `RoutingAgentAdapter` seam — no Symphony component is deployed to the remote. The engine stays centralized: one brain, many hands.

## Why not a remote daemon

The operator's first framing was a "symphony-remote" copied to each device. Rejected: pi/claude are self-contained CLIs whose dispatch is just `command + cwd + env + stdin/stdout`, which SSH provides directly (remote command, remote cwd, env forwarding, pipe pair). A daemon would re-implement process management, auth, lifecycle, and a wire protocol for no gain on a trusted LAN/tailnet, at the cost of more code and more attack surface.

## Load-bearing finding — the callback path

Agents report back to the tracker over HTTP via `SYMPHONY_PLANE_API_URL`, which is **loopback-only** (`http://127.0.0.1:8000`; Podium API binds `127.0.0.1` per its systemd unit; only the Next.js web UI is LAN-bound on `10.20.20.16:8091`). A remote agent therefore cannot reach the API directly (a probe from the test host `n8n` to the API timed out, as predicted). Accepted mechanism: the `RemoteAgentAdapter` opens the SSH session with a **reverse tunnel** (`ssh -R 8000:127.0.0.1:8000 ...`) and forwards `SYMPHONY_PLANE_API_URL=http://127.0.0.1:8000` into the remote env — the remote agent's loopback writes tunnel back to aidev's loopback API. This keeps the API loopback-only (no new LAN exposure, no auth-surface change). Rejected alternative: bind the Podium API to the LAN/tailnet.

## Scope / phasing

- **v1:** one-shot `pi --print` / claude tmux, verdict-only; reverse-tunnel callback; config schema + a small operator-facing **host badge** (the Podium `binding` table stores only `name`/`display_name`/`color`/`sort_order`/`archived`, so a remote binding is otherwise visually identical — the badge makes remote execution legible).
- **v2 (deferred):** Session Tail over SSH (the session file lives on the remote → `ssh host tail -f`), mid-run Steering over an SSH-piped RPC session, and remote orphan-reaping (local reapers use `/proc` + `/tmp` sockets, unreachable on the remote; v1 one-shot lets the SSH channel be the process handle).
- sudo/privilege stays the remote host's responsibility, consistent with ADR-0011.

## Test host

`itadmin@100.95.224.218` (hostname `n8n`, Ubuntu x86_64, a Tailscale 100.64/10 address). SSH key auth already works; `pi`, `claude`, `git`, `tmux` all present — so the v1 path needs only a repo checkout + a Remote Binding entry, no agent install.

## Status of the build

ADR accepted. Two slices landed (committed on `main`):

- **Config parsing** (commit `80c5bb4`): `config.py` gains `RemotePolicy` + `ProjectBinding.remote` + `ProjectBinding.is_remote` + `_remote_from_mapping` (additive, optional); 3 `tests/test_config.py` cases (parse, absent→local, missing-host→ConfigError).
- **Dispatch adapter** (commit `ca01062`): `agent_runner.py` gains `run_remote_agent` + `RemoteAgentAdapter`; `RoutingAgentAdapter` routes a remote binding to it (pi only — remote claude/tmux rejected in v1) and `main._build_binding_runtime` wires it when `binding.is_remote`. `run_remote_agent` ships the `plane` callback helper to a remote `/tmp/symphony-remote-<issue>` dir over SSH, then runs `ssh -R <port>:127.0.0.1:<port> user@host 'cd <repo> && export … && PATH=<helper>:$PATH pi --print …'`; the local SSH process group is the handle (kill → channel close → remote SIGHUP). pi is invoked by basename so the remote PATH resolves it (the local absolute `pi_bin` does not exist remotely). 12 tests in `tests/test_remote_agent.py` (ssh/tunnel construction, env+helper forwarding, shell quoting, silent-exit→137, timeout, routing guards). Full suite green (840 passed).

**Inert until live:** no binding carries a `remote:` block and dispatch is unchanged for local bindings, so no behavior change and no restart yet. Remaining slices: **host badge UI** (`binding` table column / `display_name` convention + chip in the card/fly-out) and a **smoke test against `n8n`** — both gated on adding the `n8n` `remote:` entry to `bindings.yml` + a James-approved `symphony-restart`.

**Known v1 gap surfaced during build:** `run_agent` puts the `plane` helper on a *local* temp-dir PATH; the remote adapter must therefore *ship* the helper to the remote per run (done via `ssh … cat > …/plane`) for the reverse-tunnel callback to resolve. A persistent remote install or a per-binding remote `pi` path are future refinements.

## Live validation 2026-06-16 — adapter is necessary but not sufficient

Staged an `n8n` remote binding (`itadmin@100.95.224.218`, `repo_path=/home/itadmin/itastack`) and ran a real end-to-end smoke against the live scheduler. Two blockers surfaced, both rooted in the **dispatch pipeline assuming a local `repo_path`** — a scope the adapter alone does not cover:

1. **Startup crash (fixed, commit `dab2b45`):** `main._build_binding_runtime` ran `verify_pi_support` with `cwd=repo_path`. For a remote binding that path is on the remote host, so the *local* pi probe raised `PermissionError` and crashed scheduler startup → a restart crash-loop once the remote binding was present. Fix: skip the local probe when `binding.is_remote`.
2. **Dispatch blocks (not fixed):** even past startup, dispatch prep does local repo I/O on `repo_path`. The smoke issue (#31) blocked with `dispatch_completed reason=workflow-missing` wrapping `PermissionError: '/home/itadmin/itastack'` from `scheduler._prepare_resume_candidate` → `resolve_code_sha(current_cwd)` (`scheduler.py:635`). The same local-`repo_path` assumption recurs across the pipeline: worktree create/remove, context compaction, and **post-run landing** (`landing.mode: local` = git commit/merge in `repo_path`).

**Conclusion (interim, since resolved — see next section):** v1 (config + `RemoteAgentAdapter` + startup-probe guard) is the foundation but does **not** make remote dispatch work end-to-end. The dispatch pipeline's local-`repo_path` touchpoints (`resolve_code_sha`, worktree, compaction, landing) must each be made remote-aware (run over SSH) or skipped for remote bindings. Decision (operator, 2026-06-16, early): rolled back the live `n8n` binding to the known-good 3-binding state; the committed code stays as the foundation; the pipeline work is a tracked follow-up on Issue #27. **This rollback was reversed later the same day — see below.**

## Resolution 2026-06-16 — RepoHost seam + invariants make remote dispatch work end-to-end

Built the remaining pipeline work (plan `plans/remote-binding-dispatch-pipeline.md`, **Strategy A**: a minimal seam + config invariants instead of scattered guards) and re-ran the live `n8n` smoke. It **passed end-to-end**. See claim **C-0217** (supersedes the "pipeline-deferred / rolled-back" portion of C-0214).

What landed:

- **`RepoHost` seam** (`repo_host.py`): `RepoHost` Protocol (`code_sha()` only), `LocalRepoHost(path)` (delegates to `code_version.resolve_code_sha`; `path` is the dispatch cwd, so local worktree-active runs still record the worktree HEAD), `SshRepoHost(remote, repo_path, run_func)` (`ssh_base_args(remote) + ["git -C <shlex.quoted> rev-parse --short HEAD"]`, 5s timeout, `"unknown"` on non-zero/`OSError`/`TimeoutExpired`, never raises), `repo_host_for(binding, *, cwd, run_func)`. SSH base args extracted to a shared **`ssh_support.py`** (`ssh_base_args`) used by both the adapter and the repo host.
- **Config invariants** (`config._binding_from_mapping`): a `remote:` binding must be `type: coding` + `pi_mode: one-shot` + `default_agent: pi`, else `ConfigError` at load — collapsing the infra-`WORKFLOW.md` read, build-mode plan-file validation, and the RPC startup probe to *unreachable* for remote bindings.
- **`resolve_code_sha` hardened**: catches `OSError`/`PermissionError` → `"unknown"`, never crashes (the proximate cause of the blocked smoke).
- **Three `scheduler.py` `resolve_code_sha` callsites** (`635`, `1508`, `1603`) routed through `repo_host_for(binding, cwd=...).code_sha()` (fallback to local when `binding is None`); `main.py:241` engine self-sha stays local.
- **Worktrees inert for remote**: API `create_binding_issue`/`patch_issue` coerce `worktree_active=False`; `_is_remote_binding` guards `_maybe_merge_worktree`/`_maybe_teardown_archived_worktree`/`_maybe_archive_worktree`/`_purge_archived_issues`; `scheduler._worktree_run_fields` returns `{}` and `_handle_archived_terminal` skips teardown for remote. Remote agent runs directly in `repo_path`; its commits are the landing.
- **Dispatch-gate guards** (`scheduler._apply_dispatch_gate`): fail-loud block remote + non-pi agent (covers issue-level `agent:claude`/`preferred_agent`, which the config `default_agent: pi` invariant does not) and remote + `preferred_skill`. `agent_runner.run_remote_agent` never appends `--skill` (logs `remote_skill_skipped`). Context compaction skipped for remote (`_maybe_compact_context` early-return; web `_compact_issue_context` → 422).
- **Non-fatal startup reachability** (`main._build_binding_runtime`): `repo_host_for(binding).code_sha()` logs `remote_repo_reachable`/`remote_repo_unreachable`, never raises.

**Live smoke (kept live):** re-staged `n8n` (`itadmin@100.95.224.218:/home/itadmin/itastack`, coding/one-shot, `pi`/`openai-codex`/`gpt-5.5:high`). Startup logged `remote_repo_reachable binding=n8n host=100.95.224.218 sha=7f91558` (bindings=4, 0 errors). Smoke Issue 32 → Run 56: `succeeded` / verdict `done` / exit 0 / `agent_session_sha=7f91558` (remote HEAD over SSH) / `worktree_path`,`branch_name`=null. Operator decision: **keep `n8n` as a permanent 4th live binding** (homelab, symphony, dotfiles, n8n). `uv run pytest -q` → 874 passed, 2 skipped (+32; new `tests/test_ssh_support.py`, `tests/test_repo_host.py`).

**Still deferred (v2):** remote worktrees + over-SSH merge/teardown; remote context compaction; remote `preferred_skill`; `_branches_for` degrades to `[]` for remote (non-blocking); Session Tail / Steering / remote orphan-reaping. Host badge UI still pending.

Evidence: `wiki/raw/sessions/2026-06-16-remote-binding-dispatch-pipeline.md`, `plans/remote-binding-dispatch-pipeline.md`, `plans/.remote-binding-dispatch-pipeline.state.yml`, `runs/56.log`.

## Host label landed 2026-06-16 (Issue 34) — "name — repo" for remote bindings

The deferred "host badge UI" got its first slice (text label only). Operator wanted a remote binding shown as **"n8n — itastack"** rather than bare `n8n`; scope per operator reply is name + repo only — **no host/IP chip, no fly-out** in v1 (see claim **C-0218**).

- **API** (`web/api/main.py` `list_bindings`, commit `ad00b0b`): each `/api/bindings` row is enriched with `is_remote` (`_is_remote_binding`) and `repo_name` (basename of `_repo_path_for_binding`), reusing the existing `pi_mode` enrichment pattern. No `binding`-table column and no migration — `bindings.yml` stays the source of truth.
- **Frontend**: `web/frontend/lib/api.ts` `Binding` gains `is_remote: boolean` + `repo_name: string | null`; `Sidebar.tsx` and the dashboard `BindingCard` (`app/page.tsx`, via `BindingSummary.repoName`/`isRemote`) append ` — {repo_name}` only when `is_remote && repo_name`. Local bindings keep single-name labels (remote-only, avoids "homelab — homelab").
- **Test**: `web/api/tests/test_endpoints.py::test_bindings_endpoint_surfaces_remote_repo_name`.
- **Still deferred:** a styled host chip (`user@host`) — the operator explicitly dropped the IP for v1.

### Scaffold writes the `remote:` block (Issue 34 follow-up, commit `60f5475`, claim C-0219)

There is **no dedicated remote-binding skill** — remote bindings are created by `symphony-binding-scaffold` (umbrella `symphony-onboard-project`). The label above is data-driven, so it auto-applies to any binding whose `bindings.yml` entry has a `remote:` block. The remaining gap was that the scaffold helper had no remote inputs, so the live `n8n` block was hand-added. Now `PodiumBindingScaffoldRequest` accepts `remote_host`/`remote_user`/`remote_identity`; when host+user are set, `scaffold_podium_binding` writes a `remote: {host, user, identity?}` block and enforces the C-0217 v1 invariants (`coding`/`pi`/`one-shot`), raising `ValueError` early rather than emitting a `bindings.yml` entry `config.py` would reject. Future remote bindings created via the skill therefore get the SSH dispatch transport *and* the "name — repo" label with no hand-editing.

**Deploy topology (load-bearing):** this change spans two services, *not* the scheduler. `podium-api.service` (loopback `127.0.0.1:8090`) serves the new JSON fields and needs a `systemctl restart`. `podium-web.service` (`10.20.20.16:8091`, `next start`) serves a **prebuilt** bundle and needs `web/frontend/deploy.sh` (build into staging → atomic stop/swap/start), *not* a plain restart. `symphony-host.service` (the scheduler) serves neither — restarting it does nothing for this label. First deploy went live 2026-06-16 (podium-api restarted 15:49 UTC, podium-web 15:52 UTC, root=200); live helpers confirm `is_remote(n8n)=True` / `repo_name=itastack`.
