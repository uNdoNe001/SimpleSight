"""API request/response models (Pydantic).

Wire shapes for the API. Kept separate from the collector dataclasses and the ORM models.
`*Out` models read from ORM objects via `from_attributes`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from app.services.scoring import compute_exposure

# --- collection / assets ---------------------------------------------------------------

class SourceRef(BaseModel):
    source: str
    collected_at: datetime
    confidence: float
    evidence_ref: str | None = None


class AssetOut(BaseModel):
    """A normalized, deduplicated asset with merged provenance (SMPLSGHT-29/30/31)."""

    model_config = ConfigDict(from_attributes=True)

    asset_type: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceRef]
    first_seen: datetime
    last_seen: datetime
    attributes: dict = Field(default_factory=dict)


class CollectorRunOut(BaseModel):
    collector: str
    outcome: str
    reason: str | None = None
    result_count: int


class RunInvestigationResponse(BaseModel):
    """Output of the pure pipeline (pre-persistence)."""

    target: str
    overall_outcome: str
    collectors: list[CollectorRunOut]
    asset_count: int
    assets: list[AssetOut]
    provider_usage: dict[str, int] = Field(default_factory=dict)


# --- findings --------------------------------------------------------------------------

class FindingOut(BaseModel):
    """A triageable observation derived from assets (SMPLSGHT-32/-33)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    finding_key: str
    finding_type: str
    title: str
    description: str
    severity: str
    confidence: float = Field(ge=0.0, le=1.0)
    classification: str
    status: str
    evidence: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FindingStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|triaged|dismissed)$")


# --- change events ---------------------------------------------------------------------

class ChangeEventOut(BaseModel):
    """One diff between an investigation's previous run and its latest run (SMPLSGHT-50)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    change_type: str
    entity_type: str
    entity_key: str
    title: str
    severity: str | None = None
    detail: dict = Field(default_factory=dict)
    run_at: datetime
    acknowledged_at: datetime | None = None
    created_at: datetime


class ExposureScoreOut(BaseModel):
    """Rolled-up exposure score for an investigation (SMPLSGHT-48)."""

    model_config = ConfigDict(from_attributes=True)

    score: int = Field(ge=0, le=100)
    grade: str
    label: str
    counts: dict[str, int] = Field(default_factory=dict)
    scored_findings: int
    rationale: str


# --- audit log -------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    """An audit-trail entry (SMPLSGHT-12). Read-only, admin-scoped."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str | None
    action: str
    target: str | None
    detail: dict
    created_at: datetime


# --- discovery plan --------------------------------------------------------------------

class PlanStepOut(BaseModel):
    collector: str
    description: str
    passive: bool
    required_keys: list[str]
    enabled: bool
    skip_reason: str | None = None


class DiscoveryPlanOut(BaseModel):
    """Preview of planned collection for an investigation (SMPLSGHT-16)."""

    target: str | None
    additional_targets: list[str]
    passive_only: bool
    enabled_count: int
    skipped_count: int
    steps: list[PlanStepOut]


# --- secrets (provider keys) -----------------------------------------------------------

class SecretSetRequest(BaseModel):
    value: str = Field(min_length=1, max_length=4096)


class SecretInfoOut(BaseModel):
    """Status of a configured secret — never the value itself (SMPLSGHT-11)."""

    name: str
    source: str
    configured: bool
    updated_at: str | None = None


# --- auth ------------------------------------------------------------------------------

class SignupRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="analyst", pattern="^(admin|analyst|readonly)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    email: EmailStr
    role: str


# --- organizations ---------------------------------------------------------------------

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list)
    primary_domain: str | None = None
    additional_domains: list[str] = Field(default_factory=list)
    notes: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    aliases: list[str] | None = None
    primary_domain: str | None = None
    additional_domains: list[str] | None = None
    notes: str | None = None
    archived: bool | None = None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    aliases: list[str]
    primary_domain: str | None
    additional_domains: list[str]
    notes: str | None
    archived: bool
    created_at: datetime


# --- investigations --------------------------------------------------------------------

class InvestigationCreate(BaseModel):
    organization_id: str
    assessment_type: str = Field(min_length=1, max_length=100)
    scope: dict = Field(default_factory=dict)


class AuthorizationAttestation(BaseModel):
    """Recorded before collection may run (SMPLSGHT-15)."""

    authorized_by: str = Field(min_length=1, max_length=255)
    authorization_scope: str = Field(min_length=1)


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    assessment_type: str
    scope: dict
    status: str
    authorized_by: str | None
    authorization_scope: str | None
    authorized_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class InvestigationDetailOut(InvestigationOut):
    assets: list[AssetOut] = Field(default_factory=list)
    findings: list[FindingOut] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def exposure_score(self) -> ExposureScoreOut:
        return ExposureScoreOut.model_validate(compute_exposure(self.findings))
