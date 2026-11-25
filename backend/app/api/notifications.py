"""Notification-channel routes (Phase 4 · SMPLSGHT-56). Tenant-scoped, admin-managed.

  GET    /api/notifications/channels            -> list channels (no secrets)
  POST   /api/notifications/channels            -> create a channel (admin)
  DELETE /api/notifications/channels/{id}       -> delete a channel (admin)
  POST   /api/notifications/channels/{id}/test  -> send a test delivery (admin)

Channels send alert data to external destinations, so management is admin-only. The signing
secret is write-only — accepted on create, used for HMAC signing, never returned or logged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import NotificationChannel, Role, User
from app.schemas import ChannelCreate, ChannelOut, DeliveryTestResult
from app.services.audit import record_audit
from app.services.notifications import SIGNATURE_HEADER, default_transport, sign

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

_admin = require_role(Role.ADMIN)


def _channel_out(ch: NotificationChannel) -> ChannelOut:
    out = ChannelOut.model_validate(ch)
    out.has_secret = bool(ch.signing_secret)
    return out


def _owned(db: Session, channel_id: str, tenant_id: str) -> NotificationChannel:
    ch = db.get(NotificationChannel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    return ch


@router.get("/channels", response_model=list[ChannelOut])
def list_channels(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChannelOut]:
    channels = db.scalars(
        select(NotificationChannel).where(NotificationChannel.tenant_id == user.tenant_id)
    )
    return [_channel_out(ch) for ch in channels]


@router.post("/channels", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(
    body: ChannelCreate,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
) -> ChannelOut:
    ch = NotificationChannel(
        tenant_id=user.tenant_id,
        name=body.name,
        channel_type=body.channel_type,
        target=body.target,
        signing_secret=body.signing_secret,
        enabled=body.enabled,
    )
    db.add(ch)
    db.flush()
    record_audit(
        db, tenant_id=user.tenant_id, actor_user_id=user.id,
        action="notification.channel.create", target=ch.id,
        detail={"channel_type": ch.channel_type, "has_secret": bool(ch.signing_secret)},
    )
    db.commit()
    db.refresh(ch)
    return _channel_out(ch)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    channel_id: str,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
) -> None:
    ch = _owned(db, channel_id, user.tenant_id)
    db.delete(ch)
    record_audit(
        db, tenant_id=user.tenant_id, actor_user_id=user.id,
        action="notification.channel.delete", target=channel_id,
    )
    db.commit()


@router.post("/channels/{channel_id}/test", response_model=DeliveryTestResult)
def test_channel(
    channel_id: str,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
) -> DeliveryTestResult:
    """Send a synthetic ping to verify a channel is reachable, without waiting for a run."""
    ch = _owned(db, channel_id, user.tenant_id)
    import json

    payload = {"type": "simplesight.test", "channel_id": ch.id, "message": "SimpleSight test"}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers = {"Content-Type": "application/json"}
    if ch.signing_secret:
        headers[SIGNATURE_HEADER] = sign(body, ch.signing_secret)
    result = default_transport.send(ch.target, body, headers)
    record_audit(
        db, tenant_id=user.tenant_id, actor_user_id=user.id,
        action="notification.channel.test", target=ch.id,
        detail={"ok": result.ok, "status": result.status, "error": result.error},
    )
    db.commit()
    return DeliveryTestResult(ok=result.ok, status=result.status, error=result.error)
