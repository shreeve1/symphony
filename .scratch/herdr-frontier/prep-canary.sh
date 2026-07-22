#!/usr/bin/env bash
# prep-canary.sh — durable prep before relaunching the (now-fixed) primitive.
# 1. Back up each worktree's salvage as a binary patch (never auto-commit
#    unreviewed partial edits).
# 2. Regenerate the ORIGINAL worker/reviewer task files — the failed cycle loop
#    overwrote .herdr-worker-task.md with "Cycle N reviewer said BLOCKING..."
#    fix-prompts. .herdr-issue.md is intact (not overwritten).
# 3. Clean wt-30's working tree: its salvage (redispatch_core.py) does not match
#    B1 (comments_md stamping) — give the canary a clean start. wt-31/#32 salvage
#    matches their issues (B2/B3) and is kept as a head start.
# 4. Write a fresh canary state dir + 1-row manifest (#30 only) referencing the
#    existing registered worktrees.
set -euo pipefail
cd /home/james/symphony
BASE=89ace5d67219a3fa9be1e36975a00854c3997b0a
WTS=/tmp/herdr-frontier-yPhn
SALV=/home/james/symphony/.scratch/herdr-frontier/salvage
mkdir -p "$SALV"

declare -A TITLE=( [30]="B1: comments_md write-side header stamping" \
                   [31]="B2: Discussion output contract selection (coding bindings)" \
                   [32]="B3: Live-tail protocol (run.tail enrichment + new endpoint + run columns)" )

write_tasks() {
	local n=$1 wt=$2; local title="${TITLE[$n]}"
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

echo "=== 1. backup salvage ==="
for n in 30 31 32; do
	wt="$WTS/wt-$n"
	git -C "$wt" diff --binary >"$SALV/salvage-wt-$n.patch"
	echo "  wt-$n: $(git -C "$wt" diff --stat | tail -1 | awk '{print $1" files, "$3" ins, "$4" del"}') -> $SALV/salvage-wt-$n.patch"
done

echo "=== 2. clean wt-30 working tree (questionable salvage; backed up) ==="
git -C "$WTS/wt-30" checkout -- . >/dev/null 2>&1 || true
echo "  wt-30 tracked changes after clean: $(git -C "$WTS/wt-30" status --porcelain | grep -vc '^??' || true)"

echo "=== 3. regenerate original worker/reviewer task files (all 3) ==="
for n in 30 31 32; do
	write_tasks "$n" "$WTS/wt-$n"
	echo "  wt-$n: regenerated .herdr-worker-task.md + .herdr-reviewer-task.md"
done

echo "=== 4. fresh canary state dir + manifest (#30 only) ==="
CANARY=/tmp/herdr-frontier-canary30
mkdir -p "$CANARY"
: >"$CANARY/wave.manifest"
printf '30\t%s\t%s/.herdr-worker-task.md\t%s/.herdr-reviewer-task.md\n' "$WTS/wt-30" "$WTS/wt-30" "$WTS/wt-30" >>"$CANARY/wave.manifest"
echo "  state=$CANARY"; cat "$CANARY/wave.manifest"
echo "$CANARY" >/home/james/symphony/.scratch/herdr-frontier-canary-state.path
echo "PREP DONE"
