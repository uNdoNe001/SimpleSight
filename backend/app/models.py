"""SQLAlchemy ORM models.

Every tenant-owned row carries `tenant_id`; the data-access layer (app/repository.py)
always filters by it so cross-tenant reads are impossible (SMPLSGHT-9).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Role(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    READONLY = "readonly"


class InvestigationStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.ANALYST.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    primary_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    additional_domains: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    assessment_type: Mapped[str] = mapped_column(String(100))
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default=InvestigationStatus.DRAFT.value)

    # Authorization attestation (SMPLSGHT-15) — required before collection runs.
    authorized_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorization_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assets: Mapped[list[Asset]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )

    @property
    def is_authorized(self) -> bool:
        return bool(self.authorized_by and self.authorized_at)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id"), index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(50), index=True)
    value: Mapped[str] = mapped_column(String(512))
    confidence: Mapped[float] = mapped_column(default=0.0)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    investigation: Mapped[Investigation] = relationship(back_populates="assets")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
