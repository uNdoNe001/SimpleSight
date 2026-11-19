"""SimpleSight backend API entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, investigations, organizations, users
from app.core.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    # MVP: create tables on startup. Replace with Alembic migrations before production.
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


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe (served at both / and /api for the frontend dev proxy)."""
    return {"status": "ok", "env": settings.app_env}
