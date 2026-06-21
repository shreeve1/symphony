---
date: 2026-06-21T00:09:33+0000
author: James Schriever
source: web-verification
video_url: https://youtu.be/yv8VZpov8bk?is=6sWVgj9ZHDCvQSbV
video_id: yv8VZpov8bk
topic: "Claude Code built-in git worktree support (claude --worktree)"
status: complete
last_updated: 2026-06-21T00:09:33+0000
last_updated_by: James Schriever
---

# Web Research: Claude Code built-in git worktree support (`claude --worktree`)

## Verification Question
Does Claude Code actually ship built-in git worktree support as the video
describes, and is the creator's "paper cut" (commits/pushes landing on `main`
instead of the worktree branch) a real, explainable behavior?

## Verdict
**Real (accurate, with the paper cut correctly identified but incompletely
explained).** Primary documentation confirms the feature exactly as Matt Pocock
demonstrates it: `claude --worktree` creates an isolated worktree under
`.claude/worktrees/<name>/` on a branch `worktree-<name>`, it is "just git
worktree under the hood," subagents can run in their own worktrees (opt-in), and
exiting prompts you to keep or remove the worktree (with un-pushed work lost on
removal). His paper cut is real and the root cause is documented: worktrees
branch from the repository's **default remote branch, `origin/HEAD`** (i.e.
`main`), so an agent that pushes without a specified branch can land commits
against the main lineage. What the video *omitted* is the official fix — the
`worktree.baseRef: "head"` setting — plus several quality-of-life features
(`.worktreeinclude` for `.env` copying, the `-w` shorthand, PR-based worktrees,
automatic subagent cleanup, and the `.gitignore` recommendation).

## What the Video Got Right
- Built-in git worktree support exists and was announced by the Claude Code team (Boris Cherny): "Introducing: built-in git worktree support for Claude Code. Now, agents can run in parallel without interfering with one other. Each agent gets its own worktree and can work independently." — [Boris Cherny on X](https://x.com/bcherny/status/2025007393290272904), [Boris Cherny on Threads](https://www.threads.com/@boris_cherny/post/DVAAnexgRUj/introducing-built-in-git-worktree-support-for-claude-code-now-agents-can-run-in)
- `claude --worktree` creates a worktree at `.claude/worktrees/<value>/` on a new branch named `worktree-<value>` — [Run parallel sessions with worktrees, Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- If you omit the name, Claude auto-generates a whimsical multi-word name (docs example: `bright-running-fox`; video saw "cheerful coalescing worth" / "delightful dazzling sketch") — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- "It's just using git worktree under the hood" — confirmed; a worktree is "a separate working directory with its own files and branch, sharing the same repository history and remote as your main checkout" — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- Exiting prompts to keep or remove the worktree, and removing one with uncommitted/un-pushed work discards it — "Removing deletes the worktree directory and its branch, discarding any uncommitted changes, untracked files, and commits" — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- Subagents can use worktrees and it is **opt-in**: "Ask Claude to 'use worktrees for your agents', or set it permanently ... by adding `isolation: worktree` to the frontmatter" — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- IDE/desktop tooling surfaces worktrees; the desktop app "creates a worktree for every new session automatically" — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)

## What the Video Oversold
- Title/thesis "I'm using claude --worktree for everything now" and "I'm not sure why you wouldn't want to use git worktrees every single time" — primary docs frame worktrees as **one of several** parallelization mechanisms ("Worktrees are one of several ways to run Claude in parallel ... subagents and agent teams coordinate the work itself"), and note real friction (first-use trust dialog, per-worktree dependency/env setup, fresh checkouts missing untracked files). Reasonable enthusiasm, but "for everything" understates the setup cost the docs call out. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- No outright fabrication was found; the video's claims are conservative relative to the documented feature set.

## What the Video Omitted
- **The actual fix for his paper cut:** worktrees branch from `origin/HEAD` by design; to branch from local `HEAD` (carrying unpushed/feature-branch state) set `worktree.baseRef: "head"` in settings. This directly addresses "it committed against main." — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **`.worktreeinclude`**: a fresh worktree is a clean checkout, so untracked files like `.env`/`.env.local` are absent; a `.worktreeinclude` file (gitignore syntax) copies them in automatically. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **`-w` shorthand** for `--worktree`. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **PR-based worktrees**: `claude --worktree "#1234"` fetches `pull/<number>/head` and creates the worktree at `.claude/worktrees/pr-<number>`. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **Automatic cleanup nuance**: subagent/background worktrees are swept once older than `cleanupPeriodDays` (if no uncommitted/untracked/unpushed work), but `--worktree` worktrees are *never* removed by that sweep; while an agent runs, Claude `git worktree lock`s its worktree. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **Recommended `.gitignore` entry** for `.claude/worktrees/` so worktree contents don't show as untracked in the main checkout. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **First-use workspace trust dialog** required before `--worktree` works interactively. — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **Non-git VCS support** via `WorktreeCreate`/`WorktreeRemove` hooks (SVN, Perforce, Mercurial). — [Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- **Version introduced**: secondary coverage attributes the CLI feature to Claude Code **v2.1.50** (not stated in the docs page fetched). — [claudefa.st worktree guide](https://claudefa.st/blog/guide/development/worktree-guide)
- **`--tmux` flag** to launch in its own tmux session was mentioned in search summaries but was NOT present on the official worktrees docs page fetched; treat as unverified pending a primary source. — [claudefa.st worktree guide](https://claudefa.st/blog/guide/development/worktree-guide)

## Primary Sources Attempted
- `https://code.claude.com/docs/en/worktrees` — fetched-ok (authoritative; used for nearly all confirmations)
- `https://x.com/bcherny/status/2025007393290272904` — not fetched directly; full announcement text captured via search result snippet
- `https://www.threads.com/@boris_cherny/post/DVAAnexgRUj/...` — not fetched directly; announcement text captured via search result snippet

## Sources
- [Run parallel sessions with worktrees — Claude Code Docs](https://code.claude.com/docs/en/worktrees)
- [Boris Cherny on X — announcement](https://x.com/bcherny/status/2025007393290272904)
- [Boris Cherny on Threads — announcement](https://www.threads.com/@boris_cherny/post/DVAAnexgRUj/introducing-built-in-git-worktree-support-for-claude-code-now-agents-can-run-in)
- [Run agents in parallel — Claude Code Docs](https://code.claude.com/docs/en/agents)
- [Claude Code Worktrees: Parallel Sessions Without Conflicts — claudefa.st](https://claudefa.st/blog/guide/development/worktree-guide)
- [Parallel Vibe Coding: Using Git Worktrees with Claude Code — Dan Does Code](https://www.dandoescode.com/blog/parallel-vibe-coding-with-git-worktrees)
- [Git Worktrees and Claude Code: A Layered Toolkit — Dan Gerlanc](https://dangerlanc.com/writing/git-worktrees-and-claude-code/)
