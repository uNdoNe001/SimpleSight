"""Centralized secrets management for provider API keys (SMPLSGHT-11).

Collectors never read the environment directly. Secrets are resolved here, from two
backends in precedence order:

  1. a tenant-scoped store in the database, encrypted at rest with Fernet; then
  2. an environment fallback, ``<SECRET_ENV_PREFIX><NAME>`` (shared across tenants).

Values are write-only from the API's perspective: they can be set, listed by name, and
deleted, but never read back out — only the collection pipeline decrypts them, in-process,
to populate a collector's ``context.config``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import TenantSecret


class SecretsError(Exception):
    """Raised when a stored secret cannot be decrypted (e.g. the key was rotated)."""


@dataclass
class SecretInfo:
    """Non-sensitive metadata about a configured secret (never the value)."""

    name: str
    source: str  # "tenant" | "env"
    configured: bool
    updated_at: str | None = None


def _fernet() -> Fernet:
    return Fernet(settings.secrets_encryption_key.encode())


def _env_name(name: str) -> str:
    return f"{settings.secret_env_prefix}{name.upper()}"


def set_secret(db: Session, tenant_id: str, name: str, value: str) -> TenantSecret:
    """Create or rotate a tenant secret. The plaintext value is encrypted immediately."""
    token = _fernet().encrypt(value.encode()).decode()
    row = db.scalar(
        select(TenantSecret).where(
            TenantSecret.tenant_id == tenant_id, TenantSecret.name == name
        )
    )
    if row is None:
        row = TenantSecret(tenant_id=tenant_id, name=name, ciphertext=token)
        db.add(row)
    else:
        row.ciphertext = token
    db.flush()
    return row


def delete_secret(db: Session, tenant_id: str, name: str) -> bool:
    row = db.scalar(
        select(TenantSecret).where(
            TenantSecret.tenant_id == tenant_id, TenantSecret.name == name
        )
    )
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def resolve(db: Session, tenant_id: str, name: str) -> str | None:
    """Return the decrypted secret value: tenant store first, then the environment."""
    row = db.scalar(
        select(TenantSecret).where(
            TenantSecret.tenant_id == tenant_id, TenantSecret.name == name
        )
    )
    if row is not None:
        try:
            return _fernet().decrypt(row.ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise SecretsError(
                f"secret '{name}' cannot be decrypted (encryption key changed?)"
            ) from exc
    return os.environ.get(_env_name(name))


def resolve_many(db: Session, tenant_id: str, names: list[str]) -> dict[str, str]:
    """Resolve several secrets, omitting any that are not configured."""
    out: dict[str, str] = {}
    for name in names:
        value = resolve(db, tenant_id, name)
        if value is not None:
            out[name] = value
    return out


def list_secrets(db: Session, tenant_id: str, known_names: list[str]) -> list[SecretInfo]:
    """List configuration status for every secret name the platform knows about, plus any
    extra tenant-stored names — never exposing values."""
    rows = {
        r.name: r
        for r in db.scalars(
            select(TenantSecret).where(TenantSecret.tenant_id == tenant_id)
        )
    }
    names = sorted(set(known_names) | set(rows))
    infos: list[SecretInfo] = []
    for name in names:
        if name in rows:
            infos.append(SecretInfo(name=name, source="tenant", configured=True,
                                    updated_at=rows[name].updated_at.isoformat()
                                    if rows[name].updated_at else None))
        elif os.environ.get(_env_name(name)):
            infos.append(SecretInfo(name=name, source="env", configured=True))
        else:
            infos.append(SecretInfo(name=name, source="tenant", configured=False))
    return infos
