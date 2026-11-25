"""Alerting over change events (Phase 3 · SMPLSGHT-53).

Alerts are not a separate store — they are the *material* subset of change events
(app/services/changes.py): a newly-appeared high/critical finding, or a severity escalation
into high/critical. Acknowledgement is carried on the change event itself (`acknowledged_at`),
so acknowledging an alert and triaging the underlying finding stay independent.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.models import ChangeType

MATERIAL_SEVERITIES = frozenset({"high", "critical"})


class _ChangeLike(Protocol):
    change_type: str
    severity: str | None
    detail: dict


def is_material(event: _ChangeLike) -> bool:
    """Whether a change event rises to an alert.

    Material = a new finding at high/critical severity, or a severity change that *escalated*
    into high/critical. A de-escalation or a low/medium appearance is tracked as a change but
    does not alert.
    """
    sev = (event.severity or "").lower()
    if event.change_type == ChangeType.FINDING_APPEARED.value:
        return sev in MATERIAL_SEVERITIES
    if event.change_type == ChangeType.FINDING_SEVERITY_CHANGED.value:
        detail = event.detail or {}
        to = str(detail.get("to", "")).lower()
        return bool(detail.get("escalated")) and to in MATERIAL_SEVERITIES
    return False


def material_events(events: Iterable[_ChangeLike]) -> list[_ChangeLike]:
    return [e for e in events if is_material(e)]
