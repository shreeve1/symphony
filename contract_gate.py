"""Contract-parser regression gate — hardens Symphony's measurement layer.

Symphony's whole self-improvement story rests on one signal it must be able to
trust: the terminal marker an agent emits (`SYMPHONY_RESULT` / `SYMPHONY_SCHEDULE`
/ question block), parsed by `scheduler.markers`, which is what the orchestrator
turns into the recorded `run.verdict`. When that parsing layer drifts — as when
tail-truncation dropped a head `SYMPHONY_RESULT` marker and a clean `review` run
was recorded as `blocked` (run 120; issues #053/#055/#057) — the marker is lost
and every downstream metric and every "lesson" learned from run outcomes is built
on a misread. A self-improvement loop with an unguarded measurement layer can
absorb a wrong lesson as easily as a right one.

This gate hardens the measurement itself. It is pure code over a free, frozen
corpus (204 real run logs already on disk) scored with Symphony's *own* parser
(`scheduler.markers`) — the model never runs, so the score cannot be faked.

Fitness = `coverage`: of the runs that exited 0 (and therefore should carry a
terminal marker), the fraction whose persisted log still yields a parseable
terminal signal. A regression in the marker regexes (tightening a pattern so it
stops matching indented / differently-cased / legacy markers) drops coverage and
fails the gate.

Loop:  propose a change to `scheduler/markers.py`  ->  re-score the frozen corpus
->  keep iff coverage does not regress below the locked baseline and no locked
case stops parsing, else the gate exits non-zero (which blocks the commit and
drives the revert). This is the "failure -> permanent check" half the wiki rule
lacks: each real parse-loss run is enumerable as a locked case that re-runs forever.

Usage:
    python contract_gate.py                       # score + gate against baseline
    python contract_gate.py --json                # machine-readable score
    python contract_gate.py --update-baseline     # ratchet baseline up (keep path)
    python contract_gate.py --auto-revert F...     # on failure, git-checkout F, rescore
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scheduler.markers import (
    _parse_question_block,
    _parse_result_marker,
    _parse_schedule_marker,
)

REPO = Path(__file__).resolve().parent
FIXTURE_PATH = REPO / "contract_gate_corpus.json"
BASELINE_PATH = REPO / "contract_gate_baseline.json"

# Failure -> permanent check. Each entry pins a real run log to the terminal
# signal Symphony's parser must keep extracting from it. Seeded with the run-120
# regression family: run 120's agent emitted `SYMPHONY_RESULT: review`, and the
# live classifier of the day recorded `blocked` from a truncated stream — the
# persisted log carries the true marker, so the parser must keep reading `review`
# from it. A future tightening of the marker regex that re-hides it flips this
# case and fails the gate.
#   signal kinds: "result:<verdict>", "schedule", "question"
LOCKED_CASES: dict[int, str] = {
    30: "result:done",
    39: "question",
    120: "result:review",
}


@dataclass(frozen=True)
class CorpusRow:
    run_id: int
    exit_code: int | None
    recorded_state: str
    recorded_verdict: str | None
    log_text: str


def load_corpus(db_path=None, runs_dir=None) -> list[CorpusRow]:
    """Load the frozen, checked-in corpus fixture."""
    data = json.loads(FIXTURE_PATH.read_text())
    return [CorpusRow(**row) for row in data]


def terminal_signal(log_text: str) -> str | None:
    """The terminal signal Symphony's own parser extracts from a log, or None.

    Pure pass-through to `scheduler.markers` — this gate measures the real parser,
    it does not reimplement it. Precedence matches the scheduler tick: a result
    marker is the primary terminal outcome; schedule and question are the
    non-result terminal forms.
    """

    verdict = _parse_result_marker(log_text)
    if verdict is not None:
        return f"result:{verdict}"
    if _parse_schedule_marker(log_text) is not None:
        return "schedule"
    if _parse_question_block(log_text) is not None:
        return "question"
    return None


def score(corpus: list[CorpusRow]) -> dict:
    """Coverage over the exit-0 population. Pure function, no model.

    A run that exited non-zero is force-blocked by the orchestrator regardless of
    any marker, so it is excluded: it is not expected to carry a parseable signal.
    """

    population = [r for r in corpus if r.exit_code in (0, None)]
    uncovered = [r for r in population if terminal_signal(r.log_text) is None]
    n = len(population)
    covered = n - len(uncovered)
    return {
        "n": n,
        "covered": covered,
        "coverage": round(covered / n, 4) if n else 0.0,
        "uncovered": [
            {"run_id": r.run_id, "recorded": [r.recorded_state, r.recorded_verdict]}
            for r in sorted(uncovered, key=lambda r: r.run_id)
        ],
    }


def check_locked(corpus: list[CorpusRow]) -> list[str]:
    """Return failure messages for any locked case whose parsed signal changed."""

    by_id = {r.run_id: r for r in corpus}
    failures: list[str] = []
    for run_id, expected in LOCKED_CASES.items():
        row = by_id.get(run_id)
        if row is None:
            failures.append(f"locked run {run_id}: missing from corpus")
            continue
        got = terminal_signal(row.log_text)
        if got != expected:
            failures.append(
                f"locked run {run_id}: signal {got!r} != expected {expected!r}"
            )
    return failures


def gate(corpus: list[CorpusRow]) -> tuple[bool, list[str], dict]:
    """The enforcement decision: (passed, failures, score)."""

    s = score(corpus)
    failures: list[str] = []

    if BASELINE_PATH.is_file():
        floor = json.loads(BASELINE_PATH.read_text()).get("coverage", 0.0)
        if s["coverage"] < floor:
            failures.append(
                f"coverage regressed: {s['coverage']} < baseline {floor} "
                f"(now-uncovered: {[u['run_id'] for u in s['uncovered']]})"
            )
    else:
        failures.append(f"no baseline at {BASELINE_PATH.name}; run --update-baseline")

    failures.extend(check_locked(corpus))
    return (not failures, failures, s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--json", action="store_true", help="emit score as JSON")
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="ratchet baseline to current coverage (keep path; refuses to lower)",
    )
    ap.add_argument(
        "--auto-revert",
        nargs="+",
        metavar="PATH",
        help="on gate failure, `git checkout -- PATH...` and re-score (revert path)",
    )
    args = ap.parse_args(argv)

    corpus = load_corpus()

    if args.update_baseline:
        s = score(corpus)
        old = (
            json.loads(BASELINE_PATH.read_text()).get("coverage", 0.0)
            if BASELINE_PATH.is_file()
            else 0.0
        )
        if s["coverage"] < old:
            print(
                f"refusing to lower baseline {old} -> {s['coverage']}; "
                "investigate the regression instead.",
                file=sys.stderr,
            )
            return 1
        BASELINE_PATH.write_text(
            json.dumps({"coverage": s["coverage"], "n": s["n"]}, indent=2) + "\n"
        )
        print(f"baseline set: coverage={s['coverage']} n={s['n']}")
        return 0

    passed, failures, s = gate(corpus)

    if args.json:
        print(json.dumps({"passed": passed, "failures": failures, **s}, indent=2))
    else:
        print(f"coverage={s['coverage']} ({s['covered']}/{s['n']})")
        for u in s["uncovered"]:
            print(f"  uncovered run {u['run_id']}: recorded={u['recorded']}")
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)

    if passed:
        return 0

    if args.auto_revert:
        for p in args.auto_revert:
            subprocess.run(["git", "-C", str(REPO), "checkout", "--", p], check=False)
        # Re-score in a fresh interpreter: the reverted module is already imported
        # in this process with its (regressed) regexes compiled, so an in-process
        # re-score would read stale code. A subprocess re-imports from disk.
        rescore = subprocess.run([sys.executable, __file__], cwd=str(REPO))
        print(
            f"auto-reverted {args.auto_revert}; gate now "
            f"{'PASS' if rescore.returncode == 0 else 'STILL FAILING'}",
            file=sys.stderr,
        )
        return rescore.returncode

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
