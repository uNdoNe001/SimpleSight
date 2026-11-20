"""Certificate Transparency collector (SMPLSGHT-25).

Queries CT logs (via crt.sh, which needs no API key) for certificates issued to the
target domain, and emits both the certificates and the hostnames found in their SANs as
candidate subdomain assets (SMPLSGHT-24's subdomain discovery is powered by CT in the
MVP; additional passive-DNS sources can be added later).

Passive: reads public CT log data only.
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

CRT_SH_URL = "https://crt.sh/"


def _clean_host(raw: str, apex: str) -> str | None:
    host = raw.strip().lower().rstrip(".")
    host = host.removeprefix("*.")
    if not host or " " in host:
        return None
    # keep only hostnames within the target domain
    if host == apex or host.endswith("." + apex):
        return host
    return None


class CertificateTransparencyCollector(Collector):
    name = "certificate_transparency"
    description = "Queries public Certificate Transparency logs (crt.sh) for certs and SAN hostnames."
    required_keys = ()  # crt.sh is keyless
    passive = True

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0, headers={"User-Agent": "SimpleSight"})

    def collect(self, context: CollectionContext) -> CollectorRun:
        apex = context.target.strip().lower().rstrip(".")
        resp = self._client.get(CRT_SH_URL, params={"q": f"%.{apex}", "output": "json"})
        resp.raise_for_status()
        entries = resp.json()  # list of cert records

        results: list[CollectorResult] = []
        seen_hosts: set[str] = set()

        for entry in entries:
            cert_id = entry.get("id")
            issuer = entry.get("issuer_name")
            not_before = entry.get("not_before")
            not_after = entry.get("not_after")

            results.append(
                CollectorResult(
                    asset_type="certificate",
                    value=str(cert_id),
                    provenance=Provenance.now(
                        source="crt.sh (CT)",
                        confidence=0.9,
                        evidence_ref=f"{CRT_SH_URL}?id={cert_id}" if cert_id else None,
                    ),
                    attributes={
                        "issuer": issuer,
                        "not_before": not_before,
                        "not_after": not_after,
                        "common_name": entry.get("common_name"),
                    },
                )
            )

            # SANs arrive newline-separated in name_value
            for raw in (entry.get("name_value") or "").splitlines():
                host = _clean_host(raw, apex)
                if host and host not in seen_hosts:
                    seen_hosts.add(host)
                    results.append(
                        CollectorResult(
                            asset_type="subdomain" if host != apex else "domain",
                            value=host,
                            provenance=Provenance.now(
                                source="crt.sh (CT)",
                                confidence=0.85,
                                evidence_ref=f"{CRT_SH_URL}?id={cert_id}" if cert_id else None,
                            ),
                            attributes={"discovered_via": "certificate_transparency"},
                        )
                    )

        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)
