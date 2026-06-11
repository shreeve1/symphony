from __future__ import annotations

import argparse
from importlib import import_module
from pathlib import Path
from typing import Any, cast

_skills = cast(Any, import_module("web.cli.podium_skills"))
DEFAULT_SOURCE = _skills.DEFAULT_SOURCE
refresh_skills = _skills.refresh_skills


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
    return parser


def _skills_refresh(args: argparse.Namespace) -> int:
    for line in refresh_skills(args.source, dry_run=args.dry_run):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
