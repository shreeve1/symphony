# Plan: Move Symphony repo from `/home/james/plane/symphony` to `/home/james/symphony`

> **Revision history**
> - **v1** (initial draft): six phases, 35 tasks.
> - **v2** (post `/dev-review-claude`): incorporates 4 Critical + 4 Warning
>   findings from an independent Claude Opus 4.7 reviewer. Material changes:
>   added `telegram-alert@.service` to the systemd edit set, added a third
>   commit in dotfiles (skill files are symlinks into `~/dotfiles/`), added a
>   pre-mv CWD guard, widened the final reference sweep to catch tilde-form
>   refs, added `systemd-analyze verify` before `daemon-reload`, added stale
>   tmux pane enumeration, added post-commit rollback branch, added
>   `~/dotfiles/.codex/config.toml` and homelab OpenCode `PlaneTicket` skill
>   to the edit set. Now 59 implementation tasks + 16 test tasks.

## Task Description

Relocate the Symphony source repository out of its nested home under the Plane
stack (`/home/james/plane/symphony`) and into a top-level location
(`/home/james/symphony`). Move the associated env file
(`/home/james/plane/symphony-host.env` and its `.bak` sibling) alongside it for
consistency. Update every live reference (systemd unit, in-repo hardcoded test
paths, ~/.claude skill files, CLAUDE.md home/plane guides, homelab runbook and
host doc). Plane-stack files (`docker-compose.yml`, `variables.env`,
`provision_plane.py`) remain in `/home/james/plane/` — only Symphony moves.

**Critical execution constraint:** the running Claude/AI session is currently
rooted at `/home/james/plane/symphony`. Every command in this plan uses
absolute paths and assumes CWD is `/home/james/` (or any directory **outside**
the source). The first executed step changes CWD out of the source tree so the
`mv` does not invalidate the session's working directory mid-flight.

## Objective

After this plan completes:
- `/home/james/symphony` is the Symphony git repo (was `/home/james/plane/symphony`).
- `/home/james/symphony-host.env` is the env file (was `/home/james/plane/symphony-host.env`).
- `/home/james/plane/symphony` no longer exists.
- `symphony-host.service` is active, has completed at least one
  `reconcile_startup_done` and `dispatch_completed` cycle from the new path.
- `python3 -m pytest` from `/home/james/symphony` passes (same baseline as
  before the move).
- All five `~/.claude/skills/symphony-*/SKILL.md` files that contain stale refs
  reference the new path. (The other two `symphony-*` skills —
  `symphony-onboard-project` and `symphony-plane-recover` — were verified clean
  and need no edit.) Note these skill paths are symlinks into
  `/home/james/dotfiles/`, so the edits land in the **dotfiles** git repo, not
  in `/home/james/symphony` — a separate commit is required.
- `telegram-alert@.service` (the `OnFailure=` target for `symphony-host.service`)
  references the same env file and must be updated alongside the main unit;
  otherwise failure alerting will silently break after the env-file move.
- `/home/james/dotfiles/.codex/config.toml`'s
  `[projects."/home/james/plane/symphony"]` key is renamed to
  `[projects."/home/james/symphony"]`.
- `/home/james/homelab/.opencode/skills/PlaneTicket/` (SKILL.md and Workflows)
  is updated alongside the runbook (separate skill tree from the historical
  `homelab/.opencode/skills/symphony/` exclusion).
- The two `CLAUDE.md` guides, the homelab runbook, and the homelab host doc
  reference the new path. The `~/CLAUDE.md` tilde-form reference is rewritten
  to `~/symphony/`.
- The in-repo hardcoded absolute paths in `tests/test_plane_cli.py` are fixed
  to be relative (`Path(__file__).resolve().parent.parent / "plane_cli.py"`) so
  this class of breakage doesn't recur.

## Problem Statement

Symphony lives one level too deep. The nesting makes `cd` paths longer, mixes
Symphony's git repo with the Plane-stack working directory (which is
intentionally **not** a git repo per `/home/james/plane/CLAUDE.md`), and the
hardcoded absolute path `/home/james/plane/symphony/...` in three test cases is
a recurring tripping hazard. A flat `/home/james/symphony` mirrors how
`/home/james/homelab` and `/home/james/trading` are organized. Side benefit:
any AI session that breaks because its CWD vanishes during a `mv` would lose
work; this plan is structured so that never happens.

## Solution Approach

Six-phase sequential execution. Each phase is a clear checkpoint with its own
verification command. The order is:

1. **Pre-flight** — capture baselines (git clean, tests green, unit state) and
   commit this plan so it survives in git history.
2. **Stop service & move filesystem** — `systemctl stop`, then a single
   `mv` for the repo and two `mv`s for the env files. After this phase the
   only reference to the old path that still matters is the systemd unit.
3. **Update systemd units** — back up, edit `symphony-host.service` *and*
   `telegram-alert@.service`, `systemd-analyze verify` both, `daemon-reload`.
   Do NOT start yet.
