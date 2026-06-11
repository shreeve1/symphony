from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any, cast

main = cast(Any, import_module("web.cli.podium")).main

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SOURCE = REPO_ROOT / "web/api/tests/fixtures/skills"


def _rows(db_path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT name, description, source FROM skill ORDER BY name"
        ).fetchall()


def test_dry_run_command_lists_fixture_skills() -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "web.cli.podium",
            "skills",
            "refresh",
            "--dry-run",
            "--source",
            "web/api/tests/fixtures/skills",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.splitlines() == [
        f"alpha\tAlpha skill from fixture.\t{FIXTURE_SOURCE / 'alpha/SKILL.md'}",
        f"bravo\tBravo skill from fixture.\t{FIXTURE_SOURCE / 'bravo/SKILL.md'}",
        f"charlie\tCharlie skill from fixture.\t{FIXTURE_SOURCE / 'charlie/SKILL.md'}",
    ]


def test_refresh_add_noop_change_and_remove(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    source = tmp_path / "skills"
    shutil.copytree(FIXTURE_SOURCE, source)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    assert main(["skills", "refresh", "--source", str(source)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "+ alpha",
        "+ bravo",
        "+ charlie",
    ]
    assert _rows(db_path) == [
        ("alpha", "Alpha skill from fixture.", str(source / "alpha/SKILL.md")),
        ("bravo", "Bravo skill from fixture.", str(source / "bravo/SKILL.md")),
        ("charlie", "Charlie skill from fixture.", str(source / "charlie/SKILL.md")),
    ]

    assert main(["skills", "refresh", "--source", str(source)]) == 0
    assert capsys.readouterr().out == ""
    assert len(_rows(db_path)) == 3

    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO skill(name, description, source) VALUES (?, ?, ?)",
            [
                ("manual", "Manual hand-seeded skill", ""),
                ("old-seed", "Retired boot seed", "seed"),
            ],
        )
        connection.commit()
    assert main(["skills", "refresh", "--source", str(source)]) == 0
    assert capsys.readouterr().out.splitlines() == ["- old-seed"]
    assert ("manual", "Manual hand-seeded skill", "") in _rows(db_path)

    (source / "bravo/SKILL.md").write_text(
        "---\nname: bravo\ndescription: Bravo skill changed.\n---\n\n# Bravo\n",
        encoding="utf-8",
    )
    os.remove(source / "charlie/SKILL.md")

    assert main(["skills", "refresh", "--source", str(source)]) == 0
    assert capsys.readouterr().out.splitlines() == ["~ bravo", "- charlie"]
    assert _rows(db_path) == [
        ("alpha", "Alpha skill from fixture.", str(source / "alpha/SKILL.md")),
        ("bravo", "Bravo skill changed.", str(source / "bravo/SKILL.md")),
        ("manual", "Manual hand-seeded skill", ""),
    ]
