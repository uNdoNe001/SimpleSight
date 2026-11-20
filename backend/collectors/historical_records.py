"""Historical / public domain records collector (SMPLSGHT-27).

Uses the Internet Archive Wayback Machine CDX API (keyless) to summarize a domain's
historical web presence: how far back it is archived and how recently. Passive: reads
public archive index data only.

Deeper historical DNS/registration history (e.g. SecurityTrails) is a provider-keyed
add-on; this keyless source covers the MVP.
"""

from __future__ import annotations

import httpx

from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)

CDX_URL = "http://web.archive.org/cdx/search/cdx"


def _fmt(ts: str) -> str:
    # Wayback timestamps are YYYYMMDDhhmmss (year with collapse=timestamp:4).
    return f"{ts[0:4]}-{ts[4:6] or '01'}-{ts[6:8] or '01'}" if len(ts) >= 4 else ts


class HistoricalRecordsCollector(Collector):
    name = "historical_records"
    description = "Enumerates historical URLs from public web archives (Wayback CDX)."
    required_keys = ()  # Wayback CDX is keyless
    passive = True

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0, headers={"User-Agent": "SimpleSight"})

    def collect(self, context: CollectionContext) -> CollectorRun:
        domain = context.target.strip().lower().rstrip(".")
        context.throttle("wayback")
        resp = self._client.get(
            CDX_URL,
            params={"url": domain, "output": "json", "fl": "timestamp",
                    "collapse": "timestamp:4"},
        )
        resp.raise_for_status()
        rows = resp.json()  # first row is the header

        timestamps = [r[0] for r in rows[1:] if r and r[0]]
        if not timestamps:
            return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[],
                                reason="no archived snapshots")

        timestamps.sort()
        result = CollectorResult(
            asset_type="archive",
            value=domain,
            provenance=Provenance.now(
                source="wayback (CDX)",
                confidence=0.8,
                evidence_ref=f"https://web.archive.org/web/*/{domain}",
            ),
            attributes={
                "first_snapshot": _fmt(timestamps[0]),
                "last_snapshot": _fmt(timestamps[-1]),
                "years_archived": len(timestamps),
            },
        )
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[result])
