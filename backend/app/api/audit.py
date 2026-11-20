"""Audit-log read API (SMPLSGHT-12). Admin-only, tenant-scoped, read-only.

The write side (`app/services/audit.record_audit`) records auth and collection activity
throughout the app; this exposes that trail for review.

  GET /api/audit?action=&target=&limit=&offset=
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, Role, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(
    action: str | None = Query(default=None, description="exact action filter, e.g. auth.login"),
    target: str | None = Query(default=None, description="exact target id filter"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target:
        stmt = stmt.where(AuditLog.target == target)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))
