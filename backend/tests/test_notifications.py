"""Outbound alert delivery (Phase 4 · Story B, SMPLSGHT-56). Fully offline via a fake transport."""

from __future__ import annotations

from types import SimpleNamespace

from app import tasks
from app.services import investigations as inv_mod
from app.services import notifications, pipeline
from app.services.findings import FindingCandidate, FindingClassification, FindingSeverity
from app.services.notifications import DeliveryResult, build_payload, sign
from collectors.base import CollectorOutcome, CollectorRun
from tests import conftest
from tests.conftest import FakeCollector, auth_header, make_result, signup


class FakeTransport:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple[str, bytes, dict]] = []

    def send(self, url, body, headers):
        self.calls.append((url, body, headers))
        return DeliveryResult(ok=self.ok, status=200 if self.ok else 500)


def _alert(change_type: str, severity: str, **detail) -> SimpleNamespace:
    return SimpleNamespace(
        change_type=change_type, entity_key="k", title="t", severity=severity, detail=detail
    )


# --- pure helpers ----------------------------------------------------------------------

def test_signature_is_stable_hmac():
    body = b'{"a":1}'
    s1 = sign(body, "secret-value")
    s2 = sign(body, "secret-value")
    assert s1 == s2 and s1.startswith("sha256=")
    assert sign(body, "other") != s1


def test_payload_is_grounded_in_alerts():
    inv = SimpleNamespace(id="inv1", organization_id="org1")
    payload = build_payload(inv, "example.com", [_alert("finding_appeared", "high")])
    assert payload["investigation_id"] == "inv1"
    assert payload["alert_count"] == 1
    assert payload["alerts"][0]["severity"] == "high"


# --- delivery service ------------------------------------------------------------------

def _authorized_inv(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    return inv["id"]


def _collector(value: str):
    return [FakeCollector("ct", run=CollectorRun(
        outcome=CollectorOutcome.SUCCESS,
        results=[make_result("subdomain", value, "crt.sh", 0.8)],
    ))]


def test_channel_crud_hides_secret(client):
    token = signup(client, "Acme", "admin@acme.io")
    r = client.post("/api/notifications/channels", headers=auth_header(token),
                    json={"name": "ops", "target": "https://hooks.example/webhook",
                          "signing_secret": "supersecret"})
    assert r.status_code == 201
    ch = r.json()
    assert "signing_secret" not in ch
    assert ch["has_secret"] is True

    listed = client.get("/api/notifications/channels", headers=auth_header(token)).json()
    assert len(listed) == 1 and listed[0]["id"] == ch["id"]

    # non-http target rejected
    bad = client.post("/api/notifications/channels", headers=auth_header(token),
                      json={"name": "x", "target": "ftp://nope"})
    assert bad.status_code == 422

    assert client.delete(f"/api/notifications/channels/{ch['id']}",
                         headers=auth_header(token)).status_code == 204


def test_readonly_cannot_create_channel(client):
    admin = signup(client, "Acme", "admin@acme.io")
    # create a readonly user in the same tenant
    client.post("/api/users", headers=auth_header(admin),
                json={"email": "ro@acme.io", "password": "password123", "role": "readonly"})
    ro = client.post("/api/auth/login", json={"email": "ro@acme.io", "password": "password123"}).json()
    r = client.post("/api/notifications/channels", headers=auth_header(ro["access_token"]),
                    json={"name": "x", "target": "https://hooks.example/h"})
    assert r.status_code == 403


def test_material_alert_is_delivered_on_rerun(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    fake = FakeTransport(ok=True)
    monkeypatch.setattr(notifications, "default_transport", fake)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)
    client.post("/api/notifications/channels", headers=auth_header(token),
                json={"name": "ops", "target": "https://hooks.example/webhook",
                      "signing_secret": "supersecret"})

    # Baseline run: no findings.
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _collector("a.example.com"))
    monkeypatch.setattr(inv_mod, "derive_findings", lambda target, assets: [])
    tasks.run_investigation_task(inv_id)
    assert fake.calls == []  # baseline has no alerts

    # Re-run introducing a HIGH finding -> material alert -> delivery.
    high = FindingCandidate(
        finding_key="exposed-admin", finding_type="exposure", title="Exposed admin",
        description="", severity=FindingSeverity.HIGH, confidence=0.9,
        classification=FindingClassification.CONFIRMED, evidence=[],
    )
    monkeypatch.setattr(inv_mod, "derive_findings", lambda target, assets: [high])
    tasks.run_investigation_task(inv_id)

    assert len(fake.calls) == 1
    url, body, headers = fake.calls[0]
    assert url == "https://hooks.example/webhook"
    assert headers["X-SimpleSight-Signature"] == sign(body, "supersecret")


def test_disabled_channel_not_delivered(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    fake = FakeTransport(ok=True)
    monkeypatch.setattr(notifications, "default_transport", fake)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)
    client.post("/api/notifications/channels", headers=auth_header(token),
                json={"name": "ops", "target": "https://hooks.example/webhook", "enabled": False})

    monkeypatch.setattr(pipeline, "default_collectors", lambda: _collector("a.example.com"))
    monkeypatch.setattr(inv_mod, "derive_findings", lambda target, assets: [])
    tasks.run_investigation_task(inv_id)
    crit = FindingCandidate(
        finding_key="k", finding_type="exposure", title="t", description="",
        severity=FindingSeverity.CRITICAL, confidence=0.9,
        classification=FindingClassification.CONFIRMED, evidence=[],
    )
    monkeypatch.setattr(inv_mod, "derive_findings", lambda target, assets: [crit])
    tasks.run_investigation_task(inv_id)
    assert fake.calls == []  # channel disabled
