"""Exposure-score trend history (Phase 5 · SMPLSGHT-65), deterministic & offline.

A snapshot is written per completed run; the endpoint returns the ordered series. Runs go
through the eager queue inline (patched session, fake collector) so no Redis/worker is needed.
"""

from __future__ import annotations

from app import tasks
from app.core.config import settings
from app.services import pipeline
from collectors.base import CollectorOutcome, CollectorRun
from tests import conftest
from tests.conftest import FakeCollector, auth_header, make_result, signup


def _one_collector(value: str):
    return [FakeCollector("ct", run=CollectorRun(
        outcome=CollectorOutcome.SUCCESS,
        results=[make_result("subdomain", value, "crt.sh", 0.8)],
    ))]


def _authorized_inv(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"],
                            "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    return inv["id"]


def test_history_accumulates_a_point_per_run(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(settings, "queue_eager", True)
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("a.example.com"))
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_inv(client, token)

    # No runs yet -> empty series.
    assert client.get(f"/api/investigations/{inv_id}/exposure-history",
                      headers=auth_header(token)).json() == []

    client.post(f"/api/investigations/{inv_id}/run", headers=auth_header(token))
    client.post(f"/api/investigations/{inv_id}/run", headers=auth_header(token))

    r = client.get(f"/api/investigations/{inv_id}/exposure-history", headers=auth_header(token))
    assert r.status_code == 200
    points = r.json()
    assert len(points) == 2  # baseline + re-run
    # oldest run first (non-decreasing run_at)
    assert [p["run_at"] for p in points] == sorted(p["run_at"] for p in points)
    for p in points:
        assert set(p) == {"score", "grade", "label", "scored_findings", "run_at"}
        assert 0 <= p["score"] <= 100


def test_history_is_tenant_scoped(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(settings, "queue_eager", True)
    monkeypatch.setattr(pipeline, "default_collectors", lambda: _one_collector("a.example.com"))
    token_a = signup(client, "Acme", "admin@acme.io")
    inv_a = _authorized_inv(client, token_a)
    client.post(f"/api/investigations/{inv_a}/run", headers=auth_header(token_a))

    token_b = signup(client, "Rival", "admin@rival.io")
    r = client.get(f"/api/investigations/{inv_a}/exposure-history", headers=auth_header(token_b))
    assert r.status_code == 404  # other tenant can't see it
