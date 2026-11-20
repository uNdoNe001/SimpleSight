"""Technology fingerprint collector (SMPLSGHT-26), with a fake resolver — no real DNS."""

from __future__ import annotations

import dns.resolver

from collectors.base import CollectionContext, CollectorOutcome
from collectors.tech_fingerprint import TechnologyFingerprintCollector

CTX = CollectionContext(target="example.com")


class _Rdata:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text


class _Answer:
    def __init__(self, texts: list[str]) -> None:
        self._items = [_Rdata(t) for t in texts]

    def __iter__(self):
        return iter(self._items)


class FakeResolver:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def resolve(self, target: str, rtype: str):
        if rtype not in self._mapping:
            raise dns.resolver.NoAnswer
        return _Answer(self._mapping[rtype])


def _techs(run) -> dict:
    return {r.value: r for r in run.results}


def test_fingerprints_ns_mx_and_txt_signals():
    resolver = FakeResolver({
        "NS": ["dana.ns.cloudflare.com.", "dan.ns.cloudflare.com."],
        "MX": ["1 aspmx.l.google.com."],
        "TXT": ['"v=spf1 include:_spf.google.com include:amazonses.com ~all"',
                '"google-site-verification=abc123"',
                '"atlassian-domain-verification=xyz"'],
    })
    run = TechnologyFingerprintCollector(resolver=resolver).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    techs = _techs(run)
    assert "Cloudflare" in techs
    assert "Google Workspace" in techs
    assert "Amazon SES" in techs
    assert "Atlassian" in techs
    # evidence is attached and typed
    assert techs["Cloudflare"].attributes["record_type"] == "NS"
    assert techs["Cloudflare"].asset_type == "technology"
    assert "cloudflare" in techs["Cloudflare"].attributes["evidence_record"].lower()


def test_no_signals_yields_no_results():
    resolver = FakeResolver({
        "NS": ["ns1.obscure-registrar.example."],
        "A": ["1.2.3.4"],
    })
    run = TechnologyFingerprintCollector(resolver=resolver).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []


def test_same_tech_from_multiple_records_deduped_by_evidence():
    # Google Workspace appears via both MX and an SPF include -> two distinct evidences.
    resolver = FakeResolver({
        "MX": ["1 aspmx.l.google.com."],
        "TXT": ['"v=spf1 include:_spf.google.com ~all"'],
    })
    run = TechnologyFingerprintCollector(resolver=resolver).collect(CTX)
    gw = [r for r in run.results if r.value == "Google Workspace"]
    assert len(gw) == 2  # one per matched record, deduped by (tech, record)
    assert {r.attributes["record_type"] for r in gw} == {"MX", "TXT"}


def test_resolver_errors_are_contained():
    class Boom:
        def resolve(self, target, rtype):
            raise TimeoutError("dns down")

    run = TechnologyFingerprintCollector(resolver=Boom()).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []
