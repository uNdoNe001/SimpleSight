"""Collector adapter interface and provenance envelope.

This is the contract every OSINT collector implements so new sources plug in without
touching orchestration (SMPLSGHT-19). Every result a collector emits is wrapped in a
`Provenance` envelope so findings can always be traced back to verifiable evidence
(SMPLSGHT-21, Design Overview §3.5 and §6: "AI must not invent findings").

MVP collectors are **passive only** — no active probing of target infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class CollectorOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. required provider key not configured


@dataclass(frozen=True)
class Provenance:
    """Where a single result came from. Attached to every emitted result."""

    source: str                      # named source/provider, e.g. "crt.sh"
    collected_at: datetime           # UTC collection timestamp
    confidence: float                # 0.0–1.0
    evidence_ref: str | None = None  # pointer to raw evidence in object storage
    collector_version: str = "0.0.1"

    @staticmethod
    def now(source: str, confidence: float, evidence_ref: str | None = None) -> Provenance:
        return Provenance(
            source=source,
            collected_at=datetime.now(UTC),
            confidence=confidence,
            evidence_ref=evidence_ref,
        )


@dataclass
class CollectorResult:
    """A single discovered item plus its provenance.

    `asset_type` and `value` are intentionally generic at this layer; normalization
    into the canonical asset model happens downstream (SMPLSGHT-30).
    """

    asset_type: str                  # e.g. "subdomain", "dns_record", "technology"
    value: str
    provenance: Provenance
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectorRun:
    """The result of running a collector once against a target."""

    outcome: CollectorOutcome
    results: list[CollectorResult] = field(default_factory=list)
    reason: str | None = None        # human-readable, required for PARTIAL/FAILED/SKIPPED


@dataclass
class CollectionContext:
    """Inputs a collector receives for a run."""

    target: str                      # e.g. a domain
    scope: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)  # provider keys, limits


class Collector(ABC):
    """Base class for all OSINT collectors.

    Implementations declare their identity and the provider keys they require, and
    implement `collect`. The framework handles scheduling, rate limiting, provenance
    persistence, and outcome roll-up — a new collector only implements this interface.
    """

    #: stable identifier, e.g. "certificate_transparency"
    name: str = "collector"

    #: one-line, human-readable summary of what this collector does (for discovery plans)
    description: str = ""

    #: config keys this collector needs; if any are missing the run is SKIPPED
    required_keys: tuple[str, ...] = ()

    #: False for anything that touches target infrastructure (gated, off in MVP)
    passive: bool = True

    def missing_keys(self, context: CollectionContext) -> list[str]:
        return [k for k in self.required_keys if not context.config.get(k)]

    @abstractmethod
    def collect(self, context: CollectionContext) -> CollectorRun:
        """Run the collector against the target and return a provenance-wrapped run."""
        raise NotImplementedError
