"""Change-event routes (Phase 3 · SMPLSGHT-51). Tenant-scoped, read-only.

  GET /api/investigations/{id}/changes            -> change events, newest run first
  GET /api/investigations/{id}/changes?latest=true -> only the most-recent run's events

Change events are produced by the collection run (app/services/changes.py) when a re-run
differs from the prior run; they are never created directly through the API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ChangeEvent, Investigation, User
from app.schemas import ChangeEventOut

router = APIRouter(tags=["changes"])

# Findings before assets, then alphabetical by key — stable, analyst-first ordering.
_TYPE_ORDER = {
    "finding_severity_changed": 0,
    "finding_appeared": 1,
    "finding_resolved": 2,
    "asset_added": 3,
    "asset_removed": 4,
}


def _owned_investigation(db: Session, inv_id: str, tenant_id: str) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    return inv


@router.get("/api/investigations/{inv_id}/changes", response_model=list[ChangeEventOut])
def list_changes(
    inv_id: str,
    latest: bool = Query(False, description="Return only the most-recent run's events."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChangeEvent]:
    _owned_investigation(db, inv_id, user.tenant_id)
    events = list(
        db.scalars(
            select(ChangeEvent).where(
                ChangeEvent.investigation_id == inv_id,
                ChangeEvent.tenant_id == user.tenant_id,
            )
        )
    )
    if latest and events:
        newest_run = max(e.run_at for e in events)
        events = [e for e in events if e.run_at == newest_run]
    # Newest run first; within a run, analyst-relevant types lead, then key alphabetical.
    events.sort(
        key=lambda e: (-e.run_at.timestamp(), _TYPE_ORDER.get(e.change_type, 9), e.entity_key)
    )
    return events
