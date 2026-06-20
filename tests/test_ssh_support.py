from __future__ import annotations

from config import RemotePolicy
from ssh_support import ssh_base_args


def test_ssh_base_args_base_form() -> None:
    remote = RemotePolicy(host="100.95.224.218", user="itadmin")
    assert ssh_base_args(remote) == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=4",
        "itadmin@100.95.224.218",
    ]


def test_ssh_base_args_identity_appends_flag() -> None:
    remote = RemotePolicy(host="h", user="u", identity="/keys/id_ed25519")
    args = ssh_base_args(remote)
    assert args == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=4",
        "-i",
        "/keys/id_ed25519",
        "u@h",
    ]


def test_ssh_base_args_reverse_port_appends_flag() -> None:
    remote = RemotePolicy(host="h", user="u")
    args = ssh_base_args(remote, reverse_port=8000)
    assert "-R" in args
    assert args[args.index("-R") + 1] == "8000:127.0.0.1:8000"
    assert args[-1] == "u@h"
