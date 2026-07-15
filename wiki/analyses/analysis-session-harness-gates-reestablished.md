---
title: Harness gates re-established (advisory posture + global safety gates + Pi precedence)
type: analysis
status: promoted
created: 2026-07-15
updated: 2026-07-15
sources:
  - wiki/raw/sessions/2026-07-15-harness-gates-reestablished.md
  - artifacts/specs/ai-readiness-symphony-2026-07-15-143322.md
  - .claude/hooks/staged-static-check.sh
  - .claude/hooks/format-on-edit.sh
  - .claude/settings.json
confidence: high
tags: [harness, hooks, claude-code, pi, harness-gates, advisory, bypassPermissions, safety, secrets, self-disarm, rm-rf, ruff]
---

# Harness gates re-established (advisory posture + global safety gates + Pi precedence)

Supersedes the posture in [claude-code-harness-profile.md](../analyses/claude-code-harness-profile.md): the **blocking** project harness it documents (four `.claude/hooks/` scripts incl. `pre-git-checks.sh` running `uv run pytest`) was removed in `20fc650` (2026-06-17) and `704b4b4` (2026-06-20) because blocking pre-git hooks break unattended `bypassPermissions` runs — the same failure class as [pre-git-pytest-gate-agent-oom.md](../analyses/pre-git-pytest-gate-agent-oom.md). This session (2026-07-15) re-established gates in an autonomy-safe form driven by the AI-readiness audit [source: artifacts/specs/ai-readiness-symphony-2026-07-15-143322.md].

## Posture split: advisory vs blocking

The governing rule: **pre-git lint/format/test gates are advisory (exit 0); blocking is reserved for ops never part of legitimate autonomous coding.**

- **Project, advisory** — `staged-static-check.sh` (`PreToolUse` Bash, gated to `git commit`/`git push`) runs `ruff check` + `ruff format --check` on staged `.py` and always **exits 0**, warning on stderr only. mypy/pyright omitted (no project config → per-file import noise); whole-project pytest left to CI/`dev-test` (flaky concurrent test + ADR-0028 slice latency) [source: .claude/hooks/staged-static-check.sh]. Demoted to advisory in `93630ba`.
- **Project, fail-open** — `format-on-edit.sh` runs `ruff format` on every `.py` Edit/Write/MultiEdit [source: .claude/hooks/format-on-edit.sh].
- **Global, blocking** (dotfiles `~/.claude/hooks/`, commit `b1ff50e`) — `block-bash-pattern.sh` hard-blocks (exit 2) catastrophic `rm -rf` of `/`, `~`, `$HOME`, whole system dirs (`/etc`,`/usr`,`/home`,…), split-flag `rm -r -f /`, and device destroyers (`dd of=/dev/*`, `mkfs`, `wipefs`, `>/dev/sd*`). `block-path-access.sh` blocks secret writes by basename (`.env`, `*.env` incl `symphony-host.env`, `*.key`, `*.pem`, `id_rsa`, `*.keystore`). This restores the destructive-command carve-out the unattended blanket modal auto-approve removed (CLAUDE.md), without touching modal handling.

## Self-disarm protection + escape hatch

Both global gates block tampering with their own machinery — `.claude/hooks/*.sh` and `.claude/settings*.json` — via the Edit/Write tool AND Bash (`sed -i`, redirect, `rm`, `mv`). Reads pass. Operator maintenance: create `~/.claude/.harness-unlock` (or `<project>/.claude/.harness-unlock`); unlock lifts self-disarm but **never** secret protection. The earlier outside-project-root write block was removed (operator choice): `/tmp` and out-of-tree tool writes are allowed.

## Dual-runtime: Pi enforcement verified + precedence fixed

The gate scripts fire in both Claude Code (via `settings.json`) and Pi (via the global `harness-gates` adapter). Delegation verified directly: through the adapter, `rm -rf ~` → `{block:true}` and a `.env` write → `{block:true}`; `tests/harness-gates-smoke.sh` passes 8/8. The adapter's script discovery was fixed from **global-wins** to **project-over-global** (`index.js` `scriptDirs`/`discoverScripts`) so a same-named project script overrides the global one, matching Claude Code and the adapter's own docstring [source: wiki/raw/sessions/2026-07-15-harness-gates-reestablished.md].

## Residual ceilings (unfixed)

Literal `/home/<user>` depth≥2 wipes pass (agents use `~`/`$HOME`, which are caught); `git commit --no-verify` bypasses gates; secrets remain readable via Bash `cat`; commits made outside the Bash tool (MCP/IDE) aren't seen — CI is the backstop.

## Claims

See CLAIMS.md entries tagged this session in [../CLAIMS.md](../CLAIMS.md).
