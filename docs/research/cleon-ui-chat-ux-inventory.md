# cleon-ui chat UX inventory (wayfinder #19)

**Date:** 2026-07-20
**Branch:** `research/cleon-ui-chat-ux-inventory`
**Purpose:** Inventory concrete chat-UX mechanisms in `/home/james/cleon-ui-pi` and `/home/james/cleon-ui-claude` worth carrying into a Podium issue-chat spec. **Design references only** — Podium owns its data model; ignore local architecture as a dependency.

Both repos are vanilla-JS single-page chat clients in front of two distinct agents (Pi Coding Agent vs the Claude Code CLI / SDK). The chat primitives are largely **a shared design ported to two backends**, with several concrete UX deltas worth calling out. All claims below cite the exact file and line in each repo.

Throughout this doc:

- `pi:` → `/home/james/cleon-ui-pi/public/...`
- `claude:` → `/home/james/cleon-ui-claude/public/js/...`

---

## 1. Message-bubble anatomy

### 1.1 Roles

Both variants render three primary message classes plus a tool-output class:

| Role     | CSS class                                  | Notes                                                                                                  |
| -------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| user     | `pi:786-803`, `claude: messages.js:155`    | Right-aligned, neon-purple gradient (`pi:786-803`); text + images in `.message-images` (`pi:2024-2032`, `claude:messages.js:158-167`). |
| assistant| `pi:820-828`, `claude: messages.js:151-154`| Left-aligned, cyan accent border; carries `.message-header` with timestamp + short-id + model badge.    |
| system / error | `pi:2044-2053`, `claude: messages.js:206-216` | Reuses `.message.assistant`, red left border (`border-left: 3px solid var(--error)`). Hidden in code only — no toast variant. |
| tool     | `.message.tool-pill` (see §1.3)            | Distinct bubble hierarchy, collapsible, clusterable.                                                   |

### 1.2 Markdown handling

Both go through `marked.parse()` → `DOMPurify.sanitize()` then post-process code blocks for a copy button (`pi:4234-4271`, `claude:markdown.js:8-45`). Custom Marked `renderer.code` wraps every fenced block in `<div class="code-block-wrapper"><div class="code-block-header">…lang + Copy button…</div><pre><code>…</code></pre></div>` — same DOM, same copy-button delegation (`pi:2985-2989`, `claude:app.js:225-238`). Both pin Marked + DOMPurify + Prism to specific versions (`pi:index.html:216-288`, `claude:index.html:217-229`) — pi with **SRI hashes**, claude without. Spec note: pod spec should keep SRI on CDN deps.

`formatMarkdown()` returns a sanitized HTML string; both clients prefer it inside `setElementHtml()` / `innerHTML` with explicit `pi-lens-ignore` comments documenting `formatMarkdown → DOMPurify` as the trust boundary (`pi:2013`, `claude:messages.js:155,174`).

**Header metadata.** Assistant messages carry a 3-field header built when `timestamp || messageId || model` is present (`pi:1995-2017`, `claude:messages.js:155-171`):

```html
<div class="message-header">
  <span class="message-timestamp">…</span>
  <span class="message-id">· short-uuid-8ch</span>
  <span class="model-badge">model-id</span>
</div>
```

The `.message-id` is click-to-copy via the full UUID (`claude:app.js:241-247`); the spec should preserve this affordance — it is the cheapest debug aid and earns its keep.

### 1.3 Tool-output presentation (the chat's most distinctive bubble)

Tools render as **one bubble per tool call** with the *icon + name + summary* collapsed by default; the full input/output live in `.tool-pill-output`, expanded on click (`pi:2371-2430`, `claude:messages.js:368-419`). Status is `running → success / error`, with the indicator glyph ` ⋯ → ✓ → ✗` and a live duration counter (`pi:2404-2428`, `claude:messages.js:382-410`).

#### Tool pill HTML shape

