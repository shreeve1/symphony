"""Enforcement wiring for the contract-parser regression gate.

These run inside the normal pytest suite, so any change to `scheduler/markers.py`
that drops marker coverage below the locked baseline — or flips a locked case —
turns the suite red and cannot ship. This is the gate's "the enforcement is the
measurement" anchor: the fitness check re-runs forever, not just once.
"""

from __future__ import annotations

import contract_gate as cg


def test_baseline_present():
    assert cg.BASELINE_PATH.is_file(), "run `python contract_gate.py --update-baseline`"


def test_gate_passes_at_head():
    corpus = cg.load_corpus()
    passed, failures, sc = cg.gate(corpus)
    assert passed, f"contract gate failed: {failures} (score={sc['coverage']})"


def test_locked_cases_parse():
    failures = cg.check_locked(cg.load_corpus())
    assert not failures, failures


def test_injected_regression_is_caught():
    """The gate must FAIL when the parser stops recognizing a verdict.

    Proves the gate has teeth without touching real source: monkeypatch the live
    parser to drop `review`, mirroring the realistic regression we validated by
    hand, and assert coverage regresses below baseline.
    """

    corpus = cg.load_corpus()
    real = cg._parse_result_marker

    def crippled(text: str):
        v = real(text)
        return None if v == "review" else v

    cg._parse_result_marker = crippled
    try:
        passed, failures, sc = cg.gate(corpus)
    finally:
        cg._parse_result_marker = real

    assert not passed
    assert sc["coverage"] < cg.json.loads(cg.BASELINE_PATH.read_text())["coverage"]
