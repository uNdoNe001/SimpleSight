"""Findings routes (SMPLSGHT-32/-33/-36/-37). Tenant-scoped.

  GET   /api/investigations/{id}/findings   -> list findings for an investigation
  GET   /api/findings/{id}                   -> one finding (with evidence)
  PATCH /api/findings/{id}                    -> update analyst triage status

Findings are produced by the collection run (see app/services/findings.py); they are not
created directly through the API — only triaged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_writer
from app.models import Finding, Investigation, User
from app.schemas import FindingOut, FindingStatusUpdate
from app.services.audit import record_audit

router = APIRouter(tags=["findings"])

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _get_owned_finding(db: Session, finding_id: str, tenant_id: str) -> Finding:
    finding = db.get(Finding, finding_id)
    if finding is None or finding.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finding not found")
    return finding


@router.get("/api/investigations/{inv_id}/findings", response_model=list[FindingOut])
def list_findings(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Finding]:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.investigation_id == inv_id,
                Finding.tenant_id == user.tenant_id,
            )
        )
    )
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), -f.confidence, f.title))
    return findings


@router.get("/api/findings/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Finding:
    return _get_owned_finding(db, finding_id, user.tenant_id)


@router.patch("/api/findings/{finding_id}", response_model=FindingOut)
def update_finding_status(
    finding_id: str,
    body: FindingStatusUpdate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Finding:
    finding = _get_owned_finding(db, finding_id, user.tenant_id)
    finding.status = body.status
    record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="finding.triage",
        target=finding.id,
        detail={"status": body.status},
    )
    db.commit()
    db.refresh(finding)
    return finding
