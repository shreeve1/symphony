---
date: 2026-06-12T13:25:38+0000
author: James Schriever
repository: symphony
topic: "personalize-harness-pi"
tags: [research, codebase, pi, harness]
status: complete
target_repo: /home/james/symphony
runtime_output: .pi/extensions/personal-harness.ts
---

# Research: personalize-harness-pi

## Summary

Symphony is live infrastructure with Python scheduler/API code, a Next.js/TypeScript Podium frontend, Playwright e2e tests, shell operational scripts, JSON configs, and a large LLM wiki. There is no CI or pre-commit gate, so the harness should provide fast blocking per-file syntax checks, advisory lint, deferred project checks, manual scenario reminders, and strict safety blockers for live service, secret, database, and generated-directory hazards.

Selected posture:

- `selected` afterWrite blocking syntax checks for Python, JSON, JavaScript/MJS/CJS, and shell.
- `skipped` automatic formatters because the repo has no declared formatter contract and autoformatting live infra code would be too surprising.
- `selected` advisory Python lint via installed `ruff` for `.py` files.
- `selected` deferred project checks: `git diff --check` before git and TypeScript `pnpm exec tsc --noEmit` at agent end for frontend changes. Python pytest remains a manual advisory because automatic beforeGit runs can stall every commit attempt.
- `selected` manual Playwright e2e listing for UI changes; never auto-run.
- `selected` safety blockers for secret paths, generated/vendor paths, live systemd operations, destructive database/log deletion, Plane mutations, Alembic downgrades, and symlink escapes.
- `selected` reference-mode architecture guidance only; avoid dumping large wiki/ADR content into every prompt.

## Local Probe Evidence

`selected` Target root: `/home/james/symphony`; git root probe returned `/home/james/symphony`.

`selected` Runtime root hardening: generated extension resolves checks/guidance/safety from `PROFILE.targetRepo` when the session cwd is inside `/home/james/symphony`, preventing nested `web/frontend/web/frontend` command roots.

`selected` Working tree already had unrelated modified files before generation: `.claude/skills/symphony-binding-scaffold/SKILL.md`, `.claude/skills/symphony-onboard-project/SKILL.md`, `.claude/skills/symphony-workflow-author/SKILL.md`.

`selected` Manifests/configs found: `pyproject.toml`, `web/frontend/package.json`, `web/frontend/tsconfig.json`, `web/frontend/playwright.config.ts`, `web/frontend/next.config.mjs`, `alembic.ini`, `web/README.md`, `CLAUDE.md`, `CONTEXT.md`, `docs/adr/*.md`, `wiki/index.md`, `wiki/ROUTING.md`.

`selected` Tool probe: `jq`, `node`, `npm`, `pnpm`, `yarn`, `bun`, `npx`, `ruff`, and `pytest` exist on PATH. `deno`, global `tsc`, `prettier`, `eslint`, `biome`, `black`, `shfmt`, `shellcheck`, `go`, and `cargo` were missing.

`selected` Frontend-local tools: `web/frontend/node_modules/.bin/tsc`, `web/frontend/node_modules/.bin/playwright`, and `web/frontend/node_modules/.bin/next` exist. `web/frontend/package.json` scripts include `build: next build`, `lint: next lint`, and `test:e2e: playwright test`.

`selected` File-type probe counted 82 Python files, 36 TS/TSX files, 3 JSON files, 2 MJS files, 2 shell files, and 101 Markdown files.

`selected` Python test config lives in `pyproject.toml`: pytest paths are `tests`, `web/api/tests`, and `web/cli/tests`; `asyncio_mode = auto`; `pythonpath = [".", "web/api"]`.

`selected` Runbook validation contract in `wiki/analyses/symphony-tests-index.md`: `python3 -m pytest -q`, `python3 -m py_compile *.py`, and `git diff --check` are expected checks.

`selected` Operational docs: `CLAUDE.md` and `wiki/concepts/symphony-operations.md` require James approval before `systemctl restart/stop`, unit edits, Plane API mutations, smoke requeues, env edits, and destructive actions.

`selected` Secret rule: `/home/james/symphony-host.env` is a 0600 secrets file and must never be printed; `.env` and `*.env` are gitignored.

