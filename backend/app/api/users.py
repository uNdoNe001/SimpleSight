"""User management (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import Role, User
from app.schemas import CreateUserRequest, UserOut
from app.security import hash_password
from app.services.audit import record_audit

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> User:
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    user = User(
        tenant_id=admin.tenant_id,  # new users always join the admin's tenant
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.flush()
    record_audit(db, tenant_id=admin.tenant_id, actor_user_id=admin.id,
                 action="user.create", target=user.email, detail={"role": user.role})
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserOut])
def list_users(
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> list[User]:
    return list(db.scalars(select(User).where(User.tenant_id == admin.tenant_id)))
