"""
tests/test_coi_engine.py
========================
Unit tests for the COI scoring engine.
Run with:  python tests/test_coi_engine.py
Or with pytest:  python -m pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.coi_engine import (
    combine_weights, coauthor_weight, institution_weight,
    CURRENT_YEAR, INSTITUTION_WEIGHT_CURRENT, INSTITUTION_WEIGHT_FORMER_BASE,
)
from src.demo_data import (
    score_offline,
    LAMAR_PIERCE, AUTHOR_HIGH_COI, AUTHOR_MEDIUM_COI,
    AUTHOR_NO_COI, AUTHOR_ADVISEE,
)


# --- Weight formula ---

def test_combine_empty():
    assert combine_weights([]) == 0.0

def test_combine_single():
    assert abs(combine_weights([0.9]) - 0.9) < 0.0001

def test_combine_two():
    # 1 - (1-0.5)(1-0.5) = 0.75
    assert abs(combine_weights([0.5, 0.5]) - 0.75) < 0.0001

def test_combine_caps_at_one():
    assert combine_weights([0.9, 0.9, 0.9, 0.9]) <= 1.0

def test_coauthor_recent():
    w, label = coauthor_weight(CURRENT_YEAR)
    assert w == 0.90

def test_coauthor_old():
    w, _ = coauthor_weight(CURRENT_YEAR - 15)
    assert w == 0.25

def test_institution_current():
    assert institution_weight(None) == INSTITUTION_WEIGHT_CURRENT

def test_institution_former_old():
    assert institution_weight(CURRENT_YEAR - 20) == 0.0


# --- Scoring integration ---

def test_high_coi_flagged():
    r = score_offline(LAMAR_PIERCE, AUTHOR_HIGH_COI)
    assert r.score >= 0.90, f"Expected >=0.90, got {r.score}"
    assert r.exceeds_threshold(0.50)
    assert any("co-authorship" in reason.lower() for reason in r.reasons)
    assert any("institution" in reason.lower() for reason in r.reasons)

def test_medium_coi_flagged():
    r = score_offline(LAMAR_PIERCE, AUTHOR_MEDIUM_COI)
    assert 0.50 < r.score < 0.85, f"Expected medium range, got {r.score}"
    assert r.exceeds_threshold(0.50)

def test_low_coi_not_flagged():
    r = score_offline(LAMAR_PIERCE, AUTHOR_NO_COI)
    assert r.score < 0.50, f"Expected <0.50, got {r.score}"
    assert not r.exceeds_threshold(0.50)

def test_advisee_high_coi():
    r = score_offline(LAMAR_PIERCE, AUTHOR_ADVISEE)
    assert r.score >= 0.90
    assert any("advisor" in reason.lower() for reason in r.reasons)

def test_symmetry():
    r1 = score_offline(LAMAR_PIERCE, AUTHOR_MEDIUM_COI)
    r2 = score_offline(AUTHOR_MEDIUM_COI, LAMAR_PIERCE)
    assert abs(r1.score - r2.score) < 0.01

def test_notification_flagged():
    r = score_offline(LAMAR_PIERCE, AUTHOR_HIGH_COI)
    text = r.notification_text(0.50)
    assert "conflict-of-interest score" in text
    assert "threshold" in text

def test_notification_clear():
    r = score_offline(LAMAR_PIERCE, AUTHOR_NO_COI)
    assert "No conflict" in r.notification_text(0.50)

def test_adjustable_threshold():
    r = score_offline(LAMAR_PIERCE, AUTHOR_MEDIUM_COI)
    assert r.exceeds_threshold(0.50)
    assert not r.exceeds_threshold(0.80)

def test_to_dict():
    r = score_offline(LAMAR_PIERCE, AUTHOR_HIGH_COI)
    d = r.to_dict()
    assert "score" in d and "reasons" in d and "edges" in d
    assert all("type" in e and "weight" in e for e in d["edges"])


if __name__ == "__main__":
    tests = [k for k in list(globals()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            globals()[t]()
            print(f"  ✓ {t}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