`selected` Frontend deploy hazard: `web/frontend/deploy.sh` and `wiki/analyses/podium-frontend-deploy-cosmetics.md` document that in-place `next build` or `next dev` can corrupt live `.next`; production deploy uses staging swap plus `podium-web.service` stop/start.

## External Best-Practice Findings

`selected` Python: primary docs recommend `python -m py_compile <file>` as fast syntax validation; pytest is project-level and should run before git or manually, not after every write. Source: https://docs.python.org/3/library/py_compile.html and https://docs.pytest.org/

`selected` Ruff: fast lint/format can run after write, but formatter should be fail-open and only selected when repo formatter contract exists. Source: https://docs.astral.sh/ruff/linter/

`selected` JSON: `jq . <file>` is fast parse validation and suitable as afterWrite blocking. Source: https://jqlang.github.io/jq/manual/

`selected` Shell: `bash -n <file>` checks syntax without executing and is suitable as afterWrite blocking. Source: https://www.gnu.org/software/bash/manual/bash.html

`selected` TypeScript/Next: `tsc --noEmit` and Next build are project-level checks; Next build is expensive and should be manual/CI or pre-git advisory, never per-write. Source: https://www.typescriptlang.org/docs/handbook/compiler-options.html and https://nextjs.org/docs

`selected` Playwright: e2e suites should run in CI/manual/pre-git only and never per-write. Source: https://playwright.dev/docs/ci

`selected` Pi harness semantics from skill contract: `tool_result` write handling can fail a write result, `tool_call` can block safety and beforeGit, and `agent_end` is advisory-only.

## Harness Profile

### Profile Metadata

| status | key | value | reason |
|---|---|---|---|
| selected | target_repo | `/home/james/symphony` | Resolved absolute git root from metadata/probe. |
| selected | runtime_output | `.pi/extensions/personal-harness.ts` | Required Pi-local generated extension path. |
| selected | source_artifact | `wiki/raw/personal-harness-pi-profile.md` | Tracked wiki raw copy is durable generator reference; ignored `.rpiv` artifact remains local skill output. |
| selected | posture_default | syntax blocking, format fail-open, lint advisory, project advisory, scenario manual, safety blocking | Matches skill timing/posture contract and repo evidence. |

### Detected Languages and Tools

| status | language/tool | evidence | reason |
|---|---|---|---|
| selected | Python `.py` | 82 files, `pyproject.toml`, `pytest` PATH, `ruff` PATH | Main scheduler/API/test language. |
| selected | TypeScript/TSX `.ts/.tsx` | 36 files, `web/frontend/tsconfig.json`, local `tsc` | Frontend uses Next.js + React + strict TS. |
| selected | JavaScript/MJS `.js/.mjs/.cjs` | 2 MJS files, `node` PATH | Config files can be syntax-checked with Node. |
| selected | JSON `.json` | 3 JSON files, `jq` PATH | Fast jq parse available. |
| selected | Shell `.sh/.bash/.zsh` | shell scripts, `bash` PATH | `bash -n` available. |
| skipped | YAML/TOML syntax | `bindings.yml`, `models.yml`, `pyproject.toml` exist | No `yamllint`, `taplo`, or equivalent in probe; do not invent dependency. |
| skipped | Markdown lint | many wiki/docs files | No markdown linter configured; docs are content, not syntax-gated. |

### Syntax Check Commands

| status | id | language | cwd | command | args | extensions | timeout | posture | reason |
|---|---|---|---|---|---|---|---:|---|---|
| selected | python-py-compile | Python | repo root | `python3` | `-m py_compile {file}` | `.py` | 10000 | blocking | Fast stdlib syntax gate, no execution. |
| selected | json-jq | JSON | repo root | `jq` | `. {file}` | `.json` | 10000 | blocking | Fast parse gate; `jq` exists. |
| selected | javascript-node-check | JavaScript | repo root | `node` | `--check {file}` | `.js,.mjs,.cjs` | 10000 | blocking | Fast parse gate; does not apply to TS/TSX. |
| selected | shell-bash-n | Shell | repo root | `bash` | `-n {file}` | `.sh,.bash,.zsh` | 10000 | blocking | Syntax-only; no execution. |
| not_detected | typescript-per-file | TypeScript | repo root | n/a | n/a | `.ts,.tsx` | n/a | n/a | TS requires project context; use deferred `tsc --noEmit`. |
| not_detected | yaml-toml | YAML/TOML | repo root | n/a | n/a | `.yml,.yaml,.toml` | n/a | n/a | No installed parser in probe. |

