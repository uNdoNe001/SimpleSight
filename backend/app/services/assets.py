"""Normalize collector output into canonical, deduplicated assets.

- Normalization (SMPLSGHT-30): map heterogeneous `CollectorResult`s onto a single asset
  shape keyed by (asset_type, canonical value).
- Deduplication (SMPLSGHT-31): the same asset found by multiple sources collapses into
  one record whose provenance is the union of sources, and whose confidence rises with
  corroboration via a noisy-OR combination:  conf = 1 - Π(1 - cᵢ).

Provenance is never discarded: every merged asset retains each contributing source.
"""

from __future__ import annotations

from app.schemas import AssetOut, SourceRef
from collectors.base import CollectorOutcome
from collectors.runner import NamedRun

CONFIDENCE_CAP = 0.99


def _canonical(asset_type: str, value: str) -> tuple[str, str]:
    """Identity used for deduplication. Hostnames are case- and trailing-dot-insensitive."""
    v = value.strip()
    if asset_type in {"domain", "subdomain"}:
        v = v.lower().rstrip(".")
    return (asset_type, v)


def _combine_confidence(confidences: list[float]) -> float:
    product = 1.0
    for c in confidences:
        product *= 1.0 - max(0.0, min(1.0, c))
    return round(min(1.0 - product, CONFIDENCE_CAP), 4)


def normalize_and_dedup(runs: list[NamedRun]) -> list[AssetOut]:
    """Fold all results from successful/partial runs into deduplicated assets."""
    acc: dict[tuple[str, str], dict] = {}

    for named in runs:
        if named.run.outcome in (CollectorOutcome.SKIPPED, CollectorOutcome.FAILED):
            continue
        for result in named.run.results:
            key = _canonical(result.asset_type, result.value)
            p = result.provenance
            ref = SourceRef(
                source=p.source,
                collected_at=p.collected_at,
                confidence=p.confidence,
                evidence_ref=p.evidence_ref,
            )
            entry = acc.get(key)
            if entry is None:
                acc[key] = {
                    "asset_type": key[0],
                    "value": key[1],
                    "sources": [ref],
                    "first_seen": p.collected_at,
                    "last_seen": p.collected_at,
                    "attributes": dict(result.attributes),
                }
            else:
                entry["sources"].append(ref)
                entry["first_seen"] = min(entry["first_seen"], p.collected_at)
                entry["last_seen"] = max(entry["last_seen"], p.collected_at)
                # later attributes fill gaps without clobbering existing values
                for k, val in result.attributes.items():
                    entry["attributes"].setdefault(k, val)

    assets: list[AssetOut] = []
    for entry in acc.values():
        confidence = _combine_confidence([s.confidence for s in entry["sources"]])
        assets.append(AssetOut(confidence=confidence, **entry))

    # deterministic, useful ordering: strongest evidence first
    assets.sort(key=lambda a: (-a.confidence, a.asset_type, a.value))
    return assets
