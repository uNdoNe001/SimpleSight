"""Investigation execution: enforce the authorization gate, run collectors, persist.

This wraps the pure collection pipeline (app/services/pipeline.run_investigation) with
persistence, tenancy, the authorization-attestation gate (SMPLSGHT-15), status lifecycle
(SMPLSGHT-17), and asset persistence (SMPLSGHT-29). Still synchronous — the job queue
(SMPLSGHT-18) will move this onto a worker next.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Asset, Investigation, InvestigationStatus, Organization
from app.services.audit import record_audit
from app.services.findings import derive_findings, persist_findings
from app.services.pipeline import run_investigation as run_pipeline
from app.services.secrets import resolve_many
from collectors.registry import required_secret_names


class AuthorizationRequiredError(Exception):
    """Raised when collection is attempted without a recorded authorization attestation."""


def run_and_persist(db: Session, investigation: Investigation, actor_user_id: str) -> Investigation:
    if not investigation.is_authorized:
        raise AuthorizationRequiredError(
            "investigation has no authorization attestation; record one before collecting"
        )

    org = db.get(Organization, investigation.organization_id)
    target = (org.primary_domain if org else None) or ""
    if not target:
        raise ValueError("organization has no primary domain to investigate")

    investigation.status = InvestigationStatus.RUNNING.value
    investigation.started_at = datetime.now(UTC)
    db.flush()

    # Resolve the tenant's provider keys centrally (SMPLSGHT-11); key-gated collectors
    # that remain unconfigured are skipped, not failed.
    config = resolve_many(db, investigation.tenant_id, required_secret_names())
    result = run_pipeline(target, config=config)

    # Replace any prior assets for this investigation (re-run = fresh snapshot).
    investigation.assets.clear()
    db.flush()
    for a in result.assets:
        investigation.assets.append(
            Asset(
                tenant_id=investigation.tenant_id,
                organization_id=investigation.organization_id,
                asset_type=a.asset_type,
                value=a.value,
                confidence=a.confidence,
                sources=[s.model_dump(mode="json") for s in a.sources],
                attributes=a.attributes,
                first_seen=a.first_seen,
                last_seen=a.last_seen,
            )
        )

    # Derive findings from the fresh assets (SMPLSGHT-32/-33). Deterministic rules over the
    # collected evidence — nothing is invented — with analyst triage preserved across re-runs.
    candidates = derive_findings(target, result.assets)
    persist_findings(db, investigation, candidates)

    investigation.status = result.overall_outcome  # success | partial | failed
    investigation.completed_at = datetime.now(UTC)

    record_audit(
        db,
        tenant_id=investigation.tenant_id,
        actor_user_id=actor_user_id,
        action="investigation.run",
        target=investigation.id,
        detail={
            "target": target,
            "outcome": result.overall_outcome,
            "asset_count": result.asset_count,
            "finding_count": len(candidates),
            "collectors": [c.model_dump() for c in result.collectors],
        },
    )
    db.commit()
    db.refresh(investigation)
    return investigation