```html
<div class="message tool-pill running" data-tool-id="…" data-tool="bash">
  <div class="tool-pill-header expanded">
    <div class="tool-pill-top">
      <span class="tool-pill-icon">$</span>
      <span class="tool-pill-name">bash</span>
      <span class="tool-pill-summary">$ npm test…</span>
      <span class="tool-pill-chevron">▾</span>
    </div>
    <span class="tool-pill-status running">⋯</span>
    <span class="tool-pill-duration">0.0s</span>
  </div>
  <div class="tool-pill-output">
    <div class="tool-pill-output-command"><code>…</code></div>
    <pre>…output…</pre>
  </div>
</div>
```

Citations: pi `app.js:2411-2427`, claude `messages.js:392-408`. Same icon map (`getToolIcon`) in `pi:app.js:~4670` and `claude:utils.js:127-141` — keep an extensible map: `Bash→$, Read→R, Write→W, Edit→E, Glob→G, Grep→?, Task→T, TodoWrite→✓`.

#### **Collapsing of long tool output** — the chat's most important UX

Three interesting behaviors, all present in both variants:

1. **Click header → toggle output** (`pi:3042-3054`, `claude:app.js:248-262`). Delegate via `closest('.tool-pill-header')`.
2. **Live reopen on result**: when `tool_result` arrives with non-empty output, **always expand the pill** so the user sees the result (`pi:2487-2496`, `claude:messages.js:454-466`). The spec should call this out — collapsing the *result* too is the most common UX bug in custom chat clients.
3. **Long-output truncation… is missing.** Both variants store the full output in a `<pre>` with no char cap; they rely on max-height + overflow CSS at the container level (`pi:1023-1051`, claude analogous in `style.css`). If Podium's replays push multi-MB tool payloads, the spec should add a per-pill row cap (e.g. 200 lines × 200 chars) with a "show more" affordance — pi's CSS already reserves a `.tool-pill-show-more` style (lines `1018-1021`) but no JS uses it. **Inheritance with a known ceiling.**

#### Auto-clustering consecutive tool calls

When 3+ tool pills arrive back-to-back without an interleaving message, they collapse into one `<div class="tool-cluster">` whose header reads e.g. *"`5 tool calls (3 Bash, 2 Grep) — 3/5 done`"* (`pi:2262-2369`, `claude:messages.js:293-365`). Cluster body is collapsible, summary auto-updates on each result. **CLUSTER_THRESHOLD = 3** in both (`pi:2257`, `claude:messages.js:16`). The spec should make threshold **a server-driven UI knob**, not a hardcoded constant — agents like Hermes that emit 20 grep calls in one burst will overflow this view.

---

## 2. Streaming presentation

### 2.1 Two implementations of the same idea — and one UX choice that actually matters

`StreamingRenderer` exists in both, with **divergent streaming feel**:

| Variant  | File                                          | Mechanism                                                                  | Feel                                |
| -------- | --------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------- |
| **pi**   | `pi:app.js:127-167`                           | One `requestAnimationFrame` per burst of chunks; `element.textContent = buffer` on the rAF tick. | Text appears in lockstep with network. No artificial pacing. ~60Hz ceiling. |
| **claude**| `claude:streaming.js:4-58`                    | `setTimeout` per character, **5 ms/char (~200 chars/s)** capped; `prefers-reduced-motion → 0` skips.  | Typewriter effect. Disabled for `prefers-reduced-motion: reduce`.            |

This is the **single biggest UX delta** between the two reference clients. Both are defensible; Podium should pick one and **gate it on the user-agent accessibility setting** the way claude does (one-liner; `claude:streaming.js:14`). Either feel is fine; mixing them is the bug.

### 2.2 Done signals

Three signals, in order, when a turn finishes:

