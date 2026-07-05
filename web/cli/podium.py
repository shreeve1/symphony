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
_seed = cast(Any, import_module("web.api.seed"))
hash_password = _auth.hash_password
sync_skills = _skills.sync_skills
create_plan_issues = _issues.create_plan_issues
list_podium_issues = _issues.list_issues
ISSUES_BINDINGS_PATH = _issues.BINDINGS_PATH
BINDINGS_PATH = _seed.BINDINGS_PATH
_load_bindings = _seed._load_bindings
PodiumIssuesError = _issues.PodiumIssuesError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podium")
    subcommands = parser.add_subparsers(dest="command", required=True)

    skills = subcommands.add_parser("skills")
    skill_commands = skills.add_subparsers(dest="skill_command", required=True)

    refresh = skill_commands.add_parser("refresh")
    refresh.add_argument("--dry-run", action="store_true")
    refresh.add_argument(
        "--bindings",
        type=Path,
        default=BINDINGS_PATH,
        help="Path to bindings.yml (hosts + repos to scan).",
    )
    refresh.set_defaults(func=_skills_refresh)

    issues = subcommands.add_parser("issues")
    issue_commands = issues.add_subparsers(dest="issue_command", required=True)

    create = issue_commands.add_parser("create-from-plan")
    create.add_argument("plan", type=Path, help="YAML plan-slice spec to create.")
    create.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Binding repo used to resolve the Podium binding.",
    )
    create.add_argument(
        "--bindings",
        type=Path,
        default=ISSUES_BINDINGS_PATH,
        help="Path to bindings.yml.",
    )
    create.add_argument("--dry-run", action="store_true")
    create.set_defaults(func=_issues_create_from_plan)

    list_cmd = issue_commands.add_parser("list")
    list_cmd.add_argument("--binding", default=None)
    list_cmd.set_defaults(func=_issues_list)

    set_password = subcommands.add_parser("set-password")
    set_password.set_defaults(func=_set_password)
    return parser


def _skills_refresh(args: argparse.Namespace) -> int:
    bindings = _load_bindings(args.bindings)
    for line in sync_skills(bindings, dry_run=args.dry_run):
        print(line)
    return 0


def _issues_create_from_plan(args: argparse.Namespace) -> int:
    try:
        for line in create_plan_issues(
            args.cwd, args.plan, bindings_path=args.bindings, dry_run=args.dry_run
        ):
            print(line)
    except PodiumIssuesError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _issues_list(args: argparse.Namespace) -> int:
    for line in list_podium_issues(args.binding):
        print(line)
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
