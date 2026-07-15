# Session Capture: Harness gates re-established (advisory posture, global safety gates, Pi precedence)

- Date: 2026-07-15
- Purpose: Apply the AI-readiness audit's harness fixes; re-establish deterministic edit/commit gates after the 2026-06 harness removal, in an autonomy-safe (advisory) form; verify Claude + Pi both enforce them.
- Scope: harness gate scripts (global dotfiles + symphony project), Pi adapter precedence fix, posture decisions. Excludes eval work (#req-AR3, deferred to /dev-plan).

## Durable Facts

- The prior blocking Claude harness (`.claude/settings.json` + `.claude/hooks/{validate-syntax,block-bash-pattern,pre-git-checks,reinject-rules}.sh`) was **removed** in two commits — `20fc650` (2026-06-17, "Remove 3 Claude Code hooks; document agent pre-commit test obligation") and `704b4b4` (2026-06-20, "Remove .claude harness + trim CLAUDE.md to Podium-era context") — because blocking pre-git hooks break unattended `bypassPermissions` runs. Evidence: `git log 20fc650 704b4b4`; audit spec `artifacts/specs/ai-readiness-symphony-2026-07-15-143322.md` ("no `.claude/hooks/` in repo").
- Re-established 2026-07-15 with an **advisory-first posture**: project `staged-static-check.sh` runs `ruff check` + `ruff format --check` on staged `.py` but always **exits 0** (warn-only). Commits `dfde739`, `93630ba` (demote to advisory), `66a31bb`. Evidence: `.claude/hooks/staged-static-check.sh`.
- Project `format-on-edit.sh` runs `ruff format` on every `.py` Edit/Write/MultiEdit (fail-open). Repo was ~89% ruff-formatted (147/165 clean) so churn is incremental. Evidence: `.claude/hooks/format-on-edit.sh`; `ruff format --check` count.
- **Blocking is reserved for never-legit ops only**, at GLOBAL scope (dotfiles, commit `b1ff50e`): `block-bash-pattern.sh` blocks catastrophic `rm -rf` of `/`, `~`, `$HOME`, whole system dirs (`/etc`,`/usr`,`/home`,…), split flags (`rm -r -f /`), and device destroyers (`dd of=/dev/*`, `mkfs`, `wipefs`, `>/dev/sd*`). `block-path-access.sh` blocks secret writes (`.env`,`*.env` incl `symphony-host.env`,`*.key`,`*.pem`,`id_rsa`,`*.keystore`) by basename. Evidence: `~/dotfiles/.claude/hooks/`.
- **Self-disarm protection:** both global gates block tampering with `.claude/hooks/*.sh` and `.claude/settings*.json` via the Edit/Write tool AND Bash (`sed -i`/redirect/`rm`/`mv`). Escape hatch: create `~/.claude/.harness-unlock` (or `<project>/.claude/.harness-unlock`) to maintain; unlock lifts self-disarm but never secret protection. Evidence: gate scripts; dry-test in session.
- The global path gate's earlier **outside-project-root write block was removed** (operator choice) — `/tmp`, other-repo, and out-of-tree tool writes are allowed; only secret globs + self-disarm remain. Evidence: `block-path-access.sh` header.
- **Pi `harness-gates` adapter delegation verified working** for these scripts: through the adapter, `rm -rf ~` → `{block:true}` and a `.env` write → `{block:true}`. The adapter is installed + registered (`~/.pi/agent/settings.json`) with zero deps (missing `node_modules` irrelevant). Evidence: direct `runBashGates`/`runPathGate` probe; `tests/harness-gates-smoke.sh` (8/8 pass).
- **Pi adapter discovery precedence fixed to project-over-global** (`index.js` `scriptDirs`/`discoverScripts`): a same-named project `.claude/hooks/` script now overrides the global one (was global-wins, contradicting the docstring). This matches Claude Code's precedence. Evidence: `~/dotfiles/.pi/agent/extensions/harness-gates/index.js`; smoke case 1 now passes.

## Decisions

- Keep symphony pre-git lint/format gates advisory (exit 0); never re-introduce a blocking pytest/lint pre-git gate — it breaks unattended runs. — Evidence: commits `20fc650`/`704b4b4`; session edit to `staged-static-check.sh`.
- Global bash gate scoped to destructive `rm -rf /|~|$HOME` first, then broadened (operator: "update all") to system dirs, split flags, device destroyers. `git push --force`/`--no-verify` deliberately NOT blocked. — Evidence: session dialogue; `block-bash-pattern.sh`.
- Path gate writes-only (secrets), reads not blocked; `.claude/` general dir not blocked, only the gate machinery. — Evidence: session dialogue; `block-path-access.sh`.

## Evidence

- `~/dotfiles/.claude/hooks/block-bash-pattern.sh`, `block-path-access.sh` — global blocking gates (commit `b1ff50e`).
- `~/dotfiles/.pi/agent/extensions/harness-gates/index.js` — adapter precedence fix.
- `.claude/hooks/format-on-edit.sh`, `staged-static-check.sh`, `.claude/settings.json` — project gates (commits `dfde739`,`93630ba`,`66a31bb`).
- `artifacts/specs/ai-readiness-symphony-2026-07-15-143322.md` — audit driving the work.

## Exclusions

- No secrets captured. `symphony-host.env` referenced by path only (contents not read/stored).
- Eval harness (#req-AR3) not built this session.
- Residual ceilings not fixed: literal `/home/<user>` depth≥2 wipes, `--no-verify` bypass, Bash `cat` secret reads, non-Bash-tool commits.

## Open Questions And Follow-Ups

- `claude-code-harness-profile.md` (updated 2026-06-14) is now stale — describes the removed blocking harness; needs supersession pointer to this session's advisory re-establishment.
- Phase 3 golden-case eval (#req-AR3) still open via /dev-plan.
- Project harness goes live in a Claude session only after restart + /hooks; Pi enforces immediately.
