"""Exposure-score rollup (Phase 2 · Story F).

A deterministic rollup of an investigation's findings into a single 0–100 exposure score
plus a grade/label, for the dashboard and the executive report. Like the rest of the
findings layer it invents nothing: the score is a pure function of the findings' severity,
confidence, and triage status.

Design:
  - Dismissed findings are excluded (an analyst has judged them not relevant).
  - Each finding contributes `severity_weight × confidence`, so an unverified low-confidence
    signal counts for less than a corroborated one.
  - The weighted sum is passed through a saturating curve so one serious issue produces a
    meaningful score while many issues approach — but never exceed — 100. The mapping is
    monotonic: more/severer findings never lower the score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

_SEVERITY_WEIGHTS = {"critical": 40.0, "high": 20.0, "medium": 8.0, "low": 3.0, "info": 1.0}
_SEVERITIES = ("critical", "high", "medium", "low", "info")
_SATURATION = 50.0  # larger => score climbs more slowly with accumulated weight

# (min_score_inclusive, grade, label) — evaluated high-to-low.
_BANDS = (
    (75, "F", "Critical"),
    (50, "D", "Elevated"),
    (25, "C", "Moderate"),
    (1, "B", "Low"),
    (0, "A", "Minimal"),
)


@dataclass
class ExposureScore:
    score: int                                  # 0–100
    grade: str                                  # A–F
    label: str                                  # Minimal / Low / Moderate / Elevated / Critical
    counts: dict[str, int] = field(default_factory=dict)  # scored findings by severity
    scored_findings: int = 0                    # non-dismissed findings counted
    rationale: str = ""


def _get(finding: object, key: str, default: object) -> object:
    if isinstance(finding, dict):
        return finding.get(key, default)
    return getattr(finding, key, default)


def _band(score: int) -> tuple[str, str]:
    for threshold, grade, label in _BANDS:
        if score >= threshold:
            return grade, label
    return "A", "Minimal"


def compute_exposure(findings: object) -> ExposureScore:
    """Roll an iterable of findings (ORM Finding, FindingOut, or report dicts) into a score."""
    counts = {s: 0 for s in _SEVERITIES}
    weighted = 0.0
    scored = 0
    for f in findings or []:
        if str(_get(f, "status", "open")).lower() == "dismissed":
            continue
        sev = str(_get(f, "severity", "info")).lower()
        if sev not in counts:
            sev = "info"
        counts[sev] += 1
        scored += 1
        conf = _get(f, "confidence", 0.5)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        conf = min(max(conf, 0.0), 1.0)
        weighted += _SEVERITY_WEIGHTS[sev] * conf

    score = round(100 * (1 - math.exp(-weighted / _SATURATION)))
    score = max(0, min(100, score))
    grade, label = _band(score)

    if scored == 0:
        rationale = "No active findings were derived from the observed footprint."
    else:
        present = [f"{counts[s]} {s}" for s in _SEVERITIES if counts[s]]
        highest = next(s for s in _SEVERITIES if counts[s])
        rationale = (
            f"{scored} active finding(s) ({', '.join(present)}); score weighted by severity "
            f"and evidence confidence, led by {highest}-severity exposure."
        )
    return ExposureScore(
        score=score, grade=grade, label=label, counts=counts,
        scored_findings=scored, rationale=rationale,
    )
