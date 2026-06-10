---
session_date: 2026-06-09
session_type: grill-me brainstorm
topic: Symphony UI — replacing Plane with a native operator console
status: handoff for next grill-me session
---

# UI Brainstorm — Handoff

This document captures the locked decisions from the 2026-06-09 grill-me session on the Symphony UI question, so a fresh session can pick up without re-litigating them. The next session should focus on **app details** (schema, screens, actions, sync model) — not the architecture choice, which is settled.

## Locked decisions

### Architecture choice: Option C — replace Plane with a Symphony-native tracker

The session considered four paths and rejected three:

- **Userscript on Plane** — rejected as a detour. Useful as a 2-day hypothesis test, but James knows what he wants.
- **Fork Plane** — rejected. Plane is Next.js + Django + Postgres + Redis at ~150k LOC, AGPL-3.0 (contamination risk for copied components), and would carry permanent upstream merge burden. The fork's value is the polished rich-text editor, which we can defer.
- **Hybrid (Plane for threads + Symphony for AI state)** — rejected in favor of full ownership. Hybrid was the safer middle path but the user wants tighter integration.
- **Replace Plane (chosen)** — Symphony owns the tracker schema, the data, the lifecycle, and the UI. Plane is retained only as a temporary safety net during migration.

The decision is a partial reversal of **ADR-0002** (which chose to keep Plane and generalize Symphony behind adapter seams). The adapter seams stay — they become the migration tool. The Plane backend itself goes. An ADR-0005 should be drafted once schema and migration model are settled.

### Stack

- **Frontend:** React + Next.js (App Router) + Tailwind + shadcn/ui. TipTap deferred to v2.
- **Backend:** FastAPI + Postgres, inside the existing Symphony repo.
- **Drag-and-drop:** `@dnd-kit` (modern, accessible, performant).
- **Data fetching / WebSocket cache:** TanStack Query.
- **Rich-text (v2):** TipTap on top of ProseMirror.

Rationale:
- Plane is React + Tailwind; UI-pattern lift is direct.
- Kanban drag-drop and rich modals are client-state-heavy, where HTMX hits a wall.
- Bundle size optimization is misplaced concern for a single-user internal tool — bundle is cached after first load.

### Repo layout

Same repo as Symphony. Top-level `web/` directory for the Next.js app. Backend additions sit alongside existing Python modules (`api.py`, `models.py`, etc.) or in a new `api/` subdirectory — to be decided in next session.

### Scope

- **Single-user auth for v1.** Just James. Defer multi-user, permissions, OAuth.
- **Per-project views with a project switcher** (Plane-inspired layout — sidebar with projects, board/list views per project).
- **AI-shaped fields first-class in schema:** model, provider, skill, agent, cost_usd, token counts, verdict, run_state, worktree_path, last_event_at. Exact shape to be designed in next session.
- **Live updates via WebSocket** from Symphony's event stream.

### Migration strategy

- Build side-by-side with Plane. Plane stays up the whole time.
- Add a new `tracker_contract.py` adapter for the Symphony-native tracker.
- Migrate `trading` binding first (smaller, lower risk).
- Migrate `homelab` last, after weeks of dogfooding on `trading`.
- Plane projects archived only after both bindings are migrated and stable.

## Reference material from this session

### OpenAI's Symphony (openai/symphony on GitHub)

The other Symphony — the one James got the original idea from. They hit our exact UI question and chose the opposite path:

- Their Linear integration is **read-only from the orchestrator**. The orchestrator polls; the **agent** mutates Linear via a tool extension (`linear_graphql`).
- **No AI metadata on Linear issues.** AI state (session_id, token counts, codex_pid, turn_count, last_event/timestamp/message) lives in Symphony's own in-memory state.
- **Rich web UI is an explicit non-goal.** Their answer is an optional thin HTTP dashboard (`/` + `/api/v1/*`) showing running sessions, retry queue, token totals, per-issue debug. Linear remains the human's primary control surface.

We chose the opposite: replace the tracker, own the UI. The reasoning is that James is doing something OpenAI explicitly is not — building a personal multi-project agent operations console where the *human* lives, not a headless orchestrator with a debug page.

### Existing Symphony code that informs the build

- `tracker_contract.py` — already a clean Role-based abstraction over Plane. The seam pays off here: write a new adapter for the native tracker, keep the engine unchanged.
- `plane_adapter.py` — current Plane implementation; reference for what the new adapter must replace.
- `scheduler.py`, `agent_runner.py` — current sources of Run-related state. Need to grow event emission for the WebSocket feed.
- `bindings.yml` — defines the current two bindings (`homelab`, `trading`). Each binding's `plane_project_id` will map to a Project in the new tracker.

## Open questions for next session

These are the grilling targets, roughly in dependency order. Schema is foundational and blocks most of the others.

### 1. Naming

