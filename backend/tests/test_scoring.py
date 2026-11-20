"""Exposure-score rollup (Phase 2 · Story F) — pure, deterministic."""

from __future__ import annotations

from app.services.scoring import compute_exposure


def _f(severity: str, *, confidence: float = 0.9, status: str = "open") -> dict:
    return {"severity": severity, "confidence": confidence, "status": status}


def test_no_findings_is_minimal():
    s = compute_exposure([])
    assert s.score == 0
    assert s.grade == "A" and s.label == "Minimal"
    assert s.scored_findings == 0


def test_score_rises_with_severity():
    low = compute_exposure([_f("low")]).score
    high = compute_exposure([_f("high")]).score
    crit = compute_exposure([_f("critical")]).score
    assert 0 < low < high < crit <= 100


def test_dismissed_findings_excluded():
    with_dismissed = compute_exposure([_f("critical", status="dismissed")])
    assert with_dismissed.score == 0
    assert with_dismissed.scored_findings == 0


def test_confidence_scales_contribution():
    strong = compute_exposure([_f("high", confidence=1.0)]).score
    weak = compute_exposure([_f("high", confidence=0.3)]).score
    assert strong > weak


def test_more_findings_never_lower_score_and_capped():
    one = compute_exposure([_f("high")]).score
    many = compute_exposure([_f("high")] * 25)
    assert many.score >= one
    assert many.score <= 100
    assert many.grade in {"D", "F"}


def test_counts_reported_by_severity():
    s = compute_exposure([_f("high"), _f("high"), _f("medium"), _f("low", status="dismissed")])
    assert s.counts["high"] == 2
    assert s.counts["medium"] == 1
    assert s.counts["low"] == 0  # dismissed not counted
    assert s.scored_findings == 3


def test_works_over_objects_not_just_dicts():
    class _Obj:
        def __init__(self, severity, confidence, status):
            self.severity, self.confidence, self.status = severity, confidence, status

    s = compute_exposure([_Obj("critical", 0.9, "open")])
    assert s.score > 0 and s.grade in {"C", "D", "F"}