### Formatter Commands

| status | id | cwd | command | args | extensions | timeout | reason |
|---|---|---|---|---|---|---:|---|
| skipped | python-ruff-format | repo root | `ruff` | `format {file}` | `.py` | 10000 | Ruff exists, but repo has no declared formatter config/contract; automatic rewrite would be surprising. |
| not_detected | prettier | repo root | n/a | n/a | `.ts,.tsx,.js,.mjs,.json,.md` | n/a | `prettier` not in PATH or frontend local bins. |
| not_detected | biome | repo root | n/a | n/a | `.ts,.tsx,.js,.json` | n/a | `biome` not in PATH or local bins. |
| not_detected | shfmt | repo root | n/a | n/a | `.sh` | n/a | `shfmt` missing. |

### Lint Commands

| status | id | cwd | command | args | extensions | timeout | posture | reason |
|---|---|---|---|---|---|---:|---|---|
| selected | python-ruff-check | repo root | `ruff` | `check {file}` | `.py` | 10000 | advisory | Ruff exists and sample check passed on core files; advisory avoids blocking style-only findings. |
| skipped | frontend-next-lint | `web/frontend` | `pnpm` | `lint` | `.ts,.tsx` | 120000 | advisory | Package script exists, but Next 15 lint behavior is project-level/legacy and too broad for afterWrite. |
| not_detected | eslint | repo root | n/a | n/a | `.ts,.tsx,.js` | n/a | n/a | Standalone `eslint` missing; no ESLint config found. |
| not_detected | shellcheck | repo root | n/a | n/a | `.sh` | n/a | n/a | `shellcheck` missing. |

### Project Check Commands

| status | id | cwd | command | args | timeout | trigger extensions/globs | timing | posture | reason |
|---|---|---|---|---|---:|---|---|---|---|
| skipped | python-pytest | `` | `uv` | `run pytest -q` | 120000 | `.py` / `tests/**,web/api/**,web/cli/**` | manual | advisory | Full suite is normal validation but too slow for every git attempt; git reminder tells agents to run it manually through the repo-managed uv environment for Python changes. |
| selected | frontend-tsc | `web/frontend` | `pnpm` | `exec tsc --noEmit` | 120000 | `.ts,.tsx` / `web/frontend/**` | agentEnd | advisory | Local `tsc` exists and catches TS/React type gaps; agentEnd cannot block. |
| selected | git-diff-check | `` | `git` | `diff --check` | 30000 | all touched files | beforeGit | advisory | Runbook validation contract; whitespace should be checked before commit/push. |
| skipped | frontend-next-build | `web/frontend` | `pnpm` | `build` | 180000 | `.ts,.tsx` / `web/frontend/**` | manual | advisory | `next build` can mutate live `.next`; use `web/frontend/deploy.sh` intentionally, not automatic harness. |
| skipped | alembic-baseline | `` | `python3` | `-m pytest tests/test_alembic_baseline.py -q` | 120000 | `.py` / `web/api/migrations/**,web/api/schema.py` | manual | advisory | Valuable for schema work, but too narrow to auto-trigger safely without a migration-specific mode. |
| skipped | podium-skills-dry-run | `` | `python3` | `-m web.cli.podium skills refresh --dry-run` | 60000 | `.md` / `.claude/skills/**` | manual | advisory | Dry-run is safe, but only relevant to skill catalog edits; prompt advisory is enough. |

### Scenario Check Commands

| status | id | cwd | command | args | timeout | trigger extensions/globs | timing | posture | reason |
|---|---|---|---|---|---:|---|---|---|---|
| selected | frontend-playwright-e2e | `web/frontend` | `pnpm` | `test:e2e` | 300000 | `.ts,.tsx` / `web/frontend/**` | manual | advisory | Expensive browser suite; current config can overwrite `.next`, so list only and never auto-run. |
| skipped | live-deploy-smoke | `web/frontend` | `./deploy.sh` | `` | 300000 | `.ts,.tsx` / `web/frontend/**` | manual | advisory | Live deploy stops/starts `podium-web.service`; requires explicit operator approval outside harness. |
| not_detected | CI e2e | n/a | n/a | n/a | n/a | n/a | n/a | n/a | No CI workflow detected. |

