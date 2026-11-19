"""Organization CRUD (SMPLSGHT-13). Every query is tenant-scoped (SMPLSGHT-9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_writer
from app.models import Organization, User
from app.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def _get_owned(db: Session, org_id: str, tenant_id: str) -> Organization:
    org = db.get(Organization, org_id)
    # Tenant check folded into the lookup: never reveal another tenant's rows.
    if org is None or org.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    return org


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_org(
    body: OrganizationCreate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Organization:
    org = Organization(tenant_id=user.tenant_id, **body.model_dump())
    db.add(org)
    db.flush()
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="organization.create", target=org.id, detail={"name": org.name})
    db.commit()
    db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationOut])
def list_orgs(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Organization]:
    stmt = select(Organization).where(Organization.tenant_id == user.tenant_id)
    if not include_archived:
        stmt = stmt.where(Organization.archived.is_(False))
    return list(db.scalars(stmt))


@router.get("/{org_id}", response_model=OrganizationOut)
def get_org(
    org_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    return _get_owned(db, org_id, user.tenant_id)


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_org(
    org_id: str,
    body: OrganizationUpdate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> Organization:
    org = _get_owned(db, org_id, user.tenant_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="organization.update", target=org.id)
    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_org(
    org_id: str,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> None:
    org = _get_owned(db, org_id, user.tenant_id)
    org.archived = True  # soft-delete
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="organization.archive", target=org.id)
    db.commit()
