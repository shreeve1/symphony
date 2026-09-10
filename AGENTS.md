# Symphony — Agent Context

## Agent skills

### Issue tracker

GitHub Issues in `shreeve1/symphony` via `gh` CLI for ad-hoc engineering prep; Podium is the production issue surface for dispatch. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles for ad-hoc engineering prep issues: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: read `CONTEXT.md` + `docs/adr/`, then `wiki/index.md` for scheduler internals. See `docs/agents/domain.md`.

## Git Remote

- Remote: `git@github-personal:shreeve1/symphony.git`
- Always use `github-personal` SSH host alias — default `github.com` key authenticates as `shreeve1/SSH` (wrong account). `github-personal` uses `~/.ssh/id_ed25519_github_personal` and authenticates as `shreeve1`.

## Unattended modal handling (claude_runner)

Claude runs unattended (`--permission-mode bypassPermissions`), but bypass does **not** suppress every confirmation modal — `.claude/` edits and the `rm -rf /` / `rm -rf ~` circuit breakers still prompt, and an unanswerable modal used to hang the run and surface as the misleading "Agent timed out". `_poll_claude_until_done` now drives parked modals automatically (`claude_runner.py`):

- **Permission / Yes-No modal → Enter.** Option 1 ("Yes") is pre-selected, so Enter approves and the agent continues. This is a **blanket auto-approve with no carve-out** — it also accepts the `rm -rf /` / `rm -rf ~` circuit breakers (operator decision, 2026-06-19). The unattended agent can therefore execute a destructive command it raised by mistake; the binding sandbox and WORKFLOW.md are the only remaining guardrails.
- **Multi-choice question picker → Escape, wait `MODAL_QUESTION_SETTLE_SECONDS`, then paste "proceed with your recommendations".** This is a fallback for an agent that wrongly opened an interactive picker; the correct path is the `SYMPHONY_QUESTION` park, which completes cleanly without a modal.
- If the same modal pane persists past `MODAL_STUCK_LIMIT` automated interactions (Enter / auto-reply not landing), the run aborts with a clear reason instead of looping.

Log lines: `claude_permission_modal_approved`, `claude_question_modal_autoreplied`, `claude_modal_stuck`. Detection is best-effort regex on the captured pane (`_hit_permission_modal` = Yes/No choices + hint; `_hit_question_modal` = non-Yes/No choices + selection/escape hint).

## LLM Wiki

This project uses `wiki/` as an LLM-maintained knowledge base for Symphony scheduler internals, runbook content, decisions, and operational patterns. Citation style is inline: `[source: path/to/file.md#section]`. **Auto-promotion is enabled** — the agent self-promotes candidates after lint passes; James gate is off.

### Directories

- `wiki/raw/` — immutable source material; read, never rewrite.
- `wiki/raw/sessions/` — curated session captures created by `/wiki-update` when conversation evidence needs citation.
- `wiki/candidates/` — transient holding for generated pages awaiting lint and auto-promotion.
- `wiki/sources/` — promoted source summaries.
- `wiki/entities/` — promoted entity pages (services, bindings, agents, projects).
- `wiki/concepts/` — promoted concept pages (dispatch loop, reconcile lifecycle, etc.).
- `wiki/analyses/` — promoted query outputs and syntheses.
- `wiki/raw/assets/` — source attachments clipped with raw material.
- `wiki/assets/` — generated or wiki-native images and attachments.

### Required Files

- Read `wiki/index.md` first when answering wiki-backed questions.
- Use `wiki/ROUTING.md` after `wiki/index.md` to narrow large searches.
- Append every ingest, query, lint, promotion, and discard to `wiki/log.md`.
- Track important factual claims in `wiki/CLAIMS.md` with inline citations.

### Wiki-First Project Search

For any Symphony-specific question, investigation, design task, bug hunt, or code search that requires project context, check the wiki first.

1. Read `wiki/index.md` before searching broadly.
2. Use `wiki/ROUTING.md` to identify relevant promoted pages, candidates, and claim entries.
3. Read relevant wiki pages and `wiki/CLAIMS.md` entries before using general repository search.
4. If the wiki does not contain enough information, search the codebase, docs (`CONTEXT.md`, `~/homelab/docs/runbooks/automation/symphony.md`), or external sources as needed.
5. When non-wiki search reveals durable project knowledge, propose ingesting the source into `wiki/raw/`, creating a `wiki/candidates/` page (auto-promoted after lint), or updating an existing promoted page with a cited change.
6. If external or codebase search was needed to answer a wiki-backed question, mention the wiki gap and the ingest or update path taken in the final answer.

