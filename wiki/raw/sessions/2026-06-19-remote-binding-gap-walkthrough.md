# 2026-06-19 — Remote binding gap walkthrough (grill-me)

Curated capture of a `/grill-me` session walking the Remote Binding (ADR-0012)
dispatch path end-to-end and triaging gaps. Source for claims C-0251–C-0254.

## Scope decision

Operator: remote bindings are a **growing capability** (more hosts/repos over
time), not a one-off `n8n` demonstrator. Harden the reliability/correctness
gaps now rather than defer everything to v2.

## Gap ledger and dispositions

| # | Gap | Disposition |
|---|-----|-------------|
| 1 | No SSH keepalive — idle NAT/Tailscale timeout drops the long pi RPC channel, killing the run | **Fixed 2026-06-19**: `ServerAliveInterval=15` + `ServerAliveCountMax=4` added to `ssh_support.ssh_base_args`. |
| 2 | Remote agent receives no Symphony-forwarded secrets (`_remote_exports` forwards only `SYMPHONY_ISSUE_ID`/`TERM`/`NO_COLOR`, plus Plane callback env for Plane bindings) | **Not a gap — confirmed intended contract**: the remote host owns its own env/secrets (SSH user shell profile / repo `.env`), consistent with ADR-0011 ("safety/secrets are the host's job"). Holds as the fleet grows. |
| 3 | Shared working tree: worktrees inert for remote + `run_cap` is per-binding (unit `SYMPHONY_RUN_CAP=3`) → up to 3 concurrent `pi` processes in one remote `repo_path` → tree corruption + tangled commits | **Decision: serialize per remote binding** (≤1 in-flight Run; effectively `run_cap=1` for remote). Chosen over building remote worktrees (the deferred v2). **NOT yet implemented** — live hazard remains. Implementation point: gate `_reserve_candidate`/`_reserve_specific_candidate` to skip when `binding.is_remote and dispatch_state.in_flight_ids`. |
| 4 | No remote orphan reaping (local reapers use `/proc` + `/tmp` sockets, host-local) | **Default: defer (v2)**. v1 handle is killing the local SSH process group → channel close → remote SIGHUP. |
| 5 | Native session resume cannot reach the remote transcript | **Default: track resume-over-SSH as v2 follow-up** (sibling of the already-deferred remote Session Tail over SSH). Keepalive (#1) cuts the practical drop risk in the interim. |
| 6 | No pre-dispatch reachability gate | **Default: defer**. A down host fails the Run; the non-fatal startup probe already logs `remote_repo_reachable`/`remote_repo_unreachable`. |

## Verified facts (code reading)

### #3 — same-binding concurrency is real, not theoretical

- `config.py:176` `run_cap: int = 2` default; `config.py:294` reads `SYMPHONY_RUN_CAP`; live `symphony-host.service` unit sets `SYMPHONY_RUN_CAP=3`.
- Each binding gets its **own** `run_loop` (`main.py:218` "Each binding gets its own run_loop with a per-binding `_DispatchState`") and its own `_DispatchState(semaphore=asyncio.Semaphore(run_cap), in_flight_ids, in_flight_lock)` (`scheduler/__init__.py:132-146,2256`). So `run_cap` bounds concurrency **per binding**, not globally.
- The poll loop starts one probe per cycle but accumulates `active_tasks` up to `run_cap` across cycles (`scheduler/__init__.py:2322` `slots_available = config.run_cap - len(active_tasks)`); each `_dispatch_one` reserves a distinct candidate via `_reserve_candidate` `in_flight_ids` dedup (`scheduler/__init__.py:2387-2399`).
- Net: a single remote binding (`n8n`, `repo_path=/home/itadmin/itastack`) can run up to 3 concurrent issues, all three `pi` processes in one working tree.

### #5 — native resume cannot engage for remote

- `_dispatch_cwd` (`scheduler/__init__.py:361-376`) returns `config.homelab_repo_path` for a remote binding (worktree fields are `{}` for remote at `:322`), i.e. a local aidev path — not even `binding.repo_path`.
- `session_continuity.evaluate_resume_eligibility` → `session_file_path("pi", cwd, id)` → `_pi_session_dir` resolves `~/.pi/agent/sessions/--…--/` on **aidev's** filesystem (`session_continuity.py:40-56,119-125`). `_session_file_exists` does local `.exists()`/`glob()` (`:111-116`).
- A remote pi RPC run writes its transcript under **n8n's** `~/.pi/agent/sessions/`. The eligibility check inspects the wrong machine → always `REASON_SESSION_ABSENT` → `refeed`. Native CLI resume never fires for remote; every re-dispatch (park/steer/drop) starts cold.

## Change made this session

`ssh_support.ssh_base_args` now emits `-o ServerAliveInterval=15 -o ServerAliveCountMax=4`
after `BatchMode=yes`. `tests/test_ssh_support.py` exact-argv assertions updated;
`tests/test_repo_host.py:92` (`argv[:3]`) and `tests/test_remote_agent.py`
(`[0]=="ssh"`, `"BatchMode=yes" in`) unaffected. `uv run pytest
tests/test_ssh_support.py tests/test_repo_host.py tests/test_remote_agent.py -q`
→ 27 passed. Uncommitted at capture time.

## Open follow-ups

- **Implement #3 serialize-per-remote-binding** — the only live correctness hazard; recommended next action.
- v2: resume-over-SSH (#5), remote orphan reaping (#4), pre-dispatch reachability gate (#6), remote worktrees, remote Session Tail over SSH, styled host chip.
