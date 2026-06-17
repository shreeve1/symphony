---
title: Pi personal harness removal
created: 2026-06-17
source_type: session
confidence: high
tags: [pi, harness, tooling, removed]
---

# Pi personal harness removal

## Durable facts

- The project-local Pi extension `.pi/extensions/personal-harness.ts` was removed on 2026-06-17 at James's request. Evidence: `git status --porcelain -- .pi` reported `D .pi/extensions/personal-harness.ts` after deletion.
- Pi extension discovery treats `.pi/extensions/*.ts` as project-local auto-discovered extensions. Removing that file removes the project-local personal harness from future Pi reloads/sessions.
- No matching global personal-harness extension was found under `/home/james/.pi/agent/extensions` during this session (`find /home/james/.pi/agent/extensions -maxdepth 3 -iname '*personal*' -o -iname '*harness*'` returned no paths).
- Current already-running Pi sessions may still have the deleted extension loaded until `/reload` or process restart. Already-injected personal-harness guidance messages in this conversation do not disappear retroactively.

## Evidence checked

- `find . -maxdepth 4 -path './.pi*' -print` showed `.pi/extensions/personal-harness.ts` as the only project-local Pi extension before removal.
- `find .pi -maxdepth 3 -type f -print | sort` produced no files after removal.
- `git status --porcelain -- .pi` showed the tracked deletion.

## Scope

This removed only the project-local Pi extension file. It did not remove:

- historical profile source: `wiki/raw/personal-harness-pi-profile.md`
- historical analysis: `wiki/analyses/personal-harness-pi-profile.md`
- Claude Code harness files under `.claude/`
- global Pi extensions under `/home/james/.pi/agent/extensions`

No secrets, `.env` contents, or `/home/james/symphony-host.env` contents were read or captured.
