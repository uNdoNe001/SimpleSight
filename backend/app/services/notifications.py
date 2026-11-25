"""Outbound alert delivery (Phase 4 · SMPLSGHT-56).

When a run produces material alerts (app/services/alerts.py), each enabled notification channel
in the tenant receives a signed JSON payload. The transport is abstracted so the test suite
stays fully offline (a fake transport records calls instead of making HTTP requests), and
delivery is best-effort: a channel that errors is recorded and skipped, never failing the run.

Signing secrets are used to compute an HMAC-SHA256 header and are never logged or echoed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Investigation, NotificationChannel
from app.services.alerts import is_material
from app.services.audit import record_audit

SIGNATURE_HEADER = "X-SimpleSight-Signature"


@dataclass
class DeliveryResult:
    ok: bool
    status: int | None = None
    error: str | None = None


class Transport(Protocol):
    def send(self, url: str, body: bytes, headers: dict[str, str]) -> DeliveryResult: ...


class HttpxTransport:
    """Real HTTP transport. Short timeout; never raises — failures become DeliveryResult."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    def send(self, url: str, body: bytes, headers: dict[str, str]) -> DeliveryResult:
        import httpx

        try:
            resp = httpx.post(url, content=body, headers=headers, timeout=self._timeout)
            return DeliveryResult(ok=resp.status_code < 400, status=resp.status_code)
        except Exception as exc:  # noqa: BLE001 - best-effort delivery
            return DeliveryResult(ok=False, error=f"{type(exc).__name__}: {exc}")


# Module-level default; tests monkeypatch this to a fake that records calls.
default_transport: Transport = HttpxTransport()


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class _AlertLike(Protocol):
    change_type: str
    entity_key: str
    title: str
    severity: str | None
    detail: dict


def build_payload(investigation: Investigation, target: str, alerts: Iterable[_AlertLike]) -> dict:
    """The JSON body delivered to a webhook — structured, grounded in the change events."""
    alerts = list(alerts)
    return {
        "type": "simplesight.alerts",
        "investigation_id": investigation.id,
        "organization_id": investigation.organization_id,
        "target": target,
        "alert_count": len(alerts),
        "alerts": [
            {
                "change_type": a.change_type,
                "entity_key": a.entity_key,
                "title": a.title,
                "severity": a.severity,
                "detail": a.detail,
            }
            for a in alerts
        ],
    }


def deliver_alerts(
    db: Session,
    investigation: Investigation,
    target: str,
    alerts: list[_AlertLike],
    transport: Transport | None = None,
) -> int:
    """Deliver the material alerts to every enabled channel. Returns the count delivered OK.

    Only material alerts are sent; a non-material list short-circuits with no channel lookup.
    Each channel's outcome is audited without the payload's signature or the signing secret.
    """
    material = [a for a in alerts if is_material(a)]
    if not material:
        return 0

    channels = list(
        db.scalars(
            select(NotificationChannel).where(
                NotificationChannel.tenant_id == investigation.tenant_id,
                NotificationChannel.enabled.is_(True),
            )
        )
    )
    if not channels:
        return 0

    tx = transport or default_transport
    payload = build_payload(investigation, target, material)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    delivered = 0
    for ch in channels:
        headers = {"Content-Type": "application/json"}
        if ch.signing_secret:
            headers[SIGNATURE_HEADER] = sign(body, ch.signing_secret)
        result = tx.send(ch.target, body, headers)
        if result.ok:
            delivered += 1
        record_audit(
            db,
            tenant_id=investigation.tenant_id,
            actor_user_id=None,
            action="notification.deliver",
            target=investigation.id,
            detail={
                "channel_id": ch.id,
                "channel_type": ch.channel_type,
                "ok": result.ok,
                "status": result.status,
                "error": result.error,
                "alert_count": len(material),
            },
        )
    return delivered
