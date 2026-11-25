"""Change-detection engine (Phase 3 · Story A, SMPLSGHT-50).

The diff itself is pure and offline; the integration test drives two persisted runs with
different collector output and asserts that only the *second* run records change events.
"""

from __future__ import annotations

from types import SimpleNamespace

from app import tasks
from app.models import ChangeEvent, ChangeType
from app.services import pipeline
from app.services.changes import diff_runs, snapshot_from_orm
from collectors.base import CollectorOutcome, CollectorRun
from tests import conftest
from tests.conftest import FakeCollector, auth_header, make_result, signup

# --- pure diff -------------------------------------------------------------------------

def _asset(atype: str, value: str) -> SimpleNamespace:
    return SimpleNamespace(asset_type=atype, value=value)


def _finding(key: str, severity: str, *, title: str = "", status: str = "open") -> SimpleNamespace:
    return SimpleNamespace(finding_key=key, title=title or key, severity=severity, status=status)


def _snap(assets, findings) -> object:
    return snapshot_from_orm(SimpleNamespace(assets=assets, findings=findings))


def test_no_difference_yields_no_events():
    prev = _snap([_asset("subdomain", "a.example.com")], [_finding("f1", "low")])
    curr = _snap([_asset("subdomain", "a.example.com")], [_finding("f1", "low")])
    assert diff_runs(prev, curr) == []


def test_detects_added_and_removed_assets():
    prev = _snap([_asset("subdomain", "old.example.com")], [])
    curr = _snap([_asset("subdomain", "new.example.com")], [])
    events = diff_runs(prev, curr)
    by_type = {e.change_type for e in events}
    assert ChangeType.ASSET_ADDED.value in by_type
    assert ChangeType.ASSET_REMOVED.value in by_type
    added = next(e for e in events if e.change_type == ChangeType.ASSET_ADDED.value)
    assert added.entity_key == "subdomain:new.example.com"


def test_detects_finding_appeared_and_resolved():
    prev = _snap([], [_finding("gone", "medium")])
    curr = _snap([], [_finding("fresh", "high")])
    events = diff_runs(prev, curr)
    appeared = next(e for e in events if e.change_type == ChangeType.FINDING_APPEARED.value)
    resolved = next(e for e in events if e.change_type == ChangeType.FINDING_RESOLVED.value)
    assert appeared.entity_key == "fresh" and appeared.severity == "high"
    assert resolved.entity_key == "gone" and resolved.severity == "medium"


def test_detects_severity_change_with_direction():
    prev = _snap([], [_finding("f", "low")])
    curr = _snap([], [_finding("f", "critical")])
    events = diff_runs(prev, curr)
    assert len(events) == 1
    ev = events[0]
    assert ev.change_type == ChangeType.FINDING_SEVERITY_CHANGED.value
    assert ev.detail == {"from": "low", "to": "critical", "escalated": True}


def test_triage_status_change_is_not_a_change():
    # Same finding_key + severity, only analyst status differs -> no event (triage ≠ posture).
    prev = _snap([], [_finding("f", "high", status="open")])
    curr = _snap([], [_finding("f", "high", status="dismissed")])
    assert diff_runs(prev, curr) == []


# --- persisted re-run integration ------------------------------------------------------

def _authorized_inv(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    return inv["id"]


def _one_collector(value: str):
    return [FakeCollector("ct", run=CollectorRun(
        outcome=CollectorOutcome.SUCCESS,
        results=[make_result("subdomain", value, "crt.sh", 0.8)],
    ))]


def test_first_run_is_baseline_second_run_records_changes(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    # Run 1: baseline — a.example.com. No change events expected.
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("a.example.com"))
    tasks.run_investigation_task(inv_id)

    db = conftest.TestSession()
    try:
        assert db.query(ChangeEvent).filter_by(investigation_id=inv_id).count() == 0

        # Run 2: b.example.com replaces a.example.com.
        monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("b.example.com"))
        tasks.run_investigation_task(inv_id)

        events = db.query(ChangeEvent).filter_by(investigation_id=inv_id).all()
        kinds = {e.change_type for e in events}
        assert ChangeType.ASSET_ADDED.value in kinds
        assert ChangeType.ASSET_REMOVED.value in kinds
        # All share one run_at (same re-run).
        assert len({e.run_at for e in events}) == 1
    finally:
        db.close()


def test_changes_endpoint_lists_events_and_enforces_tenancy(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("a.example.com"))
    tasks.run_investigation_task(inv_id)
    # No change events after the baseline run.
    r = client.get(f"/api/investigations/{inv_id}/changes", headers=auth_header(token))
    assert r.status_code == 200 and r.json() == []

    monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("b.example.com"))
    tasks.run_investigation_task(inv_id)

    r = client.get(f"/api/investigations/{inv_id}/changes", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert {e["change_type"] for e in body} == {"asset_added", "asset_removed"}

    # latest=true returns the same single run here.
    r2 = client.get(f"/api/investigations/{inv_id}/changes?latest=true", headers=auth_header(token))
    assert len(r2.json()) == len(body)

    # Another tenant cannot see this investigation's changes.
    other = signup(client, "Rival", "admin@rival.io")
    r3 = client.get(f"/api/investigations/{inv_id}/changes", headers=auth_header(other))
    assert r3.status_code == 404
