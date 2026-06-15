# Session Capture: symphony-host NoNewPrivileges Disabled

- Date: 2026-06-15
- Purpose: Capture the operator decision and live configuration change that allows Symphony-dispatched agents to attempt sudo/service operations.
- Scope: Run #33 diagnosis, the privilege-boundary decision, live systemd evidence, and operational risk notes.

## Durable Facts

- Run #33 in the `symphony` binding reported that a Claude agent could not restart `podium-web.service` because it inherited `NoNewPrivileges=yes` from `symphony-host.service`; `sudo systemctl ...` returned "The no new privileges flag is set". Evidence: `/home/james/symphony/runs/33.log`, `podium.db` Run row `id=33`.
- `NoNewPrivileges` is a service-level systemd property on `symphony-host.service`, not a per-binding property. Every agent launched by the scheduler inherits the service's privilege posture. Evidence: `systemctl show symphony-host.service --property=NoNewPrivileges,User,Group,ExecStart,MainPID,Environment --no-pager`.
- The live base unit still declares `NoNewPrivileges=yes`, but the drop-in `/etc/systemd/system/symphony-host.service.d/override.conf` now overrides it with `NoNewPrivileges=no`. Evidence: `systemctl cat symphony-host.service --no-pager`.
- Live verification after the operator-applied override and restart: `MainPID=562675`, `NoNewPrivileges=no`, `ActiveState=active`, `SubState=running`, `ActiveEnterTimestamp=Mon 2026-06-15 00:25:08 UTC`. Evidence: `systemctl show symphony-host.service --property=NoNewPrivileges,ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager`.

## Decisions

- James chose the global option: disable the `NoNewPrivileges` boundary for `symphony-host.service` so Symphony-dispatched agents can attempt sudo-backed service and system changes when sudoers permits. Evidence: current session operator confirmation and the live `NoNewPrivileges=no` verification.
- The change applies globally across all current and future Symphony bindings, including `symphony`, `homelab`, and `trading`; it is not scoped to the self-binding. Evidence: `symphony-host.service` is the single scheduler process that launches agents for all bindings.
- The high-risk blast radius is accepted by the operator. The `symphony` self-binding remains the highest-risk case because it can edit the scheduler repository while also inheriting the broader sudo-capable posture. Evidence: current session discussion and `wiki/entities/binding-symphony.md` risk posture.

## Evidence

- `/home/james/symphony/runs/33.log` — shows the Claude agent's attempted restart was blocked by the no-new-privileges flag.
- `systemctl show symphony-host.service --property=NoNewPrivileges,ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager` — verified the live runtime now has `NoNewPrivileges=no` and is active/running.
- `systemctl cat symphony-host.service --no-pager` — shows base unit `NoNewPrivileges=yes` plus drop-in override `NoNewPrivileges=no`.
- `systemctl show podium-web.service --property=NoNewPrivileges,User,Group,ExecStart,MainPID,ActiveState,SubState --no-pager` — showed `podium-web.service` itself was not the limiting service (`NoNewPrivileges=no` there); the inherited scheduler context was the limiter.

## Exclusions

- No full transcript captured.
- No secrets, credentials, tokens, environment file contents, cookies, or API headers captured.
- No raw user shell prompt content captured beyond the durable decision and command outcome.

## Open Questions And Follow-Ups

- Update any operator runbooks or skill safety wording that still assumes `NoNewPrivileges=yes` blocks agent sudo.
- Consider designing a narrower privileged action gateway later if global sudo-capable agents prove too risky.
