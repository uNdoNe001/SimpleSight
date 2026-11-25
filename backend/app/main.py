"""SimpleSight backend API entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    audit,
    auth,
    changes,
    findings,
    investigations,
    organizations,
    reports,
    secrets,
    users,
)
from app.core.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Dev convenience only. In production, AUTO_CREATE_TABLES=false and the schema is
    # managed with Alembic (`alembic upgrade head`); see migrations/.
    if settings.auto_create_tables:
        init_db()
    yield


app = FastAPI(
    title="SimpleSight API",
    version="0.0.1",
    description="Open-Source Intelligence & Digital Footprint Intelligence Platform",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(organizations.router)
app.include_router(investigations.router)
app.include_router(findings.router)
app.include_router(changes.router)
app.include_router(reports.router)
app.include_router(secrets.router)
app.include_router(audit.router)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe (served at both / and /api for the frontend dev proxy)."""
    return {"status": "ok", "env": settings.app_env}
