"""Executive report routes (SMPLSGHT-41).

  GET /api/investigations/{id}/report.pdf  -> the Executive Intelligence Report as a PDF

Tenant-scoped. A report can only be produced once a collection run has finished (so there
is something to report); draft/running investigations are refused.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Investigation, InvestigationStatus, User
from app.services.audit import record_audit
from app.services.report import build_report_pdf, gather_report_data

router = APIRouter(prefix="/api/investigations", tags=["reports"])

_NOT_READY = {InvestigationStatus.DRAFT.value, InvestigationStatus.RUNNING.value}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "report"


@router.get("/{inv_id}/report.pdf")
def get_investigation_report(
    inv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    inv = db.get(Investigation, inv_id)
    if inv is None or inv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
    if inv.status in _NOT_READY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "run collection and let it finish before generating a report",
        )

    data = gather_report_data(db, inv)
    pdf = build_report_pdf(data)

    record_audit(db, tenant_id=user.tenant_id, actor_user_id=user.id,
                 action="report.generate", target=inv.id,
                 detail={"finding_count": len(data.findings), "format": "pdf"})
    db.commit()

    filename = f"simplesight-{_slug(data.organization_name)}-{inv.id[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
