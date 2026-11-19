"""Audit logging helper (SMPLSGHT-12)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    action: str,
    target: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            detail=detail or {},
        )
    )