1. **Network close or `claude-done` WebSocket message** (`pi:1564`, `claude:ws-sse.js:204`). The handler is `finishStreaming(session)`.
2. `finishStreaming` clears `session.streamingRenderer`, finalizes markdown (`formatMarkdown` replaces the raw text), and **removes the `.streaming` class** from the most recent `.message.streaming` element so it stops bleeding the streaming cursor (`pi:1919-1937`, `claude:messages.js:62-72`). All CSS keyframes bound to `.streaming` shut off in one frame.
3. `session.isStreaming = false` + UI controls re-enabled (`chatInput`, `sendBtn`, `modelBtn` / `modeBtn`, `attachBtn` all `.disabled = false`, `abortBtn` hidden) — `pi:1930-1936`, `claude:messages.js:73-78`. **One exception:** pi resets `chatInput.placeholder = "Message..."` (`pi:1933`); claude doesn't.

Both variants also fire `sendNotification("Claude/agent finished", projectName)` **only when `document.hidden`** (`pi:4192-4215`, `claude:notifications.js:18-25`). Spec note: prefer Web Notification API over toasts for "your turn ended while you were elsewhere."

### 2.3 Typing / "thinking" indicator — both variants, identical

A single `.activity-status` row sits between header and session containers:

```
[●] thinking…                       2s
```

CSS defines two animation states (`pi:607-655`, `claude:style.css:678-715`):

- `.activity-indicator.thinking` → neon-cyan pulsing dot (`activity-pulse` 1.5s)
- `.activity-indicator.tool_executing` → neon-purple rotating square (`activity-spin` 1s)

State changes come from a single SSE message — `event.type === 'agent-activity'` — carrying `{state, label, description, elapsed, toolName}` (`pi:1652-1666`, `claude:ws-sse.js:248-262`). When the WebSocket reconnects after a drop, the server emits a `state-snapshot` and a `session-status` (`pi:1368-1418`, `claude:ws-sse.js:109-141`) so the indicator re-syncs without re-streaming text.

**Podium-relevant:** the indicator is its own DOM region (not a chat message), so it survives bubble clearance and is naturally aria-live polite (`index.html` both: `aria-live="polite"` on `#activity-status`).

---

## 3. `ask_user` question-response UX (worth carrying forward verbatim)

Both variants expose **a bubble widget** rather than relying on the chat. The widget is in the message stream (`role: "assistant"`-styled) and is **session-scoped** (driven by `session.pendingQuestion`, which guarantees only one is open at a time per session — `pi:1760-1768`, `claude:ws-sse.js:222-238`).

### 3.1 Widget anatomy (`pi:2507-2572`, `claude:messages.js:480-528`)

```html
<div class="message question-block" data-question-id="…">
  <div class="question-group" data-question-index="0" data-multiple="false">
    <div class="question-header">header text</div>     <!-- short caps label -->
    <div class="question-text">the question</div>
    <div class="question-options">
      <div class="question-option" data-label="…" data-qindex="0">
        <span class="option-label">Label</span>
        <span class="option-desc">Description</span>
      </div>
      <!-- …more options… -->
    </div>
    <div class="question-custom-container">
      <input class="question-custom-input" placeholder="Type your own answer…">
    </div>
  </div>
  <button class="question-submit" disabled>Submit Answer</button>
</div>
```

Key affordances worth keeping in spec:

- **Both selected option(s) and freeform text** are accepted. Clicking an option fills `pendingQuestion.selectedAnswers[qIndex]`; typing in the custom input clears selection for that question and stores the text as the answer (`pi:2675-2693`, `claude:messages.js:572-595`).
- **Single- vs multi-select** is per-question (`data-multiple="true"`) — toggle adds/removes the label from the array (`pi:2637-2673`, `claude:messages.js:546-573`).
- **Submit button is disabled until every question has at least one answer**, even in single-question mode (`pi:2697-2711`, `claude:messages.js:598-617`). When all questions answered, the button enables.
- **Submitted state**: on submit, the block gets `.submitted` class (opacity 0.7, dim border, `pi:1266-1270` and `claude:style.css` analog), the button label flips to "Submitted", option/inputs get `pointer-events: none` / `disabled` (`pi:2715-2748`, `claude:messages.js:620-647`).
- **Cancelled state** (different code path — when the connection to the agent dies mid-question): `.cancelled` class, red border, button label "Cancelled" (`pi:1948-1970`, `claude:messages.js:91-105`).
- **Custom-input placeholder language**: both variants use "Type your own answer…". pi ships a small helper, `getQuestionDisplayParts()` (`pi:public/question-utils.js:1-17`), that **hides the redundant header when `header === question`** — claude inlines this logic (`messages.js:497`).

