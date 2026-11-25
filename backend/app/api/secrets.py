"""Secrets (provider API key) management routes (SMPLSGHT-11). Admin-only, tenant-scoped.

  GET    /api/secrets         -> status of every known provider key (never values)
  PUT    /api/secrets/{name}  -> set or rotate a key (write-only)
  DELETE /api/secrets/{name}  -> remove a key

Values are never returned by the API; only the collection pipeline decrypts them in-process.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.deps import require_role
from app.models import Role, User
from app.schemas import SecretInfoOut, SecretSetRequest
from app.services import secrets as secrets_svc
from app.services.audit import record_audit
from collectors.registry import required_secret_names


def _known_names() -> list[str]:
    """Provider keys the collectors need, plus the optional Claude narrative key (SMPLSGHT-58)."""
    names = list(required_secret_names())
    if settings.narrative_api_key_secret not in names:
        names.append(settings.narrative_api_key_secret)
    return names

router = APIRouter(prefix="/api/secrets", tags=["secrets"])

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "secret name must be 1–100 chars of [A-Za-z0-9_.-]",
        )


@router.get("", response_model=list[SecretInfoOut])
def list_secrets(
    user: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> list[SecretInfoOut]:
    infos = secrets_svc.list_secrets(db, user.tenant_id, _known_names())
    return [SecretInfoOut(**info.__dict__) for info in infos]


@router.put("/{name}", response_model=SecretInfoOut)
def set_secret(
    name: str,
    body: SecretSetRequest,
    user: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> SecretInfoOut:
    _validate_name(name)
    secrets_svc.set_secret(db, user.tenant_id, name, body.value)
    # Never log the value — only the fact that it was set.
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="secret.set", target=name)
    db.commit()
    return SecretInfoOut(name=name, source="tenant", configured=True)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_secret(
    name: str,
    user: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    _validate_name(name)
    if not secrets_svc.delete_secret(db, user.tenant_id, name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="secret.delete", target=name)
    db.commit()
