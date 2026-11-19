"""API smoke tests for the synchronous investigation endpoint (offline)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline
from collectors.base import CollectorOutcome, CollectorRun
from tests.conftest import FakeCollector, make_result

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/health").json()["status"] == "ok"


def test_run_investigation_returns_normalized_assets(monkeypatch):
    fakes = [
        FakeCollector("ct", run=CollectorRun(
            outcome=CollectorOutcome.SUCCESS,
            results=[make_result("subdomain", "api.example.com", "crt.sh", 0.8)],
        )),
        FakeCollector("dns", run=CollectorRun(
            outcome=CollectorOutcome.SUCCESS,
            results=[make_result("subdomain", "api.example.com", "dns", 0.6)],
        )),
    ]
    # swap the registry the pipeline pulls its default collectors from
    monkeypatch.setattr(pipeline, "default_collectors", lambda: fakes)

    resp = client.post("/api/investigations/run", json={"domain": "Example.com."})
    assert resp.status_code == 200
    body = resp.json()

    assert body["target"] == "example.com"          # normalized
    assert body["overall_outcome"] == "success"
    assert body["asset_count"] == 1                   # merged across both collectors
    asset = body["assets"][0]
    assert asset["value"] == "api.example.com"
    assert len(asset["sources"]) == 2
    assert asset["confidence"] == 0.92
    assert {c["collector"] for c in body["collectors"]} == {"ct", "dns"}