### Safety Rules

| status | id | tool scope | match/path | operation | posture | reason |
|---|---|---|---|---|---|---|
| selected | secret-env-write | write,edit,ast_grep_replace | `.env`, `*.env`, `.env*`, `**/.env*` | Write env/secret file | blocking | Universal secret protection; `.env`/`*.env` are gitignored. |
| selected | secret-env-read | read | `.env`, `*.env`, `.env*`, `**/.env*`, `../symphony-host.env` | Read secret file | blocking | `/home/james/symphony-host.env` and env files must never be printed. |
| selected | secret-env-bash-read | bash | `(^|[;&|]\s*)\s*(cat|less|more|sed|grep|awk|head|tail)\b[^;&|]*(/home/james/symphony-host\.env|(^|\s)(\.env[^\s;&|]*|[^\s;&|]*/\.env[^\s;&|]*|[^\s;&|]*\.env)(\s|$))` | Read env/secret file via shell | blocking | Shell readers can print secrets; blocks common readers against `/home/james/symphony-host.env` and `.env`-like paths. |
| selected | generated-vendor-write | write,edit,ast_grep_replace | `.git/**`, `.venv/**`, `web/frontend/node_modules/**`, `web/frontend/.next/**`, `web/frontend/.next.staging/**`, `web/frontend/.next.prev/**`, `__pycache__/**`, `.pytest_cache/**`, `runs/**`, `podium.db`, `podium.db-*` | Write generated/vendor/runtime data | blocking | Protect generated dependencies, live fallback DB, run logs, and build output. |
| selected | live-config-edit | write,edit,ast_grep_replace | `bindings.yml`, `models.yml` | Edit live config | advisory | Live config changes can affect dispatch/model catalog; require deliberate review. |
| selected | live-systemctl | bash | `(^|[;&|]\s*)\s*(sudo\s+)?systemctl\s+(restart|stop|start|reload)\s+(symphony-host|podium-api|podium-web|telegram-alert@)[^\s;]*` | Mutate live services | blocking | Project docs require James approval for restart/stop/unit actions. |
| selected | unit-file-touch | bash | `/etc/systemd/system/(symphony-host|podium-api|podium-web|telegram-alert@)[^\s;]*\.service` | Touch live unit file | blocking | Unit edits require backup, daemon-reload, and operator approval. |
| selected | plane-api-mutation | bash | `(curl|http|httpx).*(POST|PATCH|DELETE|archive|/archive/).*(plane|PLANE_API|PLANE_API_URL)` | Mutate Plane API | blocking | Plane writes require explicit approval; Plane is mostly retired but still dangerous. |
| selected | destructive-db-log-rm | bash | `(^|[;&|]\s*)\s*(sudo\s+)?rm\s+-[A-Za-z]*r?f?[A-Za-z]*\s+([^;&|]*(podium\.db|/var/lib/symphony|runs/|/backup/podium)[^;&|]*)` | Delete DB, backups, or run logs | blocking | Data loss risk for Podium DB/backups/run logs. |
| selected | generic-rm-rf | bash | `(^|[;&|]\s*)\s*(sudo\s+)?rm\s+-[A-Za-z]*r[fA-Za-z]*\s+(/|\.\.|\.)($|\s|;)` | Destructive recursive delete | blocking | Universal destructive command blocker. |
| selected | alembic-downgrade | bash | `(^|[;&|]\s*)\s*(uv\s+run\s+)?alembic\s+downgrade\b` | Downgrade schema | blocking | Repo documents forward Alembic revisions; downgrade path not documented. |
| selected | podium-skills-live-refresh | bash | `python\s+-m\s+web\.cli\.podium\s+skills\s+refresh(?![^;&|]*--dry-run)` | Mutate Podium skill catalog | advisory | Docs require dry-run first; live refresh is operator action. |
| selected | frontend-build-live | bash | `(^|[;&|]\s*)\s*(pnpm\s+(build|start)|pnpm\s+exec\s+next\s+(build|start))\b` | Build/start frontend outside deploy script | advisory | In-place `.next` build/start can break live frontend; use deploy script intentionally. |

