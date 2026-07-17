from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

skill_migration = cast(Any, import_module("skill_migration"))
PodiumBindingScaffoldRequest = skill_migration.PodiumBindingScaffoldRequest
scaffold_podium_binding = skill_migration.scaffold_podium_binding


SKILL_PATH = Path(".claude/skills/symphony-binding-scaffold/SKILL.md")


def test_binding_scaffold_creates_podium_db_row_and_bindings_entry(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    result = scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="demo",
            display_name="Demo",
            repo_path=tmp_path / "repo",
            base_branch="main",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    assert result.binding_name == "demo"
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT name, display_name, archived FROM binding WHERE name = 'demo'"
        ).fetchone()
        settings = connection.execute(
            "SELECT context_compact_threshold_tokens FROM binding_settings WHERE binding_name = 'demo'"
        ).fetchone()
    assert row == ("demo", "Demo", 0)
    assert settings == (16000,)

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    [binding] = raw["bindings"]
    assert binding["name"] == "demo"
    assert binding["tracker"] == "podium"
    assert binding["repo_path"] == str(tmp_path / "repo")
    assert binding["base_branch"] == "main"
    assert (
        binding["plane_project_id"] == "demo"
    )  # transitional config compatibility only
    assert (
        binding["pi_mode"] == "rpc"
    )  # RPC is the default for new pi bindings (ADR-0010)


def test_binding_scaffold_pi_mode_one_shot_and_claude_omits_it(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="legacy",
            repo_path=tmp_path / "repo-a",
            base_branch="main",
            pi_mode="one-shot",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )
    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="cl",
            repo_path=tmp_path / "repo-b",
            base_branch="main",
            default_agent="claude",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    by_name = {b["name"]: b for b in raw["bindings"]}
    assert by_name["legacy"]["pi_mode"] == "one-shot"  # rollback path selectable
    assert "pi_mode" not in by_name["cl"]  # claude bindings carry no pi_mode


