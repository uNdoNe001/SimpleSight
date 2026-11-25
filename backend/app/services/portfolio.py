"""Tenant-wide portfolio rollup (Phase 5 · SMPLSGHT-62/63/64).

Deterministic aggregation over one tenant's stored data — org/investigation counts, exposure
grade distribution, recent change events, and monitoring health. Nothing is invented: exposure
grades come from the same `compute_exposure()` used per investigation and in the report; alert
counts from the material change-event rule; monitoring state from the monitoring helpers. Every
query is tenant-scoped, so a rollup can never leak across tenants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, ChangeType, Investigation, Organization
from app.services.alerts import is_material
from app.services.monitoring import INTERVALS, next_due_at
from app.services.scoring import compute_exposure

# Grades the exposure model can emit, worst-last for display ordering.
GRADES = ("A", "B", "C", "D", "F")

# The only change types that can be material — used to narrow the alert query.
_ALERTABLE = (ChangeType.FINDING_APPEARED.value, ChangeType.FINDING_SEVERITY_CHANGED.value)

# Newest run first; within a run, analyst-relevant types lead, then key alphabetical.
_TYPE_ORDER = {
    "finding_severity_changed": 0,
    "finding_appeared": 1,
    "finding_resolved": 2,
    "asset_added": 3,
    "asset_removed": 4,
}

# Monitoring-health sort: the things needing attention float to the top.
_STATE_ORDER = {"overdue": 0, "due": 1, "pending": 2, "fresh": 3}


@dataclass
class ExposureLeader:
    investigation_id: str
    organization_id: str
    score: int
    grade: str
    label: str


@dataclass
class PortfolioSummary:
    organizations_total: int = 0
    organizations_archived: int = 0
    investigations_total: int = 0
    investigations_by_status: dict[str, int] = field(default_factory=dict)
    assessed_investigations: int = 0  # have completed at least one run
    exposure_distribution: dict[str, int] = field(default_factory=dict)
    highest_exposure: ExposureLeader | None = None
    open_alerts: int = 0
    monitoring_enabled: int = 0
    monitoring_by_interval: dict[str, int] = field(default_factory=dict)


@dataclass
class ActivityItem:
    event: ChangeEvent
    organization_name: str
    is_material: bool


@dataclass
class MonitorHealth:
    investigation_id: str
    organization_id: str
    organization_name: str
    interval: str | None
    status: str
    last_run: datetime | None
    next_due_at: datetime | None
    state: str  # overdue | due | pending | fresh


def _org_names(db: Session, tenant_id: str, org_ids: set[str]) -> dict[str, str]:
    if not org_ids:
        return {}
    rows = db.scalars(
        select(Organization).where(
            Organization.tenant_id == tenant_id, Organization.id.in_(org_ids)
        )
    )
    return {o.id: o.name for o in rows}


def summarize(db: Session, tenant_id: str) -> PortfolioSummary:
    """Roll a tenant's orgs and investigations into one dashboard summary."""
    orgs = list(db.scalars(select(Organization).where(Organization.tenant_id == tenant_id)))
    invs = list(
        db.scalars(select(Investigation).where(Investigation.tenant_id == tenant_id))
    )

    summary = PortfolioSummary(
        organizations_total=len(orgs),
        organizations_archived=sum(1 for o in orgs if o.archived),
        investigations_total=len(invs),
        exposure_distribution={g: 0 for g in GRADES},
    )

    for inv in invs:
        summary.investigations_by_status[inv.status] = (
            summary.investigations_by_status.get(inv.status, 0) + 1
        )
        if inv.monitoring_enabled:
            summary.monitoring_enabled += 1
            key = inv.monitoring_interval or "unset"
            summary.monitoring_by_interval[key] = (
                summary.monitoring_by_interval.get(key, 0) + 1
            )

        # Exposure distribution covers only investigations that have actually been assessed.
        if inv.completed_at is None:
            continue
        summary.assessed_investigations += 1
        exp = compute_exposure(inv.findings)
        if exp.grade in summary.exposure_distribution:
            summary.exposure_distribution[exp.grade] += 1
        lead = summary.highest_exposure
        if lead is None or exp.score > lead.score or (
            exp.score == lead.score and inv.id < lead.investigation_id
        ):
            summary.highest_exposure = ExposureLeader(
                investigation_id=inv.id, organization_id=inv.organization_id,
                score=exp.score, grade=exp.grade, label=exp.label,
            )

    events = db.scalars(
        select(ChangeEvent).where(
            ChangeEvent.tenant_id == tenant_id,
            ChangeEvent.change_type.in_(_ALERTABLE),
            ChangeEvent.acknowledged_at.is_(None),
        )
    )
    summary.open_alerts = sum(1 for e in events if is_material(e))
    return summary


def recent_activity(
    db: Session, tenant_id: str, *, limit: int = 50, material_only: bool = False
) -> list[ActivityItem]:
    """Recent change events across all of a tenant's investigations, newest run first."""
    limit = max(1, min(limit, 200))
    stmt = select(ChangeEvent).where(ChangeEvent.tenant_id == tenant_id)
    if material_only:
        stmt = stmt.where(ChangeEvent.change_type.in_(_ALERTABLE))
    events = list(db.scalars(stmt))
    if material_only:
        events = [e for e in events if is_material(e)]
    events.sort(
        key=lambda e: (-e.run_at.timestamp(), _TYPE_ORDER.get(e.change_type, 9), e.entity_key)
    )
    events = events[:limit]
    names = _org_names(db, tenant_id, {e.organization_id for e in events})
    return [
        ActivityItem(
            event=e, organization_name=names.get(e.organization_id, ""),
            is_material=is_material(e),
        )
        for e in events
    ]


def _health_state(inv: Investigation, now: datetime, due_at: datetime | None) -> str:
    if inv.completed_at is None:
        return "pending"  # monitored but never run — awaiting the first collection
    if due_at is None:
        return "fresh"
    if now < due_at:
        return "fresh"
    interval = INTERVALS.get(inv.monitoring_interval or "")
    if interval is not None and (now - due_at) > interval:
        return "overdue"  # more than a full interval past due
    return "due"


def monitoring_health(
    db: Session, tenant_id: str, now: datetime | None = None
) -> list[MonitorHealth]:
    """Per-monitor freshness for every monitored investigation in the tenant."""
    now = now or datetime.now(UTC)
    invs = list(
        db.scalars(
            select(Investigation).where(
                Investigation.tenant_id == tenant_id,
                Investigation.monitoring_enabled.is_(True),
            )
        )
    )
    names = _org_names(db, tenant_id, {inv.organization_id for inv in invs})
    rows = [
        MonitorHealth(
            investigation_id=inv.id,
            organization_id=inv.organization_id,
            organization_name=names.get(inv.organization_id, ""),
            interval=inv.monitoring_interval,
            status=inv.status,
            last_run=inv.completed_at,
            next_due_at=(due := next_due_at(inv)),
            state=_health_state(inv, now, due),
        )
        for inv in invs
    ]
    rows.sort(key=lambda m: (_STATE_ORDER.get(m.state, 9), m.next_due_at or now))
    return rows
