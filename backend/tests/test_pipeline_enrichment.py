"""Pipeline second stage (Phase 2 · Story C): discovered subdomains are handed to the
enrichment collectors via scope, and their assets merge into the result. Fully offline."""

from __future__ import annotations

from app.services import pipeline
from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)


class _PrimaryCollector(Collector):
    """Discovers one subdomain in the first pass."""

    name = "fake_primary"

    def collect(self, context: CollectionContext) -> CollectorRun:
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[
            CollectorResult(asset_type="subdomain", value="gone.example.com",
                            provenance=Provenance.now(source="ct", confidence=0.8)),
        ])


class _RecordingEnrichment(Collector):
    """Captures the subdomains it receives and emits a takeover candidate for them."""

    name = "fake_takeover"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def collect(self, context: CollectionContext) -> CollectorRun:
        self.seen = list(context.scope.get("subdomains", []))
        results = [
            CollectorResult(
                asset_type="takeover_candidate", value=sub,
                provenance=Provenance.now(source="dns", confidence=0.85),
                attributes={"subdomain": sub, "service": "GitHub Pages", "dangling": True},
            )
            for sub in self.seen
        ]
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)


def test_enrichment_receives_discovered_subdomains_and_merges():
    enricher = _RecordingEnrichment()
    resp = pipeline.run_investigation(
        "example.com", collectors=[_PrimaryCollector()], enrichment=[enricher],
    )
    # the second stage saw the subdomain the first pass discovered
    assert enricher.seen == ["gone.example.com"]
    # and its asset is merged into the response
    types = {a.asset_type for a in resp.assets}
    assert "takeover_candidate" in types
    assert any(c.collector == "fake_takeover" for c in resp.collectors)


def test_enrichment_skipped_when_no_subdomains():
    class _NoSubs(Collector):
        name = "fake_nosubs"

        def collect(self, context: CollectionContext) -> CollectorRun:
            return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[
                CollectorResult(asset_type="dns_record", value="A 1.2.3.4",
                                provenance=Provenance.now(source="dns", confidence=0.9),
                                attributes={"record_type": "A"}),
            ])

    enricher = _RecordingEnrichment()
    resp = pipeline.run_investigation(
        "example.com", collectors=[_NoSubs()], enrichment=[enricher],
    )
    # no subdomains -> the second stage never ran
    assert enricher.seen == []
    assert all(c.collector != "fake_takeover" for c in resp.collectors)