### Session Update Workflow

Use `/wiki-update` during or after meaningful sessions to capture durable decisions, verified facts, root causes, follow-ups, and reusable context. Create curated raw session captures under `wiki/raw/sessions/` when conversation evidence is needed. Do not archive full transcripts, secrets from `/home/james/symphony-host.env`, private material, or raw pasted user content without explicit approval. New session-derived knowledge transits `wiki/candidates/`, gets linted, then auto-promotes; updates to `wiki/index.md`, `wiki/ROUTING.md`, `wiki/CLAIMS.md`, and `wiki/log.md` are required.

### Maintenance Trigger

The wiki is a standing obligation, not an opt-in step. Before reporting any task complete, run the end-of-session wiki check. This is mandatory, not advisory.

**Exception — Podium slice runs (ADR-0028):** If you are running as a dispatched Podium slice (an issue run), do **not** run `/wiki-update` and do **not** edit any `wiki/` file. Capture your "why" in the issue comment (ADR-0022) only. Per-slice wiki edits collide at land time and cannot dedupe/allocate claim IDs across parallel branches (C-0335). Wiki capture for slice work is a single consolidated, operator-driven `/wiki-update` pass run after a batch of slices lands. This exemption applies to every slice, including a slice running solo. The obligation below applies to interactive sessions, not slice runs.

A task produces durable project knowledge — and therefore requires a `/wiki-update` pass before it is reported done — when it includes any of:

- A decision that sets or reverses project direction, scope, or ownership.
- Accepted or changed terminology, naming, or domain concepts.
- A new or revised architecture, process, or contract that future sessions must honor.
- A verified fact, root cause, or fix that contradicts or supersedes existing wiki knowledge.

End-of-session check, every task:

1. Decide whether the task hit any trigger above.
2. If yes, run `/wiki-update` before reporting completion. If a full pass must be deferred, state the wiki gap and the proposed ingest, candidate, or promotion path in the final answer.
3. If no, state one line in the final answer confirming the wiki check ran and nothing qualified.

Mark superseded knowledge `superseded` in `wiki/CLAIMS.md` with a pointer to the newer claim; never delete it to clean up history. Routine or already-documented work does not trigger a pass.

### Ingest Workflow

1. Place new source under `wiki/raw/` (copy or symlink for in-tree files; preserve original path in citation).
2. Summarize the source with citations to the raw path.
3. Discuss key takeaways with James when the source is substantial, ambiguous, or likely to touch multiple pages.
4. Extract entities, concepts, contradictions, and atomic claims.
5. Create page in `wiki/candidates/`.
6. Run lint checks against the candidate (broken links, citation drift, duplicate concepts).
7. Auto-promote to the appropriate directory (`sources/`, `entities/`, `concepts/`, `analyses/`), set `status: promoted`, update timestamps.
8. Update `wiki/index.md`, `wiki/ROUTING.md`, and `wiki/CLAIMS.md`.
9. Append an entry to `wiki/log.md`.

### Query Workflow

1. Read `wiki/index.md` to identify relevant promoted pages and candidates.
2. Use `wiki/ROUTING.md` to narrow branches when the index is too broad.
3. Read only the relevant promoted pages and claim entries.
4. Answer with inline citations (`[source: wiki/concepts/page.md]` or `[source: wiki/raw/file.md#section]`).
5. If the answer produces durable synthesis, save as `wiki/candidates/<slug>.md`, lint, auto-promote to `wiki/analyses/`.

### Promotion Workflow

Auto-promotion: agent self-promotes after lint. No James gate.

1. Lint the candidate page for citations, confidence, and duplicates.
2. Move it to `sources/`, `entities/`, `concepts/`, or `analyses/`.
3. Set `status: promoted` and update timestamps.
4. Update `index.md`, `ROUTING.md`, `CLAIMS.md`, and `log.md`.

### Discard Workflow

When a candidate is rejected during lint, remove its candidate index row, candidate-only routes, and candidate claim page references before deleting the candidate file. Append a discard entry to `wiki/log.md`.

### Lint Workflow

Check broken wikilinks, orphan pages, duplicate concepts, uncited claims, stale claims, claim content drift against cited sources, contradictions, missing concept pages, data gaps, stale candidate references, and missing index/routing entries. Report findings before making broad changes.