### 3.2 Answer-send wire format

Answers ride on the same socket as the chat command:

```json
{
  "type": "question-response",
  "sessionId": "…",
  "toolUseId": "…",                 // = the question's id (data.questionId)
  "answers": { "0": ["Label A"], "1": ["freeform text"] }
}
```

Source: `pi:2721-2729`, `claude:messages.js:620-632`. Indexed by question index, not label string. **Spec rule:** the wire format is independent of UI; the server re-validates against its canonical question list.

### 3.3 Plan confirmation — a sibling widget

Claude-CLI emits a separate `plan-confirmation` event (not `question`); the widget is a smaller card with **Approve** and **Reject & Revise** actions plus a freeform feedback input (`pi:2575-2648`, `claude:messages.js:535-588`). Pi variant has the same widget but is rarely triggered because Pi agent's plan mode is implicit. The wire shape:

```json
{ "type": "plan-response", "sessionId": "…", "toolUseId": "…", "approved": true, "feedback": null }
```

Both variants **auto-deny a pending plan confirmation if the user toggles mode mid-confirmation** (`claude:input.js:672-689`; verified absent in pi because pi has no mode toggle). Podium should pick a side: **either lock the mode during pending confirmation, or auto-deny with a toast**. Pi picked "no mode toggle → no problem"; claude picked "auto-deny". Each is a one-line spec.

---

## 4. Composer behavior

### 4.1 Send-while-streaming rules

Both variants block sending while `session.isStreaming` is true at the *DOM* layer (chat-form submit handler bails early — `pi:2840-2845`, `claude:app.js:280-291`) AND at the *state* layer (button disabled + input disabled — `pi:2940-2945`, `claude:messages.js:84-89`). Two-layer guard is the spec rule; if a keyboard-only user hits Enter on a hidden textarea, the disabled input still swallows the key.

**One omission in both:** neither variant queues messages while a turn streams — they drop them silently. Spec should pick: **either queue with a "queued" pill, or refuse and surface a hint** ("wait for the answer, or hit Stop").

### 4.2 Abort button

Square stop icon, hidden by default, exposed only when `session.isStreaming === true` (`pi: index.html:108-115`, `claude: index.html:134-141`). Click handler is one line: `state.ws.send(JSON.stringify({type: "abort", sessionId}))` (`claude:app.js:374-380`). The server replies with `abort-result {success: boolean}` and the matching `session-status` event flips `isStreaming` to false, which `finishStreaming` then handles (`pi:1578-1580`, `claude:ws-sse.js:198-200`). Spec note: the **abort must not orphan an in-flight `.streaming` bubble**; both variants guarantee this in `finishStreaming` (`flushPendingText` merges raw text + applies markdown + drops `.streaming` class — `pi:1853-1855`, `claude:streaming.js:62-78`).

### 4.3 Attachments

Five-file cap (`MAX_ATTACHMENTS = 5`, both `pi:8`, `claude:state.js:1`).
Allowed types: `image/png|jpeg|gif|webp`, `text/plain`, `text/markdown`, `application/pdf`; extensions `.txt .md .pdf .png .jpg .jpeg .gif .webp` (`pi:4420-4445`, `claude:input.js:1296-1321`).
Image attachments inline-render as `<img class="message-image">` in the user bubble (`pi:2023-2032`, `claude:messages.js:163-169`).
**Three entry paths** (file-input, paste, drop-zone) all use the same `processAndAddAttachment` flow (`pi:4480+`, `claude:input.js:1335-1370`). User-perceived behavior is consistent — same preview UI, same `[Image: foo.png]` tag in the text fallback (`formatUserMessageWithAttachments`, `pi:4596-4607`, `claude:input.js:1393-1406`).
Wire format: `{type, name, data (base64 for image | raw text for txt/md | server-extracted for pdf), mediaType}` (`pi:2896-2903`, `claude:input.js:353-359`).