### Architecture Guidance

| status | relativePath | label | appliesTo | mode | reason |
|---|---|---|---|---|---|
| selected | `CONTEXT.md` | Symphony domain glossary | `.` | reference | Canonical terms; reference only to avoid prompt bloat. |
| selected | `wiki/index.md` | Wiki index | `.` | reference | Required before wiki-backed project questions. |
| selected | `wiki/ROUTING.md` | Wiki routing | `.` | reference | Narrows wiki searches. |
| selected | `web/README.md` | Podium web/API runbook | `web/` | reference | Covers API/frontend/migrations/e2e/reverse proxy. |
| selected | `docs/adr/0005-replace-plane-with-podium.md` | ADR-0005 Podium architecture | `web/` | reference | Governs Podium tracker/frontend architecture. |
| selected | `docs/adr/0006-engine-state-surfaced-by-polling-not-websocket.md` | ADR-0006 polling decision | `web/frontend/` | reference | Governs frontend state freshness and WebSocket expectations. |
| selected | `wiki/analyses/symphony-tests-index.md` | Symphony validation contract | `tests/` | reference | Test map and validation commands. |
| selected | `wiki/analyses/podium-frontend-deploy-cosmetics.md` | Frontend deploy hazard | `web/frontend/` | reference | `.next` and deploy hazard guidance. |
| skipped | full wiki injection | `wiki/**` | `.` | full | Too large; use reference pointers and read-on-demand. |

### Touched-File Guidance Locations

| status | relativePath | appliesTo | label | reason |
|---|---|---|---|---|
| skipped | `CLAUDE.md` | `.` | Root agent context | Pi already loads project context; duplicating it risks prompt spam. |
| skipped | `web/README.md` | `web/` | Podium web/API runbook | Covered as `Architecture Guidance` reference-mode entry to avoid full doc injection. |
| skipped | `wiki/analyses/podium-frontend-deploy-cosmetics.md` | `web/frontend/` | Frontend deploy hazard | Covered as `Architecture Guidance` reference-mode entry to avoid full doc injection. |
| skipped | `wiki/analyses/symphony-tests-index.md` | `tests/` | Test index | Covered as `Architecture Guidance` reference-mode entry to avoid full doc injection. |

### Prompt Advisories

| status | advisory | reason |
|---|---|---|
| selected | Treat this repo as live infrastructure. Do not read `/home/james/symphony-host.env`; do not print secrets. | Project safety rule. |
| selected | Ask James before service restarts/stops, systemd unit edits, Plane mutations, smoke requeues, env edits, destructive data actions, or live deploys. | Project safety rule. |
| selected | For Symphony-specific questions, read `wiki/index.md` then `wiki/ROUTING.md` before broad search. | Wiki workflow requirement. |
| selected | For frontend work, do not use automatic Playwright/e2e as an edit gate; it is manual and may affect `.next`. | Local deploy hazard. |
| selected | Before commit/push, inspect diff for secrets and run relevant advisory checks. | Git preflight safety. |

### Git Preflight Reminders

| status | enabled | posture | runProjectChecks | text | reason |
|---|---|---|---|---|---|
| selected | true | advisory | true | `Before git commit/push: inspect diff, ensure no secrets, run git diff --check. Run uv run pytest -q manually for Python changes and pnpm exec tsc --noEmit for frontend changes when relevant; Playwright stays manual for UI flows.` | Project has no CI/pre-commit; beforeGit lightweight checks run first; pytest is manual to avoid 120s git delays. |

### Blocking and Advisory Posture

| status | area | timing | posture | reason |
|---|---|---|---|---|
| selected | syntax | afterWrite | blocking | Fast, high-signal parse gates. |
| selected | formatter | afterWrite | skipped/fail-open | No formatter contract; avoid unrequested rewrites. |
| selected | lint | afterWrite | advisory | Ruff can help without blocking style findings. |
| selected | project checks | agentEnd/beforeGit | advisory | Broad checks; no clean baseline proof during this skill. `agentEnd` cannot block by Pi contract. |
| selected | scenario checks | manual | advisory | E2E expensive and potentially `.next`-mutating. |
| selected | safety | tool_call | blocking/advisory per rule | Deterministic local blockers run before tool execution. |

