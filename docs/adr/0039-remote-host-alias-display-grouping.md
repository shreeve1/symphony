# Remote `host_alias` for sidebar grouping, decoupled from the SSH target

## Status

accepted (2026-07-17). Outcome of a `/grill-with-docs` pass over issue #452.

## Context

Multiple bindings can already share one remote host with zero code collisions —
SSH dispatch (`ssh_support.ssh_base_args`), worktree paths
(`remote_worktree`/`worktree_dir`), and skill-sync host grouping
(`podium_skills._host_label`) are all keyed per-binding or per-real-host, and the
frontend sidebar groups bindings by a `host` field
(`web/frontend/components/Sidebar.tsx`). The only friction onboarding a second
folder on an existing host is the binding `name` uniqueness guard, resolved by
picking a distinct name (e.g. `n8n` → `n8n-dotfiles`).

But the sidebar then splits the two bindings into **two** group headers. Root
cause: the n8n host is reached by its Tailscale **IP** `100.95.224.218` (bare
`n8n` resolves to a NetBird address where sshd refuses, per the `bindings.yml`
comment). `list_bindings()` in `web/api/main.py` deliberately falls back to each
binding's own `display_name` as the group key when the resolved host is a raw IP
(so the operator never sees `100.95.224.218` as a header). Two bindings → two
display names → two headers (`N8N`, `N8N-DOTFILES`) instead of one `N8N` group
with two rows.

The SSH target cannot change (it must stay the IP), so display grouping has to be
decoupled from the SSH transport target.

## Decision

**Add an optional, display-only `remote.host_alias` field; the frontend groups by
it when present. The onboard/scaffold skill auto-detects a shared host and
backfills the alias onto every binding on that host.**

- **`host_alias` is display-only.** It feeds the sidebar group key and nothing
  else. SSH dispatch keeps using `remote.host` (the IP); skill-sync host grouping
  keeps using the real IP; worktree paths and the Podium DB schema are untouched.
  The alias lives only in `bindings.yml` (parsed into `RemotePolicy`).
- **Frontend wiring is minimal.** In `list_bindings()`, when a remote binding has
  `remote.host_alias`, set `binding["host"] = _host_label(host_alias)` and skip
  the IP→`display_name` fallback. The frontend already groups by `host`, so
  `Sidebar.tsx` is unchanged. Header text is the alias, uppercased by existing CSS
  (`N8N`), so the alias is **stored lowercase** (`host_alias: n8n`).
- **Scaffold auto-detects + backfills.** When scaffolding a new remote binding
  whose `remote.host`+`remote.user` matches an existing binding, the skill derives
  a shared alias (reuse the existing binding's `host_alias` if it has one; else
  derive one from the existing binding's `display_name`/host) and writes it to
  **both** the existing and the new binding in `bindings.yml`. This is the only
  path that merges the two current headers in one run.
- **Backwards-compatible.** Absent `host_alias` preserves today's behavior exactly
  (friendly hostname for DNS hosts, `display_name` fallback for raw-IP hosts).

## Consequences

- One new optional `RemotePolicy` field (`config.py`), one write path in the
  scaffold (`skill_migration.py`), one branch in `list_bindings()`
  (`web/api/main.py`), and skill-doc updates (`symphony-binding-scaffold`,
  `symphony-onboard-project`). No migration, no schema change.
- Two bindings on one raw-IP host collapse under one sidebar header once both
  carry the same `host_alias`. The n8n case (`itastack` + `dotfiles`) becomes a
  single `N8N` group.
- The alias is unvalidated for uniqueness against real hosts — two genuinely
  different hosts given the same `host_alias` would merge in the UI. Acceptable:
  it is a display grouping label the operator controls, not a transport target.

## Alternatives considered

- **Infer grouping from the shared SSH IP.** No friendly name is attached to the
  IP anywhere, so the header would read `100.95.224.218` — the exact thing the
  current fallback avoids — unless a label is added anyway. Rejected: still needs
  the alias field.
- **Central IP→label lookup table.** More moving parts (a new config surface plus
  a lookup) for the same result as a per-binding field. Rejected as
  over-engineered.
- **Derive-new-only (alias on the new binding only).** The existing binding stays
  unaliased, so the headers still split until it is hand-edited. Rejected: does
  not fix the reported screenshot in one pass.
- **Make "host" a first-class entity bindings attach to.** Large refactor with no
  functional gain — the sidebar already groups by host; only the label needed
  fixing. Rejected.
