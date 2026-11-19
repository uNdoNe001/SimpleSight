"""DNS records collector (SMPLSGHT-23), with a fake resolver — no real DNS queries."""

from __future__ import annotations

import dns.resolver

from collectors.base import CollectionContext, CollectorOutcome
from collectors.dns_records import DNSRecordsCollector

CTX = CollectionContext(target="example.com")


class _Rdata:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text


class _RRset:
    ttl = 300


class _Answer:
    def __init__(self, texts: list[str]) -> None:
        self._items = [_Rdata(t) for t in texts]
        self.rrset = _RRset()

    def __iter__(self):
        return iter(self._items)


class FakeResolver:
    """Maps record type -> list of values, a raised exception, or absent (NoAnswer)."""

    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def resolve(self, target: str, rtype: str):
        if rtype not in self._mapping:
            raise dns.resolver.NoAnswer
        value = self._mapping[rtype]
        if isinstance(value, Exception):
            raise value
        return _Answer(value)


def test_resolves_present_records_and_ignores_absent():
    collector = DNSRecordsCollector(resolver=FakeResolver({"A": ["1.2.3.4"], "MX": ["10 mail"]}))
    run = collector.collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    values = {r.value for r in run.results}
    assert values == {"A 1.2.3.4", "MX 10 mail"}
    a = next(r for r in run.results if r.attributes["record_type"] == "A")
    assert a.attributes["ttl"] == 300
    assert a.attributes["domain"] == "example.com"


def test_partial_when_some_lookups_error():
    collector = DNSRecordsCollector(
        resolver=FakeResolver({"A": ["1.2.3.4"], "TXT": TimeoutError("slow")})
    )
    run = collector.collect(CTX)
    assert run.outcome is CollectorOutcome.PARTIAL
    assert "TXT" in run.reason
    assert any(r.value == "A 1.2.3.4" for r in run.results)


def test_failed_when_all_lookups_error():
    collector = DNSRecordsCollector(
        resolver=FakeResolver({rt: TimeoutError("down") for rt in
                               ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA")})
    )
    run = collector.collect(CTX)
    assert run.outcome is CollectorOutcome.FAILED
    assert run.results == []
