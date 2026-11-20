"""Email-security posture collector (Phase 2 · Story A), with a fake resolver — no DNS."""

from __future__ import annotations

import dns.resolver

from collectors.base import CollectionContext, CollectorOutcome
from collectors.email_security import EmailSecurityCollector

CTX = CollectionContext(target="example.com")
# A small, fixed selector set keeps the fake-resolver mappings legible.
SELECTORS = ("default", "google")


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
    """Maps a fully-qualified name -> list of TXT strings, an Exception, or absent."""

    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def resolve(self, name: str, rtype: str):
        assert rtype == "TXT"
        if name not in self._mapping:
            raise dns.resolver.NoAnswer  # authoritative absence
        value = self._mapping[name]
        if isinstance(value, Exception):
            raise value
        return _Answer(value)


def _collector(mapping: dict) -> EmailSecurityCollector:
    return EmailSecurityCollector(resolver=FakeResolver(mapping), selectors=SELECTORS)


def _by_mech(run) -> dict:
    return {r.attributes["mechanism"]: r.attributes for r in run.results}


def test_detects_full_posture():
    run = _collector({
        "_dmarc.example.com": ['"v=DMARC1; p=reject; rua=mailto:x@example.com"'],
        "_mta-sts.example.com": ['"v=STSv1; id=20260101"'],
        "default._bimi.example.com": ['"v=BIMI1; l=https://example.com/logo.svg"'],
        "default._domainkey.example.com": ['"v=DKIM1; k=rsa; p=MIGf..."'],
    }).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    mech = _by_mech(run)
    assert mech["dmarc"]["present"] is True
    assert mech["dmarc"]["policy"] == "reject"
    assert mech["mta_sts"]["present"] is True
    assert mech["bimi"]["present"] is True
    assert mech["dkim"]["present"] is True
    assert mech["dkim"]["selectors"] == ["default"]


def test_absent_policies_are_recorded_not_errored():
    # Nothing in the mapping -> every name NoAnswer -> authoritative "absent".
    run = _collector({}).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    mech = _by_mech(run)
    assert mech["dmarc"]["present"] is False
    assert mech["dmarc"]["policy"] is None
    assert mech["mta_sts"]["present"] is False
    assert mech["dkim"]["present"] is False
    assert mech["dkim"]["selectors"] == []


def test_dmarc_monitor_only_policy_parsed():
    run = _collector({"_dmarc.example.com": ['"v=DMARC1; p=none"']}).collect(CTX)
    assert _by_mech(run)["dmarc"]["policy"] == "none"


def test_partial_when_one_lookup_errors():
    run = _collector({
        "_dmarc.example.com": dns.resolver.Timeout("slow"),
        "_mta-sts.example.com": ['"v=STSv1; id=1"'],
    }).collect(CTX)
    assert run.outcome is CollectorOutcome.PARTIAL
    assert "_dmarc" in run.reason
    # the mechanisms that did resolve are still reported
    assert "mta_sts" in _by_mech(run)
    assert "dmarc" not in _by_mech(run)


def test_failed_when_everything_errors():
    boom = dns.resolver.Timeout("down")
    run = _collector({
        "_dmarc.example.com": boom,
        "_mta-sts.example.com": boom,
        "default._bimi.example.com": boom,
        "default._domainkey.example.com": boom,
        "google._domainkey.example.com": boom,
    }).collect(CTX)
    assert run.outcome is CollectorOutcome.FAILED
    assert run.results == []
