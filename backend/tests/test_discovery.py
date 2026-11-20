"""Discovery-plan generation (SMPLSGHT-16): pure builder + API, offline."""

from __future__ import annotations

from app.services.discovery import build_discovery_plan
from collectors.base import CollectionContext, Collector, CollectorRun
from tests.conftest import auth_header, signup


class _C(Collector):
    def __init__(self, name, *, keys=(), passive=True, desc="d"):
        self.name = name
        self.required_keys = keys
        self.passive = passive
        self.description = desc

    def collect(self, context: CollectionContext) -> CollectorRun:  # pragma: no cover
        raise NotImplementedError


# --- pure builder ----------------------------------------------------------------------

def test_plan_marks_keyed_collector_skipped_when_key_absent():
    plan = build_discovery_plan(
        "example.com", ["alt.example.com"],
        [_C("dns"), _C("premium", keys=("shodan_api_key",))],
        configured_keys=set(),
    )
    steps = {s.collector: s for s in plan.steps}
    assert steps["dns"].enabled is True
    assert steps["premium"].enabled is False
    assert "shodan_api_key" in steps["premium"].skip_reason
    assert plan.enabled_count == 1
    assert plan.skipped_count == 1
    assert plan.additional_targets == ["alt.example.com"]


def test_plan_enables_keyed_collector_when_key_present():
    plan = build_discovery_plan(
        "example.com", [], [_C("premium", keys=("shodan_api_key",))],
        configured_keys={"shodan_api_key"},
    )
    assert plan.steps[0].enabled is True
    assert plan.skipped_count == 0


def test_plan_passive_only_flag():
    assert build_discovery_plan("x", [], [_C("a"), _C("b")], set()).passive_only is True
    assert build_discovery_plan(
        "x", [], [_C("a"), _C("b", passive=False)], set()).passive_only is False


# --- API -------------------------------------------------------------------------------

def _draft_investigation(client, token) -> str:
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com",
                            "additional_domains": ["acme.io"]}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"],
                            "assessment_type": "passive-osint"}).json()
    return inv["id"]


def test_plan_endpoint_on_draft(client):
    token = signup(client, "Acme", "admin@acme.io")
    inv_id = _draft_investigation(client, token)
    plan = client.get(f"/api/investigations/{inv_id}/plan",
                      headers=auth_header(token)).json()
    assert plan["target"] == "example.com"
    assert plan["additional_targets"] == ["acme.io"]
    assert plan["passive_only"] is True
    # the four MVP collectors are all keyless, so all are enabled
    assert plan["enabled_count"] == len(plan["steps"]) == 4
    assert plan["skipped_count"] == 0
    names = {s["collector"] for s in plan["steps"]}
    assert {"dns_records", "certificate_transparency", "whois_rdap",
            "historical_records"} == names
    assert all(s["description"] for s in plan["steps"])


def test_plan_tenant_isolated(client):
    tok_a = signup(client, "TenantA", "a@tenanta.io")
    inv_id = _draft_investigation(client, tok_a)
    tok_b = signup(client, "TenantB", "b@tenantb.io")
    assert client.get(f"/api/investigations/{inv_id}/plan",
                      headers=auth_header(tok_b)).status_code == 404
