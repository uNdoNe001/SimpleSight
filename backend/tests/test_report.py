"""Executive report (SMPLSGHT-39/-40/-41) — pure PDF build + API, fully offline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app import tasks
from app.services import pipeline
from app.services.report import ReportData, build_report_pdf
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


# --- pure generator --------------------------------------------------------------------

def _sample_data(**over) -> ReportData:
    base = {
        "organization_name": "Acme Corp",
        "primary_domain": "example.com",
        "assessment_type": "passive-osint",
        "status": "success",
        "authorized_by": "CISO",
        "authorization_scope": "example.com",
        "authorized_at": NOW,
        "started_at": NOW,
        "completed_at": NOW,
        "findings": [
            {"title": "Sensitive hostname exposed: admin.example.com", "severity": "high",
             "classification": "unverified", "status": "open", "confidence": 0.85,
             "description": "admin.example.com is publicly discoverable.",
             "finding_type": "sensitive_hostname",
             "evidence": [{"asset_type": "subdomain", "value": "admin.example.com",
                           "confidence": 0.85, "sources": ["crt.sh (CT)"]}]},
            {"title": "12 subdomain(s) discovered", "severity": "info",
             "classification": "confirmed", "status": "open", "confidence": 0.99,
             "description": "Passive discovery surfaced 12 subdomains.",
             "finding_type": "attack_surface_summary", "evidence": []},
        ],
        "asset_counts": {"subdomain": 12, "certificate": 85, "whois": 1},
        "total_assets": 98,
    }
    base.update(over)
    return ReportData(**base)


def test_build_report_pdf_returns_pdf_bytes():
    pdf = build_report_pdf(_sample_data())
    assert pdf[:5] == b"%PDF-"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1500


def test_report_handles_no_findings_and_no_auth():
    pdf = build_report_pdf(_sample_data(
        findings=[], asset_counts={}, total_assets=0,
        authorized_by=None, authorization_scope=None, authorized_at=None))
    assert pdf[:5] == b"%PDF-"


def test_report_escapes_special_characters():
    # angle brackets / ampersands must not break the PDF markup
    pdf = build_report_pdf(_sample_data(organization_name="A & B <Corp>", findings=[
        {"title": "weird <host> & co", "severity": "medium", "classification": "confirmed",
         "status": "open", "confidence": 0.5, "description": "x < y & z > w",
         "finding_type": "t", "evidence": [
             {"asset_type": "dns_record", "value": "TXT a & b", "confidence": 0.9,
              "sources": ["dns & more"]}]}]))
    assert pdf[:5] == b"%PDF-"


# --- API route -------------------------------------------------------------------------

class _FixedCollector(Collector):
    def __init__(self, name, results):
        self.name = name
        self.required_keys = ()
        self._results = results

    def collect(self, context: CollectionContext) -> CollectorRun:
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=self._results)


def _collectors():
    past = (NOW - timedelta(days=3)).isoformat()
    return [
        _FixedCollector("ct", [
            CollectorResult(asset_type="subdomain", value="admin.example.com",
                            provenance=Provenance.now(source="crt.sh (CT)", confidence=0.85)),
        ]),
        _FixedCollector("whois", [
            CollectorResult(asset_type="whois", value="example.com",
                            provenance=Provenance.now(source="rdap", confidence=0.9),
                            attributes={"expiration_date": past}),
        ]),
    ]


def _run(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"],
                            "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    tasks.run_investigation_task(inv["id"])
    return inv["id"]


def test_report_download_after_run(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", _collectors)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _run(client, token)

    r = client.get(f"/api/investigations/{inv_id}/report.pdf", headers=auth_header(token))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-"


def test_report_refused_before_run(client):
    token = signup(client, "Acme", "admin@acme.io")
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"],
                            "assessment_type": "passive-osint"}).json()
    r = client.get(f"/api/investigations/{inv['id']}/report.pdf", headers=auth_header(token))
    assert r.status_code == 409  # draft, nothing to report


def test_report_tenant_isolated(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", _collectors)

    tok_a = signup(client, "TenantA", "a@tenanta.io")
    inv_id = _run(client, tok_a)
    tok_b = signup(client, "TenantB", "b@tenantb.io")

    assert client.get(f"/api/investigations/{inv_id}/report.pdf",
                      headers=auth_header(tok_b)).status_code == 404
