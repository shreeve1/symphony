---
title: Agent runner + Run Worktree (pre-thin-engine)
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - agent_runner.py
  - run_worktree.py
confidence: high
tags: [agent-adapter, pi, claude, tmux, worktree, naming-scheme, verify_pi_support, ANSI, historical]
---

> **⚠️ Historical — pre-thin-engine.** This page documents `run_worktree.py`, `ClaudeAgentAdapter`, and worktree-per-run dispatch, all of which were removed in thin engine v2 (commit `e73e924`). The running code no longer matches this description. See [thin-engine-v2](thin-engine-v2.md) for current behavior.

# Agent runner + Run Worktree (pre-thin-engine)

`agent_runner.py` (412 LOC) implements the Agent Adapter seam from [ADR-0002](../analyses/adr-0002-generalize-symphony.md) and the tmux dispatch from [ADR-0001](../analyses/adr-0001-claude-tmux.md). `run_worktree.py` (368 LOC) implements the worktree-per-run isolation from [ADR-0003](../analyses/adr-0003-worktree-per-run.md). Combined here because the deterministic `run_id` naming scheme bridges them.

## `AgentResult` (the verdict-bearing return shape)

```python
@dataclass(frozen=True)
class AgentResult:
    exit_code: int
    duration_ms: int
    timed_out: bool
    stdout: str = ""
    stderr: str = ""
```

