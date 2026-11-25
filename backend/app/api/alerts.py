"""Alert routes (Phase 3 · SMPLSGHT-53). Tenant-scoped.

  GET  /api/investigations/{id}/alerts        -> material change events + unacknowledged count
  POST /api/alerts/{event_id}/acknowledge     -> acknowledge one alert (writer)
  GET  /api/alerts/summary                     -> tenant-wide unacknowledged count (nav badge)

Alerts are the material subset of change events (app/services/alerts.py); they are produced by
collection runs, never created directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_writer
from app.models import ChangeEvent, ChangeType, Investigation, User
from app.schemas import AlertsOut, AlertSummaryOut, ChangeEventOut
from app.services.alerts import is_material, material_events
from app.services.audit import record_audit

router = APIRouter(tags=["alerts"])

# The only change types that can ever be material — used to narrow the DB query.
_ALERTABLE = (ChangeType.FINDING_APPEARED.value, ChangeType.FINDING_SEVERITY_CHANGED.value)


@router.get("/api/investigations/{inv_id}/alerts", response_model=AlertsOut)
def list_alerts(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertsOut:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    events = material_events(
        db.scalars(
            select(ChangeEvent).where(
                ChangeEvent.investigation_id == inv_id,
                ChangeEvent.tenant_id == user.tenant_id,
                ChangeEvent.change_type.in_(_ALERTABLE),
            )
        )
    )
    events.sort(key=lambda e: e.run_at.timestamp(), reverse=True)
    unacked = sum(1 for e in events if e.acknowledged_at is None)
    return AlertsOut(
        unacknowledged=unacked,
        alerts=[ChangeEventOut.model_validate(e) for e in events],
    )


@router.post("/api/alerts/{event_id}/acknowledge", response_model=ChangeEventOut)
def acknowledge_alert(
    event_id: str,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> ChangeEvent:
    event = db.get(ChangeEvent, event_id)
    if event is None or event.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    if not is_material(event):
        raise HTTPException(status.HTTP_409_CONFLICT, "change event is not an alert")
    if event.acknowledged_at is None:
        event.acknowledged_at = datetime.now(UTC)
        record_audit(
            db, tenant_id=user.tenant_id, actor_user_id=user.id,
            action="alert.acknowledge", target=event.id,
        )
        db.commit()
        db.refresh(event)
    return event


@router.get("/api/alerts/summary", response_model=AlertSummaryOut)
def alerts_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertSummaryOut:
    events = db.scalars(
        select(ChangeEvent).where(
            ChangeEvent.tenant_id == user.tenant_id,
            ChangeEvent.change_type.in_(_ALERTABLE),
            ChangeEvent.acknowledged_at.is_(None),
        )
    )
    return AlertSummaryOut(unacknowledged=sum(1 for e in events if is_material(e)))
