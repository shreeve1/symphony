# Per-host / per-binding skill catalog, synced at scheduler startup

## Status

accepted (2026-07-05). Outcome of a `/grill-me` pass over issue #254.

## Context

The Podium `preferred_skill` dropdown is fed by a flat, global `skill` table
(`name PRIMARY KEY, description, source`) populated only when an operator
manually runs the `symphony-skills` skill (`python -m web.cli.podium skills
refresh`). That refresh scans only the **scheduler host** (aidev): the operator
dotfiles at `~/.claude/skills` merged with the symphony repo's own
`.claude/skills`. Three consequences fall out:

1. **No auto-sync.** New skills never appear in the UI until the operator
   remembers to run the manual refresh. This surprised the operator ("new
   skills don't show up unless I run symphony-skills").
2. **No remote reach.** The `n8n` binding runs on a different host (`itadmin@n8n`,
   repo `/home/itadmin/itastack`). Its project skills are never scanned, so
   itastack's skills are invisible in Podium.
3. **No scoping.** The table has no host or binding dimension. `/api/skills`
   returns one global list shown identically for every binding, so even if a
   remote host were scanned, itastack's project skills would leak to every
   binding.

The operator's dotfiles (`~/.claude/skills`) are synced across aidev and n8n, so
those host-global skills are legitimately identical on both machines — but each
project repo carries **different** `.claude/skills`. The operator wants the
dropdown for a given binding to reflect exactly the skills reachable on that
binding's host and repo.

## Decision

**Scan skills per host at scheduler startup; resolve/display them per binding.**

- **Scope unit is the binding.** A binding's skill set = its host's global
  `~/.claude/skills` **∪** that binding's own repo `.claude/skills`. Host-global
  skills carry `binding_name = NULL`; repo-local skills carry the owning
  `binding_name`. The `host` column records which machine a row came from.
- **Trigger is scheduler startup**, not dynamic and not manual. `symphony-host`
  already owns the SSH seam and the binding list, so it runs the sync once as it
  boots (which is what a "Symphony restart" restarts). The manual
  `symphony-skills` CLI path is retained as a fallback.
- **Reach is per host.** The local host is scanned directly; remote bindings
  (e.g. n8n) are scanned over the existing `ssh_support` SSH seam (ADR-0012).
  The sync is best-effort: an unreachable host leaves its existing rows intact
  and logs a warning; it never fails the boot.
- **The `issue.preferred_skill → skill(name)` foreign key is dropped.** The same
  skill name now legitimately exists per host/per binding, so `name` can no
  longer be the primary key and cannot back an FK. `skill` gets a surrogate
  `id` primary key with `UNIQUE(name, host, binding_name)`. The `preferred_skill`
  value stays a bare string; the dropdown already constrains the operator's
  choice, so no server-side membership validation is needed (the former
  `_require_known_skill` 422 gate is removed).
- **`/api/skills?binding=<name>`** resolves the union for one binding:
  `binding_name IS NULL AND host = <binding's host>` OR `binding_name = <name>`.
  Both `NewIssueModal` and `IssueFlyout` pass their binding so each dropdown is
  scoped. Called without `binding`, the endpoint returns the full catalog
  (back-compat for the manual/debug path).
- **Refresh is scope-replacing.** Each successfully scanned (host, binding-scope)
  set replaces its own rows; scopes that were not scanned (unreachable host) are
  left untouched. Manual rows (`source = ''`) remain protected from deletion.

## Consequences

- Requires Alembic migration `0015` after `0014_issue_origin`: rebuild `skill`
  with a surrogate key + `UNIQUE(name, host, binding_name)`, and rebuild `issue`
  to drop the `preferred_skill` FK (SQLite cannot drop a constraint in place).
- The dropdown now reflects reality per binding: itastack skills appear only
  under n8n; a repo-local skill on aidev never leaks to sibling aidev bindings;
  synced dotfiles skills appear everywhere.
- Best-effort remote scan means a down remote host degrades to stale-but-present
  rows rather than an empty dropdown or a failed boot.
- Dropping the FK trades a database-level guarantee for UI-level constraint. A
  hand-crafted API call could set an unknown `preferred_skill`; the dispatch
  path already tolerates an unknown skill string (it is passed through to the
  agent `--skill` flag), so the blast radius is a no-op skill load, not a crash.

## Alternatives considered

- **Strict per-host flat list.** One skill set per machine, shared by all
  bindings on that host. Rejected: it cannot express "itastack skills only under
  n8n" — repo-local project skills would leak across every binding on the host,
  which is the exact problem the operator raised.
- **Surrogate-key skill table that preserves the name FK.** Keep a real FK by
  pointing `issue.preferred_skill` at the new surrogate `id`. Rejected as
  over-engineered: it adds join machinery and id-churn on every refresh for a
  guarantee the dropdown already provides.
- **Dynamic per-request scan (SSH on every dropdown open).** Rejected: slow,
  couples the API to remote reachability, and the operator explicitly said it
  "doesn't have to happen dynamically."
