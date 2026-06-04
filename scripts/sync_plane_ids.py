#!/usr/bin/env python3
"""Regenerate STATE_IDS and LABEL_IDS in plane_cli.py from tracker_contract."""

from __future__ import annotations

import sys
from pathlib import Path

SYMPHONY_DIR = Path(__file__).resolve().parent.parent
PLANE_CLI = SYMPHONY_DIR / "plane_cli.py"

BEGIN_SENTINEL = "# BEGIN GENERATED PLANE IDS"
END_SENTINEL = "# END GENERATED PLANE IDS"

# plane_cli STATE_IDS is keyed by terminal-state command verbs plus the
# `todo` key needed by the schedule/unschedule commands. tracker_contract.state_ids
# is keyed by full PlaneState names.
STATE_KEY_MAP = {
    "done": "Done",
    "review": "In Review",
    "blocked": "Blocked",
    "todo": "Todo",
}


def _load_default_contract():
    if str(SYMPHONY_DIR) not in sys.path:
        sys.path.insert(0, str(SYMPHONY_DIR))
    from tracker_contract import DEFAULT_CONTRACT, PlaneState

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
            raise SystemExit(f"tracker_contract is missing state '{state_name}'") from exc
        state_ids[verb] = uuid

    label_ids = dict(default_contract.label_ids)

    return "\n\n".join(
        [
            BEGIN_SENTINEL
            + "\n# Source: tracker_contract.DEFAULT_CONTRACT"
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
        print("plane_cli.py already in sync with tracker_contract.")
        return 0

    PLANE_CLI.write_text(updated)
    print(f"Rewrote {PLANE_CLI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
