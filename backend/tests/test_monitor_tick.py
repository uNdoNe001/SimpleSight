"""Scheduled monitoring tick (Phase 4 · Story C, SMPLSGHT-57). Offline — enqueue is injected."""

from __future__ import annotations

from app.models import Investigation, InvestigationStatus
from app.services.monitoring import enqueue_due
from tests import conftest
from tests.conftest import auth_header, signup
from workers import monitor_tick


def _monitored_authorized_inv(client, token, *, domain: str = "example.com") -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": domain}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": domain})
    client.patch(f"/api/investigations/{inv['id']}/monitoring", headers=auth_header(token),
                 json={"enabled": True, "interval": "daily"})
    return inv["id"]


def test_tick_enqueues_due_across_tenants(client):
    # Two tenants, each with a due (never-run) monitored investigation.
    ta = signup(client, "Acme", "admin@acme.io")
    tb = signup(client, "Rival", "admin@rival.io")
    inv_a = _monitored_authorized_inv(client, ta)
    inv_b = _monitored_authorized_inv(client, tb, domain="rival.com")

    calls: list[str] = []
    db = conftest.TestSession()
    try:
        result = enqueue_due(db, enqueue=calls.append)
    finally:
        db.close()

    assert result.due == 2
    assert set(result.enqueued) == {inv_a, inv_b}
    assert set(calls) == {inv_a, inv_b}

    # Both are now marked running.
    db = conftest.TestSession()
    try:
        for i in (inv_a, inv_b):
            assert db.get(Investigation, i).status == InvestigationStatus.RUNNING.value
    finally:
        db.close()


def test_tick_skips_running_and_is_idempotent(client):
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _monitored_authorized_inv(client, token)

    calls: list[str] = []
    db = conftest.TestSession()
    try:
        first = enqueue_due(db, enqueue=calls.append)
        # Second pass immediately after: the investigation is now `running`, so not due again.
        second = enqueue_due(db, enqueue=calls.append)
    finally:
        db.close()

    assert first.enqueued == [inv_id]
    assert second.enqueued == []
    assert calls == [inv_id]


def test_run_tick_entrypoint_uses_session(client, monkeypatch):
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _monitored_authorized_inv(client, token)

    monkeypatch.setattr(monitor_tick, "SessionLocal", conftest.TestSession)
    # Keep it offline: don't let enqueue reach Redis.
    monkeypatch.setattr("app.queue.enqueue_investigation_run", lambda i: None)

    rc = monitor_tick.main()
    assert rc == 0
    db = conftest.TestSession()
    try:
        assert db.get(Investigation, inv_id).status == InvestigationStatus.RUNNING.value
    finally:
        db.close()
