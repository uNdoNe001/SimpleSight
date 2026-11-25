# SimpleSight

[![CI](https://github.com/uNdoNe001/SimpleSight/actions/workflows/ci.yml/badge.svg)](https://github.com/uNdoNe001/SimpleSight/actions/workflows/ci.yml)

**Open-Source Intelligence & Digital Footprint Intelligence Platform**
_Part of SimpleSuite by Summit Cyber Group, LLC_

> See What Others Miss.

SimpleSight is an AI-assisted OSINT platform that discovers, correlates, and analyzes
publicly available intelligence about organizations and their digital footprints —
turning public information into actionable security findings.

---

## Status

Early development. See the **[Design Overview](docs/Design%20Overview.md)** for the full
product spec and **[docs/backlog.md](docs/backlog.md)** for the Phase 1 (MVP) backlog,
which is tracked in Jira under the **SMPLSGHT** project.

**MVP scope is 100% passive OSINT.** No active probing/scanning is performed in Phase 1.
All collection requires a recorded authorization attestation.

## Architecture (proposed)

| Layer | Stack |
|---|---|
| Frontend | React + TypeScript (Vite) |
| Backend | Python + FastAPI |
| Workers | Background job queue (Redis-backed) for collectors |
| Data | PostgreSQL (tenants, assets, findings, investigations) + object storage for evidence |
| Cache / queue | Redis |

```
SimpleSight/
├── backend/           FastAPI API + collectors + workers
│   ├── app/           API application (routes, config)
│   ├── collectors/    OSINT collector adapters (passive)
│   └── workers/       Background job workers
├── frontend/          React + TypeScript SPA
├── docs/              Design overview, backlog
└── docker-compose.yml Local dev services (Postgres + Redis)
```

## Local development

```bash
# Start supporting services (Postgres + Redis)
docker compose up -d

# Backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload   # http://localhost:8000  (GET /health)

# Frontend (Node 20+)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## Security & ethics

SimpleSight collects only publicly available information and is built around strict
guardrails (see the Design Overview, §9):

- Passive-by-default; active collection is separately gated and off in the MVP.
- Every finding links to verifiable source evidence; AI must not invent findings.
- Secret values are never retained unnecessarily; evidence uses redaction.
- Strict tenant isolation, least privilege, audit logging, and provider rate limiting.

---

_Part of SimpleSuite by Summit Cyber Group._
