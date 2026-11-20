"""Subdomain-takeover collector (Phase 2 · Story C), with a fake resolver — no DNS."""

from __future__ import annotations

import dns.resolver

from collectors.base import CollectionContext, CollectorOutcome
from collectors.subdomain_takeover import SubdomainTakeoverCollector, match_service


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

    def __getitem__(self, i):
        return self._items[i]


class FakeResolver:
    """Maps (name, rtype) -> list of values, an Exception, or absent (NoAnswer)."""

    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def resolve(self, name: str, rtype: str):
        value = self._mapping.get((name, rtype), dns.resolver.NoAnswer())
        if isinstance(value, Exception):
            raise value
        return _Answer(value)


def _ctx(subs: list[str]) -> CollectionContext:
    return CollectionContext(target="example.com", scope={"subdomains": subs})


def test_match_service_recognizes_fingerprints():
    assert match_service("myrepo.github.io.") == "GitHub Pages"
    assert match_service("foo.s3.amazonaws.com") == "AWS S3"
    assert match_service("legit.example.com") is None


def test_dangling_cname_is_flagged_high_confidence():
    # subdomain -> github.io CNAME, and that target does NOT resolve (NXDOMAIN) -> dangling.
    resolver = FakeResolver({
        ("gone.example.com", "CNAME"): ["ghost-repo.github.io."],
        ("ghost-repo.github.io", "A"): dns.resolver.NXDOMAIN(),
    })
    run = SubdomainTakeoverCollector(resolver=resolver).collect(_ctx(["gone.example.com"]))
    assert run.outcome is CollectorOutcome.SUCCESS
    assert len(run.results) == 1
    attrs = run.results[0].attributes
    assert attrs["service"] == "GitHub Pages"
    assert attrs["dangling"] is True
    assert run.results[0].provenance.confidence == 0.85


def test_live_delegation_is_candidate_but_not_dangling():
    resolver = FakeResolver({
        ("shop.example.com", "CNAME"): ["acme.myshopify.com."],
        ("acme.myshopify.com", "A"): ["1.2.3.4"],  # target resolves -> not dangling
    })
    run = SubdomainTakeoverCollector(resolver=resolver).collect(_ctx(["shop.example.com"]))
    attrs = run.results[0].attributes
    assert attrs["service"] == "Shopify"
    assert attrs["dangling"] is False
    assert attrs["target_resolves"] is True


def test_non_fingerprinted_cname_is_ignored():
    resolver = FakeResolver({("www.example.com", "CNAME"): ["edge.example.net."]})
    run = SubdomainTakeoverCollector(resolver=resolver).collect(_ctx(["www.example.com"]))
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []


def test_no_cname_is_ignored():
    # No CNAME record (NoAnswer) -> nothing to check.
    run = SubdomainTakeoverCollector(resolver=FakeResolver({})).collect(_ctx(["a.example.com"]))
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []


def test_all_lookups_failing_is_failed():
    resolver = FakeResolver({("a.example.com", "CNAME"): dns.resolver.Timeout("down")})
    run = SubdomainTakeoverCollector(resolver=resolver).collect(_ctx(["a.example.com"]))
    assert run.outcome is CollectorOutcome.FAILED
    assert run.results == []


def test_empty_subdomain_list_succeeds_quietly():
    run = SubdomainTakeoverCollector(resolver=FakeResolver({})).collect(_ctx([]))
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []
