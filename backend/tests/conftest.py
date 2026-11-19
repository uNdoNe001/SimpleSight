"""Shared test fixtures and fakes.

All tests run fully offline — no collector makes a real network call, and the queue runs
inline, so no Redis/worker is needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)

# One shared in-memory SQLite DB (StaticPool => a single connection shared by all sessions).
test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- auth helpers ----------------------------------------------------------------------

def signup(client: TestClient, tenant: str, email: str, password: str = "password123") -> str:
    r = client.post(
        "/api/auth/signup",
        json={"tenant_name": tenant, "email": email, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- collector fakes -------------------------------------------------------------------

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


def two_collectors_same_asset() -> list[FakeCollector]:
    """Two collectors that both report api.example.com (to exercise dedup/merge)."""
    return [
        FakeCollector("ct", run=CollectorRun(
            outcome=CollectorOutcome.SUCCESS,
            results=[make_result("subdomain", "api.example.com", "crt.sh", 0.8)],
        )),
        FakeCollector("dns", run=CollectorRun(
            outcome=CollectorOutcome.SUCCESS,
            results=[make_result("subdomain", "api.example.com", "dns", 0.6)],
        )),
    ]