[source: agent_runner.py#68-74]

## `AgentAdapter` Protocol

```python
class AgentAdapter(Protocol):
    def __call__(
        self,
        issue: CandidateIssue,
        rendered_prompt: str,
        /,
        *,
        worktree_path: Path | None = None,
    ) -> AgentResult: ...
```

[source: agent_runner.py#77-82]

Three concrete adapters share this signature.

## `verify_pi_support` (startup probe)

Fail-fast guardrail from C-0025 / the brainstorm's M3 decision. Two-step [source: agent_runner.py#85-145]:

1. **`pi --help` advertises `--print` and `--no-session`** — if not, raise `AgentRunnerError`. Timeout `PI_HELP_TIMEOUT_SECONDS = 30`.
2. **One-token auth probe** — `pi --print --no-session --provider <p> --model <m> ping` from `cwd=str(cwd)`. Fail if `returncode != 0` or `stdout.strip() == ""`. Timeout `PI_PROBE_TIMEOUT_SECONDS = 30`.

The empty-stdout-zero-exit detection is the **specific** counter to pi's silent-failure mode confirmed in the brainstorm.

## `PiAgentAdapter`

One-shot subprocess. Delegates to `run_agent(config, issue, rendered_prompt, worktree_path=...)`. Built around `subprocess.Popen` + `process.communicate(timeout=...)`; on timeout, `_terminate_process_group` SIGTERMs the process group (`os.killpg`), waits `TERMINATE_GRACE_SECONDS = 5`, then SIGKILLs. Returns `AgentResult(timed_out=True, exit_code=-1, ...)` [source: agent_runner.py#148-275].

## `ClaudeAgentAdapter`

Tmux send-keys per [ADR-0001](../analyses/adr-0001-claude-tmux.md). Fields:

| Field | Default | Purpose |
|---|---|---|
| `claude_bin` | `"claude"` | binary launched as the tmux command |
| `tmux_bin` | `"tmux"` | tmux binary |
| `run_func` | `subprocess.run` | injectable for tests |
| `clock` | `time.monotonic` | injectable |
| `sleep` | `time.sleep` | injectable |
| `nonce_factory` | `lambda: uuid.uuid4().hex` | generates per-run Done Marker nonce |

Sequence per dispatch [source: agent_runner.py#277-340]:

1. `_run_id_from_identifier(issue.identifier or issue.id)` → derive deterministic run_id.
2. Compute `session = tmux_session_name(run_id)`, `socket = tmux_socket_name(run_id)`, `target = f"{session}:0.0"`, `cwd = worktree_path or self.config.homelab_repo_path`.
3. `marker = f"SYMPHONY_DONE_{nonce}"`.
4. `_prompt_with_done_marker(rendered_prompt, marker)` appends instructional epilogue:
   ```
   When all requested work is complete, print this exact done marker on its own line:
   <marker>
   ```
5. `tmux -L <socket> new-session -d -s <session> -c <cwd> <claude_bin>`.
6. `tmux -L <socket> load-buffer -` (stdin: prompt).
7. `tmux -L <socket> paste-buffer -t <target>`.
8. `tmux -L <socket> send-keys -t <target> Enter`.
9. Poll loop, `TMUX_POLL_INTERVAL_SECONDS = 1`:
   - `tmux capture-pane -p -t <target> -S -` → pane text.
   - `_pane_before_marker(pane, marker)` returns ANSI-stripped pane content before the marker if marker present, else `None`.
   - On marker: `_kill(socket, session)`, return `AgentResult(exit_code=0, stdout=before_marker)`.
   - On timeout (`run_timeout_ms / 1000`): `_kill`, return `AgentResult(exit_code=-1, timed_out=True, stdout=_strip_ansi(last_pane), stderr="Claude adapter timed out before done marker ...")`.
10. Any tmux subcommand returning non-zero → kill session, return `AgentResult(exit_code=127, ...)`.

## `RoutingAgentAdapter`

Per-Binding dispatch routing [source: agent_runner.py#367-380]:

```python
@dataclass(frozen=True)
class RoutingAgentAdapter:
    binding: ProjectBinding
    pi_adapter: AgentAdapter
    claude_adapter: AgentAdapter

    def __call__(self, issue, rendered_prompt, /, *, worktree_path=None):
        selected = self.binding.resolve_agent(issue.labels)
        adapter = self.claude_adapter if selected == "claude" else self.pi_adapter
        return adapter(issue, rendered_prompt, worktree_path=worktree_path)
```

`ProjectBinding.resolve_agent(labels)` checks `agent:claude` / `agent:pi` label override, falling back to `default_agent`.

## ANSI stripping

```
_ANSI_ESCAPE_RE = r"\x1b\[[0-9;?]*[ -/]*[@-~]"
```

`_strip_ansi(text)` applied to claude pane output before comparing against the Done Marker and before storing in `AgentResult.stdout` on timeout. `scheduler.py` has the same regex to clean stderr for Plane comments.

## Run Worktree — deterministic naming scheme

This is what makes [ADR-0003](../analyses/adr-0003-worktree-per-run.md) C-0019 work — without an in-memory map, durable signals (worktree dirs, branches, tmux sessions) must be recoverable from issue identifier alone.

```python
run_id          = sha256(identifier.strip().lower())[:8]
worktree_path   = config.worktrees_root / f"run-{run_id}"
worktree_branch = f"symphony/run-{run_id}"
tmux_session    = f"symphony-{run_id}"
tmux_socket     = f"symphony-run-{run_id}"
```

[source: run_worktree.py#24-58]

## `list_worktrees(homelab_repo_path)`

Reads `git worktree list --porcelain`, parses `worktree <path>` and `branch <ref>` lines, **excludes the shared checkout itself**. Returns `[(path, branch), ...]` [source: run_worktree.py#61-99].

## `_run_id_from_worktree_path(repo, wt_path)`

Reverse lookup for startup reconcile. Handles two layouts [source: run_worktree.py#102-123]:

1. Inside repo: `<repo>/worktrees/run-<id>` → returns `<id>`.
2. External `worktrees_root`: any path tail starting with `run-` → returns the suffix.

Returns `None` when neither matches.

## Lifecycle functions

| Function | Purpose |
|---|---|
| `create_worktree(config, run_id, base_branch=None)` | `git worktree add` on new branch (or reuse existing branch ref); creates `worktrees_root` parent dirs as needed; raises `WorktreeError` if path already in `git worktree list` |
| `remove_worktree(config, run_id)` | canonical cleanup after Verdict reconcile; **keeps the branch** (contains run's commits for later landing); silently succeeds if missing; falls back to `git worktree prune` on remove failure |
| `remove_worktree_if_exists(config, run_id)` | for crash/timeout paths where the worktree may or may not have been created; swallows `WorktreeError` |
| `_delete_run_branch(config, run_id)` | safe branch delete; debug-logs already-gone state; raises `WorktreeError` on git failure |
| `_run_branch_exists(config, run_id)` | checks `refs/heads/symphony/run-<id>` |

[source: run_worktree.py#229-369]

## Tmux session helpers (for reconcile and reaper)

| Function | Purpose |
|---|---|
| `_tmux_sessions_for_prefix(prefix="symphony-", *, socket_name=None)` | enumerate sessions for crash-recovery scan |
| `_tmux_session_alive(session_name, *, socket_name=None)` | probe a specific session |
| `kill_tmux_session(run_id)` | nuke session by run_id |
| `_kill_tmux_session_on_socket(run_id, *, socket_name=None)` | kill on the per-run socket (matches the launch path) |

These are the durable signals `reconcile_startup` reads to rebuild the live-Run set after a service restart (C-0019).

## Related

- [ADR-0001 — claude tmux dispatch](../analyses/adr-0001-claude-tmux.md)
- [ADR-0003 — worktree-per-run](../analyses/adr-0003-worktree-per-run.md)
- [Brainstorm — pi-swap silent-failure rationale](../analyses/brainstorm-pi-swap.md)
- [Scheduler loop](scheduler-loop.md)