What is the new tracker / UI called? Candidates: "Symphony Web," "Conductor," "Podium," "Score," "Stage." Naming affects code organization (`web/`, `api/`, namespaces) and the domain glossary in `CONTEXT.md`.

### 2. Schema (foundational)

- What fields on an Issue? Native columns vs. JSON blob vs. label-style tags?
- AI fields list: model, provider, skill, agent, cost_usd, input_tokens, output_tokens, verdict, run_state, worktree_path, last_event_at, branch_name. Which are first-class columns, which are computed/derived?
- What is a Project in the new tracker vs. Plane's project vs. Symphony's Project Binding? 1:1, or does the new tracker collapse Binding and Project into one entity?
- Relationship between Issue, Run, and Verdict — is Run a table? An event log? Both?
- Comments: native table? Markdown text? Author attribution (human / agent / system)? Structured comments (Symphony-Schedule, SYMPHONY_RESULT) shown differently?
- States and labels: per-project or workspace-global? Editable from UI?
- Hierarchy: sub-issues, parent-child, cycles, modules — what makes it to v1?

### 3. Sync model during dual-running period

- Read/write pattern during migration: one-way Plane → new DB? Bidirectional? Read-from-Plane only?
- What if a human edits an issue in Plane during the migration period?
- Cutover model per binding: atomic switch, or gradual (read native, write both, then stop writing Plane)?

### 4. Screen inventory (Plane-shaped)

- Sidebar with project switcher, board view, list view, issue detail panel, settings, run history, command palette (⌘K)?
- Which Plane views are v1, which v2, which never (cycles? modules? gantt? calendar?)?
- New Symphony-specific screens: Run console, dispatch console, agent metadata view, cost dashboard?

### 5. Action set ("orchestrate" — concretely)

James did not fully answer this in the prior session. The complete checklist to drill:

- File a new issue from the UI
- Change state / labels
- Dispatch a stuck Todo *now*
- Approve an `approval-required` issue
- Kill a running Run
- Requeue a Blocked issue
- Merge / land a completed Run's branch (rpiv-merge from the UI?)
- Edit `bindings.yml` / `WORKFLOW.md` from the UI
- View live agent log / output

The set decides whether the SPA is "viewer with two buttons" or "real control surface" — order-of-magnitude scope difference.

### 6. WebSocket event model

- What events does Symphony emit? Run start/end, state change, verdict, comment added, label change, dispatch queued, dispatch failed?
- Event envelope shape: `{ type, issue_id, timestamp, payload }`?
- Replay / catch-up if SPA reconnects mid-session?
- Per-binding subscriptions or one fat firehose?

### 7. Issue creation flow

- From the SPA: shadcn dialog with title, description, labels, priority?
- From CLI: keep `symphony-binding-smoke` and similar skills?
- Templates per binding (homelab smoke ticket vs. trading smoke)?

### 8. AI metadata UX

- Where does model / skill / cost live on a card — inline badges, sidebar, hover popover, or all three?
- Cost visualization: running total per binding, per Run, per day?
- Verdict feed: last N completed Runs across all bindings, or per-project only?
- Live Run indicator on a card (pulsing, progress bar, agent log tail)?

### 9. Auth

- Session cookie + single password on first connect?
- Tailscale-fronted (since aidev is on a trusted LAN)?
- Defer entirely for v1 (LAN-only, no auth) and add later?

### 10. Deployment

- Process model: extend `symphony-host.service` to also run uvicorn, or new `symphony-web.service`?
- Postgres: new DB on aidev, or use SQLite for v1 to defer infra setup?
- Frontend build: Next.js server in same container, static export, or Vercel-style standalone?
- Where does the WebSocket server live — same uvicorn process as the REST API, or separate?

### 11. Test / dev workflow

- Playwright stories for the frontend? (`dev-stories` skill exists for this)
- Pytest covers backend; how does FE/BE integration get tested?
- Dev loop: `next dev` + `uvicorn --reload` side-by-side; documented in README?

### 12. ADR-0005 draft

Once schema and migration model are settled, draft ADR-0005 documenting:
- The partial reversal of ADR-0002 (Plane retired)
- The reasons (live updates, AI-shaped fields, multi-project console, OpenAI Symphony's split rejected in favor of unified ownership)
- The migration path (adapter swap per binding)
- What was kept from ADR-0002 (the Tracker Adapter seam, the Workflow concept, the Agent Adapter seam)

## How to use this handoff in the next session

1. Read this file first.
2. Read `CONTEXT.md` for the canonical glossary (no new terms have been crystallized in CONTEXT yet — that should happen in the next session as schema decisions name new concepts).
3. Read `docs/adr/0002-generalize-symphony-over-adopting-a-platform.md` — the decision being partially reversed.
4. Start grilling from question 1 (naming) and work down. Schema blocks most of the other questions, so it should be settled early.
5. Update `CONTEXT.md` inline as terms crystallize (Operator Console, AI State, Run Record, etc. — names TBD).
6. Offer ADR-0005 once schema and migration are decided.
