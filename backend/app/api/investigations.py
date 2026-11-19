"""Investigation API routes (MVP, synchronous).

POST /api/investigations/run — run the passive collectors against a domain and return the
normalized, deduplicated assets with provenance plus per-collector outcomes.

NOTE: this is a thin synchronous slice to exercise the collection framework end to end.
It does not yet persist anything or enforce auth/tenancy — those arrive with SMPLSGHT-8/9
(auth + tenancy) and SMPLSGHT-15 (authorization gate), after which collection moves behind
the job queue (SMPLSGHT-18).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import RunInvestigationRequest, RunInvestigationResponse
from app.services.pipeline import run_investigation

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


@router.post("/run", response_model=RunInvestigationResponse)
def run(request: RunInvestigationRequest) -> RunInvestigationResponse:
    return run_investigation(request.domain)
