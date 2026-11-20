"""Investigation pipeline: run collectors, then normalize + dedup into assets.

This is the synchronous MVP path. When the job queue lands (SMPLSGHT-18), an investigation
will be enqueued and a worker will call `run_investigation`, persisting results instead of
returning them inline. The authorization-attestation gate (SMPLSGHT-15) sits in front of
this call in the request flow.
"""

from __future__ import annotations

from app.schemas import CollectorRunOut, RunInvestigationResponse
from app.services.assets import normalize_and_dedup
from collectors.base import CollectionContext, Collector
from collectors.registry import default_collectors
from collectors.runner import overall_outcome, run_collectors


def run_investigation(
    domain: str,
    collectors: list[Collector] | None = None,
    config: dict | None = None,
) -> RunInvestigationResponse:
    """Run the collectors against `domain`.

    `config` carries resolved provider keys/limits into each collector's context
    (SMPLSGHT-11): a collector whose `required_keys` are absent here is SKIPPED, not failed.
    """
    context = CollectionContext(target=domain.strip().lower().rstrip("."), config=config or {})
    runs = run_collectors(collectors or default_collectors(), context)
    assets = normalize_and_dedup(runs)

    collector_outs = [
        CollectorRunOut(
            collector=nr.collector,
            outcome=nr.run.outcome.value,
            reason=nr.run.reason,
            result_count=len(nr.run.results),
        )
        for nr in runs
    ]

    return RunInvestigationResponse(
        target=context.target,
        overall_outcome=overall_outcome(runs).value,
        collectors=collector_outs,
        asset_count=len(assets),
        assets=assets,
    )
