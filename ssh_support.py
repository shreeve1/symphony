"""Shared SSH invocation helper for remote bindings (ADR-0012).

Extracted from ``agent_runner._ssh_base_args`` so both the remote agent
adapter and the SSH repo host build SSH command lines identically. Depends
only on the ``RemotePolicy`` shape (``host``/``user``/``identity``); no import
of ``agent_runner`` to avoid a circular dependency.
"""

from __future__ import annotations


def ssh_base_args(remote, *, reverse_port: int | None = None) -> list[str]:
    args = ["ssh", "-o", "BatchMode=yes"]
    if remote.identity:
        args += ["-i", remote.identity]
    if reverse_port is not None:
        args += ["-R", f"{reverse_port}:127.0.0.1:{reverse_port}"]
    args.append(f"{remote.user}@{remote.host}")
    return args
