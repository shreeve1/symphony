# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Boundary with Podium (read this first)

Symphony's **production** issue surface is **Podium**, which uses its own Role vocabulary (documented in `CONTEXT.md` → "Tracker Contract") — `agent:claude`, `agent:pi`, `approval-required`, `approved`, `scheduled`, and the five issue states (Todo / In Review / Running / Blocked / Done). The Matt Pocock triage labels in the table above are a **separate vocabulary** for `.scratch/` tickets and any non-Podium ad-hoc issue work; they do **not** map onto Podium Roles. Don't apply `needs-triage` etc. to Podium issues, and don't reference Podium Roles through this file.