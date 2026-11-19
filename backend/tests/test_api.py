"""API tests for auth, tenancy, RBAC, and the investigation flow (offline)."""

from __future__ import annotations

from app.api import investigations as inv_api
from tests.conftest import auth_header, signup

# --- auth ------------------------------------------------------------------------------

def test_signup_login_me(client):
    token = signup(client, "Acme", "admin@acme.io")
    me = client.get("/api/auth/me", headers=auth_header(token)).json()
    assert me["email"] == "admin@acme.io"
    assert me["role"] == "admin"

    login = client.post("/api/auth/login",
                        json={"email": "admin@acme.io", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_unauthenticated_is_rejected(client):
    assert client.get("/api/organizations").status_code == 401  # no bearer token


def test_wrong_password_rejected(client):
    signup(client, "Acme", "admin@acme.io")
    r = client.post("/api/auth/login",
                   json={"email": "admin@acme.io", "password": "wrong"})
    assert r.status_code == 401


# --- tenancy isolation (SMPLSGHT-9) ----------------------------------------------------

def test_tenant_cannot_access_another_tenants_org(client):
    tok_a = signup(client, "TenantA", "a@tenanta.io")
    tok_b = signup(client, "TenantB", "b@tenantb.io")

    org = client.post("/api/organizations", headers=auth_header(tok_a),
                     json={"name": "A Corp", "primary_domain": "a.example"}).json()

    assert client.get(f"/api/organizations/{org['id']}",
                     headers=auth_header(tok_b)).status_code == 404
    assert client.get("/api/organizations", headers=auth_header(tok_b)).json() == []
    assert client.get(f"/api/organizations/{org['id']}",
                     headers=auth_header(tok_a)).status_code == 200


# --- RBAC (SMPLSGHT-10) ----------------------------------------------------------------

def test_readonly_user_cannot_create_org(client):
    admin = signup(client, "Acme", "admin@acme.io")
    client.post("/api/users", headers=auth_header(admin),
               json={"email": "ro@acme.io", "password": "password123", "role": "readonly"})
    ro = client.post("/api/auth/login",
                    json={"email": "ro@acme.io", "password": "password123"}).json()["access_token"]

    assert client.post("/api/organizations", headers=auth_header(ro),
                      json={"name": "Nope"}).status_code == 403
    assert client.get("/api/organizations", headers=auth_header(ro)).status_code == 200


# --- investigation flow + attestation gate + async run (SMPLSGHT-14/-15/-17/-18) -------

def _make_investigation(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                     json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                     json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    return inv["id"]


def test_run_requires_authorization(client):
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _make_investigation(client, token)
    r = client.post(f"/api/investigations/{inv_id}/run", headers=auth_header(token))
    assert r.status_code == 403  # no attestation yet


def test_run_enqueues_and_sets_running(client, monkeypatch):
    enqueued: list[str] = []
    monkeypatch.setattr(inv_api, "enqueue_investigation_run", lambda inv_id: enqueued.append(inv_id))

    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _make_investigation(client, token)
    client.post(f"/api/investigations/{inv_id}/authorize", headers=auth_header(token),
               json={"authorized_by": "CISO", "authorization_scope": "example.com"})

    r = client.post(f"/api/investigations/{inv_id}/run", headers=auth_header(token))
    assert r.status_code == 202
    assert r.json()["status"] == "running"
    assert enqueued == [inv_id]  # job was enqueued exactly once

    # running again while running is a conflict
    assert client.post(f"/api/investigations/{inv_id}/run",
                      headers=auth_header(token)).status_code == 409
