"""DNS record enumeration collector (SMPLSGHT-23).

Passive: resolves standard record types for the target domain via DNS. No brute-forcing
and nothing that touches the target's own infrastructure beyond ordinary resolution.
"""

from __future__ import annotations

import dns.rdatatype
import dns.resolver

from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)

RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA")


class DNSRecordsCollector(Collector):
    name = "dns_records"
    description = "Resolves standard DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA)."
    required_keys = ()  # keyless
    passive = True

    def __init__(self, resolver: dns.resolver.Resolver | None = None) -> None:
        self._resolver = resolver or dns.resolver.Resolver()

    def collect(self, context: CollectionContext) -> CollectorRun:
        results: list[CollectorResult] = []
        errors: list[str] = []

        for rtype in RECORD_TYPES:
            context.throttle("dns")
            try:
                answer = self._resolver.resolve(context.target, rtype)
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                continue  # absence of a record is not an error
            except Exception as exc:  # noqa: BLE001 - record one type's failure, keep going
                errors.append(f"{rtype}: {type(exc).__name__}")
                continue

            ttl = getattr(answer.rrset, "ttl", None)
            for item in answer:
                results.append(
                    CollectorResult(
                        asset_type="dns_record",
                        value=f"{rtype} {item.to_text()}",
                        provenance=Provenance.now(source="dns", confidence=0.95),
                        attributes={
                            "record_type": rtype,
                            "data": item.to_text(),
                            "ttl": ttl,
                            "domain": context.target,
                        },
                    )
                )

        if errors and not results:
            return CollectorRun(
                outcome=CollectorOutcome.FAILED,
                reason=f"all lookups failed ({'; '.join(errors)})",
            )
        if errors:
            return CollectorRun(
                outcome=CollectorOutcome.PARTIAL,
                results=results,
                reason=f"some lookups failed ({'; '.join(errors)})",
            )
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)
