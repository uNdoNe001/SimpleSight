"""Secrets manager (SMPLSGHT-11): encryption, resolution, env fallback, admin API, and
the collection-pipeline integration (key-gated collector skip), all offline."""

from __future__ import annotations

from app import tasks
from app.services import investigations as inv_svc
from app.services import pipeline
from app.services import secrets as secrets_svc
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

# --- service: encryption + resolution --------------------------------------------------

def test_set_encrypts_and_resolves_roundtrip():
    db = conftest.TestSession()
    try:
        tid = "tenant-1"
        row = secrets_svc.set_secret(db, tid, "shodan_api_key", "s3cr3t-value")
        db.commit()
        # stored ciphertext is not the plaintext
        assert "s3cr3t-value" not in row.ciphertext
        assert secrets_svc.resolve(db, tid, "shodan_api_key") == "s3cr3t-value"
    finally:
        db.close()


def test_rotate_overwrites_value():
    db = conftest.TestSession()
    try:
        tid = "tenant-1"
        secrets_svc.set_secret(db, tid, "k", "old")
        secrets_svc.set_secret(db, tid, "k", "new")
        db.commit()
        assert secrets_svc.resolve(db, tid, "k") == "new"
    finally:
        db.close()


def test_secrets_are_tenant_scoped():
    db = conftest.TestSession()
    try:
        secrets_svc.set_secret(db, "t-a", "k", "a-value")
        db.commit()
        assert secrets_svc.resolve(db, "t-b", "k") is None
    finally:
        db.close()


def test_env_fallback(monkeypatch):
    db = conftest.TestSession()
    try:
        monkeypatch.setenv("SIMPLESIGHT_SECRET_CENSYS_TOKEN", "from-env")
        assert secrets_svc.resolve(db, "any-tenant", "censys_token") == "from-env"
        # tenant store takes precedence over env
        secrets_svc.set_secret(db, "any-tenant", "censys_token", "from-db")
        db.commit()
        assert secrets_svc.resolve(db, "any-tenant", "censys_token") == "from-db"
    finally:
        db.close()


# --- admin API -------------------------------------------------------------------------

def test_secret_api_set_list_delete_admin_only(client):
    admin = signup(client, "Acme", "admin@acme.io")

    # set
    r = client.put("/api/secrets/shodan_api_key", headers=auth_header(admin),
                   json={"value": "abc123"})
    assert r.status_code == 200
    assert r.json() == {"name": "shodan_api_key", "source": "tenant",
                        "configured": True, "updated_at": None}

    # list never reveals the value
    listing = client.get("/api/secrets", headers=auth_header(admin)).json()
    entry = next(e for e in listing if e["name"] == "shodan_api_key")
    assert entry["configured"] is True
    assert "value" not in entry
    assert "abc123" not in str(listing)

    # delete
    assert client.delete("/api/secrets/shodan_api_key",
                        headers=auth_header(admin)).status_code == 204
    assert client.delete("/api/secrets/shodan_api_key",
                        headers=auth_header(admin)).status_code == 404


def test_secret_listing_includes_narrative_key(client):
    # The optional Claude narrative key (SMPLSGHT-58) is manageable via the same admin UI.
    admin = signup(client, "Acme", "admin@acme.io")
    listing = client.get("/api/secrets", headers=auth_header(admin)).json()
    names = {e["name"] for e in listing}
    assert "anthropic_api_key" in names


def test_secret_api_rejects_non_admin(client):
    admin = signup(client, "Acme", "admin@acme.io")
    client.post("/api/users", headers=auth_header(admin),
                json={"email": "an@acme.io", "password": "password123", "role": "analyst"})
    analyst = client.post("/api/auth/login",
                          json={"email": "an@acme.io", "password": "password123"}
                          ).json()["access_token"]
    assert client.get("/api/secrets", headers=auth_header(analyst)).status_code == 403
    assert client.put("/api/secrets/k", headers=auth_header(analyst),
                     json={"value": "x"}).status_code == 403


def test_secret_api_validates_name(client):
    admin = signup(client, "Acme", "admin@acme.io")
    assert client.put("/api/secrets/bad name!", headers=auth_header(admin),
                     json={"value": "x"}).status_code == 422


# --- pipeline integration: key-gated collector is skipped until the key is set ---------

class _KeyedCollector(Collector):
    name = "keyed"
    required_keys = ("mykey",)

    def collect(self, context: CollectionContext) -> CollectorRun:
        return CollectorRun(
            outcome=CollectorOutcome.SUCCESS,
            results=[CollectorResult(
                asset_type="subdomain", value="api.example.com",
                provenance=Provenance.now(source="keyed", confidence=0.9))],
        )


def _setup(client, monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", lambda: [_KeyedCollector()])
    monkeypatch.setattr(inv_svc, "required_secret_names", lambda: ["mykey"])


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


def test_keyed_collector_skipped_without_secret(client, monkeypatch):
    _setup(client, monkeypatch)
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _run(client, token)
    got = client.get(f"/api/investigations/{inv_id}", headers=auth_header(token)).json()
    assert got["status"] == "partial"      # the only collector was skipped
    assert got["assets"] == []


def test_keyed_collector_runs_once_secret_set(client, monkeypatch):
    _setup(client, monkeypatch)
    token = signup(client, "Acme", "admin@acme.io")
    client.put("/api/secrets/mykey", headers=auth_header(token), json={"value": "xyz"})
    inv_id = _run(client, token)
    got = client.get(f"/api/investigations/{inv_id}", headers=auth_header(token)).json()
    assert got["status"] == "success"
    assert any(a["value"] == "api.example.com" for a in got["assets"])
