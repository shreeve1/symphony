# Session Capture: Run #128 review → Claude unattended modal auto-drive

- Date: 2026-06-19
- Purpose: Review failed Symphony Run #128, find why an unattended Claude run was mislabelled "Agent timed out," and change the adapter to drive permission/question modals instead of stalling.
- Scope: Run #128 root cause; claude binary version behavior under bypassPermissions; the homelab additionalDirectories grant; the modal auto-drive behavior change and its security tradeoff. Excludes unrelated working-tree changes from other sessions.

## Durable Facts

- **Run #128 (issue #57, binding `symphony`) failed verdict `blocked`, summary "Agent timed out"** — but the label was wrong. It was a `resumed` Claude run that parked on an interactive Edit-confirmation modal for `.claude/skills/symphony-workflow-author/SKILL.md`. The poll loop treated the static pane as plain idle, sent 2 completion nudges, then aborted ~3m16s. — Evidence: `runs/128.log`, `podium.db` run id 128 row, `claude_runner.py` (`_poll_claude_until_done`).
- The substantive work still landed despite the failed run: homelab commits `f4f821b` + `08a64cf` (WORKFLOW.md trim/generalize), and symphony working-tree `templates/WORKFLOW.infra.md` + partial `SKILL.md` edits. Issue #57 left `blocked` with the SKILL.md/wiki wiring half-done. — Evidence: `git -C ~/homelab log`, `runs/128.log`.
- **`--permission-mode bypassPermissions` does NOT suppress every modal.** Per Claude Code docs, writes to protected paths (`.claude/`, except `.claude/worktrees`) and the `rm -rf /` / `rm -rf ~` circuit breakers are auto-approved only in `bypassPermissions`, and "as of v2.1.126 this includes writes to protected paths, which earlier versions still prompted for." `permissions.allow` rules cannot override the protected-path guard (the safety check runs before allow-rule evaluation). — Evidence: claude-code-guide agent over Claude Code permission docs.
- **Installed `claude` is 2.1.170** (≥2.1.126). Empirically, on 2.1.170, headless `claude --permission-mode bypassPermissions -p` auto-approves BOTH a `.claude/` edit and an out-of-cwd edit with no modal. So Run #128's modal came from an older binary at run time (04:11Z), since upgraded. — Evidence: `claude --version`; two headless edit probes run 2026-06-19.
- **`.claude/settings.json` gained `permissions.additionalDirectories: ["/home/james/homelab"]`** (commit `b18c943`) as the documented durable scope grant for the cross-repo homelab edits issue #57 performs, rather than relying on bypass to skip out-of-cwd prompts. — Evidence: `.claude/settings.json`, commit `b18c943`.

## Decisions

- **Auto-drive parked Claude modals instead of reject-and-abort.** Final behavior (commit `c434c59`, supersedes the interim `b18c943` Escape-reject):
  - Permission / Yes-No modal → send **Enter** (option 1 "Yes" pre-selected → approve), agent continues.
  - Multi-choice question picker → send **Escape**, wait `MODAL_QUESTION_SETTLE_SECONDS=5`, paste **"proceed with your recommendations"** (`MODAL_QUESTION_REPLY`).
  - Same modal persisting past `MODAL_STUCK_LIMIT=3` automated interactions → abort with a clear reason (not "Agent timed out").
  — Evidence: `claude_runner.py` (`_poll_claude_until_done`, `_send_enter`, `_hit_question_modal`, `_hit_permission_modal`), `tests/test_claude_runner.py`, commit `c434c59`.
- **Blanket auto-approve, NO carve-out** for the destructive `rm -rf /` / `rm -rf ~` circuit breakers — operator (James) chose "Blanket Enter" over a destructive-guard carve-out on 2026-06-19. The unattended agent can therefore execute a destructive command it raised by mistake; the binding sandbox and WORKFLOW.md are the only remaining guardrails. — Evidence: AskUserQuestion answer this session; `CLAUDE.md` "Unattended modal handling" section.

## Evidence

- `runs/128.log` — Run #128 transcript showing the parked SKILL.md Edit modal.
- `claude_runner.py` — modal auto-drive: constants `MODAL_STUCK_LIMIT`/`MODAL_QUESTION_SETTLE_SECONDS`/`MODAL_QUESTION_REPLY`, regexes `_MODAL_CHOICE_RE`/`_MODAL_HINT_RE`/`_QUESTION_CHOICE_RE`/`_QUESTION_HINT_RE`, helpers `_send_enter`/`_send_escape`/`_hit_permission_modal`/`_hit_question_modal`, new log lines `claude_permission_modal_approved`/`claude_question_modal_autoreplied`/`claude_modal_stuck`.
- `tests/test_claude_runner.py` — approve-then-complete, question auto-reply, stuck-abort; full suite 939 passed / 2 skipped.
- `CLAUDE.md` — "Unattended modal handling (claude_runner)" section.
- Restart: `symphony-host.service` PID 2958104, `code_sha=c434c59`, bindings=5, reconcile/dispatch healthy, 0 errors (2026-06-19 19:59:24Z).

## Exclusions

- No secrets from `/home/james/symphony-host.env`.
- Unrelated working-tree changes from other sessions (`ssh_support.py` SSH keepalives, `web/frontend/IssueFlyout.tsx`, `wiki/ROUTING.md` edits, `youtube/`) — not part of this change, left uncommitted.

## Open Questions And Follow-Ups

- Question-modal detection is best-effort regex; a real `ask_user_question` pane footer was not reproduced/confirmed. If a picker uses different footer text it falls through to the bounded idle-nudge path. The agent is supposed to use the `SYMPHONY_QUESTION` park, so this path should rarely fire.
- Issue #57 still `blocked` with SKILL.md template-wiring + wiki update outstanding; needs hand-reconcile or requeue now the binary handles the edits cleanly.
- `CLAUDE.md` "Live bindings" guidance: bindings=5 at this restart (homelab, symphony, dotfiles, n8n, ai-web-chat) per logs.
