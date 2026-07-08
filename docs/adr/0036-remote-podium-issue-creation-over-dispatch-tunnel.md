---
status: proposed
relates-to: ADR-0012 (remote binding SSH exec), ADR-0021 (issue dependencies + parallel dispatch), ADR-0030 (podium-issues validate model at load)
context: operator wants to plan inside a remote-binding run and slice that plan into Podium issues without leaving Podium; the podium-issues skill writes the local SQLite DB directly and cannot run off-box
---

# Remote Podium issue creation over the dispatch SSH tunnel

## Decision

Add a `podium-issues-remote` skill plus harness wiring so an **unattended agent
running a remote binding** can slice an approved plan into Podium issues in this
Symphony over the existing SSH reverse tunnel — no interactive approval, no
`bindings.yml` or DB access on the remote host.

Concretely:

- **New skill `podium-issues-remote`.** Copies the slice-authoring rules from
  `podium-issues` (vertical tracer-bullet slices, objective acceptance,
  single-backtick runnable verification, migration lock C-0335), but its create
  step is a self-contained stdlib-`urllib` HTTP client — **no `uv`, no repo
  imports, no CLI** — that POSTs to the Podium API. It posts blockers first and
  threads the returned integer ids into dependents' `blocked_by`. It is
  non-interactive: it posts directly and the operator reviews the created issues
  in the Podium board afterward (Reading 1). `--dry-run` prints the planned
  payloads to the run log without POSTing.

- **Harness injects the connection, gated on the skill.** When a remote run's
  `preferred_skill == podium-issues-remote`, remote dispatch (`agent_runner.py`)
  additionally:
  1. forwards `ssh -R 8090:127.0.0.1:8090` (the reverse tunnel is already opened
     unconditionally today, but points at Plane's `:8000` via
     `_remote_callback_port(config.plane_api_url)`; for this skill it targets the
     Podium API port instead);
  2. exports `PODIUM_BASE_URL=http://127.0.0.1:8090`, `PODIUM_API_TOKEN` (the
     existing global service token), and `SYMPHONY_BINDING_NAME` (from
     `issue.binding_name`, since the remote has no `bindings.yml` to resolve
     which binding it is).

- **No API changes.** The HTTP `IssueCreate` contract
  (`POST /api/bindings/{name}/issues`) already accepts every field the local
  DB-writer sets — `auto_land`, `worktree_active`, `blocked_by` (real int ids),
  `locks`, `preferred_model`/`agent`/`skill` — and the Bearer auth path
  (`verify_bearer_token`) already exists for the Temporal patrol worker. The
  remote skill reuses both unchanged.

## Why

The `podium-issues` skill writes `/var/lib/symphony/podium.db` directly and
resolves the binding by matching `cwd` against `repo_path` in `bindings.yml`
(`web/cli/podium_issues.py`). Neither the DB nor `bindings.yml` exists on a
remote host, so the skill cannot run off-box as-is. The Podium API is
loopback-only on aidev (`--host 127.0.0.1 --port 8090`, deliberately behind
Authelia per `web/README.md`), so a remote caller has no network path to it
either.

ADR-0012 already dispatches remote runs over SSH and already opens a reverse
tunnel; redirecting that tunnel at `:8090` and exporting the existing token is
the surgical way to give the remote run a scoped, run-lifetime path back to the
API — reusing the exact mechanism (tunnel + bearer token) patrol already uses,
without exposing the API on the LAN or minting new credentials.

## Considered options

- **Static skill carrying its own connection (rejected).** Hardcode a reachable
  API URL + token in an env file copied onto each remote host. Would require
  exposing the Podium API on the LAN/Tailscale interface and parking the master
  token in a file on every remote box permanently. Rejected in favor of the
  run-lifetime tunnel, which keeps the API loopback and the token present only
  during the run.

- **Interactive inline approval via live steering (rejected).** The operator
  approves each slice batch mid-run over the steer channel. Heavier, and the
  original skill's interactive approval step cannot run under unattended
  `bypassPermissions` dispatch anyway. Rejected for Reading 1 (unattended agent
  posts; operator reviews the board after).

- **Scoped/limited credential (rejected).** A per-binding or create-only token
  would shrink the blast radius, but no such mechanism exists — it is net-new
  auth work. Rejected as out of scope; the global token is accepted (see below).

- **Unconditional token/tunnel injection on every remote run (rejected).** Every
  remote run would carry the master token even when it has no API business.
  Rejected in favor of gating on `preferred_skill == podium-issues-remote` so the
  credential is present only for the one workflow that needs it.

## Consequences

- **The global `PODIUM_API_TOKEN` is a master key.** It is not scoped per
  binding (`web/api/auth.py`): anything holding it can create/patch/reply/steer
  issues in **every** binding. Gating injection on the skill limits *when* a
  remote box holds it, but during such a run the remote host (unattended,
  `bypassPermissions`) briefly holds full API access to all projects. Accepted:
  the remote host is already inside the trust boundary (it runs your agents
  unattended and you SSH into it), and the token lives only in the run env and
  dies with the run.

- New cross-host contract: remote hosts authenticate to the Podium API over the
  dispatch tunnel with the global token. Future remote→API features can reuse the
  same tunnel/env path.

- `podium-issues-remote` must stay dependency-free (stdlib only); it cannot
  import repo modules or call `uv`, since the remote checkout is not the Symphony
  repo.
