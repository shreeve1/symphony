---
title: Claude unattended modal auto-drive (Run #128 root cause + fix)
type: analysis
status: promoted
created: 2026-06-19
updated: 2026-06-19
sources:
  - runs/128.log
  - claude_runner.py
  - tests/test_claude_runner.py
  - .claude/settings.json
  - CLAUDE.md
  - wiki/raw/sessions/2026-06-19-claude-modal-autodrive.md
confidence: high
tags: [claude, tmux, claude-runner, unattended, permission-modal, bypassPermissions, completion-protocol, run-128, security]
---

# Claude unattended modal auto-drive (Run #128 root cause + fix)

## Problem: a modal mislabelled as "Agent timed out"

Symphony Run #128 (issue #57, binding `symphony`, a **resumed** Claude run) failed with verdict `blocked` and summary "Agent timed out." The real cause was an interactive Edit-confirmation modal: the agent tried to edit `.claude/skills/symphony-workflow-author/SKILL.md`, and `--permission-mode bypassPermissions` did **not** suppress the modal. The poll loop in `_poll_claude_until_done` saw a static pane, treated it as a plain ended-turn idle, sent 2 completion nudges, and aborted ~3m16s — the misleading "Agent timed out" path from [C-0205]. [source: runs/128.log] [source: claude_runner.py]

This is the organic live idle run that [C-0205] flagged as an open follow-up ("nudge/fail-fast path not yet exercised by an organic live idle run") — except the trigger was a non-bypassable modal, not a model turn-end.

## Why bypassPermissions did not help

Per Claude Code permission docs (verified via claude-code-guide): writes to protected paths (`.claude/`, except `.claude/worktrees`) and the `rm -rf /` / `rm -rf ~` circuit breakers are auto-approved **only** in `bypassPermissions`, and "as of v2.1.126 this includes writes to protected paths, which earlier versions still prompted for." `permissions.allow` rules **cannot** override the protected-path guard — the safety check runs before allow-rule evaluation, so `Edit(.claude/**)` does nothing.

The installed binary is `claude` **2.1.170** (≥2.1.126). Two headless probes on 2026-06-19 confirmed 2.1.170 auto-approves both a `.claude/` edit and an out-of-cwd edit under `bypassPermissions -p` with no modal. So Run #128's modal came from an **older binary at run time** (since upgraded). The fix below is the durable safety net regardless of binary version. [source: wiki/raw/sessions/2026-06-19-claude-modal-autodrive.md]

## Fix: drive parked modals automatically

`claude_runner.py` `_poll_claude_until_done` now, when a pane has been idle past `IDLE_POLLS_BEFORE_NUDGE`, classifies it before nudging:

- **Permission / Yes-No modal** (`_hit_permission_modal`: `_MODAL_CHOICE_RE` Yes/No choice + `_MODAL_HINT_RE` hint) → `_send_enter`. Option 1 ("Yes") is pre-selected, so Enter approves and the agent continues.
- **Multi-choice question picker** (`_hit_question_modal`: `_QUESTION_CHOICE_RE` non-Yes/No choice + `_QUESTION_HINT_RE` selection/escape hint, excluding Yes/No modals) → `_send_escape`, wait `MODAL_QUESTION_SETTLE_SECONDS=5`, paste `MODAL_QUESTION_REPLY="proceed with your recommendations"` via `_paste_and_submit`.
- **Stuck guard**: the same modal pane persisting past `MODAL_STUCK_LIMIT=3` automated interactions → abort `exit_code=-1` with a clear "did not clear" reason (not "Agent timed out").

New log lines: `claude_permission_modal_approved`, `claude_question_modal_autoreplied`, `claude_modal_stuck`. [source: claude_runner.py] [source: tests/test_claude_runner.py]

This supersedes an interim implementation (commit `b18c943`) that sent **Escape to reject** modals and aborted after 2 rejections — replaced in the same session by the Enter-to-approve / question-auto-reply behavior (commit `c434c59`).

## Security tradeoff (operator decision)

Enter-to-approve is a **blanket auto-approve with no carve-out** — it also accepts the `rm -rf /` / `rm -rf ~` circuit breakers. James chose "Blanket Enter" over a destructive-guard carve-out on 2026-06-19. The unattended agent can therefore execute a destructive command it raised by mistake; the binding sandbox and WORKFLOW.md are the only remaining guardrails. Documented in `CLAUDE.md` "Unattended modal handling (claude_runner)". [source: CLAUDE.md]

## Related config grant

`.claude/settings.json` gained `permissions.additionalDirectories: ["/home/james/homelab"]` (commit `b18c943`) — the documented scope grant for the cross-repo homelab edits that infra work like issue #57 performs, rather than relying on bypass to skip out-of-cwd prompts. [source: .claude/settings.json]

## Verification

- `tests/test_claude_runner.py`: approve-then-complete, question auto-reply, stuck-abort. Full suite **939 passed / 2 skipped**.
- Deployed via `symphony-restart`: `symphony-host.service` PID 2958104, `code_sha=c434c59`, bindings=5, reconcile/dispatch healthy, 0 errors (2026-06-19 19:59:24Z).

## Follow-ups

- Question-modal detection is best-effort regex; a real `ask_user_question` pane footer was not reproduced. Mis-detected pickers fall through to the bounded idle-nudge path. Correct path remains the `SYMPHONY_QUESTION` park.
- Issue #57 still `blocked` (SKILL.md template-wiring + wiki update outstanding) — hand-reconcile or requeue.

## Related claims

C-0258, C-0259, C-0260; refines [C-0205] and [C-0151]; builds on [C-0150] (launch flags) and [C-0184] (session resume).
