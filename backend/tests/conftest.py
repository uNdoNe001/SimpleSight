"""Shared test fakes.

All tests run fully offline — no collector in the suite makes a real network call.
"""

from __future__ import annotations

from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)


class FakeCollector(Collector):
    """A collector whose behavior is fixed at construction, for exercising the framework."""

    def __init__(
        self,
        name: str,
        *,
        run: CollectorRun | None = None,
        raises: Exception | None = None,
        required_keys: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.required_keys = required_keys
        self._run = run
        self._raises = raises

    def collect(self, context: CollectionContext) -> CollectorRun:
        if self._raises is not None:
            raise self._raises
        return self._run or CollectorRun(outcome=CollectorOutcome.SUCCESS)


def make_result(asset_type: str, value: str, source: str, confidence: float) -> CollectorResult:
    return CollectorResult(
        asset_type=asset_type,
        value=value,
        provenance=Provenance.now(source=source, confidence=confidence),
    )
