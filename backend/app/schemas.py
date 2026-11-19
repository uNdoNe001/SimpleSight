"""API request/response models (Pydantic).

These are the wire shapes for the synchronous MVP endpoint. They are intentionally
separate from the collector dataclasses and the (future) persisted ORM models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    source: str
    collected_at: datetime
    confidence: float
    evidence_ref: str | None = None


class AssetOut(BaseModel):
    """A normalized, deduplicated asset with merged provenance (SMPLSGHT-29/30/31)."""

    asset_type: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceRef]
    first_seen: datetime
    last_seen: datetime
    attributes: dict = Field(default_factory=dict)


class CollectorRunOut(BaseModel):
    collector: str
    outcome: str
    reason: str | None = None
    result_count: int


class RunInvestigationRequest(BaseModel):
    domain: str = Field(..., examples=["example.com"])


class RunInvestigationResponse(BaseModel):
    target: str
    overall_outcome: str
    collectors: list[CollectorRunOut]
    asset_count: int
    assets: list[AssetOut]
