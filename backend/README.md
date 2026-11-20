# SimpleSight Backend

FastAPI service, OSINT collectors, and background workers.

## Layout

```
backend/
├── app/
│   ├── main.py        FastAPI application entrypoint (GET /health)
│   ├── core/
│   │   └── config.py  Settings (env-driven)
│   └── api/           API routers (added per feature)
├── collectors/
│   └── base.py        Collector adapter interface (see SMPLSGHT-19)
└── workers/           Background job workers (see SMPLSGHT-18)
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Then `GET http://localhost:8000/health`.

## Database schema

The schema is managed with **Alembic** (`migrations/`). In production, apply migrations:

```bash
alembic upgrade head          # reads DATABASE_URL from the environment / .env
```

After changing a model, autogenerate a revision and review it before committing:

```bash
alembic revision --autogenerate -m "describe the change"
```

For local dev, `AUTO_CREATE_TABLES=true` (the default) creates tables on startup so you can
skip migrations while iterating; set it to `false` to rely solely on Alembic.

## Background worker

Collection runs on an RQ worker (SMPLSGHT-18), not in the request. Start Redis (via the
repo's `docker compose up -d`) and run a worker:

```bash
rq worker collection          # reads REDIS_URL / DATABASE_URL from the environment
```

`POST /api/investigations/{id}/run` enqueues a job and returns `202` with the investigation
in `running` status; poll `GET /api/investigations/{id}` for results.

For local dev without Redis or a worker, set `QUEUE_EAGER=true` to run collection inline.

## Conventions

- Every collector implements the `Collector` interface in `collectors/base.py` and
  returns results wrapped in a `Provenance` envelope (source, timestamp, confidence,
  evidence pointer) — see SMPLSGHT-21.
- Nothing bypasses tenant scoping; all data access is tenant-filtered.
- MVP collectors are **passive only**.
