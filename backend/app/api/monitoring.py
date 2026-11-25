"""Continuous-monitoring routes (Phase 3 · SMPLSGHT-52). Tenant-scoped.

  PATCH /api/investigations/{id}/monitoring  -> enable/disable + set cadence (writer)
  GET   /api/monitoring/due                   -> investigations due for re-collection
  POST  /api/monitoring/run-due               -> enqueue a run for each due one (writer)

Selection is deterministic (app/services/monitoring.py); there is no live scheduler in dev,
so run-due is the manual trigger a cron or worker tick would otherwise call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.deps import get_current_user, require_writer
from app.models import Investigation, User
from app.schemas import (
    DueInvestigationOut,
    InvestigationOut,
    MonitoringUpdate,
    RunDueResponse,
)
from app.services.audit import record_audit
from app.services.monitoring import due_investigations, enqueue_due, next_due_at

router = APIRouter(tags=["monitoring"])


def _require_enabled() -> None:
    if not settings.monitoring_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "monitoring is disabled")


@router.patch("/api/investigations/{inv_id}/monitoring", response_model=InvestigationOut)
def update_monitoring(
    inv_id: str,
    body: MonitoringUpdate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Investigation:
    _require_enabled()
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    inv.monitoring_enabled = body.enabled
    inv.monitoring_interval = body.interval if body.enabled else None
    record_audit(
        db, tenant_id=user.tenant_id, actor_user_id=user.id,
        action="investigation.monitoring", target=inv.id,
        detail={"enabled": body.enabled, "interval": inv.monitoring_interval},
    )
    db.commit()
    db.refresh(inv)
    return inv


def _due_out(inv: Investigation) -> DueInvestigationOut:
    out = DueInvestigationOut.model_validate(inv)
    out.next_due_at = next_due_at(inv)
    return out


@router.get("/api/monitoring/due", response_model=list[DueInvestigationOut])
def list_due(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DueInvestigationOut]:
    _require_enabled()
    return [_due_out(inv) for inv in due_investigations(db, tenant_id=user.tenant_id)]


@router.post("/api/monitoring/run-due", response_model=RunDueResponse)
def run_due(
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> RunDueResponse:
    """Enqueue a collection run for every due investigation in the caller's tenant.

    Skips any whose organization lost its primary domain (nothing to collect) rather than
    enqueuing a run destined to fail.
    """
    _require_enabled()
    result = enqueue_due(db, tenant_id=user.tenant_id)
    if result.enqueued:
        record_audit(
            db, tenant_id=user.tenant_id, actor_user_id=user.id,
            action="monitoring.run_due", target=None,
            detail={"enqueued": len(result.enqueued), "investigation_ids": result.enqueued},
        )
        db.commit()
    return RunDueResponse(enqueued=len(result.enqueued), investigation_ids=result.enqueued)
