"""Continuous-monitoring schedule logic (Phase 3 · SMPLSGHT-52).

Pure selection over stored state — no live scheduler in dev. An investigation marked
`monitoring_enabled` with an `monitoring_interval` becomes *due* for re-collection once its
last completed run is older than that interval (or it has never run). A worker tick, a cron,
or the manual `POST /api/monitoring/run-due` endpoint asks `due_investigations` what to run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Investigation, InvestigationStatus

# Supported cadences. Keys are stored on the investigation; values are the spacing between runs.
INTERVALS: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


def _aware(dt: datetime) -> datetime:
    """Treat naive timestamps (SQLite round-trips drop tzinfo) as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def next_due_at(inv: Investigation) -> datetime | None:
    """When this investigation next becomes due, or None if it isn't monitored.

    A monitored investigation that has never completed a run is due immediately (returns its
    created time), so enabling monitoring on a fresh investigation schedules an initial run.
    """
    if not inv.monitoring_enabled or inv.monitoring_interval not in INTERVALS:
        return None
    interval = INTERVALS[inv.monitoring_interval]
    if inv.completed_at is None:
        return _aware(inv.created_at)
    return _aware(inv.completed_at) + interval


def is_due(inv: Investigation, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    # Never re-enter a run that's already going, and only re-run authorized investigations.
    if inv.status == InvestigationStatus.RUNNING.value or not inv.is_authorized:
        return False
    due = next_due_at(inv)
    return due is not None and due <= now


def due_investigations(
    db: Session, tenant_id: str | None = None, now: datetime | None = None
) -> list[Investigation]:
    """All monitored investigations currently due, oldest-due first (most overdue leads)."""
    now = now or datetime.now(UTC)
    stmt = select(Investigation).where(Investigation.monitoring_enabled.is_(True))
    if tenant_id is not None:
        stmt = stmt.where(Investigation.tenant_id == tenant_id)
    due = [inv for inv in db.scalars(stmt) if is_due(inv, now)]
    due.sort(key=lambda inv: next_due_at(inv) or now)
    return due