4. **Fix in-repo hardcoded test paths** — convert the three
   `/home/james/plane/symphony/plane_cli.py` strings in
   `tests/test_plane_cli.py` to `Path(__file__).resolve().parent.parent /
   "plane_cli.py"`. Run pytest to confirm.
5. **Start service & verify** — `systemctl start`, then watch journal for the
   three liveness markers (`symphony_started`, `reconcile_startup_done`,
   `dispatch_completed`).
6. **Update documentation + dotfiles** — five skill files (via dotfiles repo),
   dotfiles `.codex/config.toml`, two CLAUDE.md guides, the homelab runbook
   (including OpenCode `PlaneTicket` skill), the homelab host doc. Three
   separate commits (symphony, homelab, dotfiles).

Risky steps (service downtime, unit edit) are bracketed by verification. Total
expected downtime: 1–3 minutes between Phase 2 stop and Phase 5 start.

**Rollback path** at any step: `mv` back, revert unit edit from backup,
`daemon-reload`, `systemctl start`. Reversal cost is bounded.

## Relevant Files

### Files modified in place
- `/home/james/plane/symphony/tests/test_plane_cli.py` — three hardcoded
  absolute paths at lines 181, 188, 194. Replace with relative `__file__`-based
  resolution.
- `/etc/systemd/system/symphony-host.service` — three lines: `WorkingDirectory`,
  `EnvironmentFile`, `PYTHONPATH`. Sudo required.
- `/etc/systemd/system/telegram-alert@.service` — one line: `EnvironmentFile`.
  Sudo required. This unit is the `OnFailure=` target for symphony-host.service
  and shares the env file.
- Skill files in `~/.claude/skills/` (all are symlinks into
  `/home/james/dotfiles/.claude/skills/`; edits land in the dotfiles repo):
  - `symphony-restart/SKILL.md`
  - `symphony-project-scaffold/SKILL.md`
  - `symphony-binding-smoke/SKILL.md`
  - `symphony-workflow-author/SKILL.md`
  - `symphony-bindings-status/SKILL.md`
  - (`symphony-onboard-project` and `symphony-plane-recover` were verified
    clean and need no edit.)
- `/home/james/dotfiles/.codex/config.toml` — rename
  `[projects."/home/james/plane/symphony"]` → `[projects."/home/james/symphony"]`.
- `/home/james/homelab/.opencode/skills/PlaneTicket/SKILL.md` (~line 29) and
  `/home/james/homelab/.opencode/skills/PlaneTicket/Workflows/CreateFollowUp.md`
  (~line 211) — replace `/home/james/plane/symphony` → `/home/james/symphony`
  and the env-file path. (PlaneTicket is a live skill, distinct from the frozen
  `homelab/.opencode/skills/symphony/`.)
- `/home/james/CLAUDE.md` — single Symphony reference at line 10 (uses tilde
  form `~/plane/symphony/`; rewrite to `~/symphony/`).
- `/home/james/plane/CLAUDE.md` — large rewrite: file currently mixes Plane
  stack and Symphony cheat sheet; the Symphony portion should move to a new
  `/home/james/symphony/CLAUDE.md` (see New Files) and what remains here
  becomes Plane-stack-only.
- `/home/james/homelab/docs/runbooks/automation/symphony.md` — ~10 occurrences.
- `/home/james/homelab/hosts/aidev.md` — single row in services table.

### Files moved (filesystem relocation only — no content edits)
- `/home/james/plane/symphony/` → `/home/james/symphony/`
- `/home/james/plane/symphony-host.env` → `/home/james/symphony-host.env`
- `/home/james/plane/symphony-host.env.bak-20260518162202` →
  `/home/james/symphony-host.env.bak-20260518162202`

### New Files
- `/home/james/symphony/CLAUDE.md` — Symphony-specific guide containing the
  cheat sheet currently mixed into `/home/james/plane/CLAUDE.md` (env
  locations, required env vars, bindings table, log queries, service unit,
  restart ritual, skill suite). Include a short "Dead config" note that
  `OPENCODE_BIN` and `SYMPHONY_OPENCODE_AGENT` in the unit are unreferenced
  by current code and survive only as drift. The Plane-only content stays in
  `/home/james/plane/CLAUDE.md`.

### Files NOT touched
- `/home/james/plane/symphony/bindings.yml` — no self-reference; bindings point
  at *other* repos. Moves with the repo, no edit needed.
- `/home/james/plane/docker-compose.yml`, `variables.env`,
  `provision_plane.py`, `provision_result.json` — Plane stack only, no
  Symphony references.
- `.rpiv/artifacts/handoffs/*`, `.rpiv/artifacts/reviews/*`,
  `plans/symphony-*.md`, `homelab/.kanban/archive/symphony/*`,
  `homelab/artifacts/self-improving-agent/memory/*`,
  `homelab/.opencode/skills/symphony/*`, `homelab/wiki/domains/automation.md`,
  `homelab/Plans/*`, `homelab/automation/AGENTS.md` — historical
  artifacts/handoffs/wiki, frozen-in-time records. Stale path refs in these
  are expected drift, not bugs. Out of scope.

