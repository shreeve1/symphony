# SMOKE checklist — GitHub ⇄ Podium dispatch bridge

ADR-0042 bridge smoke-test steps. Run in order; each step gates the next.

- [ ] **Sync from GitHub** — press the binding's Sync action; verify `ready-for-agent` issues land in Podium with no duplicate `external_id` rows.
- [ ] **Scheduler dispatch** — confirm `list_candidates` picks up the mirrored issues and the agent slice lands in a fresh worktree (`ralph/run` branch).
- [ ] **FF-land** — review path approves; the local fast-forward merge into the base repo's main succeeds without operator intervention.
- [ ] **Close-back** — on `done`, the bridge closes the linked GitHub issue exactly once (idempotent on re-run).
