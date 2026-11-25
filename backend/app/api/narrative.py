"""Narrative route (Phase 4 · SMPLSGHT-58). Tenant-scoped, read-only.

  GET /api/investigations/{id}/narrative  -> grounded executive narrative

Deterministic by default; uses the Claude-backed narrator only when the tenant has an API key
configured (secrets manager) and the feature is enabled. Either way the summary is built from
the investigation's own derived findings/exposure/changes — never invented.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ChangeEvent, ChangeType, Investigation, Organization, User
from app.schemas import NarrativeOut
from app.services.narrative import build_payload, generate_narrative
from app.services.scoring import compute_exposure
from app.services.secrets import resolve


def _latest_change_summary(db: Session, inv_id: str, tenant_id: str) -> dict[str, int]:
    """Counts of what changed in the most recent run (appeared / resolved / escalated)."""
    events = list(
        db.scalars(
            select(ChangeEvent).where(
                ChangeEvent.investigation_id == inv_id,
                ChangeEvent.tenant_id == tenant_id,
            )
        )
    )
    if not events:
        return {}
    newest = max(e.run_at for e in events)
    latest = [e for e in events if e.run_at == newest]
    summary = {
        "appeared": sum(1 for e in latest if e.change_type == ChangeType.FINDING_APPEARED.value),
        "resolved": sum(1 for e in latest if e.change_type == ChangeType.FINDING_RESOLVED.value),
        "escalated": sum(
            1 for e in latest
            if e.change_type == ChangeType.FINDING_SEVERITY_CHANGED.value
            and (e.detail or {}).get("escalated")
        ),
    }
    return {k: v for k, v in summary.items() if v}


router = APIRouter(tags=["narrative"])


@router.get("/api/investigations/{inv_id}/narrative", response_model=NarrativeOut)
def get_narrative(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NarrativeOut:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")

    org = db.get(Organization, inv.organization_id)
    target = (org.primary_domain if org else None) or ""
    exposure = compute_exposure(inv.findings)
    payload = build_payload(
        target=target,
        findings=inv.findings,
        exposure=exposure,
        changes=_latest_change_summary(db, inv_id, user.tenant_id),
    )
    api_key = resolve(db, user.tenant_id, settings.narrative_api_key_secret)
    narrative = generate_narrative(payload, api_key=api_key)
    return NarrativeOut(text=narrative.text, mode=narrative.mode, model=narrative.model)
