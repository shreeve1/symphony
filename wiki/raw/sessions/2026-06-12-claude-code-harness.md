---
title: Claude Code hook harness personalization session
date: 2026-06-12
type: raw-session
tags: [claude-code, harness, hooks, validation, safety, uv, ruff, pytest, alembic]
---

# Claude Code hook harness personalization (2026-06-12)

Session ran the `personalize-harness` skill (Claude Code variant, distinct from the
earlier `personalize-harness-pi` run) against `/home/james/symphony` in **team** layer.

## Durable facts

- Generated a team-committed Claude Code hook harness: `.claude/settings.json` plus
  four scripts under `.claude/hooks/`. No prior `.claude/settings*.json` existed.
- The four hooks and their event/posture:
  - `validate-syntax.sh` — `PostToolUse` `Edit|Write|MultiEdit`, **blocking** (exit 2).
    Parse-checks the edited file: Python (`python3 -m py_compile`), JSON (`jq .`),
    shell (`bash -n`). JS arm dropped (no JS in repo).
  - `block-bash-pattern.sh` — `PreToolUse` `Bash`, **blocking**. Blocks catastrophic
    recursive deletes of `/`, `~`, `$HOME` (boundary-anchored — does NOT match safe
    absolute deletes like `rm -f /tmp/x`) and the wrong package managers
    `pip/pipenv/poetry install|add`. Explicitly **allows** `uv pip install` and
    `uv add` (pip pattern only matches pip at a command boundary, not inside `uv pip`).
  - `pre-git-checks.sh` — `PreToolUse` `Bash`, gated to `git commit`/`git push`,
    **blocking**. Runs `ruff format --check` + `ruff check` on **staged `*.py` only**
    (via `git diff --cached --name-only --diff-filter=ACM | grep '\.py$'`), then
    `uv run pytest -q` over the full suite. Each check time-boxed (`TIMEOUT_S=180`).
  - `reinject-rules.sh` — `SessionStart` `compact`, **advisory**. Re-injects Symphony
    live-infra invariants (live infra, never print `symphony-host.env`, ask James
    before systemctl/Plane/Podium mutations, github-personal SSH alias, bindings.yml
    is source of truth, tests run under `uv run`).

## Decisions

- **Ruff at commit-time, changed-files-only, not per-edit.** The repo has no
  `[tool.ruff]` config, so a repo-wide `ruff format --check .` is red: 38 of 82 files
  would reformat and `ruff check .` reports 5 errors. Gating repo-wide would block
  every commit. Decision: gate only the staged `*.py` in each commit — the legacy
  backlog never blocks, and no `[tool.ruff]` config is required to start. Adding a
  config + one-time reformat is a separate optional cleanup.
- **Test gate command is `uv run pytest`, not `python3 -m pytest`.** `python3 -m pytest`
  fails at collection — system `/usr/bin/python3` lacks `alembic` (and other deps).
  The uv-managed project venv `/home/james/symphony/.venv` has them; `uv run pytest`
  → 615 passed, 1 skipped in 53s (exit 0). This contradicts the `CLAUDE.md` quick-check
  line that documented `python3 -m pytest` — corrected to `uv run pytest` this session.
  (A `PATH="$PWD/.venv/bin:..." python3 -m pytest` form also works, as used by Ralph
  verification runs, but `uv run pytest` needs no activation.)
- **alembic stays project-only; do NOT install it into the system interpreter.**
  alembic is already a declared dep (`pyproject.toml:7` `alembic>=1.17`), locked in
  `uv.lock`, installed in `.venv` at 1.18.4. `.venv` lives inside the repo — it is
  project-scoped already. A system-wide install would create an unpinned second copy
  that drifts from the lockfile.
- **Path guard (cat 8) skipped.** Secrets live outside the repo at
  `/home/james/symphony-host.env`; in-repo `.env` is gitignored. User opted out.
- **Stop self-review checkpoint skipped** (per-turn token cost). systemctl and
  `git push --force` bash guards offered but not selected — user chose only the
  recursive-delete + wrong-package-manager patterns.

## Live bug caught

The first `rm` guard pattern (`rm -[rf]+ /`) matched safe `rm -f /tmp/...` because the
target merely started with `/`. The live hook blocked the verification command itself.
Fixed to boundary-anchored targets so only `/`, `~`, `$HOME` (at a token boundary or
with a trailing `*`) match.

## Skill improvement (global, outside this repo)

Edited `~/.claude/skills/personalize-harness/SKILL.md` to add a mandatory **Baseline
verification + runner resolution** step in Step 2.5: dry-run each candidate project
check, and on a missing-dependency/interpreter error (`ModuleNotFoundError`,
`command not found`, …) retry with the build-tool runner prefix (`uv run`,
`poetry run`, `pipenv run`, `node_modules`, …) before offering a build-tool install
(never the system interpreter). Records the `VERIFIED_CMD` the gate actually uses.
This is what was done by hand this session (`python3 -m pytest` → `uv run pytest`).
The edit is in global dotfiles, not the Symphony repo.

## Verification

- `bash -n` clean on all four scripts; `.claude/settings.json` valid JSON, 3 event keys.
- Bash-guard dry checks: `rm -rf /` blocked, `rm -fr ~` blocked, `rm -f /tmp/x` allowed,
  `pip install` blocked, `poetry add` blocked, `uv pip install` allowed, `uv add`
  allowed, `ls -la` allowed.
- pre-git detector: non-git command passes through (exit 0).
- Baseline: `uv run pytest` green (615 passed/1 skip/53s).

## Note on wiki re-apply

This page and its claims were first written 2026-06-12, then wiped when concurrent
Ralph work (#033–#036, archive feature) reverted the wiki and reclaimed the claim IDs
C-0126/C-0127. Re-applied with claims renumbered to C-0130/C-0131.

## Follow-ups

- Config uncommitted at capture (`?? .claude/hooks/`, `?? .claude/settings.json`).
- `CLAUDE.md` quick-check corrected to `uv run pytest` this session.
- Every `git commit`/`git push` through the Bash tool now pays ~53s for `uv run pytest`.