### 4.4 Model picker placement

Both variants: model picker lives in the **header** (left of the stop button), not in the composer. Dropdown is populated from `/api/models` for pi (provider-aware — `pi:868-942`) or hardcoded for claude (`haiku/sonnet/opus` — `claude:index.html:158-167`). The dropdown is **disabled while streaming** in both (`pi:1408 / 1437`, `claude:ws-sse.js:131-140`). The spec should keep it in the header and keep it disabled-while-busy — moving the picker next to the send button collides with attachment UI on mobile.

### 4.5 Slash commands & file mentions (claude-only)

The claude variant has two rich-picker affordances not present in pi:

- **Slash commands** via a `#slash-commands` overlay over the composer (`claude:input.js:186-330`). Score-ranked, arrow-key navigable, Tab/Enter to complete. `/clear`, `/reset`, `/help`, `/tokens`, `/context`, `/model` are local-only handlers; everything else gets forwarded to Claude.
- **File @mentions** via a `#file-mentions` overlay (`claude:input.js:331-444`). Debounced 300ms, populated from `/api/projects/{name}/files/search`.

Podium has its own command system (slash commands already in the issue-composer). **The file-mention picker is the load-bearing UX** — it should be carried into the issue-chat spec, while slash commands are likely a Symphony-level not chat-level concern.

---

## 5. Session-status affordances

### 5.1 Streaming / idle badges

The single `.activity-status` row (see §2.3) is the canonical indicator. It is one row, always in the same place, aria-live polite — the spec should not invent more badges.

Both variants also have **per-session `.hasUnread` + session-tab badge** (`pi: app.js:221`, `claude:sessions.js:282-298`) and a **scroll-to-bottom FAB** with an unread count badge (`pi:index.html:180-189`, `claude:app.js:199-208`). The FAB only shows when the user has scrolled away from bottom; the unread counter clears on scroll-to-bottom or when new content arrives at bottom. This is good — drop it in the spec verbatim.

### 5.2 Eviction and reconnect — divergence between variants

This is where the variants visibly diverge and a spec should pick a side.

| Event                  | pi                                                                   | claude                                            |
| ---------------------- | -------------------------------------------------------------------- | ------------------------------------------------- |
| `session-evicted`      | Triggers `showToast()` with `"<project>" paused…` (`pi:1465-1480`, `5352-5419`) | **Not handled** (passed to generic `handleWsMessage`; would log) |
| `session-closed` (remote tab closed) | Calls `closeSession(index)` to mirror the close (`pi:1451-1463`) | **Not handled** (same gap as above)               |
| WS drop, retry        | Exponential backoff `1s × 2^n` capped at 30s (`pi:1314-1324`)        | Same backoff, identical caps (`claude:ws-sse.js:34-44`) |
| WS reconnect → replay   | Server emits `replay-start` / `replay-end`, client flushes then refills `streamingRenderer` (`pi:1669-1685, 1718-1733`) | Same protocol (`claude:ws-sse.js:265-282`) |
| `state-snapshot` on reconnect | Server re-emits known sessions' statuses; client re-renders buttons + activity (`pi:1368-1418`) | Same (`claude:ws-sse.js:109-139`)               |

**Podium-spec implications:**

1. The pi toast machinery (`showToast`, `dismissToast`, `toast-container`, `style.css:3081-3160`) is a clean, single-file piece of UX plumbing and is currently **missing from the claude variant**. Podium should ship the toast system in the first cut: it's the only way to surface `session-evicted` to the user. Backed by `aria-live="polite"`, auto-dismiss 3s, role `alert` (`pi:5352-5419`).
2. The `session-evicted` and `session-closed` event surface **must be part of the issue-chat spec**, not an afterthought. The server side already has the data; the client just has to wire it up. Two events, ~10 lines of JS each.

