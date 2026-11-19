"""SimpleSight backend API entrypoint.

Minimal scaffold: exposes a health check so the dev stack can be verified end to end.
Feature routers (auth, organizations, investigations, findings) are added under app/api
as the SMPLSGHT backlog is implemented.
"""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title="SimpleSight API",
    version="0.0.1",
    description="Open-Source Intelligence & Digital Footprint Intelligence Platform",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "env": settings.app_env}
