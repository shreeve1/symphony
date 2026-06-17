from tracker_contract import (
    PlaneContract,
    PlaneLabel,
    PlaneState,
    PlaneUserMapping,
    TrackerContract,
    TrackerLabel,
    TrackerState,
    TrackerUserMapping,
)


def test_tracker_contract_exports_canonical_tracker_vocab():
    assert TrackerState.TODO.value == "Todo"
    assert TrackerState.IN_REVIEW.value == "In Review"
    assert TrackerLabel.PLAN.value == "plan"
    assert TrackerLabel.HAS_WORKTREE.value == "has-worktree"


def test_plane_vocab_names_are_compat_aliases():
    assert PlaneState is TrackerState
    assert PlaneLabel is TrackerLabel
    assert PlaneUserMapping is TrackerUserMapping
    assert PlaneContract is TrackerContract
