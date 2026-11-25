"""Scheduled monitoring tick (Phase 4 · SMPLSGHT-57).

Selects every monitored investigation that is due for re-collection (SMPLSGHT-52) and enqueues
a run for it, across all tenants. Intended to be driven by an external scheduler — cron, a
systemd timer, or a container sidecar — e.g. every 15 minutes:

    */15 * * * *  cd /app/backend && python -m workers.monitor_tick

It is idempotent: an investigation already `running` is never re-selected, and the per-run
interval keeps a just-collected investigation from being picked again until it is due.
"""

from __future__ import annotations

import logging
import sys

from app.db import SessionLocal
from app.services.monitoring import TickResult, enqueue_due

logger = logging.getLogger("simplesight.monitor_tick")


def run_tick(db) -> TickResult:
    """Enqueue all due investigations in a single pass (tenant-agnostic)."""
    return enqueue_due(db)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    db = SessionLocal()
    try:
        result = run_tick(db)
    finally:
        db.close()
    logger.info(
        "monitoring tick: due=%d enqueued=%d skipped=%d",
        result.due, len(result.enqueued), len(result.skipped),
    )
    if result.skipped:
        logger.warning("skipped (no primary domain): %s", ", ".join(result.skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
