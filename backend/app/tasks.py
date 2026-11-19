"""Background tasks executed by the RQ worker (SMPLSGHT-18).

A task owns its own DB session (it runs in a worker process, outside any request). The
module-level `SessionLocal` is referenced by name so tests can point it at a test engine.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import SessionLocal
from app.models import Investigation, InvestigationStatus
from app.services.audit import record_audit
from app.services.investigations import run_and_persist


def run_investigation_task(investigation_id: str) -> None:
    db = SessionLocal()
    try:
        inv = db.get(Investigation, investigation_id)
        if inv is None:
            return
        try:
            run_and_persist(db, inv, actor_user_id=inv.created_by)
        except Exception as exc:  # noqa: BLE001 - record failure on the investigation
            db.rollback()
            inv = db.get(Investigation, investigation_id)
            if inv is not None:
                inv.status = InvestigationStatus.FAILED.value
                inv.completed_at = datetime.now(UTC)
                record_audit(
                    db,
                    tenant_id=inv.tenant_id,
                    actor_user_id=inv.created_by,
                    action="investigation.run.failed",
                    target=inv.id,
                    detail={"error": f"{type(exc).__name__}: {exc}"},
                )
                db.commit()
    finally:
        db.close()
