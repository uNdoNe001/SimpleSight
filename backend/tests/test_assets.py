"""Normalization + deduplication + confidence combination (SMPLSGHT-30/31)."""

from __future__ import annotations

from app.services.assets import normalize_and_dedup
from collectors.base import CollectorOutcome, CollectorRun
from collectors.runner import NamedRun
from tests.conftest import make_result


def _run(name: str, results, outcome=CollectorOutcome.SUCCESS) -> NamedRun:
    return NamedRun(name, CollectorRun(outcome=outcome, results=results))


def test_same_asset_from_two_sources_is_merged_with_combined_confidence():
    runs = [
        _run("ct", [make_result("subdomain", "a.example.com", "crt.sh", 0.8)]),
        _run("dns", [make_result("subdomain", "A.example.com.", "dns", 0.6)]),  # case/dot variant
    ]
    assets = normalize_and_dedup(runs)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.value == "a.example.com"            # canonicalized
    assert len(asset.sources) == 2                   # provenance from both preserved
    # noisy-OR: 1 - (1-0.8)(1-0.6) = 0.92, and above either input
    assert asset.confidence == 0.92


def test_distinct_assets_are_not_merged():
    runs = [
        _run("ct", [
            make_result("subdomain", "a.example.com", "crt.sh", 0.8),
            make_result("subdomain", "b.example.com", "crt.sh", 0.8),
        ]),
    ]
    assets = normalize_and_dedup(runs)
    assert {a.value for a in assets} == {"a.example.com", "b.example.com"}


def test_failed_and_skipped_runs_contribute_no_assets():
    runs = [
        _run("ct", [make_result("subdomain", "a.example.com", "crt.sh", 0.8)],
             outcome=CollectorOutcome.FAILED),
        _run("dns", [make_result("dns_record", "A 1.2.3.4", "dns", 0.9)],
             outcome=CollectorOutcome.SKIPPED),
    ]
    assert normalize_and_dedup(runs) == []


def test_results_sorted_by_confidence_desc():
    runs = [
        _run("ct", [
            make_result("subdomain", "low.example.com", "crt.sh", 0.5),
            make_result("subdomain", "high.example.com", "crt.sh", 0.95),
        ]),
    ]
    assets = normalize_and_dedup(runs)
    assert [a.value for a in assets] == ["high.example.com", "low.example.com"]
