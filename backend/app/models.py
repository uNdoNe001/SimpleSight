"""SQLAlchemy ORM models.

Every tenant-owned row carries `tenant_id`; the data-access layer (app/repository.py)
always filters by it so cross-tenant reads are impossible (SMPLSGHT-9).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
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


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingClassification(str, Enum):
    """Whether a finding rests on authoritative/corroborated evidence (SMPLSGHT-33)."""

    CONFIRMED = "confirmed"  # positive, authoritative or multi-source evidence
    UNVERIFIED = "unverified"  # single passive signal or inference from absence


class FindingStatus(str, Enum):
    """Analyst triage state. Set by people, preserved across re-runs."""

    OPEN = "open"
    TRIAGED = "triaged"
    DISMISSED = "dismissed"


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

    # Continuous monitoring (SMPLSGHT-52): when enabled, the investigation is eligible for
    # periodic re-collection on `monitoring_interval` (a key into monitoring.INTERVALS).
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    monitoring_interval: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assets: Mapped[list[Asset]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    findings: Mapped[list[Finding]] = relationship(
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


class Finding(Base):
    """A triageable observation derived deterministically from collected assets.

    Findings are produced by the rule engine in `app/services/findings.py`, never invented:
    each one carries an `evidence` envelope pointing at the concrete assets that
    substantiate it (SMPLSGHT-32). `classification` records whether that evidence is
    authoritative/corroborated or a single unverified signal (SMPLSGHT-33). `finding_key`
    is a stable identity so analyst triage (`status`) survives re-runs.
    """

    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id"), index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    finding_key: Mapped[str] = mapped_column(String(255), index=True)
    finding_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default=FindingSeverity.INFO.value)
    confidence: Mapped[float] = mapped_column(default=0.0)
    classification: Mapped[str] = mapped_column(
        String(20), default=FindingClassification.UNVERIFIED.value
    )
    status: Mapped[str] = mapped_column(String(20), default=FindingStatus.OPEN.value)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    investigation: Mapped[Investigation] = relationship(back_populates="findings")


class ChangeType(str, Enum):
    """A difference between an investigation's previous run and its latest run (SMPLSGHT-50)."""

    ASSET_ADDED = "asset_added"
    ASSET_REMOVED = "asset_removed"
    FINDING_APPEARED = "finding_appeared"
    FINDING_RESOLVED = "finding_resolved"
    FINDING_SEVERITY_CHANGED = "finding_severity_changed"


class ChangeEvent(Base):
    """An append-only record of what changed between two runs of an investigation.

    Produced deterministically by diffing the prior run's assets/findings against the fresh
    run (`app/services/changes.py`) — never invented. Events from one re-run share `run_at`,
    which lets the API group "what changed in the latest run". Material changes (a new
    high/critical finding) seed alerts (SMPLSGHT-53); `acknowledged_at` carries analyst
    acknowledgement forward like finding triage.
    """

    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id"), index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    change_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(20))  # "asset" | "finding"
    entity_key: Mapped[str] = mapped_column(String(512), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class NotificationChannel(Base):
    """An outbound destination for alerts (Phase 4 · SMPLSGHT-56).

    One per tenant row; `channel_type` is "webhook" for now. The optional `signing_secret`
    (HMAC-SHA256 over the payload) is write-only — set and used for signing, never returned by
    the API and never logged. Delivery is best-effort: a failing channel is audited, not fatal.
    """

    __tablename__ = "notification_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    channel_type: Mapped[str] = mapped_column(String(20), default="webhook")
    target: Mapped[str] = mapped_column(String(1024))  # webhook URL
    signing_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TenantSecret(Base):
    """A provider API key (or similar secret) scoped to a tenant (SMPLSGHT-11).

    The value is stored encrypted at rest (Fernet) in `ciphertext` and is never returned
    through the API — only set, listed by name, and deleted. The collection pipeline
    resolves these into a collector's `context.config` at run time.
    """

    __tablename__ = "tenant_secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tenant_secret"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
