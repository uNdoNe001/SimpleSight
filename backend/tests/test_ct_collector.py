"""Certificate transparency collector (SMPLSGHT-25/-24), with a fake HTTP client."""

from __future__ import annotations

from collectors.base import CollectionContext, CollectorOutcome
from collectors.certificate_transparency import CertificateTransparencyCollector

CTX = CollectionContext(target="example.com")

SAMPLE = [
    {
        "id": 111,
        "issuer_name": "Let's Encrypt",
        "not_before": "2026-01-01",
        "not_after": "2026-04-01",
        "common_name": "example.com",
        "name_value": "example.com\n*.example.com\napi.example.com",
    },
    {
        "id": 222,
        "issuer_name": "Let's Encrypt",
        "name_value": "api.example.com\nmail.other.com",  # other.com must be filtered out
    },
]


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _Resp(self._payload)


def test_extracts_certs_and_in_scope_hostnames():
    collector = CertificateTransparencyCollector(client=FakeClient(SAMPLE))
    run = collector.collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS

    certs = [r for r in run.results if r.asset_type == "certificate"]
    subs = {r.value for r in run.results if r.asset_type == "subdomain"}
    domains = {r.value for r in run.results if r.asset_type == "domain"}

    assert len(certs) == 2
    # wildcard stripped, apex classified as domain, out-of-scope host dropped, deduped
    assert subs == {"api.example.com"}
    assert domains == {"example.com"}
    assert "mail.other.com" not in subs
    # provenance carries an evidence pointer back to the crt.sh record
    assert any("id=111" in (r.provenance.evidence_ref or "") for r in run.results)


def test_queries_crtsh_with_wildcard_and_json_output():
    client = FakeClient(SAMPLE)
    CertificateTransparencyCollector(client=client).collect(CTX)
    _, params = client.calls[0]
    assert params["q"] == "%.example.com"
    assert params["output"] == "json"