def test_binding_scaffold_writes_remote_block(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n",
            repo_path=Path("/home/itadmin/itastack"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="n8n",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    [binding] = raw["bindings"]
    assert binding["remote"] == {"host": "n8n", "user": "itadmin"}
    assert "identity" not in binding["remote"]


def test_solo_remote_binding_gets_no_host_alias(tmp_path: Path) -> None:
    # A remote binding with no sibling on its host needs no alias (ADR-0039);
    # the frontend fallback handles a lone host.
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n",
            repo_path=Path("/home/itadmin/itastack"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="100.95.224.218",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    [binding] = raw["bindings"]
    assert "host_alias" not in binding["remote"]


def test_second_binding_same_host_derives_and_backfills_alias(tmp_path: Path) -> None:
    # The ADR-0039 flow: itastack + dotfiles on one raw-IP host must collapse
    # under one sidebar header. Scaffolding the second binding derives a shared
    # alias and backfills it onto the first.
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n",
            display_name="n8n",
            repo_path=Path("/home/itadmin/itastack"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="100.95.224.218",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )
    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n-dotfiles",
            repo_path=Path("/home/itadmin/dotfiles"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="100.95.224.218",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    by_name = {b["name"]: b for b in raw["bindings"]}
    # Both bindings carry the same lowercase alias derived from the first's
    # display_name.
    assert by_name["n8n"]["remote"]["host_alias"] == "n8n"
    assert by_name["n8n-dotfiles"]["remote"]["host_alias"] == "n8n"
    # SSH target is untouched — still the IP.
    assert by_name["n8n-dotfiles"]["remote"]["host"] == "100.95.224.218"


def test_explicit_host_alias_lowercased_and_backfilled(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n",
            repo_path=Path("/home/itadmin/itastack"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="100.95.224.218",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )
    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n-dotfiles",
            repo_path=Path("/home/itadmin/dotfiles"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="100.95.224.218",
            remote_user="itadmin",
            remote_host_alias="N8N",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    by_name = {b["name"]: b for b in raw["bindings"]}
    assert by_name["n8n"]["remote"]["host_alias"] == "n8n"
    assert by_name["n8n-dotfiles"]["remote"]["host_alias"] == "n8n"


def test_binding_scaffold_remote_requires_rpc_pi_coding(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    base = {
        "name": "bad",
        "repo_path": Path("/home/itadmin/itastack"),
        "base_branch": "main",
        "remote_host": "n8n",
        "remote_user": "itadmin",
    }

    # one-shot rejected for remote (remote parity requires RPC)
    try:
        scaffold_podium_binding(
            PodiumBindingScaffoldRequest(**base, pi_mode="one-shot"),
            db_path=db_path,
            bindings_path=bindings_path,
        )
    except ValueError as exc:
        assert "rpc" in str(exc)
    else:
        raise AssertionError("expected ValueError for remote pi_mode=one-shot")

    # host without user rejected
    try:
        scaffold_podium_binding(
            PodiumBindingScaffoldRequest(
                name="bad2",
                repo_path=Path("/home/itadmin/itastack"),
                base_branch="main",
                pi_mode="rpc",
                remote_host="n8n",
            ),
            db_path=db_path,
            bindings_path=bindings_path,
        )
    except ValueError as exc:
        assert "remote_user" in str(exc)
    else:
        raise AssertionError("expected ValueError for remote_host without remote_user")


def test_append_binding_preserves_existing_formatting_and_comments(
    tmp_path: Path,
) -> None:
    # Seed a hand-written 2-indent bindings.yml with a comment and a blank
    # line between entries -- the byte-level detail that a load/dump/rewrite
    # silently destroys (turning an append into a whole-file diff).
    seed = (
        "# Symphony bindings\n"
        "bindings:\n"
        "  - name: homelab\n"
        "    type: infra\n"
        "    repo_path: /home/james/homelab\n"
        "    base_branch: main\n"
        "\n"
        "  - name: dotfiles\n"
        "    type: coding\n"
        "    repo_path: /home/james/dotfiles\n"
        "    base_branch: main\n"
    )
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(seed, encoding="utf-8")
    db_path = tmp_path / "podium.db"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="agency",
            repo_path=tmp_path / "repo",
            base_branch="main",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    result = bindings_path.read_text(encoding="utf-8")
    # Existing content survives byte-for-byte; only the new block is added.
    assert result.startswith(seed)
    assert "# Symphony bindings" in result  # comment preserved
    assert "  - name: homelab" in result  # 2-space indent preserved
    assert "\n\n  - name: dotfiles" in result  # blank line preserved
    assert result.count("name: homelab") == 1  # no duplication / rewrite
    # New entry appended at the matching indent and parses correctly.
    assert "  - name: agency" in result
    raw = yaml.safe_load(result)
    by_name = {b["name"]: b for b in raw["bindings"]}
    assert by_name["agency"]["repo_path"] == str(tmp_path / "repo")
    assert by_name["agency"]["tracker"] == "podium"
    assert by_name["homelab"]["type"] == "infra"


def test_backfill_host_alias_preserves_comments_and_formatting(
    tmp_path: Path,
) -> None:
    # ADR-0039 backfill must be byte-preserving like the append path: a
    # load/dump rewrite would drop the NetBird sshd caveat comment on the live
    # n8n block and reflow the whole file, tripping restart pre-sanity.
    seed = (
        "# Symphony bindings\n"
        "bindings:\n"
        "  - name: n8n\n"
        "    type: coding\n"
        "    repo_path: /home/itadmin/itastack\n"
        "    base_branch: main\n"
        "    pi_mode: rpc\n"
        "    default_agent: pi\n"
        "    tracker: podium\n"
        "    remote:\n"
        "      host: 100.95.224.218 # bare 'n8n' hits netbird where sshd refuses\n"
        "      user: itadmin\n"
    )
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text(seed, encoding="utf-8")
    db_path = tmp_path / "podium.db"
    # Pre-seed the podium row so the scaffold's DB dupe-guard passes for n8n.
    with skill_migration.connect(db_path) as connection:
        skill_migration._ensure_schema(connection)

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n-dotfiles",
            repo_path=Path("/home/itadmin/dotfiles"),
            base_branch="main",
            pi_mode="rpc",
            remote_host="100.95.224.218",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    result = bindings_path.read_text(encoding="utf-8")
    # The caveat comment survives verbatim; the IP line is untouched.
    assert "# bare 'n8n' hits netbird where sshd refuses" in result
    assert "      host: 100.95.224.218" in result
    assert result.count("name: n8n\n") == 1  # no rewrite/duplication
    raw = yaml.safe_load(result)
    by_name = {b["name"]: b for b in raw["bindings"]}
    # Both siblings now share the derived alias, spliced under remote:.
    assert by_name["n8n"]["remote"]["host_alias"] == "n8n"
    assert by_name["n8n"]["remote"]["host"] == "100.95.224.218"
    assert by_name["n8n-dotfiles"]["remote"]["host_alias"] == "n8n"


def test_binding_scaffold_skill_is_not_plane_coupled() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "No Plane API calls" in text
    assert "plane_adapter" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
