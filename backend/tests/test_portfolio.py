"""Portfolio dashboard rollups (Phase 5 · SMPLSGHT-62/63/64), deterministic & offline.

Service-level tests seed ORM rows directly so they don't depend on the findings rule engine;
one API smoke test confirms the route wiring and tenant scoping end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import (
    ChangeEvent,
    ChangeType,
    Finding,
    FindingClassification,
    FindingSeverity,
    FindingStatus,
    Investigation,
    Organization,
    Tenant,
)
from app.services.portfolio import monitoring_health, recent_activity, summarize
from tests import conftest

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


# --- seeding helpers -------------------------------------------------------------------

def _tenant(db, name="Acme") -> str:
    t = Tenant(name=name)
    db.add(t)
    db.flush()
    return t.id


def _org(db, tenant_id, name="Acme Corp", archived=False) -> Organization:
    o = Organization(tenant_id=tenant_id, name=name, primary_domain="example.com",
                     archived=archived)
    db.add(o)
    db.flush()
    return o


def _inv(db, tenant_id, org, *, status="success", completed_at=NOW - timedelta(hours=1),
         monitoring_enabled=False, monitoring_interval=None, findings=()) -> Investigation:
    inv = Investigation(
        tenant_id=tenant_id, organization_id=org.id, assessment_type="passive-osint",
        status=status, completed_at=completed_at, created_at=NOW - timedelta(days=5),
        authorized_by="CISO", authorized_at=NOW - timedelta(days=5),
        monitoring_enabled=monitoring_enabled, monitoring_interval=monitoring_interval,
        created_by="u1",
    )
    for sev, conf in findings:
        inv.findings.append(Finding(
            tenant_id=tenant_id, organization_id=org.id, finding_key=f"{sev}-{conf}",
            finding_type="test", title=f"{sev} finding", severity=sev, confidence=conf,
            classification=FindingClassification.CONFIRMED.value,
            status=FindingStatus.OPEN.value,
        ))
    db.add(inv)
    db.flush()
    return inv


def _event(db, inv, *, change_type=ChangeType.FINDING_APPEARED.value, severity="high",
           run_at=NOW, acknowledged_at=None, entity_key="k", detail=None) -> ChangeEvent:
    e = ChangeEvent(
        tenant_id=inv.tenant_id, investigation_id=inv.id, organization_id=inv.organization_id,
        change_type=change_type, entity_type="finding", entity_key=entity_key,
        title="t", severity=severity, run_at=run_at, acknowledged_at=acknowledged_at,
        detail=detail or {},
    )
    db.add(e)
    db.flush()
    return e


# --- summary ---------------------------------------------------------------------------

def test_summary_counts_distribution_and_leader():
    db = conftest.TestSession()
    try:
        t = _tenant(db)
        org = _org(db, t)
        _org(db, t, name="Old", archived=True)
        crit = _inv(db, t, org, findings=[(FindingSeverity.CRITICAL.value, 0.9)],
                    monitoring_enabled=True, monitoring_interval="daily")
        _inv(db, t, org, findings=[(FindingSeverity.HIGH.value, 0.9)],
             monitoring_enabled=True, monitoring_interval="weekly")
        _inv(db, t, org, findings=[])                      # assessed, no findings -> A
        _inv(db, t, org, status="draft", completed_at=None)  # not assessed
        db.commit()

        s = summarize(db, t)
        assert s.organizations_total == 2 and s.organizations_archived == 1
        assert s.investigations_total == 4
        assert s.assessed_investigations == 3
        # one critical (D), one high (C), one empty (A)
        assert s.exposure_distribution == {"A": 1, "B": 0, "C": 1, "D": 1, "F": 0}
        assert s.highest_exposure is not None
        assert s.highest_exposure.investigation_id == crit.id
        assert s.highest_exposure.grade == "D"
        assert s.monitoring_enabled == 2
        assert s.monitoring_by_interval == {"daily": 1, "weekly": 1}
    finally:
        db.close()


def test_summary_open_alerts_counts_only_unacked_material():
    db = conftest.TestSession()
    try:
        t = _tenant(db)
        org = _org(db, t)
        inv = _inv(db, t, org)
        _event(db, inv, severity="high", entity_key="a")                      # material, open
        _event(db, inv, severity="low", entity_key="b")                       # not material
        _event(db, inv, severity="critical", entity_key="c",
               acknowledged_at=NOW)                                           # acked -> excluded
        db.commit()
        assert summarize(db, t).open_alerts == 1
    finally:
        db.close()


def test_summary_is_tenant_isolated():
    db = conftest.TestSession()
    try:
        a = _tenant(db, "A")
        b = _tenant(db, "B")
        _inv(db, b, _org(db, b), findings=[(FindingSeverity.CRITICAL.value, 0.9)])
        db.commit()
        s = summarize(db, a)
        assert s.investigations_total == 0 and s.highest_exposure is None
        assert s.exposure_distribution == {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    finally:
        db.close()


# --- activity feed ---------------------------------------------------------------------

def test_activity_newest_first_annotated_and_filtered():
    db = conftest.TestSession()
    try:
        t = _tenant(db)
        org = _org(db, t, name="Acme Corp")
        inv = _inv(db, t, org)
        _event(db, inv, severity="high", run_at=NOW - timedelta(hours=2), entity_key="old")
        _event(db, inv, severity="low", change_type=ChangeType.ASSET_ADDED.value,
               run_at=NOW, entity_key="new")
        db.commit()

        items = recent_activity(db, t)
        assert [i.event.entity_key for i in items] == ["new", "old"]  # newest run first
        assert items[0].organization_name == "Acme Corp"
        assert items[0].is_material is False and items[1].is_material is True

        material = recent_activity(db, t, material_only=True)
        assert [i.event.entity_key for i in material] == ["old"]

        assert len(recent_activity(db, t, limit=1)) == 1
    finally:
        db.close()


# --- monitoring health -----------------------------------------------------------------

def test_monitoring_health_states_and_ordering():
    db = conftest.TestSession()
    try:
        t = _tenant(db)
        org = _org(db, t)
        fresh = _inv(db, t, org, monitoring_enabled=True, monitoring_interval="daily",
                     completed_at=NOW - timedelta(hours=1))
        due = _inv(db, t, org, monitoring_enabled=True, monitoring_interval="daily",
                   completed_at=NOW - timedelta(hours=25))
        overdue = _inv(db, t, org, monitoring_enabled=True, monitoring_interval="daily",
                       completed_at=NOW - timedelta(days=3))
        pending = _inv(db, t, org, monitoring_enabled=True, monitoring_interval="daily",
                       completed_at=None, status="draft")
        _inv(db, t, org, monitoring_enabled=False)  # excluded
        db.commit()

        rows = monitoring_health(db, t, now=NOW)
        state = {r.investigation_id: r.state for r in rows}
        assert state[fresh.id] == "fresh"
        assert state[due.id] == "due"
        assert state[overdue.id] == "overdue"
        assert state[pending.id] == "pending"
        # overdue, due, pending, fresh — attention first
        assert [r.state for r in rows] == ["overdue", "due", "pending", "fresh"]
    finally:
        db.close()


# --- API smoke -------------------------------------------------------------------------

def test_portfolio_routes_scoped_to_caller(client):
    from tests.conftest import auth_header, signup

    token = signup(client, "Acme", "admin@acme.io")
    r = client.get("/api/portfolio/summary", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["investigations_total"] == 0
    assert body["organizations"]["total"] == 0
    assert body["highest_exposure"] is None
    assert client.get("/api/portfolio/activity", headers=auth_header(token)).json() == []
    assert client.get("/api/portfolio/monitoring-health",
                      headers=auth_header(token)).json() == []
