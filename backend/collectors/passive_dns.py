"""Passive-DNS subdomain discovery collector (SMPLSGHT-24).

Complements the Certificate Transparency source with passive-DNS aggregators, so a subdomain
seen by several independent sources accrues confidence through the downstream noisy-OR merge
(SMPLSGHT-31). Passive and keyless: it reads public aggregator APIs and never probes the
target's own infrastructure.

Sources (both keyless):
  - AlienVault OTX passive DNS
  - HackerTarget hostsearch

Each source is queried independently; one source failing yields a PARTIAL run, not a failed
investigation (SMPLSGHT-28).
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

OTX_URL = "https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
HACKERTARGET_URL = "https://api.hackertarget.com/hostsearch/"


def _clean_host(raw: str, apex: str) -> str | None:
    host = (raw or "").strip().lower().rstrip(".").removeprefix("*.")
    if not host or " " in host:
        return None
    if host == apex or host.endswith("." + apex):
        return host
    return None


class PassiveDnsCollector(Collector):
    name = "passive_dns"
    description = "Discovers subdomains from passive-DNS aggregators (OTX, HackerTarget)."
    required_keys = ()  # both sources are keyless
    passive = True

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": "SimpleSight"}
        )

    # --- per-source fetchers: return a list of hostnames, or raise on failure -----------

    def _otx(self, domain: str) -> list[str]:
        resp = self._client.get(OTX_URL.format(domain=domain))
        resp.raise_for_status()
        data = resp.json()
        return [rec.get("hostname", "") for rec in data.get("passive_dns", [])]

    def _hackertarget(self, domain: str) -> list[str]:
        resp = self._client.get(HACKERTARGET_URL, params={"q": domain})
        resp.raise_for_status()
        text = resp.text.strip()
        # Free tier returns a plain-text error (e.g. "API count exceeded") instead of rows.
        if not text:
            raise ValueError("hackertarget: empty response")
        low = text.lower()
        if "," not in text and ("error" in low or "exceeded" in low or "invalid" in low):
            raise ValueError(f"hackertarget: {text[:80]}")
        return [line.split(",", 1)[0] for line in text.splitlines() if line]

    def collect(self, context: CollectionContext) -> CollectorRun:
        apex = context.target.strip().lower().rstrip(".")
        sources = [("otx", self._otx), ("hackertarget", self._hackertarget)]

        results: list[CollectorResult] = []
        seen: set[str] = set()
        errors: list[str] = []
        succeeded = 0

        for label, fetch in sources:
            context.throttle(f"passive-dns-{label}")
            try:
                hosts = fetch(apex)
            except Exception as exc:  # noqa: BLE001 - contain one source's failure
                errors.append(f"{label}: {type(exc).__name__}")
                continue
            succeeded += 1
            for raw in hosts:
                host = _clean_host(raw, apex)
                if host is None or host in seen:
                    continue
                seen.add(host)
                results.append(CollectorResult(
                    asset_type="subdomain" if host != apex else "domain",
                    value=host,
                    provenance=Provenance.now(source=f"passive-dns ({label})", confidence=0.7),
                    attributes={"discovered_via": "passive_dns", "source": label},
                ))

        if succeeded == 0:
            return CollectorRun(outcome=CollectorOutcome.FAILED,
                                reason=f"all passive-DNS sources failed ({'; '.join(errors)})")
        if errors:
            return CollectorRun(outcome=CollectorOutcome.PARTIAL, results=results,
                                reason=f"some sources failed ({'; '.join(errors)})")
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)
