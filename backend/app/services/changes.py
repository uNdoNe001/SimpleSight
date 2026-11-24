"""Change detection between two runs of an investigation (SMPLSGHT-50).

Pure, deterministic diffing — no I/O, no invented data. A re-run replaces an investigation's
assets and findings wholesale (`run_and_persist`), so to know *what changed* we snapshot the
prior state before it is cleared, snapshot the fresh state after it is persisted, and diff the
two. The result is a list of typed change candidates that the caller writes as `ChangeEvent`
rows and that alerting (SMPLSGHT-53) reads back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import ChangeType, Investigation

# Severity ordering, lowest → highest. Used to tell an escalation from a de-escalation.
_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def severity_rank(severity: str | None) -> int:
    return _SEVERITY_RANK.get((severity or "").lower(), 0)


@dataclass(frozen=True)
class _FindingState:
    title: str
    severity: str
    status: str


@dataclass(frozen=True)
class RunSnapshot:
    """A comparable, order-independent summary of one run's observable state."""

    asset_keys: frozenset[tuple[str, str]]  # (asset_type, value)
    findings: dict[str, _FindingState]  # finding_key -> state


@dataclass(frozen=True)
class ChangeCandidate:
    change_type: str
    entity_type: str  # "asset" | "finding"
    entity_key: str
    title: str
    severity: str | None = None
    detail: dict = field(default_factory=dict)


def snapshot_from_orm(investigation: Investigation) -> RunSnapshot:
    """Build a snapshot from an investigation's currently-loaded ORM rows.

    Call once before a re-run clears the collections (the previous run) and once after the
    fresh rows are appended (the new run) — the same investigation object, two points in time.
    """
    asset_keys = frozenset((a.asset_type, a.value) for a in investigation.assets)
    findings = {
        f.finding_key: _FindingState(title=f.title, severity=f.severity, status=f.status)
        for f in investigation.findings
    }
    return RunSnapshot(asset_keys=asset_keys, findings=findings)


def _asset_event(change_type: str, atype: str, value: str) -> ChangeCandidate:
    return ChangeCandidate(
        change_type=change_type,
        entity_type="asset",
        entity_key=f"{atype}:{value}",
        title=value,
        detail={"asset_type": atype, "value": value},
    )


def diff_runs(prev: RunSnapshot, curr: RunSnapshot) -> list[ChangeCandidate]:
    """Diff two snapshots into ordered change candidates (findings before assets).

    Findings lead because they are the analyst-facing signal; within each group output is
    sorted for stable, reproducible ordering. Asset identity is (type, value); finding
    identity is the stable `finding_key`, so analyst triage churn never shows up as change.
    """
    events: list[ChangeCandidate] = []

    appeared = curr.findings.keys() - prev.findings.keys()
    resolved = prev.findings.keys() - curr.findings.keys()
    common = prev.findings.keys() & curr.findings.keys()

    for key in sorted(appeared):
        st = curr.findings[key]
        events.append(
            ChangeCandidate(
                change_type=ChangeType.FINDING_APPEARED.value,
                entity_type="finding",
                entity_key=key,
                title=st.title,
                severity=st.severity,
                detail={"severity": st.severity},
            )
        )
    for key in sorted(resolved):
        st = prev.findings[key]
        events.append(
            ChangeCandidate(
                change_type=ChangeType.FINDING_RESOLVED.value,
                entity_type="finding",
                entity_key=key,
                title=st.title,
                severity=st.severity,
                detail={"severity": st.severity},
            )
        )
    for key in sorted(common):
        before, after = prev.findings[key], curr.findings[key]
        if before.severity != after.severity:
            events.append(
                ChangeCandidate(
                    change_type=ChangeType.FINDING_SEVERITY_CHANGED.value,
                    entity_type="finding",
                    entity_key=key,
                    title=after.title,
                    severity=after.severity,
                    detail={
                        "from": before.severity,
                        "to": after.severity,
                        "escalated": severity_rank(after.severity)
                        > severity_rank(before.severity),
                    },
                )
            )

    added = curr.asset_keys - prev.asset_keys
    removed = prev.asset_keys - curr.asset_keys
    for atype, value in sorted(added):
        events.append(_asset_event(ChangeType.ASSET_ADDED.value, atype, value))
    for atype, value in sorted(removed):
        events.append(_asset_event(ChangeType.ASSET_REMOVED.value, atype, value))

    return events
