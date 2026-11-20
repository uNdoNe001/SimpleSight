"""Audit-log read API (SMPLSGHT-12): admin-only, tenant-scoped, filtered, offline."""

from __future__ import annotations

from tests.conftest import auth_header, signup


def test_signup_and_activity_are_audited_and_listed(client):
    token = signup(client, "Acme", "admin@acme.io")
    # generate some auditable activity
    client.post("/api/organizations", headers=auth_header(token),
                json={"name": "Acme", "primary_domain": "example.com"})

    entries = client.get("/api/audit", headers=auth_header(token)).json()
    actions = {e["action"] for e in entries}
    assert "auth.signup" in actions
    assert "organization.create" in actions
    # newest first
    times = [e["created_at"] for e in entries]
    assert times == sorted(times, reverse=True)


def test_audit_filter_by_action(client):
    token = signup(client, "Acme", "admin@acme.io")
    client.post("/api/auth/login", json={"email": "admin@acme.io", "password": "password123"})

    logins = client.get("/api/audit?action=auth.login", headers=auth_header(token)).json()
    assert len(logins) >= 1
    assert all(e["action"] == "auth.login" for e in logins)


def test_audit_requires_admin(client):
    admin = signup(client, "Acme", "admin@acme.io")
    client.post("/api/users", headers=auth_header(admin),
                json={"email": "an@acme.io", "password": "password123", "role": "analyst"})
    analyst = client.post("/api/auth/login",
                          json={"email": "an@acme.io", "password": "password123"}
                          ).json()["access_token"]
    assert client.get("/api/audit", headers=auth_header(analyst)).status_code == 403


def test_audit_is_tenant_scoped(client):
    tok_a = signup(client, "TenantA", "a@tenanta.io")
    client.post("/api/organizations", headers=auth_header(tok_a),
                json={"name": "A Corp", "primary_domain": "a.example"})
    tok_b = signup(client, "TenantB", "b@tenantb.io")

    a_entries = client.get("/api/audit", headers=auth_header(tok_a)).json()
    b_entries = client.get("/api/audit", headers=auth_header(tok_b)).json()
    assert any(e["action"] == "organization.create" for e in a_entries)
    # Tenant B sees only its own signup, never Tenant A's org creation.
    assert all(e["action"] != "organization.create" for e in b_entries)


def test_audit_limit(client):
    token = signup(client, "Acme", "admin@acme.io")
    for i in range(3):
        client.post("/api/organizations", headers=auth_header(token),
                    json={"name": f"Org{i}"})
    limited = client.get("/api/audit?limit=2", headers=auth_header(token)).json()
    assert len(limited) == 2
