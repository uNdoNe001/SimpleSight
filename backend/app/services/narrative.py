"""Grounded executive narrative (Phase 4 · SMPLSGHT-58).

The core design rule of SimpleSight is that AI must never invent findings. This module honors
that: the narrative is built from the *same structured findings/exposure/change data* the rest
of the platform derived deterministically — not from free-form model imagination.

Two narrators:

* `TemplateNarrator` — deterministic, dependency-free, always available. It is the default and
  the only path the test suite exercises, so report output stays reproducible and offline.
* `ClaudeNarrator` — optional. Activated only when a Claude API key is configured for the
  tenant *and* `narrative_ai_enabled` is on. It is handed the structured payload as the sole
  ground truth with a system prompt that forbids new claims, and any error falls back to the
  template. Enabling it (configuring the key) is the user's explicit opt-in to sending
  investigation data to the model API.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger("simplesight.narrative")

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_MATERIAL = {"high", "critical"}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@dataclass
class NarrativePayload:
    """The structured ground truth a narrator may summarize — and nothing beyond it."""

    target: str
    score: int = 0
    grade: str = "A"
    label: str = "Minimal"
    counts: dict[str, int] = field(default_factory=dict)  # severity -> count (non-dismissed)
    confirmed: int = 0
    unverified: int = 0
    top_findings: list[dict] = field(default_factory=list)  # {title, severity, classification}
    changes: dict[str, int] = field(default_factory=dict)  # appeared/resolved/escalated

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "exposure": {"score": self.score, "grade": self.grade, "label": self.label},
            "counts": self.counts,
            "confirmed": self.confirmed,
            "unverified": self.unverified,
            "top_findings": self.top_findings,
            "changes": self.changes,
        }


@dataclass
class Narrative:
    text: str
    mode: str  # "template" | "claude"
    model: str | None = None


def build_payload(target: str, findings: Iterable[Any], exposure: Any,
                  changes: dict[str, int] | None = None) -> NarrativePayload:
    """Assemble the narrative payload from derived findings + exposure score (+ optional changes).

    Dismissed findings are excluded (they are not part of the posture), mirroring scoring.
    """
    active = [f for f in findings if _get(f, "status", "open") != "dismissed"]
    counts: dict[str, int] = {}
    confirmed = unverified = 0
    for f in active:
        sev = str(_get(f, "severity", "info")).lower()
        counts[sev] = counts.get(sev, 0) + 1
        if str(_get(f, "classification", "unverified")).lower() == "confirmed":
            confirmed += 1
        else:
            unverified += 1

    ordered = sorted(active, key=lambda f: (
        _SEVERITY_ORDER.get(str(_get(f, "severity", "info")).lower(), 9),
        -float(_get(f, "confidence", 0.0) or 0.0),
    ))
    top = [
        {
            "title": _get(f, "title", ""),
            "severity": str(_get(f, "severity", "info")).lower(),
            "classification": str(_get(f, "classification", "unverified")).lower(),
        }
        for f in ordered[:5]
    ]

    return NarrativePayload(
        target=target,
        score=int(_get(exposure, "score", 0) or 0),
        grade=str(_get(exposure, "grade", "A")),
        label=str(_get(exposure, "label", "Minimal")),
        counts=counts,
        confirmed=confirmed,
        unverified=unverified,
        top_findings=top,
        changes=changes or {},
    )


class Narrator(Protocol):
    def narrate(self, payload: NarrativePayload) -> str: ...


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


class TemplateNarrator:
    """Deterministic prose from the structured payload — no model, no network, no invention."""

    def narrate(self, payload: NarrativePayload) -> str:
        total = sum(payload.counts.values())
        material = sum(payload.counts.get(s, 0) for s in _MATERIAL)

        if total == 0:
            lead = (
                f"This passive assessment of {payload.target} surfaced no findings. "
                f"Exposure is rated {payload.score}/100 (grade {payload.grade}, "
                f"{payload.label.lower()})."
            )
            return lead

        sentences = [
            (
                f"This passive assessment of {payload.target} surfaced "
                f"{_plural(total, 'finding')} ({payload.confirmed} confirmed, "
                f"{payload.unverified} unverified), scoring {payload.score}/100 on exposure "
                f"(grade {payload.grade}, {payload.label.lower()})."
            )
        ]

        if material:
            titles = [
                f.get("title", "") for f in payload.top_findings
                if f.get("severity") in _MATERIAL
            ]
            lead_titles = "; ".join(t for t in titles[:3] if t)
            detail = f" — {lead_titles}" if lead_titles else ""
            sentences.append(
                f"{_plural(material, 'finding').capitalize()} rated high or critical warrant "
                f"priority attention{detail}."
            )
        else:
            sentences.append(
                "No high- or critical-severity findings were observed; the surfaced items are "
                "lower-severity hygiene and posture signals."
            )

        ch = payload.changes
        if ch:
            parts = []
            if ch.get("appeared"):
                parts.append(_plural(ch["appeared"], "new finding"))
            if ch.get("escalated"):
                parts.append(f"{ch['escalated']} escalated")
            if ch.get("resolved"):
                parts.append(f"{ch['resolved']} resolved")
            if parts:
                sentences.append("Since the previous run: " + ", ".join(parts) + ".")

        sentences.append(
            "All findings derive from passively collected evidence and are reported without "
            "active probing; unverified items reflect single-source or absence-based signals."
        )
        return " ".join(sentences)


_SYSTEM_PROMPT = (
    "You are a cybersecurity analyst writing a brief executive summary for a passive OSINT "
    "footprint assessment. You will be given a JSON object of findings that were derived "
    "deterministically from collected evidence. Summarize ONLY what is in that JSON. Do not "
    "invent findings, hosts, severities, numbers, or recommendations beyond what the data "
    "states. Do not speculate about exploitation. Write 2-4 sentences of plain prose, no "
    "markdown, no bullet points, no preamble."
)


class ClaudeNarrator:
    """Optional model-backed narrator. Strictly grounded; never the test path."""

    def __init__(self, api_key: str, model: str, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def narrate(self, payload: NarrativePayload) -> str:
        import httpx

        body = {
            "model": self._model,
            "max_tokens": 400,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Summarize this assessment. Ground every statement in this JSON:\n"
                        + json.dumps(payload.to_dict(), sort_keys=True)
                    ),
                }
            ],
        }
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = " ".join(p.strip() for p in parts if p).strip()
        if not text:
            raise ValueError("empty narrative from model")
        return text


def generate_narrative(payload: NarrativePayload, *, api_key: str | None = None) -> Narrative:
    """Produce a narrative, preferring the model only when configured; always falling back.

    The template narrator is the guaranteed path. The Claude narrator is attempted only when a
    key is supplied and the feature flag is on, and any failure degrades silently to template —
    the report must never break because the model was slow or unavailable.
    """
    if api_key and settings.narrative_ai_enabled:
        try:
            text = ClaudeNarrator(api_key, settings.narrative_model).narrate(payload)
            return Narrative(text=text, mode="claude", model=settings.narrative_model)
        except Exception as exc:  # noqa: BLE001 - never let AI failure break the report
            logger.warning("model narration failed, using template: %s", exc)
    return Narrative(text=TemplateNarrator().narrate(payload), mode="template")
