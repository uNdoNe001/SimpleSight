"""Safe collector execution and outcome roll-up.

Runs collectors against a target and guarantees a well-formed outcome for each, even
when a collector raises or a required provider key is missing (SMPLSGHT-28). This is the
synchronous core; the async job-queue wrapper (SMPLSGHT-18) will call into the same
logic from a worker.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorRun,
)


@dataclass
class NamedRun:
    """A collector's run paired with the collector's name, for reporting."""

    collector: str
    run: CollectorRun


def run_collector(collector: Collector, context: CollectionContext) -> NamedRun:
    """Run a single collector, converting missing keys and exceptions into outcomes.

    - Missing required config keys -> SKIPPED (not a failure of the investigation).
    - Any exception raised by the collector -> FAILED with the reason, never propagated.
    """
    missing = collector.missing_keys(context)
    if missing:
        return NamedRun(
            collector.name,
            CollectorRun(
                outcome=CollectorOutcome.SKIPPED,
                reason=f"missing required config: {', '.join(missing)}",
            ),
        )

    try:
        run = collector.collect(context)
    except Exception as exc:  # noqa: BLE001 - deliberately contain collector failures
        return NamedRun(
            collector.name,
            CollectorRun(outcome=CollectorOutcome.FAILED, reason=f"{type(exc).__name__}: {exc}"),
        )

    # A PARTIAL/FAILED/SKIPPED outcome must carry a reason; fill a default if omitted.
    if run.outcome is not CollectorOutcome.SUCCESS and not run.reason:
        run.reason = f"collector reported {run.outcome.value} without a reason"
    return NamedRun(collector.name, run)


def run_collectors(collectors: list[Collector], context: CollectionContext) -> list[NamedRun]:
    """Run each collector in turn. (Concurrency is added with the job queue, SMPLSGHT-18.)"""
    return [run_collector(c, context) for c in collectors]


def overall_outcome(runs: list[NamedRun]) -> CollectorOutcome:
    """Roll individual collector outcomes up into an investigation-level status.

    - FAILED if every collector failed.
    - PARTIAL if some (but not all) failed, or any was skipped alongside successes.
    - SUCCESS if all non-skipped collectors succeeded and at least one ran.
    """
    if not runs:
        return CollectorOutcome.FAILED

    outcomes = [nr.run.outcome for nr in runs]
    failed = [o for o in outcomes if o is CollectorOutcome.FAILED]
    succeeded = [o for o in outcomes if o is CollectorOutcome.SUCCESS]

    if failed and not succeeded:
        return CollectorOutcome.FAILED
    if failed or any(o is CollectorOutcome.SKIPPED for o in outcomes) or any(
        o is CollectorOutcome.PARTIAL for o in outcomes
    ):
        return CollectorOutcome.PARTIAL
    return CollectorOutcome.SUCCESS if succeeded else CollectorOutcome.PARTIAL
