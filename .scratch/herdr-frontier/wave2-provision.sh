#!/usr/bin/env bash
# Provision wave 2 (F-series frontend: #33,#34,#35) off current main (post-B-merges + schema fix).
# Adds an explicit prototype reference (web/frontend/prototype/chat-mock.html Variant B) to every
# worker + reviewer task so the frontend is built against the canonical visual, not improvised.
set -euo pipefail
cd /home/james/symphony
REPO=shreeve1/symphony
BASE=$(git rev-parse HEAD) # efc59c5… (green main)
STATE_DIR=$(mktemp -d -t herdr-frontier-wave2-XXXX)
echo "STATE_DIR=$STATE_DIR"
echo "BASE=$BASE"
: >"$STATE_DIR/wave.manifest"

# Prototype reference block — mandatory for all F-series (frontend) slices.
PROTO_BLOCK='**FRONTEND VISUAL SOURCE OF TRUTH — do not improvise the look.**
This issue is part of the Podium issue-chat FRONTEND. Before writing any
rendering / CSS / layout code, READ `web/frontend/prototype/chat-mock.html` in
your cwd and study its **Variant B** (the visual the spec §3 locked): full-width
message blocks (NO left/right chat alignment), role-color vocabulary
agent=#2563eb / operator=#16a34a / patrol=#d97706 / system=#64748b, and bubbles
split from comments_md on the `### <role> · <ISO-ts>` header grammar (spec §2.1,
already implemented by B1/#30). The prototype is the canonical visual contract —
match its layout, colors, and component structure; do NOT invent a new design.
If your slice (bubble renderer, composer + mode pill, live-tail rows, creation
flyout) is shown in the prototype, mirror it exactly.'

PROTO_CRIT='6. Frontend fidelity: the implementation matches
   `web/frontend/prototype/chat-mock.html` **Variant B** (full-width blocks;
   role-color vocabulary agent/op/patrol/system; bubble grammar from spec §2.1)
   rather than an improvised design. Call out any explicit deviation.'

write_tasks() {
	local n=$1 title=$2 wt=$3
	cat >"$wt/.herdr-worker-task.md" <<EOF
You are implementing GitHub issue #$n: $title. Work ONLY in this worktree (your cwd).
Do NOT run gh. Do NOT close or edit the GitHub issue — the orchestrator owns that.

Read \`.herdr-issue.md\` in your cwd: full issue body, acceptance criteria, and a
## Verification command.

$PROTO_BLOCK

The \`/implement\` skill is loaded for you — RUN IT (\`/implement\`) against the
ticket in \`.herdr-issue.md\`, honoring the visual source of truth above.

**HARD OVERRIDE on \`/implement\`'s last step.** \`/implement\` ends with "use
\`/code-review\` to review the work." DO NOT. You have no delegation tools and the
independent reviewer pane does the review out-of-band. If \`/code-review\` is
reported not found, that is EXPECTED — stop; do not retry or improvise a review.
(\`/tdd\` is also not loaded — apply TDD directly at the seams if you want test-first.)

**Also override \`/implement\`'s "independent verify" step.** If \`/implement\`
references an "independent verify" via subagents (e.g. \`../_shared/verify-claims.md\`),
SKIP IT. You have no subagent tools in this pane. The reviewer pane is the gate.

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
5. No uncommitted ISSUE work left (\`git status --porcelain\` filtered as above must be empty).
$PROTO_CRIT

Output reasoning per criterion, then end with EXACTLY ONE of these on its own line:
VERDICT: LGTM
VERDICT: BLOCKING
EOF
}

for n in 33 34 35; do
	title=$(gh issue view "$n" --repo "$REPO" --json title -q .title 2>/dev/null || gh api repos/$REPO/issues/$n --jq '.title')
	ts=$(date +%s)
	branch="herdr/issue-$n-$ts"
	wt="$STATE_DIR/wt-$n"
	echo "=== provisioning #$n ($title) -> $wt on $branch ==="
	git worktree add -b "$branch" "$wt" "$BASE" >/dev/null
	gh issue edit "$n" --repo "$REPO" --add-assignee "@me" >/dev/null 2>&1 || echo "  (assignee claim skipped)"
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
echo "$STATE_DIR" >/home/james/symphony/.scratch/herdr-frontier/wave2-state.path
