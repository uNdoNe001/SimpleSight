"""Continuous-monitoring schedule (Phase 3 · Story C, SMPLSGHT-52)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app import tasks
from app.core.config import settings
from app.models import InvestigationStatus
from app.services import pipeline
from app.services.monitoring import is_due, next_due_at
from collectors.base import CollectorOutcome, CollectorRun
from tests import conftest
from tests.conftest import FakeCollector, auth_header, make_result, signup

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def _inv(**kw) -> SimpleNamespace:
    base = {
        "monitoring_enabled": True,
        "monitoring_interval": "daily",
        "status": "success",
        "completed_at": NOW - timedelta(days=2),
        "created_at": NOW - timedelta(days=5),
        "authorized_by": "CISO",
        "authorized_at": NOW - timedelta(days=5),
    }
    base.update(kw)
    obj = SimpleNamespace(**base)
    obj.is_authorized = bool(obj.authorized_by and obj.authorized_at)
    return obj


# --- pure selection --------------------------------------------------------------------

def test_due_when_last_run_older_than_interval():
    assert is_due(_inv(completed_at=NOW - timedelta(days=2)), NOW) is True


def test_not_due_when_within_interval():
    assert is_due(_inv(completed_at=NOW - timedelta(hours=1)), NOW) is False


def test_never_run_is_due_immediately():
    inv = _inv(completed_at=None)
    assert next_due_at(inv) == inv.created_at
    assert is_due(inv, NOW) is True


def test_unmonitored_is_never_due():
    assert next_due_at(_inv(monitoring_enabled=False)) is None
    assert is_due(_inv(monitoring_enabled=False), NOW) is False


def test_running_or_unauthorized_not_due():
    assert is_due(_inv(status=InvestigationStatus.RUNNING.value), NOW) is False
    assert is_due(_inv(authorized_by=None), NOW) is False


def test_bad_interval_is_not_due():
    assert next_due_at(_inv(monitoring_interval="yearly")) is None


# --- API -------------------------------------------------------------------------------

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


def test_enable_monitoring_and_validation(client):
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    # enabled without interval -> 422
    r = client.patch(f"/api/investigations/{inv_id}/monitoring", headers=auth_header(token),
                     json={"enabled": True})
    assert r.status_code == 422

    r = client.patch(f"/api/investigations/{inv_id}/monitoring", headers=auth_header(token),
                     json={"enabled": True, "interval": "daily"})
    assert r.status_code == 200
    assert r.json()["monitoring_enabled"] is True
    assert r.json()["monitoring_interval"] == "daily"

    # disabling clears the interval
    r = client.patch(f"/api/investigations/{inv_id}/monitoring", headers=auth_header(token),
                     json={"enabled": False})
    assert r.json()["monitoring_enabled"] is False
    assert r.json()["monitoring_interval"] is None


def test_due_endpoint_and_run_due(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(settings, "queue_eager", True)  # run enqueued tasks inline (no Redis)
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    # Baseline run, then enable monitoring — never-"stale" yet since it just ran... so force
    # due by using an immediate cadence check: a fresh monitored inv with completed run is not
    # due within the interval, so we test the never-run path: enable before first run.
    client.patch(f"/api/investigations/{inv_id}/monitoring", headers=auth_header(token),
                 json={"enabled": True, "interval": "daily"})

    # Not yet run -> due immediately.
    r = client.get("/api/monitoring/due", headers=auth_header(token))
    assert r.status_code == 200
    due_ids = {d["id"] for d in r.json()}
    assert inv_id in due_ids

    # run-due enqueues it (eager tasks run inline via the patched session).
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("a.example.com"))
    r = client.post("/api/monitoring/run-due", headers=auth_header(token))
    assert r.status_code == 200
    assert r.json()["enqueued"] == 1 and inv_id in r.json()["investigation_ids"]

    # After running, it is no longer due (completed just now, within the daily interval).
    r = client.get("/api/monitoring/due", headers=auth_header(token))
    assert inv_id not in {d["id"] for d in r.json()}


def test_run_due_is_tenant_scoped(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    token_a = signup(client, "Acme", "admin@acme.io")
    inv_a = _authorized_inv(client, token_a)
    client.patch(f"/api/investigations/{inv_a}/monitoring", headers=auth_header(token_a),
                 json={"enabled": True, "interval": "daily"})

    token_b = signup(client, "Rival", "admin@rival.io")
    # Rival sees nothing due and runs nothing.
    assert client.get("/api/monitoring/due", headers=auth_header(token_b)).json() == []
    assert client.post("/api/monitoring/run-due", headers=auth_header(token_b)).json()["enqueued"] == 0
