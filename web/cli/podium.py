from __future__ import annotations

import argparse
import getpass
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, cast

_auth = cast(Any, import_module("web.api.auth"))
_skills = cast(Any, import_module("web.cli.podium_skills"))
_issues = cast(Any, import_module("web.cli.podium_issues"))
DEFAULT_SOURCE = _skills.DEFAULT_SOURCE
hash_password = _auth.hash_password
refresh_skills = _skills.refresh_skills
import_kanban_issues = _issues.import_kanban_issues
ISSUES_BINDINGS_PATH = _issues.BINDINGS_PATH
PodiumIssuesError = _issues.PodiumIssuesError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podium")
    subcommands = parser.add_subparsers(dest="command", required=True)

    skills = subcommands.add_parser("skills")
    skill_commands = skills.add_subparsers(dest="skill_command", required=True)

    refresh = skill_commands.add_parser("refresh")
    refresh.add_argument("--dry-run", action="store_true")
    refresh.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Directory scanned recursively for SKILL.md files.",
    )
    refresh.set_defaults(func=_skills_refresh)

    issues = subcommands.add_parser("issues")
    issue_commands = issues.add_subparsers(dest="issue_command", required=True)

    import_kanban = issue_commands.add_parser("import-kanban")
    import_kanban.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Binding repo whose .kanban/issues/ are mirrored into Podium.",
    )
    import_kanban.add_argument(
        "--bindings",
        type=Path,
        default=ISSUES_BINDINGS_PATH,
        help="Path to bindings.yml.",
    )
    import_kanban.add_argument("--dry-run", action="store_true")
    import_kanban.set_defaults(func=_issues_import_kanban)

    set_password = subcommands.add_parser("set-password")
    set_password.set_defaults(func=_set_password)
    return parser


def _skills_refresh(args: argparse.Namespace) -> int:
    for line in refresh_skills(args.source, dry_run=args.dry_run):
        print(line)
    return 0


def _issues_import_kanban(args: argparse.Namespace) -> int:
    try:
        for line in import_kanban_issues(
            args.cwd, bindings_path=args.bindings, dry_run=args.dry_run
        ):
            print(line)
    except PodiumIssuesError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _read_password(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\n")


def _set_password(_args: argparse.Namespace) -> int:
    password = _read_password("Password: ")
    confirm = _read_password("Confirm password: ")
    if password != confirm:
        print("passwords do not match", file=sys.stderr)
        return 1
    if not password:
        print("password cannot be empty", file=sys.stderr)
        return 1
    print(f"PODIUM_PASSWORD_HASH={hash_password(password)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
