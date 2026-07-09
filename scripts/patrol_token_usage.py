#!/usr/bin/env python3
"""Total up token/context spend across patrol runs (issue #343).

Passive observability for the homelab infra binding: sums the per-run usage
now harvested from pi RPC ``message_end`` events (input/output/cache-read
tokens + computed cost) so you can see whether patrol dispatch — in particular
the re-fed comment history — is wasting money.

The cache-read share is the tell: a large re-fed history that is cache-hit is
nearly free, so a high cache-read fraction means the re-feed is cheap, while a
low one on a fat prompt means real spend.

Usage:
    uv run python scripts/patrol_token_usage.py [--days N] [--binding NAME]
                                                 [--limit N]

Defaults: last 14 days, binding=homelab, top 20 issues by cost.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

SYMPHONY_DIR = Path(__file__).resolve().parent.parent
if str(SYMPHONY_DIR) not in sys.path:
    sys.path.insert(0, str(SYMPHONY_DIR))

from web.api.db import resolve_db_path  # noqa: E402


def _int(value: object) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _fmt_int(value: object) -> str:
    return f"{_int(value):,}"


def _fmt_usd(value: object) -> str:
    return f"${_float(value):.4f}"


# All filtering is by bound parameters; binding/window/limit are never
# interpolated into SQL text.
_PER_ISSUE_SQL = """
    SELECT
      i.id                             AS issue_id,
      i.external_id                    AS external_id,
      i.title                          AS title,
      COUNT(r.id)                      AS runs,
      COALESCE(SUM(r.input_tokens), 0) AS input_tokens,
      COALESCE(SUM(r.output_tokens), 0) AS output_tokens,
      COALESCE(SUM(r.cache_read_tokens), 0) AS cache_read_tokens,
      COALESCE(SUM(r.cost_usd), 0)     AS cost_usd
    FROM run r
    JOIN issue i ON r.issue_id = i.id
    WHERE i.binding_name = :binding
      AND r.started_at >= datetime('now', :window)
    GROUP BY i.id
    ORDER BY cost_usd DESC, input_tokens DESC
    LIMIT :limit
"""

_TOTALS_SQL = """
    SELECT
      COUNT(r.id)                      AS runs,
      COALESCE(SUM(r.input_tokens), 0) AS input_tokens,
      COALESCE(SUM(r.output_tokens), 0) AS output_tokens,
      COALESCE(SUM(r.cache_read_tokens), 0) AS cache_read_tokens,
      COALESCE(SUM(r.cost_usd), 0)     AS cost_usd,
      SUM(CASE WHEN r.input_tokens IS NULL THEN 1 ELSE 0 END) AS missing_usage
    FROM run r
    JOIN issue i ON r.issue_id = i.id
    WHERE i.binding_name = :binding
      AND r.started_at >= datetime('now', :window)
"""


def _query(
    connection: sqlite3.Connection, *, binding: str, days: int, limit: int
) -> tuple[list[sqlite3.Row], sqlite3.Row]:
    params = {"binding": binding, "window": f"-{days} days", "limit": limit}
    per_issue = connection.execute(_PER_ISSUE_SQL, params).fetchall()
    totals = connection.execute(_TOTALS_SQL, params).fetchone()
    return per_issue, totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14, help="lookback window")
    parser.add_argument("--binding", default="homelab", help="binding name")
    parser.add_argument("--limit", type=int, default=20, help="top-N issues")
    args = parser.parse_args()

    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"No Podium DB at {db_path}", file=sys.stderr)
        return 1

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        per_issue, totals = _query(
            connection, binding=args.binding, days=args.days, limit=args.limit
        )
    finally:
        connection.close()

    print(
        f"Patrol token/context usage — binding={args.binding}, "
        f"last {args.days} days\n"
    )
    header = (
        f"{'issue':<38} {'runs':>5} {'input':>12} {'cache-rd':>12} "
        f"{'output':>10} {'cost':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in per_issue:
        label = (row["external_id"] or row["title"] or str(row["issue_id"]))[:38]
        print(
            f"{label:<38} {row['runs']:>5} "
            f"{_fmt_int(row['input_tokens']):>12} "
            f"{_fmt_int(row['cache_read_tokens']):>12} "
            f"{_fmt_int(row['output_tokens']):>10} "
            f"{_fmt_usd(row['cost_usd']):>10}"
        )

    print("-" * len(header))
    input_tokens = _int(totals["input_tokens"])
    cache_read = _int(totals["cache_read_tokens"])
    cache_pct = (cache_read / input_tokens * 100) if input_tokens else 0.0
    print(
        f"{'TOTAL':<38} {_int(totals['runs']):>5} "
        f"{_fmt_int(input_tokens):>12} "
        f"{_fmt_int(cache_read):>12} "
        f"{_fmt_int(totals['output_tokens']):>10} "
        f"{_fmt_usd(totals['cost_usd']):>10}"
    )
    print(
        f"\ncache-read share of input: {cache_pct:.1f}% "
        "(higher = re-fed history is cheap/cached)"
    )
    missing = _int(totals["missing_usage"])
    if missing:
        print(
            f"note: {missing} run(s) in window have no usage recorded "
            "(pre-#343 runs, or non-RPC agents without SYMPHONY_* markers)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
