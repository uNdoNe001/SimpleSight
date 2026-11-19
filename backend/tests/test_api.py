"""API tests for auth, tenancy, RBAC, and the persisted investigation flow (offline)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.services import pipeline
from collectors.base import CollectorOutcome, CollectorRun
from tests.conftest import FakeCollector, make_result

# Shared in-memory SQLite across sessions via StaticPool.
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_Session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)


def _signup(tenant: str, email: str, password: str = "password123") -> str:
    r = client.post(
        "/api/auth/signup",
        json={"tenant_name": tenant, "email": email, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- auth ------------------------------------------------------------------------------

def test_signup_login_me():
    token = _signup("Acme", "admin@acme.io")
    me = client.get("/api/auth/me", headers=_hdr(token)).json()
    assert me["email"] == "admin@acme.io"
    assert me["role"] == "admin"

    login = client.post("/api/auth/login",
                        json={"email": "admin@acme.io", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_unauthenticated_is_rejected():
    assert client.get("/api/organizations").status_code == 401  # no bearer token


def test_wrong_password_rejected():
    _signup("Acme", "admin@acme.io")
    r = client.post("/api/auth/login",
                   json={"email": "admin@acme.io", "password": "wrong"})
    assert r.status_code == 401


# --- tenancy isolation (SMPLSGHT-9) ----------------------------------------------------

def test_tenant_cannot_access_another_tenants_org():
    tok_a = _signup("TenantA", "a@tenanta.io")
    tok_b = _signup("TenantB", "b@tenantb.io")

    org = client.post("/api/organizations", headers=_hdr(tok_a),
                     json={"name": "A Corp", "primary_domain": "a.example"}).json()

    # Tenant B cannot read or see Tenant A's org.
    assert client.get(f"/api/organizations/{org['id']}", headers=_hdr(tok_b)).status_code == 404
    assert client.get("/api/organizations", headers=_hdr(tok_b)).json() == []
    # Tenant A can.
    assert client.get(f"/api/organizations/{org['id']}", headers=_hdr(tok_a)).status_code == 200


# --- RBAC (SMPLSGHT-10) ----------------------------------------------------------------

def test_readonly_user_cannot_create_org():
    admin = _signup("Acme", "admin@acme.io")
    client.post("/api/users", headers=_hdr(admin),
               json={"email": "ro@acme.io", "password": "password123", "role": "readonly"})
    ro = client.post("/api/auth/login",
                    json={"email": "ro@acme.io", "password": "password123"}).json()["access_token"]

    r = client.post("/api/organizations", headers=_hdr(ro), json={"name": "Nope"})
    assert r.status_code == 403
    # read-only can still read
    assert client.get("/api/organizations", headers=_hdr(ro)).status_code == 200


# --- investigation flow + attestation gate (SMPLSGHT-14/-15/-17/-29) -------------------

def test_investigation_requires_authorization_then_runs(monkeypatch):
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
    monkeypatch.setattr(pipeline, "default_collectors", lambda: fakes)

    token = _signup("Acme", "admin@acme.io")
    org = client.post("/api/organizations", headers=_hdr(token),
                     json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=_hdr(token),
                     json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    assert inv["status"] == "draft"

    # Running before authorization is forbidden (SMPLSGHT-15).
    blocked = client.post(f"/api/investigations/{inv['id']}/run", headers=_hdr(token))
    assert blocked.status_code == 403

    # Record authorization, then run.
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=_hdr(token),
               json={"authorized_by": "CISO", "authorization_scope": "example.com domains"})
    run = client.post(f"/api/investigations/{inv['id']}/run", headers=_hdr(token))
    assert run.status_code == 200, run.text
    body = run.json()

    assert body["status"] == "success"
    assert body["authorized_by"] == "CISO"
    # two collectors found the same asset -> one deduped asset with merged provenance
    assert len(body["assets"]) == 1
    asset = body["assets"][0]
    assert asset["value"] == "api.example.com"
    assert len(asset["sources"]) == 2
    assert asset["confidence"] == 0.92

    # persisted and retrievable
    fetched = client.get(f"/api/investigations/{inv['id']}", headers=_hdr(token)).json()
    assert len(fetched["assets"]) == 1
