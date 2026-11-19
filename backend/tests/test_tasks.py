"""Worker task + queue dispatch tests (SMPLSGHT-18), fully offline (no Redis)."""

from __future__ import annotations

from app import queue as queue_mod
from app import tasks
from app.core.config import settings
from app.services import pipeline
from tests import conftest
from tests.conftest import auth_header, signup, two_collectors_same_asset


def _authorized_investigation(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                     json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                     json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
               json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    return inv["id"]


def test_task_persists_assets(client, monkeypatch):
    # Point the worker's session factory at the test engine; use fake collectors.
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", two_collectors_same_asset)

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _authorized_investigation(client, token)

    tasks.run_investigation_task(inv_id)

    got = client.get(f"/api/investigations/{inv_id}", headers=auth_header(token)).json()
    assert got["status"] == "success"
    assert got["completed_at"] is not None
    assert len(got["assets"]) == 1              # merged across both collectors
    assert len(got["assets"][0]["sources"]) == 2


def test_task_marks_failed_on_error(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)

    token = signup(client, "Acme", "admin@acme.io")
    # Create an investigation but do NOT authorize it -> run_and_persist raises,
    # and the task must record the failure rather than propagate.
    org = client.post("/api/organizations", headers=auth_header(token),
                     json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                     json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()

    tasks.run_investigation_task(inv["id"])  # must not raise

    got = client.get(f"/api/investigations/{inv['id']}", headers=auth_header(token)).json()
    assert got["status"] == "failed"


# --- queue dispatch --------------------------------------------------------------------

def test_enqueue_eager_runs_inline(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(settings, "queue_eager", True)
    monkeypatch.setattr("app.tasks.run_investigation_task", lambda i: calls.append(i))
    assert queue_mod.enqueue_investigation_run("abc") == "eager"
    assert calls == ["abc"]


def test_enqueue_async_uses_queue(monkeypatch):
    monkeypatch.setattr(settings, "queue_eager", False)

    class _Job:
        id = "job-1"

    class _Queue:
        def enqueue(self, task, arg):
            assert arg == "abc"
            return _Job()

    monkeypatch.setattr(queue_mod, "get_queue", lambda: _Queue())
    assert queue_mod.enqueue_investigation_run("abc") == "job-1"
