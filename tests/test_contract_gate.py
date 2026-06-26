"""Enforcement wiring for the contract-parser regression gate.

These run inside the normal pytest suite, so any change to `scheduler/markers.py`
that drops marker coverage below the locked baseline — or flips a locked case —
turns the suite red and cannot ship. This is the gate's "the enforcement is the
measurement" anchor: the fitness check re-runs forever, not just once.
"""

from __future__ import annotations

import json

import pytest

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


def test_fixture_path_is_wired():
    """FIXTURE_PATH points to the checked-in corpus file."""
    assert cg.FIXTURE_PATH.name == "contract_gate_corpus.json"


def test_load_corpus_corrupt_fixture(tmp_path, monkeypatch):
    """load_corpus propagates JSON decode errors clearly."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("NOT_JSON_GARBAGE")
    monkeypatch.setattr(cg, "FIXTURE_PATH", bad_file)
    with pytest.raises(json.JSONDecodeError):
        cg.load_corpus()


def test_midline_marker_is_uncovered():
    """Run 9999 (mid-line SYMPHONY_RESULT) must NOT be parseable by terminal_signal.

    The ^ anchor in the regex prevents mid-line matches. This run exists in the
    fixture so a future relaxation of that anchor registers as a coverage gain.
    """
    corpus = cg.load_corpus()
    midline = [r for r in corpus if r.run_id == 9999]
    assert len(midline) == 1, "run 9999 (mid-line marker) must exist in fixture"
    sig = cg.terminal_signal(midline[0].log_text)
    assert sig is None, f"mid-line marker should NOT parse, got {sig!r}"
    s = cg.score(corpus)
    uncovered_ids = [u["run_id"] for u in s["uncovered"]]
    assert 9999 in uncovered_ids, "mid-line run must be in uncovered list"


def test_score_empty_corpus():
    """score() handles empty corpus gracefully (coverage=0.0)."""
    s = cg.score([])
    assert s["n"] == 0
    assert s["coverage"] == 0.0
    assert s["uncovered"] == []
    passed, failures, sc = cg.gate([])
    assert not passed
    assert any("regressed" in f for f in failures)
