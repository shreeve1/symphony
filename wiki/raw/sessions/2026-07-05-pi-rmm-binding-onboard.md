# Session Capture: pi-rmm Binding Onboard

- Date: 2026-07-05
- Purpose: Capture durable evidence from onboarding `/home/james/pi-rmm` as a Podium-backed Symphony binding.
- Scope: Binding creation, restart evidence, smoke-test evidence, verification, and explicit exclusions.

## Durable Facts

- `/home/james/pi-rmm` was not initially a git repository, so it was initialized on branch `main` and committed as `c7d955e Initial commit`. Evidence: `git init -b main && git add . && git commit -m "Initial commit"` in `/home/james/pi-rmm`.
- Symphony binding `pi-rmm` was scaffolded with `type: coding`, `tracker: podium`, `repo_path: /home/james/pi-rmm`, `base_branch: main`, `default_agent: pi`, and `pi_mode: rpc`. Evidence: `bindings.yml` and `PodiumBindingScaffoldResult(binding_name='pi-rmm', db_path=PosixPath('/home/james/symphony/podium.db'), bindings_path=PosixPath('/home/james/symphony/bindings.yml'))`.
- The Podium DB contains `binding` and `binding_settings` rows for `pi-rmm`. Evidence: SQLite checks returned `('pi-rmm', 'pi-rmm', 0)` and `('pi-rmm',)`.
- `symphony-host.service` was restarted onto code SHA `8bdcbc5` with seven bindings loaded. Evidence: journal line `symphony_started service=symphony code_sha=8bdcbc5 bindings=7`.
- Startup verification included `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, and `reconcile_startup_done binding=pi-rmm cleaned=0`. Evidence: `sudo journalctl -u symphony-host.service _PID=949375 ...`.
- Podium smoke Issue `225` created Run `851`, which succeeded with verdict `done` using agent `pi`, provider `deepseek`, model `deepseek-v4-pro:high`; the Issue parked in `in_review`. Evidence: TestClient smoke output in this session.
- The smoke run summary reported a healthy clean repo and no code changes needed. Evidence: Run `851` summary text in this session.
- Skill verification passed: `uv run pytest tests/skills/test_onboard_project.py tests/skills/test_binding_scaffold.py tests/skills/test_restart_troubleshooter.py tests/skills/test_binding_smoke.py` returned `12 passed, 1 warning`.

## Decisions

- Operator approved defaults for onboarding: `name=pi-rmm`, `binding_type=coding`, `base_branch=main`, `default_agent=pi`, `pi_mode=rpc`. Evidence: session reply "approved defaults".

## Evidence

- `bindings.yml` — durable binding configuration.
- `/home/james/pi-rmm` git commit `c7d955e` — target repo bootstrap.
- Symphony commit `8bdcbc5 Add pi-rmm binding` — committed `bindings.yml` append.
- Podium Issue `225` / Run `851` — live smoke evidence.
- `tests/skills/test_onboard_project.py` plus sibling skill tests — workflow regression evidence.

## Exclusions

- No secrets, credentials, tokens, private env files, or `/home/james/symphony-host.env` contents were read or captured.
- Full transcript omitted; only operational facts and command evidence were captured.

## Open Questions And Follow-Ups

- `/home/james/pi-rmm` has no top-level `CLAUDE.md` or `AGENTS.md`; for a coding binding this is a warning, not a Symphony blocker, but repo-owned safety/convention guidance should be added if desired.
