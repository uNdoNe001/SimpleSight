"""SimpleSight backend API entrypoint.

Minimal scaffold: exposes a health check so the dev stack can be verified end to end.
Feature routers (auth, organizations, investigations, findings) are added under app/api
as the SMPLSGHT backlog is implemented.
"""

from fastapi import FastAPI

from app.api import investigations
from app.core.config import settings

app = FastAPI(
    title="SimpleSight API",
    version="0.0.1",
    description="Open-Source Intelligence & Digital Footprint Intelligence Platform",
)

app.include_router(investigations.router)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe (served at both / and /api for the frontend dev proxy)."""
    return {"status": "ok", "env": settings.app_env}