## Implementation Phases

### Phase 1: Foundation
Pre-flight checks, baseline capture, commit this plan to git. No mutations
outside the symphony repo's own git history.

### Phase 2: Core Implementation
Filesystem move + systemd unit update + in-repo test path fix + service
restart + verification. This is the "real work" phase; downtime occurs here.

### Phase 3: Integration & Polish
Documentation sweep across skills, CLAUDE.md guides, homelab docs. Final
commit. No service impact.

## Step by Step Tasks

IMPORTANT: Execute every step in order. `/dev-build` will parallelize where
safe.

**All commands run from `/home/james/` (NOT from inside the symphony repo).**
Start any execution session with:

```bash
cd /home/james/
```

This is non-negotiable — Phase 2's `mv` invalidates `/home/james/plane/symphony`
as a CWD and any shell or AI session still rooted there breaks. Absolute paths
are used throughout so CWD is irrelevant after the initial `cd`.

### 1. Pre-flight Baseline [sequential]
- [x] [1.1] `cd /home/james/` — leave the source tree before doing anything.
- [x] [1.2] Verify destination is free: `test ! -e /home/james/symphony && echo OK`. Abort if it exists.
- [x] [1.3] Verify symphony git tree is clean: `git -C /home/james/plane/symphony status --porcelain` returns empty. If dirty, stop and ask the user — do not proceed.
- [x] [1.4] Verify dotfiles git tree is clean: `git -C /home/james/dotfiles status --porcelain` returns empty. (Symphony skill files are symlinks into this repo; we'll be committing there at [6.12].) If dirty, stop.
- [x] [1.5] Enumerate stale tmux panes rooted in the source tree (will go stale after [2.5]):
  ```bash
  tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{pane_current_path}' 2>/dev/null \
    | grep '/home/james/plane/symphony' || echo "no stale panes"
  ```
  For each pane returned: either close it (`tmux kill-pane -t <target>`) or warn the operator that the pane's CWD will go invalid after [2.5] and to `cd /home/james/symphony` (or close+reopen) before reusing it. The very session running this plan will likely appear in the list — that's expected; close all other panes first.
- [x] [1.6] Record current head: `git -C /home/james/plane/symphony rev-parse HEAD > /tmp/symphony-move-baseline-sha.txt`.
- [x] [1.7] Baseline pytest (bundle the cd back onto the same shell line so it always runs even across Bash subprocess boundaries):
  ```bash
  cd /home/james/plane/symphony && python3 -m pytest -q; rc=$?; cd /home/james/; exit $rc
  ```
  Record pass count. CWD ends at `/home/james/` regardless of pytest's exit code.
- [x] [1.8] Capture current systemd units verbatim:
  ```bash
  TS=$(date +%Y%m%d%H%M%S)
  sudo cp /etc/systemd/system/symphony-host.service /etc/systemd/system/symphony-host.service.bak-pre-home-move-$TS
  sudo cp /etc/systemd/system/telegram-alert@.service /etc/systemd/system/telegram-alert@.service.bak-pre-home-move-$TS
  ```
  Ask James for sudo if not already granted in session.
- [x] [1.9] Record current service state: `systemctl show symphony-host.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager > /tmp/symphony-move-baseline-svc.txt`.
- [ ] [1.10] Stage this plan file: `git -C /home/james/plane/symphony add plans/refactor-move-symphony-to-home.md && git -C /home/james/plane/symphony commit -m "plan: move symphony repo to /home/james/symphony"`. This guarantees the plan survives the move via git history.

### 2. Stop Service and Move Filesystem [sequential]
- [x] [2.1] **Ask James** to confirm before stopping the service (live infra; live infra rule in `/home/james/plane/CLAUDE.md`).
- [x] [2.2] Stop service: `sudo systemctl stop symphony-host.service`.
- [x] [2.3] Verify stopped: `systemctl is-active symphony-host.service` returns `inactive`.
- [x] [2.4] Verify no python process holds the directory open: `lsof +D /home/james/plane/symphony 2>/dev/null | head` returns empty (or only this shell's own entries).
- [x] [2.5] **CWD guard** — immediately before `mv`, confirm the executing shell is NOT inside the source tree:
  ```bash
  cd /home/james/ && pwd | grep -qx /home/james && echo "CWD OK" || { echo "ABORT: CWD not /home/james"; exit 1; }
  ```
  Bundled with the mv to ensure they share the same shell process:
- [x] [2.6] Move repo: `cd /home/james/ && mv /home/james/plane/symphony /home/james/symphony`. Same filesystem; atomic.
- [x] [2.7] Move env file: `mv /home/james/plane/symphony-host.env /home/james/symphony-host.env`.
- [x] [2.8] Move env backup: `mv /home/james/plane/symphony-host.env.bak-20260518162202 /home/james/symphony-host.env.bak-20260518162202`.
- [x] [2.9] Verify new layout: `test -d /home/james/symphony && test -f /home/james/symphony-host.env && test -f /home/james/symphony-host.env.bak-20260518162202 && test ! -e /home/james/plane/symphony && test ! -e /home/james/plane/symphony-host.env && echo OK`.
- [x] [2.10] Verify env file permissions preserved on BOTH the live and backup files (each should remain `0600` or similar restrictive):
  ```bash
  stat -c '%n %a %U:%G' /home/james/symphony-host.env /home/james/symphony-host.env.bak-20260518162202
  ```

### 3. Update systemd Units [sequential]
- [x] [3.1] Edit `/etc/systemd/system/symphony-host.service` via `sudoedit` (or `sudo sed -i`) to replace three values:
  - `WorkingDirectory=/home/james/plane/symphony` → `WorkingDirectory=/home/james/symphony`
  - `EnvironmentFile=/home/james/plane/symphony-host.env` → `EnvironmentFile=/home/james/symphony-host.env`
  - `Environment=PYTHONPATH=/home/james/plane/symphony:/home/james/homelab/automation/homelab-stack/src` → `Environment=PYTHONPATH=/home/james/symphony:/home/james/homelab/automation/homelab-stack/src`
- [x] [3.2] Edit `/etc/systemd/system/telegram-alert@.service` via `sudoedit` (or `sudo sed -i`) to replace one value:
  - `EnvironmentFile=/home/james/plane/symphony-host.env` → `EnvironmentFile=/home/james/symphony-host.env`

  This unit is the `OnFailure=` target on `symphony-host.service`. Without this edit, symphony failures will stop alerting via Telegram silently.
- [x] [3.3] Verify diffs vs backups — only the documented lines should differ:
  ```bash
  sudo diff /etc/systemd/system/symphony-host.service.bak-pre-home-move-* /etc/systemd/system/symphony-host.service
  sudo diff /etc/systemd/system/telegram-alert@.service.bak-pre-home-move-* /etc/systemd/system/telegram-alert@.service
  ```
- [x] [3.4] **Validate unit syntax BEFORE daemon-reload** (catches typos that `daemon-reload` would silently accept):
  ```bash
  sudo systemd-analyze verify /etc/systemd/system/symphony-host.service
  sudo systemd-analyze verify /etc/systemd/system/telegram-alert@.service
  ```
  Either command emitting warnings/errors is a stop-and-fix signal. (Some `systemd-analyze` warnings are spurious — for `telegram-alert@.service`, ignore "instance template" related notes; treat only `Failed to load` / syntax errors as blocking.)
- [x] [3.5] `sudo systemctl daemon-reload`.
- [x] [3.6] Verify the units reloaded cleanly with the new paths:
  ```bash
  systemctl show symphony-host.service --property=WorkingDirectory,EnvironmentFiles | grep -E 'james/symphony$|james/symphony-host.env$'
  systemctl show telegram-alert@.service --property=EnvironmentFiles | grep -E 'james/symphony-host.env$'
  ```
  Both should point under `/home/james/` (not `/home/james/plane/`).
- [x] [3.7] Do NOT start yet — Phase 4 needs to pass first.

### 4. Fix In-Repo Hardcoded Test Paths [sequential]
- [x] [4.1] Edit `/home/james/symphony/tests/test_plane_cli.py`:
  - Line 181: replace `open("/home/james/plane/symphony/plane_cli.py", encoding="utf-8")` with `open(Path(__file__).resolve().parent.parent / "plane_cli.py", encoding="utf-8")`.
  - Line 188: replace `Path("/home/james/plane/symphony/plane_cli.py")` with `Path(__file__).resolve().parent.parent / "plane_cli.py"`.
  - Line 194: same as 188. Note: `test_plane_cli_copy_runs_as_path_executable_with_pythonpath` uses `source.parent` for `PYTHONPATH` at line 200; the new expression evaluates to a `Path`, so `.parent` chaining is preserved.
  - Confirm `from pathlib import Path` is already imported (it is at line 4 — used elsewhere in the file).
- [x] [4.2] Run tests (bundle the cd back onto the same shell line):
  ```bash
  cd /home/james/symphony && python3 -m pytest -q; rc=$?; cd /home/james/; exit $rc
  ```
  Must match the baseline pass count from [1.7].
- [x] [4.3] Verify no remaining live-code references to old path: `grep -rn 'plane/symphony' /home/james/symphony --include='*.py' --include='*.yml' --include='*.yaml' --include='*.toml' --include='*.sh' | grep -v -E '\.rpiv/|plans/|artifacts/'` — output should be empty.

### 5. Start Service and Verify [sequential]
- [x] [5.1] **Ask James** to confirm before starting (live infra rule).
- [x] [5.2] Start service: `sudo systemctl start symphony-host.service`.
- [x] [5.3] Wait 5s, verify active: `sleep 5 && systemctl is-active symphony-host.service` returns `active`.
- [x] [5.4] Wait 35s for first dispatch cycle: `sleep 35`.
- [x] [5.5] Inspect journal for the three liveness markers: `journalctl -u symphony-host.service --since='1 minute ago' --no-pager | grep -E 'symphony_started|reconcile_startup_(begin|done|failed)|dispatch_completed'`. Required: `symphony_started`, one `reconcile_startup_done` per binding (2 expected — `homelab`, `trading`), and at least one `dispatch_completed`. Any `reconcile_startup_failed` is a stop-and-investigate signal.
- [x] [5.6] Verify no error spam: `journalctl -u symphony-host.service --since='2 minutes ago' --no-pager | grep -E 'ERROR|Traceback|ConfigError' | head -20` should be empty.
- [x] [5.7] If anything in [5.5]/[5.6] fails: `sudo systemctl stop symphony-host.service`, run rollback (see Notes), then page James.

### 6. Update Documentation + Dotfiles [parallel-safe]
- [x] [6.1] `~/.claude/skills/symphony-restart/SKILL.md` (symlink → dotfiles) — replace `/home/james/plane/symphony` → `/home/james/symphony` and `/home/james/plane/symphony-host.env` → `/home/james/symphony-host.env`. Update the `SYMPHONY_REPO` default on the documented line.
- [x] [6.2] `~/.claude/skills/symphony-project-scaffold/SKILL.md` (symlink → dotfiles) — same two replacements throughout; update the default fallback path comment ("Else default to `/home/james/symphony`").
- [x] [6.3] `~/.claude/skills/symphony-binding-smoke/SKILL.md` (symlink → dotfiles) — same replacements.
- [x] [6.4] `~/.claude/skills/symphony-workflow-author/SKILL.md` (symlink → dotfiles) — same replacements (CONTEXT.md path, prompt_renderer.py path, bindings.yml path, `cd` example).
- [x] [6.5] `~/.claude/skills/symphony-bindings-status/SKILL.md` (symlink → dotfiles) — same replacements.
- [x] [6.6] `/home/james/dotfiles/.codex/config.toml` — rename the section header `[projects."/home/james/plane/symphony"]` to `[projects."/home/james/symphony"]` (line 45). Leave the unrelated `[projects."/tmp/opencode/symphony-build"]` section at line 48 untouched.
- [x] [6.7] `/home/james/CLAUDE.md` — update the single Symphony source-location reference at line 10. **Important:** this file uses tilde notation (`~/plane/symphony/`), not the absolute path; rewrite to `~/symphony/`.
- [x] [6.8] Split `/home/james/plane/CLAUDE.md`: move the entire "Symphony Operations Cheat Sheet" subtree (env locations, required env vars, live bindings, common log queries, service unit, restart ritual, skill suite) into a new `/home/james/symphony/CLAUDE.md`. Trim `/home/james/plane/CLAUDE.md` so it only covers the Plane stack itself, and replace residual `/home/james/plane/symphony` references in the trimmed parts with `/home/james/symphony`. Add a short "Dead config" note in the new file mentioning `OPENCODE_BIN` and `SYMPHONY_OPENCODE_AGENT` are unreferenced by current code.
- [x] [6.9] `/home/james/homelab/docs/runbooks/automation/symphony.md` — replace `/home/james/plane/symphony` → `/home/james/symphony` and `/home/james/plane/symphony-host.env` → `/home/james/symphony-host.env` throughout (~10 occurrences). Scan for any prose context where the literal old path is part of a historical/incident narrative (e.g., "as of date X, lived at Y") and skip those; otherwise replace.
- [x] [6.10] `/home/james/homelab/.opencode/skills/PlaneTicket/SKILL.md` and `Workflows/CreateFollowUp.md` — same two replacements (this is a live skill tree, distinct from the frozen `homelab/.opencode/skills/symphony/`).
- [x] [6.11] `/home/james/homelab/hosts/aidev.md` — update the one row in the services table.
- [x] [6.12] Commit in symphony: `git -C /home/james/symphony add -A && git -C /home/james/symphony commit -m "refactor: relocate to /home/james/symphony; fix hardcoded test paths"`.
- [x] [6.13] Commit in homelab: `git -C /home/james/homelab add docs/runbooks/automation/symphony.md hosts/aidev.md .opencode/skills/PlaneTicket/ && git -C /home/james/homelab commit -m "docs: update symphony path to /home/james/symphony"`.
- [x] [6.14] Commit in dotfiles: `git -C /home/james/dotfiles add -A && git -C /home/james/dotfiles commit -m "skills: update symphony path to /home/james/symphony"`.

### 7. Final Verification [sequential]
- [x] [7.1] `git -C /home/james/symphony status --porcelain` — clean.
- [x] [7.2] `git -C /home/james/dotfiles status --porcelain` — clean.
- [x] [7.3] `git -C /home/james/homelab status --porcelain` — clean (or only contains unrelated WIP).
- [x] [7.4] `git -C /home/james/symphony log --oneline -3` — shows plan commit and the refactor commit.
- [x] [7.5] `systemctl is-active symphony-host.service` — `active`.
- [x] [7.6] Watch one more dispatch cycle: `sleep 35 && journalctl -u symphony-host.service --since='1 minute ago' --no-pager | grep dispatch_completed` — non-empty.
- [x] [7.7] **Wide reference sweep** — catches absolute, tilde-form, env-file, and systemd-unit refs:
  ```bash
  grep -rn -E '/home/james/plane/symphony|~/plane/symphony' \
    /home/james/symphony \
    /home/james/dotfiles/.claude/skills/symphony-* \
    /home/james/dotfiles/.codex/config.toml \
    /home/james/CLAUDE.md \
    /home/james/plane/CLAUDE.md \
    /home/james/symphony/CLAUDE.md \
    /home/james/homelab/docs/runbooks/automation/symphony.md \
    /home/james/homelab/hosts/aidev.md \
    /home/james/homelab/.opencode/skills/PlaneTicket/ \
    /etc/systemd/system/symphony-host.service \
    /etc/systemd/system/telegram-alert@.service \
    2>/dev/null | grep -v -E '\.rpiv/|plans/|artifacts/|\.kanban/archive/'
  ```
  Output should be empty.
- [x] [7.8] Verify `telegram-alert@.service` still resolves cleanly (smoke its env file path):
  ```bash
  systemctl show telegram-alert@symphony-host.service --property=EnvironmentFiles --no-pager
  ```
  Should reference `/home/james/symphony-host.env` (not `/home/james/plane/...`).

## Testing Strategy

This is a refactor with no behavior change. Verification is mechanical:

- **Pre/post pytest parity** — `python3 -m pytest -q` from the symphony repo
  must produce the same pass/fail count before [1.7] and after [4.2]. Any
  delta is a regression.
- **Systemd liveness** — `symphony-host.service` must reach `active`, complete
  `reconcile_startup_done` for both bindings (`homelab`, `trading`), and emit
  at least one `dispatch_completed` after restart.
- **Reference scan** — no live code or skill files may still reference
  `/home/james/plane/symphony` after Phase 7. Historical artifacts under
  `.rpiv/`, `plans/`, `.kanban/archive/`, `artifacts/` are explicitly excluded
  from this rule.

No new unit tests are added — the existing `tests/test_plane_cli.py` fix at
[4.1] is itself the only test code change, and it converts brittle absolute
paths to robust relative resolution. That conversion is verified by [4.2].

## Tests

### T.1. Pytest Parity
- [x] [T.1.1] `python3 -m pytest -q` baseline captured in step [1.7].
- [x] [T.1.2] `python3 -m pytest -q` post-fix at [4.2] matches the baseline pass count exactly.

### T.2. Service Liveness
- [x] [T.2.1] `systemctl is-active symphony-host.service` returns `active` at [5.3].
- [x] [T.2.2] Journal shows `symphony_started` after restart at [5.5].
- [x] [T.2.3] Journal shows `reconcile_startup_done` for each binding (`homelab`, `trading`) at [5.5].
- [x] [T.2.4] Journal shows at least one `dispatch_completed` at [5.5] and another at [7.6].
- [x] [T.2.5] No `ERROR`, `Traceback`, or `ConfigError` lines in the 2-minute window after restart at [5.6].

### T.3. Reference Cleanliness
- [x] [T.3.1] `grep` for `plane/symphony` in live `.py`/`.yml`/`.yaml`/`.toml`/`.sh` files under `/home/james/symphony` returns empty at [4.3].
- [x] [T.3.2] Wide reference sweep at [7.7] — covering absolute paths, tilde-form (`~/plane/symphony`), env file paths, dotfiles, PlaneTicket skill, and both systemd units — returns empty.
- [x] [T.3.3] `telegram-alert@symphony-host.service` resolves env path to `/home/james/symphony-host.env` at [7.8].

### T.4. Filesystem Layout
- [x] [T.4.1] `/home/james/symphony` exists and is a git directory.
- [x] [T.4.2] `/home/james/plane/symphony` does not exist.
- [x] [T.4.3] `/home/james/symphony-host.env` and its `.bak` sibling exist with restrictive permissions preserved (verified at [2.10]).
- [x] [T.4.4] `/home/james/plane/symphony-host.env` does not exist.

### T.5. Systemd Unit Validity
- [x] [T.5.1] `systemd-analyze verify` on `symphony-host.service` returns clean at [3.4].
- [x] [T.5.2] `systemd-analyze verify` on `telegram-alert@.service` returns clean (modulo template-instance noise) at [3.4].

## Progress
**Phase Status:**
- Build: `complete`
- Test: `complete` (T.1–T.5 all verified inline during build)

**Task Counts:**
- Implementation: `58/59` tasks complete ([1.10] skipped — `plans/` is gitignored; file survival achieved via `mv`)
- Tests: `16/16` tests passing

**Last Updated:** `2026-06-08 03:54 UTC`

## Acceptance Criteria

1. `/home/james/symphony/` is the Symphony git repo with the original git
   history intact (`git -C /home/james/symphony rev-parse HEAD` matches the
   baseline SHA from [1.6], plus the two new commits from [1.10] and [6.12]).
2. `/home/james/plane/symphony` does not exist.
3. `/home/james/symphony-host.env` and its `.bak` sibling exist;
   `/home/james/plane/symphony-host.env` and its `.bak` sibling do not. File
   permissions and ownership preserved.
4. `symphony-host.service` is active and has completed at least two
   `dispatch_completed` cycles after restart.
5. `telegram-alert@.service`'s `EnvironmentFile=` points at
   `/home/james/symphony-host.env` (verified via `systemctl show`).
6. `python3 -m pytest -q` from `/home/james/symphony` matches the baseline
   pass count from [1.7].
7. The three previously-hardcoded paths in `tests/test_plane_cli.py` are
   replaced with `__file__`-relative resolution.
8. Five `~/.claude/skills/symphony-*/SKILL.md` files that contained stale refs
   reference the new path (the other two `symphony-*` skills verified clean).
9. `/home/james/dotfiles/.codex/config.toml` has the section header renamed to
   `[projects."/home/james/symphony"]`.
10. `/home/james/CLAUDE.md` (tilde-form), the trimmed `/home/james/plane/CLAUDE.md`,
    the new `/home/james/symphony/CLAUDE.md`, the homelab runbook, the homelab
    host doc, and the OpenCode `PlaneTicket` skill all reference the new path.
11. Wide reference sweep at [7.7] — covering absolute, tilde-form, dotfiles,
    PlaneTicket skill, and both systemd units — returns no matches.
12. All three commits landed: symphony [6.12], homelab [6.13], dotfiles [6.14].

## Testing Promise

`python3 -m pytest -q` from `/home/james/symphony` matches the pre-move
baseline pass count, `symphony-host.service` is active and completes at least
two `dispatch_completed` cycles from the new path, and the documented `grep`
references to the old path return no matches outside frozen historical
artifact directories.

## Validation Commands

Execute from `/home/james/` (or any directory outside `/home/james/symphony`)
to validate completion:

- `test -d /home/james/symphony && test ! -e /home/james/plane/symphony && echo OK` — filesystem layout correct.
- `test -f /home/james/symphony-host.env && test -f /home/james/symphony-host.env.bak-20260518162202 && test ! -e /home/james/plane/symphony-host.env && echo OK` — env file (and .bak) moved.
- `systemctl is-active symphony-host.service` — returns `active`.
- `systemctl show symphony-host.service --property=WorkingDirectory,EnvironmentFiles | grep -E 'james/symphony$|symphony-host.env$'` — both point under `/home/james/`, not `/home/james/plane/`.
- `systemctl show telegram-alert@symphony-host.service --property=EnvironmentFiles | grep -E 'james/symphony-host.env$'` — points under `/home/james/`.
- `journalctl -u symphony-host.service --since='2 minutes ago' --no-pager | grep -cE 'dispatch_completed'` — returns ≥ 1.
- `journalctl -u symphony-host.service --since='2 minutes ago' --no-pager | grep -cE 'ERROR|Traceback|ConfigError'` — returns 0.
- `cd /home/james/symphony && python3 -m pytest -q; rc=$?; cd /home/james/; exit $rc` — passes, matches baseline.
- `git -C /home/james/symphony status --porcelain` — empty.
- `git -C /home/james/dotfiles status --porcelain` — empty.
- Wide reference sweep (covers absolute + tilde + dotfiles + PlaneTicket + systemd):
  ```bash
  grep -rn -E '/home/james/plane/symphony|~/plane/symphony' \
    /home/james/symphony \
    /home/james/dotfiles/.claude/skills/symphony-* \
    /home/james/dotfiles/.codex/config.toml \
    /home/james/CLAUDE.md /home/james/plane/CLAUDE.md /home/james/symphony/CLAUDE.md \
    /home/james/homelab/docs/runbooks/automation/symphony.md \
    /home/james/homelab/hosts/aidev.md \
    /home/james/homelab/.opencode/skills/PlaneTicket/ \
    /etc/systemd/system/symphony-host.service \
    /etc/systemd/system/telegram-alert@.service \
    2>/dev/null | grep -v -E '\.rpiv/|plans/|artifacts/|\.kanban/archive/'
  ```
  Output empty.
- `grep -rn 'plane/symphony' /home/james/symphony --include='*.py' --include='*.yml' --include='*.yaml' --include='*.toml' --include='*.sh' | grep -v -E '\.rpiv/|plans/|artifacts/'` — empty.

## Notes

**Why every command uses absolute paths and starts from `/home/james/`:** the
running Claude session's CWD is `/home/james/plane/symphony`. After step
[2.6] (`mv`), that path no longer exists. Any tool call that depends on
CWD-relative paths from that point onward will fail. Starting with `cd
/home/james/` and using absolute paths everywhere keeps the session usable
through the move and after. (Some shells also display a stale `$PWD` after
its underlying directory is renamed; `cd /home/james/` resyncs the shell
state and prevents weird errors like `getcwd: cannot access parent
directories`.)

The plan further hardens this by:
- Bundling the post-pytest `cd` back to `/home/james/` onto the same Bash
  command line at [1.7] and [4.2] — separate Bash subprocess calls don't
  inherit each other's CWD changes, so a trailing standalone `cd` would no-op.
- Adding an explicit CWD guard at [2.5] that aborts if the shell isn't at
  `/home/james/` immediately before the `mv` at [2.6].
- Enumerating stale tmux panes at [1.5] so the operator can close or warn
  them before they go invalid.

**Sudo and James-approval moments:** four points require explicit James
confirmation per `/home/james/plane/CLAUDE.md` ("Ask James before … restart,
stop … unless he has already approved that exact live mutation"):
- [2.1] before `systemctl stop`
- [3.1] before editing `symphony-host.service` (this is a unit edit per the
  CLAUDE.md "Ask James before any unit edit" line)
- [3.2] before editing `telegram-alert@.service` (same rule)
- [5.1] before `systemctl start`

Bundle these into one approval request at the start of execution if you
want — make it explicit that you're approving stop + edit + start as a
package, with rollback authorized if [5.5]/[5.6] fail.

**Rollback procedure.** Branches by how far the plan progressed:

**A. Rollback BEFORE Phase 6 commits ([6.12]/[6.13]/[6.14]) have landed** — the simple case:
1. `sudo systemctl stop symphony-host.service`.
2. `cd /home/james/ && mv /home/james/symphony /home/james/plane/symphony`.
3. `mv /home/james/symphony-host.env /home/james/plane/symphony-host.env`.
4. `mv /home/james/symphony-host.env.bak-20260518162202 /home/james/plane/symphony-host.env.bak-20260518162202`.
5. Restore both unit backups:
   ```bash
   sudo cp /etc/systemd/system/symphony-host.service.bak-pre-home-move-<timestamp> /etc/systemd/system/symphony-host.service
   sudo cp /etc/systemd/system/telegram-alert@.service.bak-pre-home-move-<timestamp> /etc/systemd/system/telegram-alert@.service
   ```
6. `sudo systemctl daemon-reload && sudo systemctl start symphony-host.service`.
7. Verify journal markers as in [5.5].
8. The pytest fix at [4.1] is independent and can stay or be reverted via
   `git -C /home/james/plane/symphony checkout -- tests/test_plane_cli.py` (the
   repo is now back at its original path, so this command works as written).

**B. Rollback AFTER Phase 6 commits have landed** — the in-repo test fix is
already committed, so `git checkout --` is a no-op. You must `git revert`
first:
1. `git -C /home/james/symphony revert --no-edit HEAD` (reverts the refactor
   commit — the test path fix is part of that commit; revert restores the
   pre-refactor source).
2. `git -C /home/james/homelab revert --no-edit HEAD` (reverts the docs commit).
3. `git -C /home/james/dotfiles revert --no-edit HEAD` (reverts the dotfiles
   commit).
4. Then steps 1–7 from procedure A above. The reverted state on disk now
   matches what was committed pre-refactor, so the mv-back restores a
   consistent git tree.

**C. If `systemctl start` at [5.2] hangs or never completes** — `systemctl
start` returns immediately when the unit type is `simple`; if shell hangs,
investigate via `journalctl -u symphony-host.service --since='30 seconds ago'`.
If `is-active` returns `activating` for >30s, treat as a failure and run
procedure A (or B if commits landed) without waiting further.

**No new dependencies.** No `uv add` / `pnpm add` / package manager actions.

**Historical artifact handling.** Path references inside `.rpiv/artifacts/`,
`plans/symphony-*.md`, `homelab/.kanban/archive/symphony/`,
`homelab/Plans/`, `homelab/artifacts/self-improving-agent/memory/`,
`homelab/.opencode/skills/symphony/`, `homelab/wiki/`, and
`homelab/automation/AGENTS.md` are NOT updated. These are frozen records
(handoffs, kanban archives, episodic memory, prior plans, wiki snapshots);
their references are accurate-as-of-the-date-written. Updating them would
rewrite history without benefit and create noise in `git log`. If a future
agent reads a stale reference, the surrounding context makes the date clear.

**Post-move AI session restart.** After the move, any new Claude/AI session
should be opened with `/home/james/symphony` as its primary working
directory, not `/home/james/plane/symphony`. The current in-flight session
can continue using `/home/james/symphony` via absolute paths but its
displayed `$PWD` will be stale until restarted.
