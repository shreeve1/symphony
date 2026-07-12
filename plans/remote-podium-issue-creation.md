# Plan: Remote Podium Issue Creation Over the Dispatch Tunnel

## Task Description

Enable an **unattended agent running a remote binding** to slice an approved plan
into Podium issues in this Symphony, without leaving Podium. Implements ADR-0036
(`docs/adr/0036-remote-podium-issue-creation-over-dispatch-tunnel.md`).

Today the `podium-issues` skill writes `/var/lib/symphony/podium.db` directly and
resolves the binding by matching `cwd` against `repo_path` in `bindings.yml`
(`web/cli/podium_issues.py`) — neither the DB nor `bindings.yml` exists on a
remote host, and the Podium API is loopback-only on aidev. This plan adds:

1. a new global skill `podium-issues-remote` — a self-contained stdlib-`urllib`
   HTTP client that POSTs slices to the Podium API (blockers first, threading
   returned int ids into dependents' `blocked_by`); and
2. harness wiring in `agent_runner.py` so that **when a remote run's
   `preferred_skill == podium-issues-remote`**, remote dispatch forwards the SSH
   reverse tunnel at `:8090` and exports `PODIUM_BASE_URL`, `PODIUM_API_TOKEN`
   (existing global token), and `SYMPHONY_BINDING_NAME` into the remote env.

## Objective

An issue filed against a remote binding with `preferred_skill=podium-issues-remote`
dispatches an unattended agent that plans, then POSTs its slices to this
Symphony's Podium API over the SSH reverse tunnel — creating real `todo` issues
(with `auto_land`, `worktree_active`, `blocked_by`, `locks`) against the same
remote binding, which the operator reviews in the board. No API changes, no new
credentials, no exposure of the API beyond loopback.

## Problem Statement

The slice-authoring workflow (`podium-issues`) is on-box only: it writes SQLite
directly and reads `bindings.yml` to resolve `cwd`. A remote host has neither,
and the Podium API it would otherwise call (`POST /api/bindings/{name}/issues`)
binds `127.0.0.1:8090` deliberately behind Authelia (`web/README.md`). So a
remote agent cannot create issues here — the operator must SSH back to aidev and
run the skill manually, defeating "never leave Podium."

## Solution Approach

Reuse ADR-0012's existing remote-dispatch SSH plumbing. The `ssh -R` reverse
tunnel is already opened on every remote run (`agent_runner.py:670`), but its
port is derived from `config.plane_api_url` (Plane's `:8000`,
`_remote_callback_port`), which nothing listens on for a Podium binding.

- **Harness (Option B, skill-gated):** in `run_remote_agent`, detect
  `issue.preferred_skill == "podium-issues-remote"`. When true, force the reverse
  tunnel port to the Podium API port (parsed from `config.podium_api_url`,
  default `8090`) and add `PODIUM_BASE_URL=http://127.0.0.1:<port>`,
  `PODIUM_API_TOKEN` (from the scheduler's env), and `SYMPHONY_BINDING_NAME`
  (`issue.binding_name`, resolved via `binding.name`) to `_remote_exports`. When
  false, behavior is byte-for-byte unchanged (Plane bindings keep `:8000` +
  callback env; Podium bindings keep no callback env and the dead `:8000`
  tunnel exactly as today).

- **Skill:** `podium-issues-remote` lives in-repo at
  `.claude/skills/podium-issues-remote/` so it is catalog-scannable (ADR-0033)
  and ships over SSH via the existing `skill_source` tar path
  (`agent_runner.py:588`). It bundles `create_issues.py`, a stdlib-only
  (`urllib.request`, `json`, `os`, `sys`) client that reads `PODIUM_BASE_URL` /
  `PODIUM_API_TOKEN` / `SYMPHONY_BINDING_NAME` from env, reads a YAML/JSON slice
  spec, topologically orders slices, POSTs blockers first, and threads returned
  ids into dependents' `blocked_by`. It mirrors the local `_description()`
  format (What to build / Acceptance criteria / Verification). `--dry-run`
  prints planned payloads without POSTing.

Note on YAML: to stay dependency-free on the remote (no `pyyaml` guarantee), the
bundled client accepts the slice spec as **JSON** (the SKILL.md instructs the
agent to write a `.json` spec). This avoids importing `yaml` on the remote,
unlike the local skill which runs inside the Symphony venv.

## Relevant Files

Use these files to complete the task:

- `agent_runner.py` — `run_remote_agent` (line ~540), `_remote_exports` (line
  ~459), `_remote_callback_port` (line ~447), and the `port =` / `_ssh_base_args(remote, reverse_port=port)`
  call sites (lines ~618, ~670). The only production file that changes.
- `config.py` — `SymphonyConfig` (line ~181, `plane_api_url` and the
  `tracker_api_url` property at ~210). Add a `podium_api_url` field with an
  `8090` default sourced from a `PODIUM_BASE_URL`/`PODIUM_API_URL` env, so the
  port is not hardcoded in `agent_runner.py`.
- `tracker_types.py` — `CandidateIssue` (`preferred_skill` line 42,
  `binding_name` line 45). Both present on the dispatched issue; the harness uses
  `binding.name` for `SYMPHONY_BINDING_NAME`. Read-only reference.
- `ssh_support.py` — `ssh_base_args(reverse_port=...)`; no change expected, just
  the consumer of the new port value. Read-only reference.
- `web/api/main.py` — `IssueCreate` (line 608) and
  `POST /api/bindings/{name}/issues` (line 1127). Read-only: confirms the
  client's payload contract. No change.
- `web/api/auth.py` — `verify_bearer_token` (line 77), `PODIUM_API_TOKEN` read
  (line 65). Read-only: confirms the auth path. No change.
- `web/cli/podium_issues.py` — `_description()` (line ~192), `_topo_order`
  (line ~150). Read-only reference the bundled client mirrors.
- `tests/test_remote_agent.py` — existing remote-dispatch tests (527 lines) to
  extend with skill-gated tunnel/env assertions.
- `tests/test_config.py` — extend for the new `podium_api_url` field/default.

### New Files

- `.claude/skills/podium-issues-remote/SKILL.md` — the remote slice-authoring
  skill (authoring rules copied from `podium-issues`; create step invokes the
  bundled client; non-interactive; `--dry-run` documented).
- `.claude/skills/podium-issues-remote/create_issues.py` — stdlib-only HTTP
  client (POST blockers-first, id-threading, dry-run).
- `tests/test_podium_issues_remote.py` — unit tests for the client's topo
  ordering, id-threading, payload shape, and dry-run (import the module by path;
  monkeypatch `urllib.request.urlopen`).

## Implementation Phases

### Phase 1: Foundation
Add `podium_api_url` to `SymphonyConfig` (default `http://127.0.0.1:8090`,
env-overridable) so the port is config-driven, and confirm the dispatched issue
carries `binding_name` (else use `binding.name`).

### Phase 2: Core Implementation
Wire the skill-gated tunnel port + env exports into `run_remote_agent` /
`_remote_exports`. Author the `podium-issues-remote` SKILL.md and bundled
`create_issues.py` client.

### Phase 3: Integration & Polish
Extend `tests/test_remote_agent.py`, add `tests/test_podium_issues_remote.py`,
extend `tests/test_config.py`; run the full suite.

## Step by Step Tasks

IMPORTANT: Execute every step in order when running manually. `/dev-build` will
parallelize independent groups automatically.

### 1. Config: podium_api_url
- [x] [1.1] In `config.py`, add a `podium_api_url: str = "http://127.0.0.1:8090"`
      field to the frozen `SymphonyConfig` dataclass. In `from_env` (line ~300),
      populate it: `podium_api_url=(source.get("PODIUM_BASE_URL") or
      source.get("PODIUM_API_URL") or "http://127.0.0.1:8090").rstrip("/")`. AND
      add `f"podium_api_url={self.podium_api_url!r}, "` to the custom `__repr__`
      (config.py:391, which enumerates every field) so the field is visible in
      logs and assertion failures — every other field follows this pattern.
      `__post_init__` needs no change (the default is not derived from other
      fields).
- [x] [1.2] Confirm `CandidateIssue` exposes the owning binding name for dispatch;
      if `binding_name` is absent, plan to pass `binding.name` in step 2 (no
      schema change).

### 2. Harness: skill-gated tunnel + env
- [x] [2.1] In `agent_runner.py`, add a module-level constant
      `PODIUM_ISSUES_REMOTE_SKILL = "podium-issues-remote"` and a helper
      `_wants_podium_api(issue) -> bool` returning
      `getattr(issue, "preferred_skill", "") == PODIUM_ISSUES_REMOTE_SKILL`.
- [x] [2.2] In `run_remote_agent`, when `_wants_podium_api(issue)`, set
      `port = _remote_callback_port(config.podium_api_url)` (else keep the
      existing `config.plane_api_url` derivation). The existing
      `_ssh_base_args(remote, reverse_port=port)` call then forwards `:port`.
      Note: `_remote_callback_port` falls back to 8000 when the URL has no
      explicit port; the `podium_api_url` default carries `:8090` explicitly, so
      the happy path is correct. If an operator overrides `PODIUM_BASE_URL`
      without a port, the tunnel would open on 8000 while the API listens on
      8090 — acceptable for now (documented risk in Notes), since the default is
      port-explicit.
- [x] [2.3] Change the `_remote_exports` signature to
      `_remote_exports(config, issue, *, binding, source_env) -> dict[str, str]`
      and update the call site in `run_remote_agent` (line ~631) to pass
      `source_env=source_env` (already defined at line ~592 as
      `os.environ if environ is None else environ`). When `_wants_podium_api(issue)`,
      add `PODIUM_BASE_URL=f"http://127.0.0.1:{port}"` (the tunnel always lands
      on the remote's loopback — do NOT export `config.podium_api_url` verbatim,
      or an externally-set `PODIUM_BASE_URL` in the scheduler env would make the
      remote POST to an external host and bypass the tunnel),
      `SYMPHONY_BINDING_NAME=binding.name`, and the token. Read the token via
      `token = source_env.get("PODIUM_API_TOKEN") or ""`; if it is empty, raise
      `AgentRunnerError("PODIUM_API_TOKEN not set; required for "
      "podium-issues-remote dispatch")` at this point rather than shipping an
      empty `Bearer` that 401s cryptically on the remote. Reading the token via
      `source_env` (not `os.environ` directly) is what makes T.2.2 testable via
      the `environ=` kwarg. Non-gated runs add none of these — behavior
      unchanged.
- [x] [2.4] Ensure `needs_remote_tmp` / skill shipping already covers this skill
      (it does, via `skill_source`); no change to the ship path, but verify the
      skill dir tar includes `create_issues.py` (whole-parent-dir tar already
      does).

### 3. Skill: podium-issues-remote
- [x] [3.1] Create `.claude/skills/podium-issues-remote/SKILL.md`: front matter
      (`disable-model-invocation: true`, name, description), authoring rules
      copied from `podium-issues` (vertical slices, objective acceptance,
      single-backtick verification, migration lock C-0335), and a create step
      that writes a JSON slice spec then runs
      `python3 create_issues.py <spec.json>` (and `--dry-run` first). Explicitly
      note: no operator approval (unattended), operator reviews the board after.
      **Model-validation limitation:** unlike the local skill (which validates
      each slice `model` against `models.yml` at create time via
      `_validate_model_agent`), the remote client cannot — it has no `models.yml`
      and the API does not validate models on create. The `symphony-models` skill
      is NOT shipped to the remote (only the `podium-issues-remote` dir is
      tarred over), so the agent cannot look up the catalog remotely. Therefore
      SKILL.md MUST instruct the agent to **omit `model`/`agent` entirely**
      (issues inherit the binding default) unless the operator named an exact
      model in the plan — and warn that a bad model name is caught only at
      dispatch (a broken `todo` row), not at create. Omitting is the safe
      default.
- [x] [3.2] Create `.claude/skills/podium-issues-remote/create_issues.py`:
      stdlib-only, shebang `#!/usr/bin/env python3`. Read `PODIUM_BASE_URL`,
      `PODIUM_API_TOKEN`, `SYMPHONY_BINDING_NAME` from env (fail loud if any
      missing). Parse JSON spec (list of slices: key, title, description,
      acceptance[], verification, blocked_by[keys], locks[], optional
      priority/model/agent). Topo-order by `blocked_by` keys (raise on cycle).
      POST each to `{base}/api/bindings/{binding}/issues` with
      `Authorization: Bearer <token>`, body per `IssueCreate`. The `description`
      MUST reproduce the local `_description()` format exactly
      (`web/cli/podium_issues.py:192`):
      `"## What to build\n\n{description}\n\n## Acceptance criteria\n\n{accept}\n\n## Verification\n\n{verification}\n"`
      where `{accept}` is `"\n".join(f"- [ ] {item}" for item in acceptance)`.
      Set `auto_land=True`, `worktree_active=True`; map resolved blocker keys →
      returned int ids in `blocked_by`; pass `locks`, and
      `preferred_model`/`preferred_agent` only when set. Do NOT send `origin`
      — include a comment: `# origin deliberately omitted; API defaults to
      "operator" (agent acts on operator's behalf, not a patrol)`. `--dry-run`
      prints payloads and skips POST. Raise nonzero on any HTTP 4xx/5xx
      (surface the API's error body).

### 4. Tests
- [x] [4.1] In `tests/test_config.py`, assert `podium_api_url` default is
      `http://127.0.0.1:8090` and that `PODIUM_BASE_URL` overrides it.
- [x] [4.2] In `tests/test_remote_agent.py`, add a positive test: Podium remote
      binding + an issue with `preferred_skill=podium-issues-remote`, called as
      `run_remote_agent(config, issue, "spec", binding=..., environ={"PODIUM_API_TOKEN": "test-token"}, ...)`.
      Assert SSH argv contains `-R 8090:127.0.0.1:8090` AND the remote command
      string contains `PODIUM_BASE_URL=`, `PODIUM_API_TOKEN=test-token`, and
      `SYMPHONY_BINDING_NAME=`. (Passing the token via `environ=` is required —
      `_remote_exports` reads it from `source_env`, per 2.3.)
- [x] [4.3] In `tests/test_remote_agent.py`, add a negative test: Podium remote
      binding with a different/no `preferred_skill` → argv still `-R 8000:...`
      and NO `PODIUM_*` exports (behavior unchanged), even when
      `environ={"PODIUM_API_TOKEN": "test-token"}` is passed. Confirm the
      existing `test_run_remote_agent_omits_plane_env_and_helper_for_podium`
      still passes.
- [x] [4.3b] In `tests/test_remote_agent.py`, add a test: gated skill with an
      empty/missing `PODIUM_API_TOKEN` (call with `environ={}`) raises
      `AgentRunnerError` before dispatch (no `Bearer ` shipped).
- [x] [4.4] Create `tests/test_podium_issues_remote.py`: load `create_issues.py`
      by path (`importlib`), monkeypatch `urllib.request.urlopen` to capture
      requests and return canned `{"id": N}` responses; assert blockers POST
      before dependents, dependent `blocked_by` carries the real returned ids,
      description contains acceptance+verification, and `--dry-run` issues zero
      requests.
- [x] [4.5] Run the full suite (relocation/new-module safety per C-0335 /
      podium-issues refactor rule).

## Testing Strategy

- **Unit — client:** `tests/test_podium_issues_remote.py` covers topo ordering,
  id threading, payload shape, auth header, and dry-run with a mocked
  `urlopen` (no network, no live API).
- **Unit — harness:** `tests/test_remote_agent.py` covers the skill-gated tunnel
  port and env exports (positive) and the unchanged path (negative), using the
  existing fake `run_func`/`popen_factory` fixtures.
- **Unit — config:** `tests/test_config.py` covers the new field default and env
  override.
- Edge cases: missing env var in client (fail loud); slice dependency cycle
  (client raises); empty `preferred_skill` (harness no-op).

## Tests

### T.1. Client (create_issues.py)
- [x] [T.1.1] blockers POST before dependents (topo order)
- [x] [T.1.2] dependent `blocked_by` contains real returned int ids
- [x] [T.1.3] description folds acceptance + verification; auto_land/worktree_active set
- [x] [T.1.4] `--dry-run` performs zero HTTP requests
- [x] [T.1.5] missing `PODIUM_API_TOKEN`/`PODIUM_BASE_URL`/`SYMPHONY_BINDING_NAME` fails loud
- [x] [T.1.6] dependency cycle raises

### T.2. Harness (run_remote_agent)
- [x] [T.2.1] gated: argv has `-R 8090:127.0.0.1:8090`
- [x] [T.2.2] gated: exports include `PODIUM_BASE_URL`, `PODIUM_API_TOKEN`, `SYMPHONY_BINDING_NAME`
- [x] [T.2.3] non-gated Podium binding: argv unchanged (`8000`), no `PODIUM_*` exports
- [x] [T.2.4] Plane binding path unaffected

### T.3. Config
- [x] [T.3.1] `podium_api_url` default `http://127.0.0.1:8090`
- [x] [T.3.2] `PODIUM_BASE_URL` env overrides it

## Progress
**Phase Status:**
- Build: `complete`
- Test: `complete`

**Task Counts:**
- Implementation: `14/14` tasks complete
- Tests: `12/12` tests passing

**Last Updated:** `2026-06-19`

## Acceptance Criteria

- A remote-binding run with `preferred_skill=podium-issues-remote` gets a
  `-R 8090:127.0.0.1:8090` tunnel and `PODIUM_BASE_URL`/`PODIUM_API_TOKEN`/
  `SYMPHONY_BINDING_NAME` in its remote env; all other remote runs are byte-for-
  byte unchanged.
- The bundled `create_issues.py` creates issues over the API in dependency order
  with correct `blocked_by` int ids, `auto_land`/`worktree_active`, and `locks`,
  using the existing Bearer auth; `--dry-run` posts nothing.
- No changes to `web/api/` (endpoint, schema, auth) are required.
- Full test suite passes.

## Testing Promise

All unit tests in `tests/` pass with zero failures — specifically the new
`tests/test_podium_issues_remote.py`, the added remote-dispatch cases in
`tests/test_remote_agent.py`, and the config cases in `tests/test_config.py` —
verifying skill-gated tunnel/env injection and the client's ordering, id
threading, payload shape, auth, and dry-run.

## Validation Commands

Execute these commands to validate the task is complete:

- `.venv/bin/python -m pytest -q` — full suite (mandatory for new-module/import
  changes per the podium-issues refactor rule / C-0335).
- `.venv/bin/python -m pytest tests/test_remote_agent.py tests/test_config.py tests/test_podium_issues_remote.py -q` — focused run for this change.
- `python3 -m py_compile .claude/skills/podium-issues-remote/create_issues.py` — client compiles under bare python3 (no venv), proving stdlib-only.

## Notes

- **Security (ADR-0036 consequence):** `PODIUM_API_TOKEN` is a single global
  bearer token, not scoped per binding — anything holding it can act on every
  binding. Skill-gated injection limits *when* a remote box holds it; accepted
  because the remote host is already inside the trust boundary. Do not log the
  token; `_build_remote_command` already `shlex.quote`s exports.
- **Stdlib-only constraint:** `create_issues.py` must not import `yaml` or any
  repo module — the remote checkout is not the Symphony repo and has no venv.
  Spec is JSON. `py_compile` under bare `python3` is the guard.
- **No new dependencies** (`uv add` not needed).
- **Deferred model validation (ADR-0036 scope):** the local skill validates each
  slice `model` against `models.yml` at create time; the remote client cannot
  (no `models.yml`, and "no API changes" forbids server-side validation on
  create). A bad model name is therefore caught only at dispatch as a run
  failure, leaving a broken `todo` row. Mitigated by the SKILL.md instruction to
  use only known catalog models / omit `model` when unsure (task 3.1). Accepted
  as consistent with ADR-0036's "no API changes" boundary. The remote agent
  cannot reach the `symphony-models` skill (not shipped), so SKILL.md tells it to
  omit `model`/`agent` and inherit the binding default unless the operator named
  an exact model.
- **PODIUM_BASE_URL is loopback on the remote:** the harness exports
  `http://127.0.0.1:{port}`, never the scheduler's own `config.podium_api_url`
  verbatim — the reverse tunnel always terminates on the remote's loopback, and
  exporting an externally-set base URL would bypass the tunnel.
- **Empty token fails loud at dispatch:** the harness raises `AgentRunnerError`
  if `PODIUM_API_TOKEN` is unset for a gated run, rather than shipping an empty
  `Bearer` that 401s cryptically on the remote.
- **Port-explicit default:** `podium_api_url` defaults to `http://127.0.0.1:8090`
  (explicit port). `_remote_callback_port` falls back to 8000 only when a URL
  carries no port; an operator overriding `PODIUM_BASE_URL` without a port would
  get a tunnel/API port mismatch — documented, low-likelihood, acceptable.
- **`origin` defaults to `operator`:** the client sends no `origin`, so the API
  tags created issues `operator` (agent acting on the operator's behalf) — not
  `patrol`. This is intentional; a comment in `create_issues.py` preempts an
  implementor adding `origin=patrol`.
- **Remote Python:** the SKILL.md invokes `python3`; the remote host must have
  Python 3 (true for all current remote bindings). Stdlib-only keeps it
  venv-free.
- This plan is deliberately small/cohesive — one production file (`agent_runner.py`,
  plus a config field) and a self-contained skill. It is not a multi-slice
  vertical fan-out.
