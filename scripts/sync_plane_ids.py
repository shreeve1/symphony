#!/usr/bin/env python3
"""Regenerate STATE_IDS and LABEL_IDS in plane_cli.py from plane_contract.

plane_cli.py is intentionally a standalone urllib script because it runs
inside the OpenCode agent's environment via PATH injection (see
agent_runner.run_agent). It cannot import homelab_router at runtime, so
its UUID dicts are kept in sync with homelab_router.plane_contract.DEFAULT_CONTRACT
by this generator. Drift is enforced at test time by tests/test_plane_cli.py.

Run from /home/james/plane/symphony:

    python3 scripts/sync_plane_ids.py

Exits 0 on no change, 0 after rewriting, non-zero if the homelab repo
cannot be located or the sentinel block is missing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SYMPHONY_DIR = Path(__file__).resolve().parent.parent
PLANE_CLI = SYMPHONY_DIR / "plane_cli.py"

BEGIN_SENTINEL = "# BEGIN GENERATED PLANE IDS"
END_SENTINEL = "# END GENERATED PLANE IDS"

# plane_cli STATE_IDS is keyed by terminal-state command verbs plus the
# `todo` key needed by the schedule/unschedule commands. plane_contract.state_ids
# is keyed by full PlaneState names.
STATE_KEY_MAP = {
    "done": "Done",
    "review": "In Review",
    "blocked": "Blocked",
    "todo": "Todo",
}


def _resolve_homelab_path() -> Path:
    candidates = []
    env_path = os.environ.get("HOMELAB_REPO_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path("/home/james/homelab"))
    candidates.append(SYMPHONY_DIR.parent.parent / "homelab")
    for cand in candidates:
        contract = cand / "automation/homelab-stack/src/homelab_router/plane_contract.py"
        if contract.is_file():
            return cand
    raise SystemExit(
        "Could not locate homelab repo. Set HOMELAB_REPO_PATH or run from /home/james/plane/symphony."
    )


def _load_default_contract():
    homelab = _resolve_homelab_path()
    src_root = homelab / "automation/homelab-stack/src"
    sys.path.insert(0, str(src_root))
    try:
        from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneState
    finally:
        sys.path.pop(0)
    return DEFAULT_CONTRACT, PlaneState


def _format_dict(name: str, items: dict[str, str]) -> str:
    lines = [f"{name} = {{"]
    for key, value in items.items():
        lines.append(f'    "{key}": "{value}",')
    lines.append("}")
    return "\n".join(lines)


def _build_block(default_contract, plane_state) -> str:
    state_ids = {}
    for verb, state_name in STATE_KEY_MAP.items():
        try:
            uuid = default_contract.state_ids[state_name]
        except KeyError as exc:
            raise SystemExit(f"plane_contract is missing state '{state_name}'") from exc
        state_ids[verb] = uuid

    label_ids = dict(default_contract.label_ids)

    return "\n\n".join(
        [
            BEGIN_SENTINEL
            + "\n# Source: homelab_router.plane_contract.DEFAULT_CONTRACT"
            + "\n# Regenerate with: python3 scripts/sync_plane_ids.py"
            + "\n# Drift is enforced by tests/test_plane_cli.py.",
            _format_dict("STATE_IDS", state_ids),
            _format_dict("LABEL_IDS", label_ids) + "\n" + END_SENTINEL,
        ]
    )


def main() -> int:
    if not PLANE_CLI.is_file():
        raise SystemExit(f"plane_cli.py not found at {PLANE_CLI}")

    default_contract, plane_state = _load_default_contract()
    new_block = _build_block(default_contract, plane_state)

    text = PLANE_CLI.read_text()
    begin = text.find(BEGIN_SENTINEL)
    end = text.find(END_SENTINEL)
    if begin == -1 or end == -1 or end < begin:
        raise SystemExit(
            f"Sentinel block not found in {PLANE_CLI}. "
            f"Expected '{BEGIN_SENTINEL}' ... '{END_SENTINEL}'."
        )
    end += len(END_SENTINEL)

    updated = text[:begin] + new_block + text[end:]
    if updated == text:
        print(f"plane_cli.py already in sync with plane_contract.")
        return 0

    PLANE_CLI.write_text(updated)
    print(f"Rewrote {PLANE_CLI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