### 5.3 Connection-lost UX

Three behaviors both variants share cleanly:

- **Dedup at the wire**: server-sent text-deduplication by `messageId` for completed messages (`pi:1696-1702`, `claude:ws-sse.js:287`).
- **Lazy history load on session resume**: on reconnect, a `watch-session` message tells the server to start streaming the JSONL for that session — the client buffers any chunks that arrive *during* the history-load fetch into `session.watcherBuffer` and flushes on the `cleon:history-loaded` event (`claude:sessions.js:386-394`). Podium already has a JSONL watcher; this is the spec rule for **windowing** the race.
- **Connection lost in `sendMessage`**: explicit `appendSystemMessage("Connection lost. Reconnecting — try again when connected.", session)` (`pi:2907-2909`, `claude:input.js:370-378`). Spec should call this "informational, not destructive" — the message disappears when streaming resumes and `finishStreaming` clears it. (Note: in practice this system-message does **not** auto-clear — both variants carry it as a leftover in the bubble history. Future cleanup.)

---

## 6. Differences that matter for the spec

### 6.1 What both variants already agree on (port verbatim)

- The bubble shape (user / assistant / tool-pill / question-block / plan-confirmation-block).
- The streaming protocol: `text` SSE events carrying incremental `content` + `messageId` + `timestamp` + `model`.
- The commit signal: `claude-done` from the WebSocket channel + state-snapshot reconciliation on reconnect.
- The activity-status row above the chat, with `thinking` and `tool_executing` CSS states.
- The 3-tool-pill auto-clustering with running/done/failed summary line.
- The question-block widget anatomy and wire format.
- The 5-attachment cap, image-only-inline, drop/paste/file-input three-path capture.
- The exponential-backoff WebSocket reconnect (1s, 2s, 4s, 8s, 16s, 30s cap).
- The scroll-to-bottom FAB with unread badge.
- The session-tab `unread` badge.
- The Markdown pipeline: `marked.parse()` → `DOMPurify.sanitize()` → Prism highlight inside `<pre><code>`.

### 6.2 Where they diverge — and what Podium should pick

