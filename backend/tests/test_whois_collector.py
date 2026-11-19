"""WHOIS/RDAP collector (SMPLSGHT-22), with a fake HTTP client."""

from __future__ import annotations

from collectors.base import CollectionContext, CollectorOutcome
from collectors.whois_rdap import WhoisRdapCollector

CTX = CollectionContext(target="example.com")

RDAP_SAMPLE = {
    "ldhName": "EXAMPLE.COM",
    "status": ["client delete prohibited"],
    "events": [
        {"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2026-08-13T04:00:00Z"},
        {"eventAction": "last changed", "eventDate": "2025-08-14T07:01:44Z"},
    ],
    "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}, {"ldhName": "B.IANA-SERVERS.NET"}],
    "entities": [
        {"roles": ["registrar"],
         "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                  ["fn", {}, "text", "RESERVED-Internet Assigned Numbers Authority"]]]},
    ],
}


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload, status_code=200):
        self._resp = _Resp(payload, status_code)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(url)
        return self._resp


def test_parses_registration_details():
    run = WhoisRdapCollector(client=FakeClient(RDAP_SAMPLE)).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert len(run.results) == 1
    attrs = run.results[0].attributes
    assert attrs["registrar"].startswith("RESERVED-Internet")
    assert attrs["registration_date"] == "1995-08-14T04:00:00Z"
    assert attrs["expiration_date"] == "2026-08-13T04:00:00Z"
    assert attrs["nameservers"] == ["a.iana-servers.net", "b.iana-servers.net"]


def test_missing_registration_is_empty_success():
    run = WhoisRdapCollector(client=FakeClient({}, status_code=404)).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []
    assert "no RDAP" in run.reason
