"""Registry of available collectors.

A new collector becomes part of the platform by being added here (and implementing the
`Collector` interface). The discovery-plan generator (SMPLSGHT-16) and the pipeline read
from this registry.
"""

from __future__ import annotations

from collectors.base import Collector
from collectors.certificate_transparency import CertificateTransparencyCollector
from collectors.dns_records import DNSRecordsCollector
from collectors.historical_records import HistoricalRecordsCollector
from collectors.whois_rdap import WhoisRdapCollector


def default_collectors() -> list[Collector]:
    """Instantiate the collectors enabled for the MVP (all passive, all keyless)."""
    return [
        DNSRecordsCollector(),
        CertificateTransparencyCollector(),
        WhoisRdapCollector(),
        HistoricalRecordsCollector(),
    ]


def required_secret_names(collectors: list[Collector] | None = None) -> list[str]:
    """The sorted, de-duplicated provider keys the given (or default) collectors may need.

    Drives the secrets manager (SMPLSGHT-11): these are the names an admin can configure
    and whose presence decides whether a key-gated collector runs or is skipped.
    """
    names: set[str] = set()
    for c in collectors or default_collectors():
        names.update(c.required_keys)
    return sorted(names)
