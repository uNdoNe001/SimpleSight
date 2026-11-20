"""Passive-DNS subdomain collector (SMPLSGHT-24), with a fake HTTP client — no network."""

from __future__ import annotations

import httpx

from collectors.base import CollectionContext, CollectorOutcome
from collectors.passive_dns import HACKERTARGET_URL, OTX_URL, PassiveDnsCollector

CTX = CollectionContext(target="example.com")


class _Resp:
    def __init__(self, *, json_data=None, text="", status=200):
        self._json = json_data
        self.text = text
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class FakeClient:
    """Routes GETs to canned responses keyed by a URL fragment."""

    def __init__(self, routes: dict):
        self._routes = routes

    def get(self, url, params=None):
        for frag, resp in self._routes.items():
            if frag in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return _Resp(text="", status=404)


def _otx(hosts):
    return _Resp(json_data={"passive_dns": [{"hostname": h} for h in hosts]})


def test_merges_subdomains_from_both_sources():
    client = FakeClient({
        "otx.alienvault.com": _otx(["api.example.com", "www.example.com", "evil.other.com"]),
        "hackertarget.com": _Resp(text="www.example.com,1.2.3.4\nvpn.example.com,5.6.7.8"),
    })
    run = PassiveDnsCollector(client=client).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    values = {r.value for r in run.results}
    # out-of-scope host dropped; in-scope union deduped
    assert values == {"api.example.com", "www.example.com", "vpn.example.com"}
    assert all(r.asset_type == "subdomain" for r in run.results)


def test_partial_when_one_source_fails():
    client = FakeClient({
        "otx.alienvault.com": _otx(["api.example.com"]),
        "hackertarget.com": _Resp(text="API count exceeded"),  # error, no comma
    })
    run = PassiveDnsCollector(client=client).collect(CTX)
    assert run.outcome is CollectorOutcome.PARTIAL
    assert "hackertarget" in run.reason
    assert {r.value for r in run.results} == {"api.example.com"}


def test_failed_when_all_sources_fail():
    client = FakeClient({
        "otx.alienvault.com": httpx.ConnectError("down"),
        "hackertarget.com": _Resp(text="error: invalid"),
    })
    run = PassiveDnsCollector(client=client).collect(CTX)
    assert run.outcome is CollectorOutcome.FAILED
    assert run.results == []


def test_apex_is_typed_as_domain():
    client = FakeClient({
        "otx.alienvault.com": _otx(["example.com"]),
        "hackertarget.com": _Resp(text="example.com,1.2.3.4"),
    })
    run = PassiveDnsCollector(client=client).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert [r.asset_type for r in run.results] == ["domain"]  # deduped to one apex entry


def test_urls_are_the_expected_keyless_endpoints():
    # guards against accidentally swapping in a keyed provider
    assert "otx.alienvault.com" in OTX_URL
    assert "api.hackertarget.com" in HACKERTARGET_URL
