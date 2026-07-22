#!/usr/bin/env bash
# Provision wave 1 worktrees for herdr-issue-frontier (parentless: #30,#31,#32).
set -euo pipefail
cd /home/james/symphony
REPO=shreeve1/symphony
BASE=$(git rev-parse HEAD)
STATE_DIR=$(mktemp -d -t herdr-frontier-XXXX)
echo "STATE_DIR=$STATE_DIR"
echo "BASE=$BASE"
: >"$STATE_DIR/wave.manifest"

write_tasks() {
	local n=$1 title=$2 wt=$3
	cat >"$wt/.herdr-worker-task.md" <<EOF
You are implementing GitHub issue #$n: $title. Work ONLY in this worktree (your cwd).
Do NOT run gh. Do NOT close or edit the GitHub issue — the orchestrator owns that.

Read \`.herdr-issue.md\` in your cwd: full issue body, acceptance criteria, and a
## Verification command.

The \`/implement\` skill is loaded for you — RUN IT (\`/implement\`) against the
ticket in \`.herdr-issue.md\`.

**HARD OVERRIDE on \`/implement\`'s last step.** \`/implement\` ends with "use
\`/code-review\` to review the work." DO NOT. You have no delegation tools and the
independent reviewer pane does the review out-of-band. If \`/code-review\` is
reported not found, that is EXPECTED — stop; do not retry or improvise a review.
(\`/tdd\` is also not loaded — apply TDD directly at the seams if you want test-first.)

**Also override \`/implement\`'s "independent verify" step.** If \`/implement\`
references an "independent verify" via subagents (e.g. \`../_shared/verify-claims.md\`),
SKIP IT. You have no subagent tools in this pane — attempting it will silently fail
or burn cycles. The reviewer pane is the verification gate; trust it.

Additional rule \`/implement\` does not encode:
- Run the issue's exact ## Verification command (the backtick-quoted one) — it MUST exit 0.

Before finishing, COMMIT and VERIFY. The reviewer diffs your commits — UNCOMMITTED
WORK IS INVISIBLE and will be rejected as "no implementation" (this is the #1 failure):
1. \`git add <your source files by name>\` then \`git commit -m "feat(#$n): <subject>"\`.
   NEVER \`git add -A\` / \`git add .\` — orchestration artifacts (\`.pi-orch-logs/\`,
   \`.herdr-orch-sessions/\`, \`.herdr-*.md\`) must not be committed.
2. VERIFY the commit landed: \`git log --oneline -1\` shows your \`feat(#$n)\` at HEAD, and
   the filtered status is empty:
   \`git status --porcelain -- . ':(exclude).pi-orch-logs' ':(exclude).herdr-orch-sessions' ':(exclude).herdr-issue.md' ':(exclude).herdr-worker-task.md' ':(exclude).herdr-reviewer-task.md'\`
3. Only then print exactly one final line: IMPL_DONE
If you produced NO changes, do NOT print IMPL_DONE — print: IMPL_STUCK: no changes produced
Otherwise for a hard blocker print: IMPL_STUCK: <one-line reason>
EOF
	cat >"$wt/.herdr-reviewer-task.md" <<EOF
You are a READ-ONLY reviewer for GitHub issue #$n: $title. You lack write/edit — do not
modify files.

Read \`.herdr-issue.md\` in your cwd for acceptance criteria + ## Verification.
Review the implementation. Diff the WORKING TREE (committed AND uncommitted — the
worker sometimes forgets to commit, and uncommitted work must still be visible to
you), excluding orchestration artifacts:
\`git diff $BASE -- . ':(exclude).pi-orch-logs' ':(exclude).herdr-orch-sessions' ':(exclude).herdr-issue.md' ':(exclude).herdr-worker-task.md' ':(exclude).herdr-reviewer-task.md'\`
Then read every changed file. If the only changes are uncommitted, that is criterion
5 failing — say so explicitly ("implementation is uncommitted — worker must commit")
so the next cycle's fix-prompt is actionable.

Mechanically verify:
1. Every acceptance-criterion checkbox is objectively satisfied.
2. The issue's ## Verification command passes (exit 0).
3. Lint/typecheck pass for touched files.
4. No unrelated or scope-creep changes in the diff.
5. No uncommitted ISSUE work left. The worktree holds orchestration artifacts
   (\`.pi-orch-logs/\`, \`.herdr-orch-sessions/\`, \`.herdr-*.md\`) that are NOT issue work —
   exclude them:
   \`git status --porcelain -- . ':(exclude).pi-orch-logs' ':(exclude).herdr-orch-sessions' ':(exclude).herdr-issue.md' ':(exclude).herdr-worker-task.md' ':(exclude).herdr-reviewer-task.md'\`
   must be empty.

Output reasoning per criterion, then end with EXACTLY ONE of these on its own line:
VERDICT: LGTM
VERDICT: BLOCKING
EOF
}

for n in 30 31 32; do
	title=$(gh issue view "$n" --repo "$REPO" --json title -q .title)
	ts=$(date +%s)
	branch="herdr/issue-$n-$ts"
	wt="$STATE_DIR/wt-$n"
	echo "=== provisioning #$n ($title) -> $wt on $branch ==="
	git worktree add -b "$branch" "$wt" "$BASE" >/dev/null
	gh issue edit "$n" --repo "$REPO" --add-assignee "@me" >/dev/null 2>&1 || echo "  (assignee claim skipped — flaky gh; worktree is the real isolation)"
	# gh issue view hard-fails on this repo (GraphQL Projects-classic deprecation -> exit 1).
	# REST API skips the Projects field. Comments appended if any (these tickets have 0).
	{
		gh api repos/$REPO/issues/$n --jq '.body'
		gh api repos/$REPO/issues/$n/comments --jq '.[] | "\n---\n**Comment by \(.user.login) (\(.created_at)):**\n\(.body)"' 2>/dev/null || true
	} >"$wt/.herdr-issue.md"
	write_tasks "$n" "$title" "$wt"
	printf '%s\t%s\t%s\t%s\n' "$n" "$wt" "$wt/.herdr-worker-task.md" "$wt/.herdr-reviewer-task.md" >>"$STATE_DIR/wave.manifest"
	echo "  ok"
done

echo "=== manifest ==="
cat "$STATE_DIR/wave.manifest"
echo "$STATE_DIR" >/home/james/symphony/.scratch/herdr-frontier-state.path
