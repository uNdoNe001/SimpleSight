"""Alerting over change events (Phase 3 · Story D, SMPLSGHT-53)."""

from __future__ import annotations

from types import SimpleNamespace

from app import tasks
from app.models import ChangeEvent, ChangeType
from app.services import findings as findings_mod
from app.services import investigations as inv_mod
from app.services import pipeline
from app.services.alerts import is_material, material_events
from collectors.base import CollectorOutcome, CollectorRun
from tests import conftest
from tests.conftest import FakeCollector, auth_header, make_result, signup


def _ev(change_type: str, severity: str | None, **detail) -> SimpleNamespace:
    return SimpleNamespace(change_type=change_type, severity=severity, detail=detail)


# --- pure rule -------------------------------------------------------------------------

def test_new_high_or_critical_finding_is_material():
    assert is_material(_ev(ChangeType.FINDING_APPEARED.value, "high"))
    assert is_material(_ev(ChangeType.FINDING_APPEARED.value, "critical"))


def test_new_low_finding_is_not_material():
    assert not is_material(_ev(ChangeType.FINDING_APPEARED.value, "low"))
    assert not is_material(_ev(ChangeType.FINDING_APPEARED.value, "medium"))


def test_escalation_into_high_is_material_deescalation_is_not():
    up = _ev(ChangeType.FINDING_SEVERITY_CHANGED.value, "high", to="high", escalated=True)
    down = _ev(ChangeType.FINDING_SEVERITY_CHANGED.value, "low", to="low", escalated=False)
    into_medium = _ev(ChangeType.FINDING_SEVERITY_CHANGED.value, "medium", to="medium", escalated=True)
    assert is_material(up)
    assert not is_material(down)
    assert not is_material(into_medium)


def test_asset_changes_are_never_material():
    assert not is_material(_ev(ChangeType.ASSET_ADDED.value, None))


def test_material_events_filters():
    evs = [
        _ev(ChangeType.FINDING_APPEARED.value, "critical"),
        _ev(ChangeType.FINDING_APPEARED.value, "low"),
        _ev(ChangeType.ASSET_ADDED.value, None),
    ]
    assert len(material_events(evs)) == 1


# --- API with a real material change -----------------------------------------------------

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


def test_alerts_surface_and_acknowledge(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    # Baseline run with no findings.
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _collector("a.example.com"))
    monkeypatch.setattr(inv_mod, "derive_findings", lambda target, assets: [])
    tasks.run_investigation_task(inv_id)

    # Second run: inject a brand-new HIGH finding -> finding_appeared(high) -> material alert.
    high = findings_mod.FindingCandidate(
        finding_key="exposed-admin",
        finding_type="exposure",
        title="Exposed admin panel",
        description="",
        severity=findings_mod.FindingSeverity.HIGH,
        confidence=0.9,
        classification=findings_mod.FindingClassification.CONFIRMED,
        evidence=[],
    )
    monkeypatch.setattr(inv_mod, "derive_findings", lambda target, assets: [high])
    tasks.run_investigation_task(inv_id)

    r = client.get(f"/api/investigations/{inv_id}/alerts", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["unacknowledged"] == 1
    assert len(body["alerts"]) == 1
    alert = body["alerts"][0]
    assert alert["change_type"] == "finding_appeared" and alert["severity"] == "high"

    # Tenant-wide badge count.
    assert client.get("/api/alerts/summary", headers=auth_header(token)).json()["unacknowledged"] == 1

    # Acknowledge it -> count drops to zero.
    ack = client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=auth_header(token))
    assert ack.status_code == 200 and ack.json()["acknowledged_at"] is not None
    assert client.get("/api/alerts/summary", headers=auth_header(token)).json()["unacknowledged"] == 0


def test_acknowledge_rejects_non_material_event(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    monkeypatch.setattr(pipeline, "default_collectors", lambda: _collector("a.example.com"))
    tasks.run_investigation_task(inv_id)
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _collector("b.example.com"))
    tasks.run_investigation_task(inv_id)

    db = conftest.TestSession()
    try:
        asset_event = db.query(ChangeEvent).filter_by(
            investigation_id=inv_id, change_type="asset_added"
        ).first()
    finally:
        db.close()
    r = client.post(f"/api/alerts/{asset_event.id}/acknowledge", headers=auth_header(token))
    assert r.status_code == 409