### Gap Analysis

| category | status | local evidence | web evidence | selected mitigation | skipped alternatives | residual risk |
|---|---|---|---|---|---|---|
| touched-file syntax | selected | `python3`, `jq`, `node`, `bash` available | py_compile/jq/node/bash docs recommend fast parse gates | afterWrite blocking syntax checks | TS per-file parser skipped | TS errors wait for `tsc`. |
| formatter | skipped | No Prettier/Biome/Black; Ruff exists but no formatter contract | Formatters should fail-open and follow repo convention | No automatic formatting | Ruff format skipped | Code style drift remains manual. |
| lint | selected | Ruff available; sample core-file ruff check passed | Lint afterWrite advisory recommended | Ruff `.py` advisory | ESLint/shellcheck not detected | TS/shell lint remains manual. |
| project typecheck/build/test | selected | pytest config, local tsc, runbook validation | Project checks should be deferred advisory unless clean baseline | git diff beforeGit advisory; tsc agentEnd advisory; `uv run pytest -q` manual reminder | Next build skipped due `.next` hazard; Alembic baseline manual; `uv run pytest -q` automatic beforeGit skipped | Broad tests remain manual and can be missed. |
| scenario / e2e | selected | `pnpm test:e2e`, Playwright config | E2E manual/pre-git, never per-write | manual scenario listing | No auto-run | User must run manually when UI risk warrants. |
| architecture / context guidance | selected | `CONTEXT.md`, ADRs, wiki | Reference/scoped guidance preferred for large docs | reference-mode guidance pointers | full wiki injection skipped | Agent may ignore reference unless task relevant. |
| operational safety | selected | CLAUDE/runbook service gates | Safety blockers at tool_call | systemctl/unit/Plane/destructive command blockers | Allowlisted approval state not modeled | Approved live actions may require temporarily disabling/editing profile. |
| secrets / protected paths | selected | `.env` gitignored; `symphony-host.env` secret | Block `.env*`, read-tool secret reads, bash shell reader secret reads, vendor writes | path blockers + symlink hardening + bash reader regex | None | Exotic secret path or unusual shell reader not listed may pass. |
| git / preflight | selected | no CI/pre-commit; runbook checks | beforeGit reminder/checks recommended | git reminder + beforeGit project checks | blocking git checks skipped without clean baseline | Commit can proceed after advisory failures. |
| unsupported write tools | selected | Pi write-capable tools with concrete paths: write/edit/ast_grep_replace | Gate concrete file tools; skip directory-only tools | gate write/edit/ast_grep_replace apply=true | bash-generated files cannot be per-file syntax-checked | Bash commands can mutate files without post-write file gates. |

### Smoke-Test Commands

| status | smoke | command/check | reason |
|---|---|---|---|
| selected | load smoke | `PI_OFFLINE=1 pi --no-session -e ./.pi/extensions/personal-harness.ts --list-models haiku >/dev/null` | Proves extension loads with normal extension discovery. |
| selected | isolated load smoke | `PI_OFFLINE=1 pi --no-session --no-extensions -e ./.pi/extensions/personal-harness.ts --list-models haiku >/dev/null` | Proves generated extension loads alone. |
| selected | syntax dry checks | temp `.py`, `.json`, `.mjs`, `.sh` through selected syntax commands | Proves selected tools work. |
| selected | safety dry checks | mocked ExtensionAPI events for safe synthetic bash/file inputs | Avoids touching secrets/services while proving blockers fire and benign commands pass. |
| selected | project-check trigger dry checks | mocked ExtensionAPI events from repo root and `web/frontend` cwd | Proves trigger state, agentEnd advisory behavior, beforeGit ordering, and targetRepo root resolution. |
| selected | manual scenario listing | mocked ExtensionAPI agentEnd after frontend touch | Ensures manual scenarios are listed, not run. |
| selected | guidance dry | prompt advisory/reference-mode inspection | No full doc dump expected. |
