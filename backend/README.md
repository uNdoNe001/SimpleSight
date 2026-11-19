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

## Conventions

- Every collector implements the `Collector` interface in `collectors/base.py` and
  returns results wrapped in a `Provenance` envelope (source, timestamp, confidence,
  evidence pointer) — see SMPLSGHT-21.
- Nothing bypasses tenant scoping; all data access is tenant-filtered.
- MVP collectors are **passive only**.
