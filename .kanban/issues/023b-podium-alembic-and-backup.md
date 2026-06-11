---
id: 023b
title: Alembic baseline + SQLite backup wiring
status: review
blocked_by: [020]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Two operational hardenings: collapse Alembic history into a clean linear
revision chain, and add `/var/lib/symphony/` to the host backup schedule.

**1. Alembic baseline.**

Every schema change since #012a is squashed into a single linear migration
chain checked in under `web/api/migrations/versions/`. `alembic upgrade
head` against an empty SQLite produces a schema byte-identical (modulo
order) to a runtime-introspected one.

- `alembic check` (or equivalent verify) added to CI pre-commit (or
  documented as the way to validate before merging schema changes).
- A `web/api/migrations/README.md` notes the rule "schema changes ship as
  a new revision, never an edited prior revision."

**2. Backup wiring.**

`/var/lib/symphony/` (the SQLite store + `runs/*.log`) added to the
existing host backup chain. Verify mechanism on the host:
- If `rsnapshot` is installed: add the path to `/etc/rsnapshot.conf`
  under daily/weekly retain blocks. Test with `rsnapshot configtest`.
- If `rsnapshot` is absent: add a small `cron` job that runs
  `sqlite3 /var/lib/symphony/podium.db ".backup /backup/podium-$(date +%F).db"`
  daily and rotates beyond 14 days.

Either path is documented in `web/README.md` under a "Backup" section.
The single-host single-point-of-failure posture is acknowledged
explicitly: no off-host replication, accepted as the single-user posture's
known weakness (per ADR-0005).

Operator-approval moment: editing `/etc/rsnapshot.conf` (or installing a
cron entry) requires James to confirm.

## Acceptance criteria

- [ ] `web/api/migrations/versions/` contains exactly one revision (or a clean linear chain) producing the current schema.
- [ ] `alembic upgrade head` against a fresh in-memory SQLite produces the same table set as the running DB (asserted via `tests/test_alembic_baseline.py`).
- [ ] `web/api/migrations/README.md` exists with the "never edit prior revisions" rule.
- [ ] `/var/lib/symphony/` is captured by `rsnapshot` (verify with `rsnapshot configtest && rsnapshot du`) OR by a documented cron `.backup` job.
- [ ] `web/README.md` has a "Backup" section describing the chosen mechanism, the retention window, and the restore procedure.
- [ ] Restore drill executed once: copy current `podium.db` aside, restore from backup, verify schema + row counts match.

## Verification

```
cd /home/james/symphony && uv run pytest && \
rsnapshot configtest 2>/dev/null || ls -la /backup/podium-*.db 2>/dev/null
```

## Blocked by

- #020 (real run logs need to exist before backup retention windows are meaningful)