| Decision                                  | pi                      | claude                   | Podium recommendation                                       |
| ----------------------------------------- | ----------------------- | ------------------------ | ----------------------------------------------------------- |
| Streaming feel                            | rAF-batched, lockstep with network | 5 ms/char typewriter (~200 chars/s) | Pick one. Gate typewriter behind `prefers-reduced-motion: reduce` (claude's approach; trivial to flip on pi). |
| Mode toggle (Default / Plan / Bypass)     | **Absent**              | 3-mode cycle button      | **For Podium, expose this surface in the issue form, not in the chat widget** — issue-chat is a thin surface over an existing run. Sidebar/window is the better home for mode toggle. |
| Toast container                           | `showToast()` (pi-only) | Not present              | Ship the toast system. It's the cleanest path for `session-evicted` / capacity errors / "this run was migrated to the bigger worker." |
| `session-evicted` handling                | Toast                   | Unhandled (silent)       | Spec-mandated: handle and toast. Two events, ~10 LOC. |
| `session-closed` (remote tab) handling    | Close local tab         | Unhandled (silent)       | Spec-mandated: mirror close.                                  |
| Slash-command overlay                     | **Absent**              | Full picker              | Defer to Podium's existing `/command` handling; the chat does not need its own. |
| File @mentions overlay                    | **Absent**              | Full picker              | **Keep** — file-mention is the highest-ROI composer feature. Build it server-side via Podium's existing `files/search` endpoint. |
| SRI-hashes on CDN scripts                 | **Yes**                 | No                       | **Yes.** Defense-in-depth in an XSS-adjacent surface.        |
| `pi-lens-ignore` annotations on DOM-set helpers | Yes, with rationale | Yes, but sparser       | Adopt the pi convention (one comment per innerHTML-set call).|
| Attach-while-streaming                    | Disabled                | Disabled                 | Both right. Spec rule: stay disabled.                        |
| Pinia / state                            | Single global `state` object | Same pattern         | Drop both — use the existing Podium state containers.        |
| Pin anywhere                             | Server-driven via JSONL watcher (`watch-session`) | Same | Spec says: the chat client never reads from disk; the server pushes via the existing Issue bridge. |

### 6.3 Things Podium should **not** copy

- **JSONL-watcher buffers**: pi + claude both rely on a server-side file watcher to deliver live `watcher-text` events. Podium's dispatch model already has its own event bridge; do **not** copy the JSONL-watch path.
- **Per-session `tab` chrome**: the multi-tab sidebar (new-session tab, switcher, eviction) is a UX assumption that makes sense only for "many projects in one app". Podium's Issue page is the right home for switching focus, not a chat sidebar.
- **The `3,234-line monorepo style.css + 5,444-line app.js` shape**: both variants ship one giant stylesheet + one giant JS file. The split into 13 modules in cleon-ui-claude (`messages.js`, `streaming.js`, etc.) is the **clearer** pattern. The Podium issue-chat should follow the claude module split: one module per concern.
- **`session-tab.show-close` mobile pattern** (`claude:app.js:300-310`): long-press a tab on mobile to reveal a close button. Nice on small screens, but only relevant if Podium ships a tab bar inside the issue-chat (it should not).

### 6.4 Suggested scope cuts for the spec

If the spec is too long, drop in this order:

1. Plan-confirmation widget (Claude-only; Pi ignores it). Defer until version 2.
2. Tool-pill auto-clustering (3-threshold fallback). Defer until version 2.
3. File @mentions (high ROI but split work: client-side picker is small; the `/files/search` server endpoint is the heavy lift). Defer if needed.
4. Toast container. Defer if needed — but you will regret it the first time a user loses a 4-hour session to silent eviction.

---

## 7. Files cited (index)

```
pi variant (/home/james/cleon-ui-pi/public)
├── app.js                                 (5,444 lines, monolith)
├── question-utils.js                        (17 lines)
├── index.html                              (391 lines)
├── style.css                            (3,234 lines)
└── server/, docs/, specs/, wiki/             (out of scope for UX inventory)

claude variant (/home/james/cleon-ui-claude/public)
├── app.js                                  (605 lines)
├── js/messages.js                          (870 lines)
├── js/streaming.js                         (117 lines)
├── js/input.js                           (1,516 lines)
├── js/sessions.js                          (555 lines)
├── js/ws-sse.js                            (524 lines)
├── js/markdown.js                          (145 lines)
├── js/state.js                              (95 lines)
├── js/utils.js                             (202 lines)
├── js/notifications.js                      (41 lines)
├── js/tasks-ui.js                          (190 lines)
├── js/files-ui.js                          (670 lines)
├── js/dom.js                               (122 lines)
├── js/auth.js                               (56 lines)
├── sw.js                                    (19 lines)
├── index.html                              (401 lines)
└── style.css                            (3,234 lines)
```

`server/` directories in both projects are out of scope — Podium's runloop is its own concern.

---

## Sources

- `/home/james/cleon-ui-pi/public/{app.js,question-utils.js,index.html,style.css}` — read in full.
- `/home/james/cleon-ui-claude/public/{app.js,index.html,style.css}` and `/home/james/cleon-ui-claude/public/js/{messages.js,streaming.js,input.js,sessions.js,ws-sse.js,markdown.js,state.js,utils.js,notifications.js,tasks-ui.js,dom.js,auth.js}.js` — read in full.
- Cleon-ui conventions described by the operators' CLAUDE.md / AGENTS.md / wiki in each repo (not re-cited here).
