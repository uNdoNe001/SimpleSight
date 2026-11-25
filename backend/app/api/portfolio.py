"""Portfolio dashboard routes (Phase 5 · SMPLSGHT-62/63/64). Tenant-scoped, read-only.

  GET /api/portfolio/summary            -> org/investigation counts, exposure mix, alerts, monitoring
  GET /api/portfolio/activity           -> recent change events across all investigations
  GET /api/portfolio/monitoring-health  -> freshness of every monitored investigation

All three are deterministic rollups over stored data (app/services/portfolio.py); they create
nothing and are scoped to the caller's tenant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ActivityItemOut,
    ExposureLeaderOut,
    MonitoringHealthItemOut,
    PortfolioOrgCounts,
    PortfolioSummaryOut,
)
from app.services.portfolio import monitoring_health, recent_activity, summarize

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummaryOut)
def portfolio_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSummaryOut:
    s = summarize(db, user.tenant_id)
    leader = s.highest_exposure
    return PortfolioSummaryOut(
        organizations=PortfolioOrgCounts(
            total=s.organizations_total, archived=s.organizations_archived
        ),
        investigations_total=s.investigations_total,
        investigations_by_status=s.investigations_by_status,
        assessed_investigations=s.assessed_investigations,
        exposure_distribution=s.exposure_distribution,
        highest_exposure=(
            ExposureLeaderOut(
                investigation_id=leader.investigation_id,
                organization_id=leader.organization_id,
                score=leader.score, grade=leader.grade, label=leader.label,
            )
            if leader
            else None
        ),
        open_alerts=s.open_alerts,
        monitoring_enabled=s.monitoring_enabled,
        monitoring_by_interval=s.monitoring_by_interval,
    )


@router.get("/activity", response_model=list[ActivityItemOut])
def portfolio_activity(
    limit: int = Query(50, ge=1, le=200),
    material: bool = Query(False, description="Only material (alert-worthy) events."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityItemOut]:
    items = recent_activity(db, user.tenant_id, limit=limit, material_only=material)
    return [
        ActivityItemOut(
            id=it.event.id,
            investigation_id=it.event.investigation_id,
            organization_id=it.event.organization_id,
            organization_name=it.organization_name,
            change_type=it.event.change_type,
            entity_type=it.event.entity_type,
            entity_key=it.event.entity_key,
            title=it.event.title,
            severity=it.event.severity,
            detail=it.event.detail or {},
            is_material=it.is_material,
            run_at=it.event.run_at,
            acknowledged_at=it.event.acknowledged_at,
            created_at=it.event.created_at,
        )
        for it in items
    ]


@router.get("/monitoring-health", response_model=list[MonitoringHealthItemOut])
def portfolio_monitoring_health(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MonitoringHealthItemOut]:
    rows = monitoring_health(db, user.tenant_id)
    return [
        MonitoringHealthItemOut(
            investigation_id=m.investigation_id,
            organization_id=m.organization_id,
            organization_name=m.organization_name,
            interval=m.interval,
            status=m.status,
            last_run=m.last_run,
            next_due_at=m.next_due_at,
            state=m.state,
        )
        for m in rows
    ]
