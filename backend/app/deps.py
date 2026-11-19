"""Request dependencies: authentication and role enforcement."""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Role, User
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return user


def require_role(*allowed: Role) -> Callable[[User], User]:
    """Dependency factory: require the current user to hold one of `allowed` roles."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in {r.value for r in allowed} and user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return _dep


# Convenience: anything that mutates requires at least Analyst.
def require_writer(user: User = Depends(get_current_user)) -> User:
    if user.role == Role.READONLY or user.role == Role.READONLY.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "read-only users cannot modify data")
    return user
