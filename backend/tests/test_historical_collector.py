"""Historical records collector (SMPLSGHT-27), with a fake HTTP client."""

from __future__ import annotations

from collectors.base import CollectionContext, CollectorOutcome
from collectors.historical_records import HistoricalRecordsCollector

CTX = CollectionContext(target="example.com")

# CDX returns a header row followed by data rows (collapsed to one per year).
CDX_SAMPLE = [["timestamp"], ["19991128000000"], ["20050314000000"], ["20231101000000"]]


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _Resp(self._payload)


def test_summarizes_archive_history():
    client = FakeClient(CDX_SAMPLE)
    run = HistoricalRecordsCollector(client=client).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert len(run.results) == 1
    attrs = run.results[0].attributes
    assert attrs["first_snapshot"] == "1999-11-28"
    assert attrs["last_snapshot"] == "2023-11-01"
    assert attrs["years_archived"] == 3
    # queried with year-collapse
    _, params = client.calls[0]
    assert params["collapse"] == "timestamp:4"


def test_no_snapshots_is_empty_success():
    run = HistoricalRecordsCollector(client=FakeClient([["timestamp"]])).collect(CTX)
    assert run.outcome is CollectorOutcome.SUCCESS
    assert run.results == []
    assert "no archived snapshots" in run.reason
