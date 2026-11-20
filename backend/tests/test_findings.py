"""Findings engine (SMPLSGHT-32/-33) — pure, offline tests over AssetOut inputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app import tasks
from app.models import FindingClassification, FindingSeverity
from app.schemas import AssetOut, SourceRef
from app.services import pipeline
from app.services.findings import derive_findings
from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)
from tests import conftest
from tests.conftest import auth_header, signup

NOW = datetime.now(UTC)


def _asset(asset_type: str, value: str, *, confidence: float = 0.85,
           sources: list[str] | None = None, attributes: dict | None = None) -> AssetOut:
    srcs = sources or ["crt.sh (CT)"]
    return AssetOut(
        asset_type=asset_type,
        value=value,
        confidence=confidence,
        sources=[SourceRef(source=s, collected_at=NOW, confidence=confidence) for s in srcs],
        first_seen=NOW,
        last_seen=NOW,
        attributes=attributes or {},
    )


def _by_type(cands, finding_type):
    return [c for c in cands if c.finding_type == finding_type]


def _dns(record_type: str, data: str) -> AssetOut:
    return _asset("dns_record", f"{record_type} {data}",
                  attributes={"record_type": record_type, "data": data})


def test_dns_hygiene_flags_missing_caa_and_dnssec():
    # Only an A record present -> no CAA, no DNSKEY -> both hygiene findings fire.
    cands = derive_findings("example.com", [_dns("A", "1.2.3.4")])
    caa = _by_type(cands, "missing_caa")
    dnssec = _by_type(cands, "missing_dnssec")
    assert len(caa) == 1 and caa[0].severity is FindingSeverity.LOW
    assert caa[0].classification is FindingClassification.UNVERIFIED
    assert len(dnssec) == 1 and dnssec[0].severity is FindingSeverity.LOW


def test_dns_hygiene_satisfied_emits_nothing():
    assets = [_dns("A", "1.2.3.4"), _dns("CAA", '0 issue "letsencrypt.org"'),
              _dns("DNSKEY", "257 3 13 ...")]
    cands = derive_findings("example.com", assets)
    assert _by_type(cands, "missing_caa") == []
    assert _by_type(cands, "missing_dnssec") == []


def test_dns_hygiene_silent_without_dns_data():
    # No dns_record assets at all (lookup failed) -> never reads as "missing".
    cands = derive_findings("example.com", [_asset("subdomain", "www.example.com")])
    assert _by_type(cands, "missing_caa") == []
    assert _by_type(cands, "missing_dnssec") == []


def _mx() -> AssetOut:
    return _asset("dns_record", "MX 10 mail.example.com",
                  attributes={"record_type": "MX", "data": "10 mail.example.com"})


def _email(mechanism: str, *, present: bool, policy: str | None = None,
           selectors_probed: int = 10) -> AssetOut:
    attrs = {"mechanism": mechanism, "present": present}
    if mechanism == "dmarc":
        attrs["policy"] = policy
    if mechanism == "dkim":
        attrs["selectors_probed"] = list(range(selectors_probed))
    return _asset("email_security", mechanism, confidence=0.9,
                  sources=["dns"], attributes=attrs)


def test_email_posture_flags_missing_dmarc_and_mta_sts():
    assets = [_mx(), _email("dmarc", present=False),
              _email("mta_sts", present=False), _email("dkim", present=True)]
    cands = derive_findings("example.com", assets)
    dmarc = _by_type(cands, "missing_dmarc")
    assert len(dmarc) == 1
    assert dmarc[0].severity is FindingSeverity.MEDIUM
    assert dmarc[0].classification is FindingClassification.UNVERIFIED
    assert len(_by_type(cands, "missing_mta_sts")) == 1
    # DKIM present -> no "no_dkim_observed" finding
    assert _by_type(cands, "no_dkim_observed") == []


def test_email_posture_weak_dmarc_is_confirmed():
    assets = [_mx(), _email("dmarc", present=True, policy="none")]
    weak = _by_type(derive_findings("example.com", assets), "weak_dmarc")
    assert len(weak) == 1
    assert weak[0].severity is FindingSeverity.LOW
    assert weak[0].classification is FindingClassification.CONFIRMED
    # a strong policy produces no DMARC finding at all
    strong = [_mx(), _email("dmarc", present=True, policy="reject")]
    assert _by_type(derive_findings("example.com", strong), "weak_dmarc") == []
    assert _by_type(derive_findings("example.com", strong), "missing_dmarc") == []


def test_email_posture_requires_mx():
    # No MX -> email-posture rules do not fire (parked/non-mail domain).
    assets = [_email("dmarc", present=False), _email("mta_sts", present=False)]
    cands = derive_findings("example.com", assets)
    assert _by_type(cands, "missing_dmarc") == []
    assert _by_type(cands, "missing_mta_sts") == []


def test_sensitive_hostname_high_and_medium():
    assets = [
        _asset("subdomain", "admin.example.com"),
        _asset("subdomain", "staging.example.com"),
        _asset("subdomain", "www.example.com"),  # not sensitive
    ]
    found = _by_type(derive_findings("example.com", assets), "sensitive_hostname")
    by_value = {c.evidence[0]["value"]: c for c in found}
    assert set(by_value) == {"admin.example.com", "staging.example.com"}
    assert by_value["admin.example.com"].severity is FindingSeverity.HIGH
    assert by_value["staging.example.com"].severity is FindingSeverity.MEDIUM


def test_sensitive_hostname_classification_depends_on_corroboration():
    ct_only = _asset("subdomain", "dev.example.com", confidence=0.85, sources=["crt.sh (CT)"])
    corroborated = _asset(
        "subdomain", "vpn.example.com", confidence=0.97, sources=["crt.sh (CT)", "dns"]
    )
    cands = {c.evidence[0]["value"]: c
             for c in _by_type(derive_findings("example.com", [ct_only, corroborated]),
                               "sensitive_hostname")}
    assert cands["dev.example.com"].classification is FindingClassification.UNVERIFIED
    assert cands["vpn.example.com"].classification is FindingClassification.CONFIRMED


def test_expired_registration_is_high_and_confirmed():
    past = (NOW - timedelta(days=5)).date().isoformat()
    whois = _asset("whois", "example.com", confidence=0.9,
                   sources=["rdap"], attributes={"expiration_date": past})
    found = _by_type(derive_findings("example.com", [whois]), "registration_expiry")
    assert len(found) == 1
    assert found[0].severity is FindingSeverity.HIGH
    assert found[0].classification is FindingClassification.CONFIRMED


def test_registration_expiring_soon_vs_far_off():
    soon = _asset("whois", "soon.com", attributes={
        "expiration_date": (NOW + timedelta(days=20)).isoformat()})
    mid = _asset("whois", "mid.com", attributes={
        "expiration_date": (NOW + timedelta(days=50)).isoformat()})
    far = _asset("whois", "far.com", attributes={
        "expiration_date": (NOW + timedelta(days=400)).isoformat()})
    assert _by_type(derive_findings("soon.com", [soon]), "registration_expiry")[0].severity \
        is FindingSeverity.HIGH
    assert _by_type(derive_findings("mid.com", [mid]), "registration_expiry")[0].severity \
        is FindingSeverity.MEDIUM
    assert _by_type(derive_findings("far.com", [far]), "registration_expiry") == []


def test_missing_spf_when_mx_present_and_no_spf_txt():
    assets = [
        _asset("dns_record", "MX 10 mail.example.com", confidence=0.95, sources=["dns"],
               attributes={"record_type": "MX", "data": "10 mail.example.com"}),
        _asset("dns_record", "TXT google-site-verification=abc", confidence=0.95,
               sources=["dns"], attributes={"record_type": "TXT",
                                            "data": "google-site-verification=abc"}),
    ]
    found = _by_type(derive_findings("example.com", assets), "missing_spf")
    assert len(found) == 1
    assert found[0].severity is FindingSeverity.MEDIUM
    assert found[0].classification is FindingClassification.UNVERIFIED


def test_no_spf_finding_when_spf_present():
    assets = [
        _asset("dns_record", "MX 10 mail.example.com", sources=["dns"],
               attributes={"record_type": "MX", "data": "10 mail.example.com"}),
        _asset("dns_record", "TXT v=spf1 include:_spf.google.com ~all", sources=["dns"],
               attributes={"record_type": "TXT", "data": "v=spf1 include:_spf.google.com ~all"}),
    ]
    assert _by_type(derive_findings("example.com", assets), "missing_spf") == []


def test_no_spf_finding_without_mx():
    assets = [_asset("dns_record", "A 1.2.3.4", sources=["dns"],
                     attributes={"record_type": "A", "data": "1.2.3.4"})]
    assert _by_type(derive_findings("example.com", assets), "missing_spf") == []


def test_surface_summary_counts_subdomains():
    assets = [_asset("subdomain", f"h{i}.example.com") for i in range(30)]
    found = _by_type(derive_findings("example.com", assets), "attack_surface_summary")
    assert len(found) == 1
    assert "30 subdomain(s)" in found[0].title
    assert found[0].severity is FindingSeverity.LOW  # >= threshold
    assert len(found[0].evidence) == 10  # capped sample


def test_no_findings_from_empty_assets():
    assert derive_findings("example.com", []) == []


def test_results_sorted_most_severe_first():
    assets = [
        _asset("subdomain", "www.example.com"),  # -> only in summary (info)
        _asset("subdomain", "admin.example.com"),  # high
        _asset("whois", "example.com", attributes={
            "expiration_date": (NOW - timedelta(days=1)).isoformat()}),  # high
    ]
    cands = derive_findings("example.com", assets)
    severities = [c.severity for c in cands]
    # highest severity first, info/summary last
    assert severities[0] in {FindingSeverity.HIGH, FindingSeverity.CRITICAL}
    assert severities[-1] is FindingSeverity.INFO


# --- end-to-end: run -> findings persisted -> listed -> triaged (SMPLSGHT-36/-37) ------

class _FixedCollector(Collector):
    def __init__(self, name: str, results: list[CollectorResult]) -> None:
        self.name = name
        self.required_keys = ()
        self._results = results

    def collect(self, context: CollectionContext) -> CollectorRun:
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=self._results)


def _rich_collectors() -> list[Collector]:
    past = (NOW - timedelta(days=3)).isoformat()
    return [
        _FixedCollector("ct", [
            CollectorResult(asset_type="subdomain", value="admin.example.com",
                            provenance=Provenance.now(source="crt.sh (CT)", confidence=0.85)),
            CollectorResult(asset_type="subdomain", value="www.example.com",
                            provenance=Provenance.now(source="crt.sh (CT)", confidence=0.85)),
        ]),
        _FixedCollector("whois", [
            CollectorResult(asset_type="whois", value="example.com",
                            provenance=Provenance.now(source="rdap", confidence=0.9),
                            attributes={"expiration_date": past, "registrar": "ACME Registrar"}),
        ]),
        _FixedCollector("dns", [
            CollectorResult(asset_type="dns_record", value="MX 10 mail.example.com",
                            provenance=Provenance.now(source="dns", confidence=0.95),
                            attributes={"record_type": "MX", "data": "10 mail.example.com"}),
        ]),
    ]


def _run_investigation(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"],
                            "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    tasks.run_investigation_task(inv["id"])
    return inv["id"]


def test_run_derives_and_lists_findings(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", _rich_collectors)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _run_investigation(client, token)

    detail = client.get(f"/api/investigations/{inv_id}", headers=auth_header(token)).json()
    types = {f["finding_type"] for f in detail["findings"]}
    assert {"sensitive_hostname", "registration_expiry", "missing_spf",
            "attack_surface_summary"} <= types

    listed = client.get(f"/api/investigations/{inv_id}/findings",
                        headers=auth_header(token)).json()
    # severity-sorted: the first finding is high severity
    assert listed[0]["severity"] == "high"
    admin = next(f for f in listed if f["finding_type"] == "sensitive_hostname")
    assert admin["evidence"][0]["value"] == "admin.example.com"
    assert admin["status"] == "open"


def test_triage_status_update_and_carry_over_on_rerun(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", _rich_collectors)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _run_investigation(client, token)

    listed = client.get(f"/api/investigations/{inv_id}/findings",
                        headers=auth_header(token)).json()
    admin = next(f for f in listed if f["finding_type"] == "sensitive_hostname")

    r = client.patch(f"/api/findings/{admin['id']}", headers=auth_header(token),
                     json={"status": "dismissed"})
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"

    # Re-run: findings are regenerated, but analyst triage must survive by finding_key.
    tasks.run_investigation_task(inv_id)
    listed2 = client.get(f"/api/investigations/{inv_id}/findings",
                        headers=auth_header(token)).json()
    admin2 = next(f for f in listed2 if f["finding_type"] == "sensitive_hostname")
    assert admin2["status"] == "dismissed"
    assert admin2["id"] != admin["id"]  # fresh row, preserved triage


def test_findings_are_tenant_isolated(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", _rich_collectors)

    tok_a = signup(client, "TenantA", "a@tenanta.io")
    inv_id = _run_investigation(client, tok_a)
    tok_b = signup(client, "TenantB", "b@tenantb.io")

    assert client.get(f"/api/investigations/{inv_id}/findings",
                      headers=auth_header(tok_b)).status_code == 404
    a_findings = client.get(f"/api/investigations/{inv_id}/findings",
                            headers=auth_header(tok_a)).json()
    fid = a_findings[0]["id"]
    assert client.get(f"/api/findings/{fid}", headers=auth_header(tok_b)).status_code == 404
    assert client.patch(f"/api/findings/{fid}", headers=auth_header(tok_b),
                        json={"status": "triaged"}).status_code == 404
