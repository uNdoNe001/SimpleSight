"""Investigation routes (SMPLSGHT-14/-15/-17). Tenant-scoped; collection is gated on an
authorization attestation.

Flow:
  POST /api/investigations                      -> create a draft
  POST /api/investigations/{id}/authorize       -> record the authorization attestation
  POST /api/investigations/{id}/run             -> run collectors + persist assets
  GET  /api/investigations                      -> list
  GET  /api/investigations/{id}                 -> detail (with assets)

Collection is still synchronous here; the job queue (SMPLSGHT-18) moves /run onto a worker.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_writer
from app.models import Investigation, InvestigationStatus, Organization, User
from app.queue import enqueue_investigation_run
from app.schemas import (
    AuthorizationAttestation,
    DiscoveryPlanOut,
    InvestigationCreate,
    InvestigationDetailOut,
    InvestigationOut,
)
from app.services.audit import record_audit
from app.services.discovery import build_discovery_plan
from app.services.secrets import list_secrets
from collectors.registry import default_collectors, required_secret_names

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


def _get_owned(db: Session, inv_id: str, tenant_id: str) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    return inv


@router.post("", response_model=InvestigationOut, status_code=status.HTTP_201_CREATED)
def create_investigation(
    body: InvestigationCreate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Investigation:
    org = db.get(Organization, body.organization_id)
    if org is None or org.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")

    inv = Investigation(
        tenant_id=user.tenant_id,
        organization_id=org.id,
        assessment_type=body.assessment_type,
        scope=body.scope,
        status=InvestigationStatus.DRAFT.value,
        created_by=user.id,
    )
    db.add(inv)
    db.flush()
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="investigation.create", target=inv.id)
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{inv_id}/authorize", response_model=InvestigationOut)
def authorize_investigation(
    inv_id: str,
    body: AuthorizationAttestation,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Investigation:
    inv = _get_owned(db, inv_id, user.tenant_id)
    if inv.status != InvestigationStatus.DRAFT.value:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "authorization can only be set while the investigation is a draft")
    inv.authorized_by = body.authorized_by
    inv.authorization_scope = body.authorization_scope
    inv.authorized_at = datetime.now(UTC)
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="investigation.authorize", target=inv.id,
                 detail={"authorized_by": body.authorized_by})
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{inv_id}/run", response_model=InvestigationOut, status_code=status.HTTP_202_ACCEPTED)
def run_investigation_endpoint(
    inv_id: str,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Investigation:
    """Enqueue a collection run. Returns 202 with the investigation in `running` status;
    poll GET /api/investigations/{id} for results."""
    inv = _get_owned(db, inv_id, user.tenant_id)

    # Fail fast on the client-correctable problems before enqueuing.
    if not inv.is_authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "record an authorization attestation before collecting")
    if inv.status == InvestigationStatus.RUNNING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "investigation is already running")
    org = db.get(Organization, inv.organization_id)
    if org is None or not org.primary_domain:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "organization has no primary domain to investigate")

    inv.status = InvestigationStatus.RUNNING.value
    inv.started_at = datetime.now(UTC)
    inv.completed_at = None
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="investigation.run.enqueue", target=inv.id)
    db.commit()
    db.refresh(inv)

    enqueue_investigation_run(inv.id)
    return inv


@router.get("", response_model=list[InvestigationOut])
def list_investigations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Investigation]:
    return list(
        db.scalars(select(Investigation).where(Investigation.tenant_id == user.tenant_id))
    )


@router.get("/{inv_id}/plan", response_model=DiscoveryPlanOut)
def get_discovery_plan(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiscoveryPlanOut:
    """Preview the planned collection (SMPLSGHT-16): targets, collectors, and which will be
    skipped for an unconfigured provider key. Available in any state, including draft."""
    inv = _get_owned(db, inv_id, user.tenant_id)
    org = db.get(Organization, inv.organization_id)
    configured = {
        s.name for s in list_secrets(db, user.tenant_id, required_secret_names())
        if s.configured
    }
    plan = build_discovery_plan(
        target=org.primary_domain if org else None,
        additional_targets=list(org.additional_domains) if org and org.additional_domains else [],
        collectors=default_collectors(),
        configured_keys=configured,
    )
    return DiscoveryPlanOut(
        target=plan.target,
        additional_targets=plan.additional_targets,
        passive_only=plan.passive_only,
        enabled_count=plan.enabled_count,
        skipped_count=plan.skipped_count,
        steps=[s.__dict__ for s in plan.steps],
    )


@router.get("/{inv_id}", response_model=InvestigationDetailOut)
def get_investigation(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Investigation:
    return _get_owned(db, inv_id, user.tenant_id)
