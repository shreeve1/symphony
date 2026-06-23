"""Transport seam for the file/tempdir I/O a Claude turn is gated on.

ADR-0012 v2 / Issue #96. ``claude_runner`` drives an interactive tmux/Claude
session and gates completion on files it writes (the prompt) and reads (the
``result``/``done`` markers) inside a temp dir. Those files must live on whichever
host runs the agent. ``ClaudeHost`` is the seam that keeps the runner
host-agnostic for that I/O; ``LocalClaudeHost`` is today's behavior verbatim
(everything on the scheduler host).

This is the remote-Claude host seam: file/tempdir I/O, tmux argv construction,
and cleanup removal are host-owned. Transcript mtime still stays a
``claude_runner`` module function (a test monkeypatches it).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

import ssh_support
from config import RemotePolicy


class ClaudeHost(Protocol):
    """The file/tempdir operations Claude dispatch performs on the agent's host."""

    def write_text(self, path: Path, text: str) -> None:
        """Write ``text`` to ``path`` (the prompt / steer / nudge file)."""
        ...

    def read_text(self, path: Path) -> str:
        """Return the text at ``path``, or ``""`` if it does not exist."""
        ...

    def exists(self, path: Path) -> bool:
        """True when ``path`` exists (the ``done`` / ``result`` marker check)."""
        ...

    def mkdtemp(self, *, prefix: str) -> Path:
        """Create a temp dir for the prompt/result/done files and return it."""
        ...

    def tmux_argv(self, socket_path: Path, *args: str) -> list[str]:
        """Return argv for a tmux command against ``socket_path`` on this host."""
        ...

    @property
    def is_remote(self) -> bool:
        """True when Claude dispatch runs on a remote host."""
        ...

    def rmtree(self, path: Path) -> None:
        """Remove a dispatch temp dir, ignoring missing paths."""
        ...


class LocalClaudeHost:
    """Run Claude dispatch I/O on the scheduler host — today's behavior.

    ``mkdtemp_func`` stays injectable so existing tests drive it; file ops use
    plain ``Path`` so the bytes are identical to the pre-seam runner.
    """

    def __init__(self, mkdtemp_func: Callable[..., str] = tempfile.mkdtemp) -> None:
        self._mkdtemp = mkdtemp_func

    def write_text(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def mkdtemp(self, *, prefix: str) -> Path:
        return Path(self._mkdtemp(prefix=prefix))

    def tmux_argv(self, socket_path: Path, *args: str) -> list[str]:
        return ["tmux", "-S", str(socket_path), *args]

    @property
    def is_remote(self) -> bool:
        return False

    def rmtree(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            with suppress(FileNotFoundError):
                path.unlink()


class SshClaudeHost:
    """Run Claude dispatch file/tempdir I/O on a remote host over SSH.

    ADR-0012 v2 / Issue #96, Step B. Mirrors ``repo_host.SshRepoHost``: every
    operation is ``ssh_support.ssh_base_args(remote)`` + a remote command,
    reusing a single SSH **ControlMaster** connection (the per-second poll loop
    in ``claude_runner`` makes connection reuse load-bearing, not optional).
    File reads/exists never raise — a down host or missing file maps to
    ``""``/``False`` under a bounded timeout, matching ``SshRepoHost``.

    ``tmux_argv`` returns the ssh-wrapped argv that runs ``tmux`` *on the remote*
    (against a remote-side socket). The runner routes tmux command construction
    through this method so transport choice stays behind the host seam.
    """

    def __init__(
        self,
        remote: RemotePolicy,
        *,
        run_func: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        control_path: Path | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.remote = remote
        self._run = run_func
        self._timeout_s = timeout_s
        self._control_path = control_path or (
            Path(tempfile.gettempdir()) / f"symphony-claude-{remote.host}.ctl"
        )

    @property
    def is_remote(self) -> bool:
        return True

    def _ssh_base(self) -> list[str]:
        # ControlMaster opts must precede the user@host that ssh_base_args puts
        # last; insert them rather than append (ssh stops option parsing at the
        # host, so trailing -o would be read as part of the command).
        argv = ssh_support.ssh_base_args(self.remote)
        argv[-1:-1] = [
            "-o",
            "ControlMaster=auto",
            "-o",
            f"ControlPath={self._control_path}",
            "-o",
            "ControlPersist=60s",
        ]
        return argv

    def _ssh(self, remote_command: str) -> list[str]:
        return self._ssh_base() + [remote_command]

    def write_text(self, path: Path, text: str) -> None:
        self._run(
            self._ssh(f"cat > {shlex.quote(str(path))}"),
            input=text,
            capture_output=True,
            text=True,
            check=True,
            timeout=self._timeout_s,
        )

    def read_text(self, path: Path) -> str:
        try:
            result = self._run(
                self._ssh(f"cat {shlex.quote(str(path))} 2>/dev/null"),
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout if result.returncode == 0 else ""

    def exists(self, path: Path) -> bool:
        try:
            result = self._run(
                self._ssh(f"test -e {shlex.quote(str(path))}"),
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def mkdtemp(self, *, prefix: str) -> Path:
        template = shlex.quote(f"/tmp/{prefix}XXXXXXXX")
        result = self._run(
            self._ssh(f"mktemp -d {template}"),
            capture_output=True,
            text=True,
            check=True,
            timeout=self._timeout_s,
        )
        return Path(result.stdout.strip())

    def tmux_argv(self, socket_path: Path, *args: str) -> list[str]:
        # ssh joins the trailing argv with spaces and re-parses it in the remote
        # shell; the socket path, session name, and tmux verbs used by the runner
        # carry no shell metacharacters. ponytail: Step C wires this into
        # claude_runner and validates quoting/timing live against n8n before the
        # remote path is trusted unattended.
        return self._ssh_base() + ["tmux", "-S", str(socket_path), *args]

    def rmtree(self, path: Path) -> None:
        self._run(
            self._ssh(f"rm -rf {shlex.quote(str(path))}"),
            capture_output=True,
            text=True,
            check=False,
            timeout=self._timeout_s,
        )
