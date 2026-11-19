"""Authentication routes (SMPLSGHT-8).

Signup creates a new tenant and its first user as Admin. Additional users are added by an
admin via POST /api/users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Role, Tenant, User
from app.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password
from app.services.audit import record_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_token(user: User) -> TokenResponse:
    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return TokenResponse(access_token=token)


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == body.email.lower()))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    tenant = Tenant(name=body.tenant_name)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=Role.ADMIN.value,
    )
    db.add(user)
    db.flush()
    record_audit(db, tenant_id=tenant.id, actor_user_id=user.id, action="auth.signup",
                 target=user.email)
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        # same response whether the email exists or not
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id, action="auth.login")
    db.commit()
    return _issue_token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
