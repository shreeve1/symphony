---
name: symphony-plane-recover
description: Plane retirement tool only. Recover or archive legacy Plane projects left from pre-Podium Symphony operations; do not use for Podium bindings.
---

# Symphony Plane Recover

Legacy escape hatch for retiring Plane safely.

## Purpose

Use only for the Plane retirement phase: archive legacy Plane projects or fill missing legacy states before final archive. New bindings use `symphony-binding-scaffold` and Podium instead.

## Safety rules

- Treat every action as a legacy Plane mutation.
- Require typed-slug confirmation at the moment of action.
- Never touch `bindings.yml`; Podium binding ownership belongs to `symphony-binding-scaffold`.
- Never use this skill for new project onboarding.

## Out of scope

- Creating Podium bindings.
- Filing Podium smoke Issues.
- Restarting services.
