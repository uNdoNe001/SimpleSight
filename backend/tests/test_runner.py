"""Collection framework: safe execution, skip/fail containment, outcome roll-up."""

from __future__ import annotations

from collectors.base import CollectionContext, CollectorOutcome, CollectorRun
from collectors.runner import overall_outcome, run_collector, run_collectors
from tests.conftest import FakeCollector, make_result

CTX = CollectionContext(target="example.com")


def test_missing_required_key_is_skipped_not_failed():
    c = FakeCollector("needs_key", required_keys=("API_KEY",))
    nr = run_collector(c, CTX)
    assert nr.run.outcome is CollectorOutcome.SKIPPED
    assert "API_KEY" in nr.run.reason


def test_exceptions_are_contained_as_failed():
    c = FakeCollector("boom", raises=RuntimeError("provider down"))
    nr = run_collector(c, CTX)
    assert nr.run.outcome is CollectorOutcome.FAILED
    assert "provider down" in nr.run.reason  # reason preserved, not raised


def test_success_passes_through_results():
    run = CollectorRun(
        outcome=CollectorOutcome.SUCCESS,
        results=[make_result("subdomain", "a.example.com", "crt.sh", 0.8)],
    )
    nr = run_collector(FakeCollector("ok", run=run), CTX)
    assert nr.run.outcome is CollectorOutcome.SUCCESS
    assert len(nr.run.results) == 1


def test_partial_without_reason_gets_default_reason():
    run = CollectorRun(outcome=CollectorOutcome.PARTIAL)
    nr = run_collector(FakeCollector("meh", run=run), CTX)
    assert nr.run.reason  # filled in by the runner


def test_overall_outcome_rollup():
    ok = CollectorRun(outcome=CollectorOutcome.SUCCESS)
    fail = CollectorRun(outcome=CollectorOutcome.FAILED, reason="x")
    skip = CollectorRun(outcome=CollectorOutcome.SKIPPED, reason="x")

    assert overall_outcome([]) is CollectorOutcome.FAILED

    runs = run_collectors([FakeCollector("a", run=fail), FakeCollector("b", run=fail)], CTX)
    assert overall_outcome(runs) is CollectorOutcome.FAILED

    runs = run_collectors([FakeCollector("a", run=ok), FakeCollector("b", run=fail)], CTX)
    assert overall_outcome(runs) is CollectorOutcome.PARTIAL

    runs = run_collectors([FakeCollector("a", run=ok), FakeCollector("b", run=skip)], CTX)
    assert overall_outcome(runs) is CollectorOutcome.PARTIAL

    runs = run_collectors([FakeCollector("a", run=ok), FakeCollector("b", run=ok)], CTX)
    assert overall_outcome(runs) is CollectorOutcome.SUCCESS
