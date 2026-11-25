"""Grounded AI narrative (Phase 4 · Story D, SMPLSGHT-58).

The deterministic template narrator is the always-available path exercised here; the
Claude-backed narrator is never called without a configured key, which these tests assert.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services import narrative as narr
from app.services.narrative import (
    TemplateNarrator,
    build_payload,
    generate_narrative,
)
from tests import conftest
from tests.conftest import auth_header, signup


def _finding(severity: str, *, title: str, classification: str = "confirmed", status: str = "open",
             confidence: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(
        severity=severity, title=title, classification=classification, status=status,
        confidence=confidence,
    )


def _exposure(score: int, grade: str, label: str) -> SimpleNamespace:
    return SimpleNamespace(score=score, grade=grade, label=label)


# --- payload + template ----------------------------------------------------------------

def test_payload_excludes_dismissed_and_counts():
    findings = [
        _finding("high", title="Exposed admin"),
        _finding("low", title="Missing CAA", classification="unverified"),
        _finding("critical", title="Takeover", status="dismissed"),
    ]
    p = build_payload("example.com", findings, _exposure(40, "C", "Moderate"))
    assert p.counts == {"high": 1, "low": 1}  # dismissed critical excluded
    assert p.confirmed == 1 and p.unverified == 1
    assert p.top_findings[0]["title"] == "Exposed admin"  # highest severity leads


def test_template_mentions_only_supplied_facts():
    findings = [_finding("high", title="Exposed admin panel")]
    p = build_payload("acme.com", findings, _exposure(55, "D", "Elevated"))
    text = TemplateNarrator().narrate(p)
    assert "acme.com" in text
    assert "55/100" in text and "grade D" in text
    assert "Exposed admin panel" in text
    assert "1 finding" in text


def test_template_handles_no_findings():
    p = build_payload("clean.com", [], _exposure(0, "A", "Minimal"))
    text = TemplateNarrator().narrate(p)
    assert "no findings" in text.lower()
    assert "clean.com" in text


def test_template_reports_changes_when_present():
    p = build_payload("acme.com", [_finding("high", title="X")],
                      _exposure(30, "C", "Moderate"),
                      changes={"appeared": 2, "escalated": 1})
    text = TemplateNarrator().narrate(p)
    assert "Since the previous run" in text
    assert "2 new findings" in text


def test_generate_uses_template_without_api_key():
    p = build_payload("acme.com", [_finding("high", title="X")], _exposure(30, "C", "Moderate"))
    n = generate_narrative(p, api_key=None)
    assert n.mode == "template" and n.model is None


def test_generate_falls_back_to_template_on_model_error(monkeypatch):
    # With a key present but the model call raising, we must degrade to template, never break.
    class _Boom:
        def __init__(self, *a, **k): ...
        def narrate(self, payload):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(narr, "ClaudeNarrator", _Boom)
    p = build_payload("acme.com", [_finding("high", title="X")], _exposure(30, "C", "Moderate"))
    n = generate_narrative(p, api_key="sk-test")
    assert n.mode == "template"


def test_generate_uses_model_when_key_and_it_succeeds(monkeypatch):
    class _Fake:
        def __init__(self, api_key, model, timeout=20.0):
            assert api_key == "sk-test"
        def narrate(self, payload):
            return "Grounded summary from the model."

    monkeypatch.setattr(narr, "ClaudeNarrator", _Fake)
    p = build_payload("acme.com", [_finding("high", title="X")], _exposure(30, "C", "Moderate"))
    n = generate_narrative(p, api_key="sk-test")
    assert n.mode == "claude" and n.text == "Grounded summary from the model."


# --- API -------------------------------------------------------------------------------

def test_narrative_endpoint_returns_template(client, monkeypatch):
    from app import tasks
    from app.services import pipeline
    from collectors.base import CollectorOutcome, CollectorRun
    from tests.conftest import FakeCollector, make_result

    monkeypatch.setattr(tasks, "SessionLocal", conftest.TestSession)
    monkeypatch.setattr(pipeline, "default_collectors", lambda: [
        FakeCollector("ct", run=CollectorRun(
            outcome=CollectorOutcome.SUCCESS,
            results=[make_result("subdomain", "a.example.com", "crt.sh", 0.8)],
        ))
    ])

    token = signup(client, "Acme", "admin@acme.io")
    org = client.post("/api/organizations", headers=auth_header(token),
                      json={"name": "Acme", "primary_domain": "example.com"}).json()
    inv = client.post("/api/investigations", headers=auth_header(token),
                      json={"organization_id": org["id"], "assessment_type": "passive-osint"}).json()
    client.post(f"/api/investigations/{inv['id']}/authorize", headers=auth_header(token),
                json={"authorized_by": "CISO", "authorization_scope": "example.com"})
    tasks.run_investigation_task(inv["id"])

    r = client.get(f"/api/investigations/{inv['id']}/narrative", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "template"
    assert "example.com" in body["text"]
