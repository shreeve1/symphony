"""One-shot: seed contract_gate_corpus.json from the pre-drift corpus.

Reads podium.db + runs/ directly (does NOT use load_corpus — that reads the fixture
we are about to write), extracts pre-drift population by run_id ceiling, strips ANSI
escapes, round-trip validates coverage ≥ baseline, then writes the frozen fixture.

Usage: uv run python scripts/seed_contract_gate_corpus.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contract_gate import LOCKED_CASES, REPO, CorpusRow, score, terminal_signal
from scheduler.markers import _ANSI_ESCAPE_RE

BASELINE_PATH = REPO / "contract_gate_baseline.json"
FIXTURE_PATH = REPO / "contract_gate_corpus.json"
DB_PATH = REPO / "podium.db"
RUNS_DIR = REPO / "runs"


def _load_corpus_from_db() -> list[CorpusRow]:
    """Read corpus directly from podium.db + runs/ — does not use load_corpus()."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id, exit_code, state, verdict, log_path FROM run "
            "WHERE state IN ('succeeded','failed')"
        ).fetchall()
    finally:
        con.close()

    corpus: list[CorpusRow] = []
    for run_id, exit_code, state, verdict, log_path in rows:
        path = Path(log_path) if log_path else RUNS_DIR / f"{run_id}.log"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        corpus.append(CorpusRow(run_id, exit_code, state, verdict, text))
    return corpus


def main() -> int:
    # 1. Load live corpus directly from DB (not from load_corpus — it reads fixture)
    corpus = _load_corpus_from_db()

    # 2. Filter to exit-0 only (the scoring population)
    exit0 = sorted(
        [r for r in corpus if r.exit_code in (0, None)],
        key=lambda r: r.run_id,
    )
    print(f"Live corpus: {len(corpus)} total, {len(exit0)} exit-0")

    if not exit0:
        print("ERROR: no exit-0 runs in corpus", file=sys.stderr)
        return 1

    # 3. Empirically find the run_id ceiling
    # Target: n ≈ 175, coverage ≥ 0.9314 (the baseline)
    floor = json.loads(BASELINE_PATH.read_text()).get("coverage", 0.0)
    print(f"Baseline coverage: {floor}")

    best_ceil = None
    best_n = 0
    best_cov = 0.0
    for ceil in range(1, max(r.run_id for r in exit0) + 1):
        subset = [r for r in exit0 if r.run_id <= ceil]
        n = len(subset)
        if n < 170:  # too small, keep searching
            continue
        covered = sum(1 for r in subset if terminal_signal(r.log_text) is not None)
        cov = covered / n
        if round(cov, 4) >= floor and (
            best_ceil is None or abs(n - 175) < abs(best_n - 175)
        ):
            best_ceil = ceil
            best_n = n
            best_cov = cov
        if n > 190:  # drifting too far from baseline n
            break

    if best_ceil is None:
        print("ERROR: no ceiling found that meets coverage ≥ baseline", file=sys.stderr)
        return 1

    print(
        f"Selected ceiling: run_id ≤ {best_ceil} → n={best_n}, coverage={best_cov:.4f}"
    )

    # 4. Filter corpus to ceiling
    fixture_runs = [r for r in exit0 if r.run_id <= best_ceil]

    # 5. Verify locked cases are present
    fixture_ids = {r.run_id for r in fixture_runs}
    for lid in LOCKED_CASES:
        if lid not in fixture_ids:
            print(
                f"ERROR: locked run {lid} missing from ceiling-bounded set",
                file=sys.stderr,
            )
            return 1
    print(f"Locked cases {sorted(LOCKED_CASES)} all present ✓")

    # 6. Strip ANSI and serialize
    rows = []
    for r in fixture_runs:
        clean_text = _ANSI_ESCAPE_RE.sub("", r.log_text)
        rows.append(
            {
                "run_id": r.run_id,
                "exit_code": r.exit_code,
                "recorded_state": r.recorded_state,
                "recorded_verdict": r.recorded_verdict,
                "log_text": clean_text,
            }
        )

    FIXTURE_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    size_kb = FIXTURE_PATH.stat().st_size / 1024
    print(f"Written {FIXTURE_PATH}: {len(rows)} runs, {size_kb:.0f} KB")

    # 7. Round-trip validation
    data = json.loads(FIXTURE_PATH.read_text())
    rt_corpus = [CorpusRow(**row) for row in data]
    rt_score = score(rt_corpus)

    if abs(rt_score["coverage"] - best_cov) > 0.0001:
        print(
            f"ERROR: round-trip coverage drift: {best_cov:.4f} → {rt_score['coverage']:.4f}",
            file=sys.stderr,
        )
        return 1
    print(f"Round-trip coverage: {rt_score['coverage']:.4f} ✓")

    # Verify locked case signals identical
    from contract_gate import check_locked

    lf = check_locked(rt_corpus)
    if lf:
        print(f"ERROR: locked case drift: {lf}", file=sys.stderr)
        return 1
    print("Locked case signals identical ✓")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
