# Podium issue-chat spec

- **Status:** locked (wayfinder map #18, spec ticket #26, 2026-07-21)
- **Destination:** replace Podium's `IssueFlyout` comments view with a chat-session UI (cleon-ui as design reference only), plus a reworked issue/chat-creation flow with a pi/claude agent picker. This spec is **the map's destination** — ready to slice into Podium issues for dispatched build work. The build itself is out of scope here.
- **Provenance:** folded from closed decisions #19, #20, #21, #22, #23, #24, #25, #27, #28, #29 on map #18, plus two patches resolved at spec time (state-visibility, header grammar). Each section cites its source ticket. All load-bearing repo claims were grounded and independently verified (`pi -p`, deepseek-v4-pro) against the working tree on 2026-07-21.

## Standing decisions (from charting)

- Podium **grows** the chat UI; `cleon-ui` (`/home/james/cleon-ui-pi`, `/home/james/cleon-ui-claude`) is a **design reference only** — Podium keeps its own data model and remote-binding support. Nothing is copied verbatim without a decision below.
- **Navigation unchanged** — clicking an issue opens a chat instead of comments; no chat-list surface.
- `comments_md` stays the **baseline source of truth**; storage changes only where a decision below explicitly requires it (one new `run` column, §13).
- The dispatched **engine is unchanged** — RPC dispatch, `SYMPHONY_QUESTION` park, reply→wake→resume, steer channel all stay as-is. Chat is a rendering + contract layer, not an engine change (except the bounded, explicit server work in §13).

## Non-goals (explicit)

- **The build** — slicing and dispatching this spec is post-map Podium work.
- **Navigation / chat-list surfaces** — operator confirmed no navigation change.
- **Wholesale `comments_md` storage replacement** — only the one `run` column in §13 is in scope; no message table, no structured-rows rework (#23 rejected opt-3).
- **Dedicated question widget / answer endpoint** — free-text only (#24).
- **A per-issue chat opt-in flag** — the discussion output contract is binding-level, not per-issue (#28).
- **A full structured transcript viewer for completed runs** — none; `/log` (stdout/stderr) stays a debug fallback (#29 i-a).
- **Token-level streaming** — does not ship; 2 s poll floor stands (#20).

---

## 1. Thread data model — what's in the chat thread [#21]

The chat thread is **`comments_md` + run rows rendered chat-style**. The agent session file is **not** the durable source (one issue spans multiple session files; refeed prompts re-embed `comments_md` so raw transcripts duplicate prompt blobs; remote bindings' session JSONL is unreadable from the web tier — prose-only spool, deleted at run end).

**Per-stream disposition:**

| Stream | Renders as |
|---|---|
| Operator reply / plain comment | operator bubble |
| Operator steer / abort | operator bubble **with `steer`/`abort` badge** |
| Agent completion turn + question-park turn | agent bubble |
| Machine markers (`### Symphony Retry Epoch`, `Symphony-Schedule:`, `**Symphony review passed:**`, retry/stall) | collapsed one-line **system** row |
| Run boundaries (dispatch → verdict/cost/tokens) | inline **system** rows (start + terminal bubbles, §7) |

The **run-history tab is eliminated** — runs live inside the thread.

**Live tail = ephemeral layer, not thread content.** While `run.state = running`, a collapsed "agent working" region is pinned at thread bottom (expandable to the tail view); replaced by the durable terminal bubble at run end. Honors the 2 s poll floor; dodges the remote prose-only/deleted-spool fidelity gap.

**Scroll-back fidelity: turn-level.** Durable history = final agent turns + operator messages + machine markers; tool pills / intermediate deltas are live-only and vanish after run end. **No storage change** for fidelity.

**Engine unchanged.** Question bubble = the park; composer send routes reply-vs-steer (§8).

## 2. Rendering — `comments_md` → bubbles [#23, + grammar patch #26]

**Strategy: write the boundary at write time, split dumbly at read time.** Reliability lives in write code every writer passes through, not in a read-time parser's guess. No new table, no schema change to `comments_md`, no AI-session dependency, no extra agent step.

### 2.1 Header grammar (locked)

Every `comments_md` writer stamps a uniform machine-parseable header:

```
### <role> · <ISO-ts>
```

- **Roles (4 tokens):** `agent` · `operator` · `patrol` · `system`.
- **Timestamp:** ISO-8601 **UTC with `Z`**, seconds precision — e.g. `2026-07-21T22:56:03Z`. The stamp stores ISO; the bubble *displays* a friendly localized time.
- **Split regex (frontend, dumb, zero heuristics):**
  ```
  ^### (agent|operator|patrol|system) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$
  ```

### 2.2 Legacy / pre-existing un-headered blocks (locked)

- **No backfill.** Existing DB rows are **not** rewritten — blob stays source of truth, no destructive migration. Only new writes get stamped.
- Old-format headers (`### Operator Reply (...)`, `Symphony-Schedule:`, `### Symphony Review`, …) don't match the new regex → they and their following prose fall into the legacy bucket.
- Each **maximal run of un-headered content** renders as a single neutral grey **legacy bubble**, **collapsed by default**, no actor attribution, no timestamp. Post-hoc attribution is unknowable; we don't guess agent-vs-operator. Ages out as issues close.

### 2.3 Write-side stamping scope (server, all Python) [#23]

- One shared header format + stamping helper that takes the **role** as a parameter (the server already classifies the block kind at each write site — `completion_body`, `question_body`, `close_body`, `schedule_body`).
- **Stamp the in-process scheduler `add_comment` path** (the dominant header-less writer; ~17 sites) with **role = `agent`** for agent turns, **`patrol`** for patrol-originated comments. Patrols are in-process — they call `tracker.add_comment`, not any HTTP route.
- **Stamp the HTTP `/api/issues/{id}/comment` endpoint** with **`operator` unconditionally** — it is the web-UI operator path; the body shape (`ReplyCreate`, `extra="forbid"`, `main.py:720–728`) accepts no author/role field. The server wraps the operator's verbatim body with an attribution header. This lightly bends ADR-0017's "verbatim" wording (it adds an attribution header, not a reopen effect); the operator still owns the body content — only the wrapper changes.
- **Normalize the already-stamping writers** onto the one grammar: `/reply` (`operator`), `/steer` (`operator` + badge), `### Symphony AI Summary` (`system`), `### Symphony Review` (`system`), `Symphony-Schedule:` marker (`system`), `### Symphony Retry Epoch` (`system`).
- The agent itself emits **only prose** — `_capture_natural_turn` strips every `SYMPHONY_` marker before writing. The target-repo AI session is untouched.
- Blob stays the single source of truth — the header is just markdown, so all 11 read/write paths and the prompt-renderer keep working.
- The `### role · ts` headers **intentionally** flow into the agent's re-fed prompt context (the `prompt-renderer` re-embeds `comments_md`) — they provide clean role attribution in the agent's own history and are **not** stripped. The agent itself never emits SYMPHONY_ markers (`_capture_natural_turn` strips them), so the agent won't generate role headers — only server write sites stamp them.

## 3. Visual contract — Variant B (Slack-style full-width blocks) [#27, + state-visibility patch #26]

The thread renders as **full-width block rows**, not left/right chat bubbles: each turn is an **avatar + colored role-name + timestamp header** above the body. Denser and log-like; keeps the chat metaphor readable at Symphony's high system-row density while staying familiar.

| Element | Treatment |
|---|---|
| Role color | **agent** blue · **operator** green · **patrol** amber · **system** neutral grey · **legacy** neutral grey |
| Collapsed system rows | faint full-width divider + caret, **collapsed by default** (expandable) |
| Legacy bubbles | **collapsed by default** (§2.2) |
| Live-tail region | inline collapsible "agent working" row pinned at thread bottom (§1 ephemeral layer) |
| Mode pill | **in the composer**, always-visible (§8) |

### 3.1 State visibility (locked)

- A **topbar chip** on the flyout carries `state · sublabel`, always visible. Sublabel vocabulary:
  - `todo` → **queued**
  - `running` → **agent working**
  - `in_review` → **your turn** (the actionable state; pairs with the composer pill)
  - `blocked` → **blocked**
  - `done` → **done**
  - fresh-created `todo` (§10) → **say something**, composer auto-focused
- Run-level state rides the **inline run system rows** (start + terminal bubble, §7) — the last run's verdict also reads in-thread.

The throwaway reference mock stays on disk at `web/frontend/prototype/chat-mock.html` (not routed by Next).

## 4. Run-row merge & the two system bubbles per run [#29 Q2]

Client interleaves run rows into the comment timeline by timestamp. The run row already carries every column a bubble needs (`id`, `agent`, `model`, `skill_invoked`, `state`, `verdict`, `summary`, `exit_code`, `started_at`, `ended_at`); the frontend synthesizes the header, **server stamps nothing new on run rows** (run rows are a structured source, distinct from the `comments_md` prose §2 stamps).

**Two system bubbles per run** (the minimum that stays honest):

- **Start** @ `started_at` — "Run #N started · agent · model · skill"
- **Terminal** @ `ended_at` — verdict + summary, from `state`/`verdict`/`summary`/`exit_code`:
  `parked-for-review` / `completed ✓` / `blocked` / `failed (exit N)` / `retry`

While running (no `ended_at`): only the start bubble + the ephemeral live-tail region beneath. `verdict=review` on the terminal bubble is the **"your turn" handback** (#24); its visual emphasis is the §3 treatment.

Nothing durable lands in `comments_md` mid-run (the review-epoch marker is written pre-`STATE_RUNNING` at `tick.py:450`; agent prose lands only at verdict transitions) → a run occupies a clean `[started_at, ended_at]` interval with only ephemeral tail between.

**Interleave ordering** — stable sort by `timestamp`; on collision (e.g. review-epoch marker vs run start at `started_at`), order: `comment_bubble` < `run_start_bubble` < `run_terminal_bubble`. Full tie-breaker: `(ts, kind_rank, id)` for determinism.

## 5. Live tail + robust run-scoped in-flight catch-up [#29 Q3 AUTHORITATIVE FINAL]

> This is the corrected, verified contract — three earlier #29 drafts had errors (each caught by independent review + re-grounded in code + independently verified). Encode only this version.

### 5.1 Why the existing event is insufficient (all verified)

- `run.tail` today is `{type, issue_id, lines}` — **no `run_id`, no cursor, no source identity** (`main.py:316–322`).
- `WebSocketHub.stream()` gives each subscriber a **fresh `Queue(maxsize=100)`, no backlog**; full queues are dropped (`main.py:184–196`); the tailer's first-encounter replay is once-per-API-process (keyed on `_state[issue_id]`), not per-client; page reload resets client `tailEvents`; reconnect loses the disconnect gap → **no catch-up for late-join/reconnect/reload**.
- Common coding issues resume with `session_generation=0` (`scheduler/__init__.py:246–253`) → `derive_session_id(issue_id, 0)` is stable (`session_continuity.py`) → resumed runs **share one session JSONL** → a naive full-file read leaks prior-run lines under the new `run_id`.
- Remote `tail_spool_path(run_id)` is `unlink`ed at cleanup (`agent_runner.py:839–840`); `/api/runs/{id}/log` is the agent **stdout/stderr** capture (`run_records.py:50–54`), not the transcript.

### 5.2 The robust run-scoped protocol (the build)

**Persist per Run before sending the prompt:** session-file start byte-offset (`run.agent_session_start_offset`) **and** the opaque `source_id` (`agent_session_id` + inode) — **both new columns, written at dispatch** so rotation is observable to clients. Local resumed run → start-offset = file size at dispatch (scopes within the shared file); remote/fresh → 0.

**`run.tail` event becomes:**
```
{type, issue_id, run_id, source_id, from_cursor, cursor, lines, line_cursors}
```
- `run_id` = `row["run_id"]` — **hoist to the top of `_poll_running`'s loop** (today assigned only in the remote branch, `main.py:308–321`; the SQL already selects it for all rows). A naive dict-key add `NameError`s on local bindings.
- `[from_cursor, cursor)` = byte range of `lines`; `line_cursors[i]` = end-offset of `lines[i]`.
- **Emit only complete newline-terminated records; retain the incomplete suffix without advancing the cursor** (fixes the partial-line case). `lines: string[]` kept for compat.

**`GET /api/runs/{id}/tail`** — **active-run only**. Gate predicate: `run.state != 'running'` → 404 (remote spool is unlinked at cleanup `agent_runner.py:839–840`; the local file is per-issue, so a completed-run read is ambiguous — return 404, not 200). Returns:
```
{run_id, source_id, from_cursor: agent_session_start_offset, cursor: current_size, lines, line_cursors}
```
reading `[start_offset, current_size)` via the existing `_read_jsonl_lines` (same complete-record rule).

**Client catch-up flow** (on flyout-open for a running issue, and on reconnect):
1. subscribe to ws, buffer incoming `run.tail` by `(run_id, source_id)`;
2. `GET /api/runs/{active_run_id}/tail` → snapshot;
3. render snapshot;
4. drop buffered/future lines whose `line_cursors[i] ≤ snapshot.cursor` (covered), append the rest.

Result: seamless session-so-far + live appends, run-scoped, no leakage/dupes/gaps, rotation-safe. On `source_id` change → reset + refetch.

### 5.3 Completed runs (i-a, locked)

`/tail` is active-only. Completed runs render from the durable record: **terminal bubble + `summary` + the natural-turn prose captured in `comments_md`**. `/api/runs/{id}/log` (stdout/stderr) is a low-fidelity debug fallback only — **not** the transcript. **No chat affordance to browse a completed run's full transcript.**

## 6. Live-tail rendering fidelity [#19, #20]

`lines` format: **JSONL for local bindings** (parse to agent-text deltas + collapsed tool pills) / **prose for remote bindings** (RPC spool). 2 s poll floor; the publisher drops on overflow — fine for turn-level, unsafe for token-level.

**Parse contract for local pi JSONL** — `lines` are raw session-JSONL events from pi's session file (`_read_jsonl_lines` splits on `\n`). The builder must either (a) confirm `#19`'s tool-pill/delta anatomy maps directly to pi's session event vocabulary (text deltas, tool_use, tool_result, …), or (b) implement a parse step mapping pi event types → `#19`'s pill/delta shapes. Pin the pi JSONL event vocabulary — or flag it as an explicit F3 discovery task. This is the one place a builder could get quietly stuck.

- **Tool pill** — one bubble per tool call: icon + name + summary collapsed by default, full input/output in `.tool-pill-output` expanded on click; status `⋯ → ✓ → ✗` with a live duration counter. Extensible icon map (`Bash→$`, `Read→R`, `Write→W`, `Edit→E`, `Glob→G`, `Grep→?`, `Task→T`, `TodoWrite→✓`).
- **Long output** — add a per-pill row cap (e.g. 200 lines × 200 chars) with "show more" (cleon-ui reserves the style but wires no JS — a known ceiling to add).
- **Auto-clustering** — 3+ consecutive tool pills collapse into one cluster header ("`5 tool calls (3 Bash, 2 Grep) — 3/5 done`"); make the threshold a **server-driven UI knob**, not a hardcoded constant (Hermes-class bursts overflow a fixed value).
- **Streaming feel** — pick one: rAF-batched lockstep OR 5 ms/char typewriter. **Gate the typewriter behind `prefers-reduced-motion: reduce`** (don't mix).
- **Activity-status row** — a single DOM region above the chat (not a message): `thinking` (cyan pulse) / `tool_executing` (purple spin), `aria-live="polite"`.
- **Markdown pipeline** — `marked.parse()` → `DOMPurify.sanitize()` → Prism; keep **SRI hashes** on CDN deps; one `pi-lens-ignore` comment per `innerHTML`-set call.
- **Done signal** — on turn finish, clear `.streaming` class + finalize markdown; fire a Web Notification **only when `document.hidden`**.

**Don't copy from cleon-ui:** the JSONL-watcher path (Podium has its own event bridge), the per-session tab sidebar, and the monolith `style.css`/`app.js` shape — follow cleon-ui-claude's **one-module-per-concern** split.

**Scope-cut order if needed:** (1) plan-confirmation widget, (2) tool-pill auto-clustering, (3) file @mentions, (4) toast container (you will regret cutting this — silent eviction loses sessions).

## 7. Composer — one auto-routing box [#22, + #25 fresh-todo]

One composer auto-routes by the issue's current run state (collapses today's separate `ReplyComposer` + `SteerComposer`). No mode-picker.

| Issue state | Send routes to | Endpoint | Side effect |
|---|---|---|---|
| Parked (`in_review`/`blocked`/`done`) | **reply** | `POST /api/issues/{id}/reply` | append + flip `todo` → **re-dispatches agent** |
| Scheduled-hold (`todo` + `scheduled_for`) | **comment** | `POST /api/issues/{id}/comment` | append-only, no re-dispatch |
| Live, steerable (pi `pi_mode=rpc` / claude `claude_persist`) | **steer** | `POST /api/issues/{id}/steer {action:"steer"}` | inject mid-run, no state change |
| Live, **non-steerable** (one-shot pi / non-persist claude) | **comment** | `POST /api/issues/{id}/comment` | append-only; agent sees it at next park |
| Fresh-todo (just created, §10) | **comment** | `POST /api/issues/{id}/comment` | append-only seed |

The last two comment rows are **new routing** — today the composer *disables* for those states (`IssueFlyout.tsx:635–647`); only `scheduled-hold → comment` is wired. Endpoints exist; the routing logic is the new work.

**Mode pill** — medium-loudness, on the send button, always visible, naming mode + consequence: `Reply · re-dispatches` / `Steer · live` / `Comment · note` / `Comment · agent sees it next park` / `Comment · seed`. (Rejected: quiet placeholder-only — operators tune it out; confirm-on-reply — fights the chat idiom.)

**Abort button** — distinct, visible **only on steerable live runs**. Abort rides the *same* `steer_issue` RPC gate as steer (`POST /api/issues/{id}/steer {action:"abort"}`); there is no stop path for non-steerable runs. "Stop-and-redispatch" is **two honest steps**: Abort → run stops → issue parks → next send auto-routes to reply → re-dispatch. Live steer is retained for capable runs.

**Steerable detection (client):** reuse the existing `canSteer` derivation in `IssueFlyout.tsx` (`SteerComposer`, line 762): `liveRun && ((latestRunAgent === 'pi' && bindingPiMode === 'rpc') || (latestRunAgent === 'claude' && bindingClaudePersist === true))`, where `liveRun = issue.state === 'running' && latest_run_state === 'running' && latest_run_id != null`. `bindingPiMode` and `bindingClaudePersist` are already exposed via `GET /api/bindings` (`main.py:951–952`); no new client-side signal needed.

## 8. Agent questions — free-text, "your turn" [#24]

The park protocol is **prose only** (`SYMPHONY_QUESTION_BEGIN … <question> … END` captures one free-text blob; no options/multi-select grammar exists). **Decision: free-text only, no first-class question widget, no protocol change.**

- A parked question renders as the normal agent bubble under §2's split, in the shared **"your turn"** review treatment. A question-park and a plain `SYMPHONY_RESULT: review` completion land at the *identical* structured state (`state=in_review, latest_verdict=review`); no persisted field distinguishes them — and none is added.
- Answering = **reply** (appends + flips `in_review→todo` → re-dispatch). No `/question` or `/answer` endpoint.
- Answering reflects the real transition: reply posts as a user bubble, the "your turn" affordance clears, state flips `todo→running`, and §1's ephemeral live-tail region reappears as the run wakes.

**Spec must NOT describe** a dedicated question widget, question-only styling, or an answer endpoint.

## 9. Chat-mode output contract (coding bindings) [#28]

Coding bindings get a new **discussion contract** modeling the dispatched run as a CLI-style conversation. **Infra bindings keep `OUTPUT_CONTRACT` unchanged. Scheduler/engine untouched** — renderer-side contract selection only.

- **Trigger:** `binding_type == "coding"`, selected inside `render_prompt` (which already receives `binding_type`). No new flag/column/per-issue opt-in. Coding: `symphony`, `dotfiles`, `n8n`, `trading`, `ai-web-chat`, …; infra: `homelab`.
- **Rationale:** coding-binding issues are conversational (skill → follow-ups → another skill); infra-binding issues are ticket-shaped runbook execution. Commit/test discipline rides the **skill body** (the skill directive at `prompt_renderer.py:351` only says "invoke the skill").
- **Scope of selection:** the discussion contract applies to **both full renders and resume deltas** — `prompt_renderer.py:447` (resume) and `:465` (full). Selection happens inside `render_prompt`, which both code paths invoke.

**Contract text shape (discussion variant) — turn-taking, not build-completion:**
- Respond naturally to the latest operator turn.
- Invoke any skill you're handed (`preferred_skill`, per-dispatch) and follow it.
- Commit changes you make during a turn (commit-as-you-go) — not "before your final verdict."
- Stop when the turn is said — that yields back to the operator.
- Emit a terminal outcome **only** when a skill-driven turn completes work; otherwise just stop.

**Markers:**
- `SYMPHONY_RESULT` / `SYMPHONY_SCHEDULE` — **available but not mandated.** A bare conversational turn emits no marker → `agent-clean-review` → parks to **In Review** → operator replies → resume (verified: `scheduler/__init__.py:1591,1598`). Markers emit only on skill-driven completion → feed the existing review→land→close loop (unchanged; coding can't `auto_close_on_verified`, infra-only per `config.py:565`).
- `SYMPHONY_QUESTION` — **dropped entirely** for coding/chat. Asking = type the question in prose and stop → parks to In Review → operator answers in the composer (same "your turn" state as #24). Infra keeps it verbatim; the engine's marker parser stays in place, just uninvoked by coding agents.

## 10. Issue/chat creation rework [#25]

- **Agent picker → A1.** The create form leads with a **two-up segmented control: pi | claude** at the top — agent is the primary fork, not one of six peer metadata fields. The **model picker collapses to models valid for the chosen agent** (the agent-aware preselect already exists). Skill / effort / base stay secondary; description stays the body input.
  - `preferred_agent` semantics are **correct as-is**: persists to the row, `tracker_podium._row_to_issue` synthesizes `agent:<preferred_agent>` into labels at read time, dispatch honors it via `binding.resolve_agent`. No dispatch-gap fix. (Carrier is a synthesized label, not a column — only relevant if Podium is ever swapped for a tracker without that synthesis step.)
- **Description role → B2.** Description renders as a **pinned chat-native header** atop the thread — evolving the current muted-Markdown block (`IssueFlyout.tsx:1275–1279`) into a top-of-scroll issue card. `description` stays the canonical editable column; `comments_md` stays append-only; **no seed block** written into `comments_md`.
- **Post-create transition → C1.** On create success, close the modal and **auto-open the chat flyout with the composer focused**. Sequence the auto-open **after `finishIssue` resolves** (the two-stage attachment flow must settle), not on bare create success. A freshly-created `todo` is the **fresh-todo → comment/seed** composer case (§7).

## 11. Integration contract — read shape & write paths [#29 Q1, Q4]

**Read = reuse + client-side merge.** `GET /api/issues/{id}` (full row incl. raw `comments_md`) + `GET /api/issues/{id}/runs`; client merges + interleaves by timestamp. Both already in react-query, refreshed by existing `issue.updated` / `run.updated` ws events. **No `/thread` endpoint.**

**Write = five routing cases + abort onto existing endpoints (§7); no new write endpoint.**

## 12. Backend changes (consolidated, bounded)

1. **`comments_md` write-side header stamping [#23]** — shared helper (role param) + stamp the scheduler `add_comment` and API `/comment` paths + normalize `/reply`, `/steer`, patrol, AI Summary, Review, schedule marker onto the §2.1 grammar. No schema change.
2. **Discussion output contract selection [#28]** — renderer-side: when `binding_type == "coding"`, select the discussion contract; infra keeps `OUTPUT_CONTRACT`. Engine/marker-parser unchanged.
3. **`run.tail` protocol [#29]** — add `run_id`, `source_id`, `from_cursor`, `cursor`, `line_cursors`; hoist `run_id` to the `_poll_running` loop top; emit complete records only.
4. **New `run` column `agent_session_start_offset` (+ `source_id`) [#29]** — populated at dispatch. (The only schema addition in the whole spec.)
5. **New `GET /api/runs/{id}/tail` [#29]** — active-run only; returns `{run_id, source_id, from_cursor, cursor, lines, line_cursors}`.

Everything else is frontend.

## 13. Frontend changes (consolidated)

1. **`IssueFlyout`** — replace the single raw `<Markdown source={comments_md}/>` render with a client-side split-on-header → per-role bubble render (#23, §2).
2. **Client merge** — interleave `GET /api/issues/{id}` + `/runs` by timestamp; synthesize 2 run bubbles/run (#29 Q2, §4).
3. **Visual** — Variant B full-width blocks, role colors, collapsed system + legacy rows, ephemeral live-tail region, topbar state chip, composer mode pill (#27, §3).
4. **Composer** — single auto-routing box, 5 cases + abort, mode pill, conditional abort button (#22 + #25, §7).
5. **Live-tail consumer** — new consumer of `run.tail` (filter `issue_id`+`run_id`), catch-up flow via `GET /api/runs/{id}/tail` (#29 Q3, §5); rendering fidelity per §6.
6. **Creation** — `NewIssueModal` two-up pi|claude picker; description pinned header; auto-open flyout + focus composer after attachment settle (#25, §10).
7. **Agent-question "your turn" treatment** — folds into the §3 state chip + §4 terminal bubble; no separate widget (#24, §8).

## 14. Slice guide (for Podium dispatch)

Suggested vertical slices, in dependency order (a slicer / `to-tickets` pass refines):

1. **B1 — `comments_md` header stamping [#23]** (server-only, no UI). Foundational; unblocks all rendering.
2. **B2 — discussion output contract [#28]** (renderer-side). Independent of B1.
3. **B3 — live-tail protocol [#29]**: `run.tail` fields + `agent_session_start_offset` + `GET /api/runs/{id}/tail` (server). Unblocks the live-tail consumer.
4. **F1 — bubble rendering + Variant B visual + client merge + 2 run bubbles [#23,#27,#29 Q1/Q2, §2–4]**. Depends on B1.
5. **F2 — auto-routing composer + mode pill + abort [#22,#25, §7]**. (Fresh-todo case included.)
6. **F3 — live-tail consumer + catch-up flow [#29 Q3, §5–6]** (includes pinning the local-pi session-JSONL parse contract — the one piece of the spec not fully pinned; see §6). Depends on B3.
7. **F4 — creation rework [#25, §10]**. Independent.
8. **F5 — agent-question "your turn" treatment [#24, §8]** — small; folds into F1/F2.

## 15. Builder reading list

A builder picking up the slices in §14 should start here:

- `wiki/concepts/operator-reply.md` — `/reply` + ADR-0017 `/comment` primitive (reopen effects, append-only; the rules the composer routing sits on).
- `wiki/concepts/session-resume-continuity.md` — `session_generation`, `derive_session_id`, the shared-session-on-resume behavior that drives §5's catch-up rationale.
- `wiki/concepts/podium-tracker.md` — schema/state enums, `comments_md` storage, `blocked_by`/locks.
- `wiki/concepts/prompt-renderer.md` — full render vs resume delta code paths (the §9 contract selection hook point).

Plus the inline research: `docs/research/cleon-ui-chat-ux-inventory.md` (#19, on `main`) and `docs/research/run-tail-capability-matrix.md` (#20, on branch `research/run-tail-capability-matrix-20`).

## Decision provenance

| § | Ticket(s) |
|---|---|
| 1 | #21 |
| 2 | #23 + grammar patch (#26) |
| 3 | #27 + state-visibility patch (#26) |
| 4 | #29 Q2 |
| 5 | #29 Q3 (AUTHORITATIVE FINAL) |
| 6 | #19, #20 |
| 7 | #22, #25 |
| 8 | #24 |
| 9 | #28 |
| 10 | #25 |
| 11 | #29 Q1, Q4 |
| 12–13 | consolidated from above |
| Research refs | #19 (`docs/research/cleon-ui-chat-ux-inventory.md`), #20 (`docs/research/run-tail-capability-matrix.md`, branch `research/run-tail-capability-matrix-20`) |
