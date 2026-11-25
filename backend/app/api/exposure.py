"""Exposure-trend route (Phase 5 · SMPLSGHT-65). Tenant-scoped, read-only.

  GET /api/investigations/{id}/exposure-history -> the exposure score series, oldest run first

Points are written per completed run by the collection pipeline (ExposureSnapshot); they are
never created directly through the API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ExposureSnapshot, Investigation, User
from app.schemas import ExposureHistoryPointOut

router = APIRouter(tags=["exposure"])


@router.get(
    "/api/investigations/{inv_id}/exposure-history",
    response_model=list[ExposureHistoryPointOut],
)
def exposure_history(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExposureSnapshot]:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    snaps = list(
        db.scalars(
            select(ExposureSnapshot).where(
                ExposureSnapshot.investigation_id == inv_id,
                ExposureSnapshot.tenant_id == user.tenant_id,
            )
        )
    )
    # Oldest run first — a trend reads left-to-right.
    snaps.sort(key=lambda s: s.run_at.timestamp())
    return snaps
