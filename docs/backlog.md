# SimpleSight Backlog (Phase 1 — MVP)

Tracked in Jira: **[SMPLSGHT](https://summitcyber.atlassian.net/browse/SMPLSGHT)**.
This file mirrors the Jira structure for in-repo reference. Jira is the source of truth.

## Scope decisions (Phase 1)

- **Subject model:** investigations may target the tenant's own org **or** a third party
  (vendor/client), gated by an explicit **authorization attestation** recorded before any
  collection runs. _(Assumption pending confirmation — see SMPLSGHT-1.)_
- **Passive only:** no active probing/scanning in the MVP. Active collection is deferred
  and separately gated.
- Phases 2–4 (expanded OSINT, AI correlation, continuous monitoring, SimpleSuite
  integration) are **not** yet on the board — MVP only.

## Epics

| Key | Epic |
|---|---|
| SMPLSGHT-1 | Platform Foundation & Multi-Tenancy |
| SMPLSGHT-2 | Investigation Workspace & Organization Management |
| SMPLSGHT-3 | Digital Infrastructure Discovery (MVP Collectors) |
| SMPLSGHT-4 | Collection Framework & Job Orchestration |
| SMPLSGHT-5 | Intelligence Model, Normalization & Findings |
| SMPLSGHT-6 | Dashboards & Findings UX |
| SMPLSGHT-7 | Executive Reporting (PDF) |

## Stories

### SMPLSGHT-1 · Platform Foundation & Multi-Tenancy
- SMPLSGHT-8 — User authentication (signup, login, sessions)
- SMPLSGHT-9 — Tenant model and strict row-level isolation
- SMPLSGHT-10 — Role-based access control (Admin, Analyst, Read-only)
- SMPLSGHT-11 — Centralized secrets management for provider API keys
- SMPLSGHT-12 — Audit logging for auth and collection activity

### SMPLSGHT-2 · Investigation Workspace & Organization Management
- SMPLSGHT-13 — Organization CRUD (name, aliases, domains) · OSINT004
- SMPLSGHT-14 — Create investigation with scope and assessment type · OSINT002
- SMPLSGHT-15 — Authorization attestation gate before collection
- SMPLSGHT-16 — Discovery-plan generation from scope
- SMPLSGHT-17 — Investigation status lifecycle (draft/running/complete/partial/failed)

### SMPLSGHT-3 · Digital Infrastructure Discovery (MVP Collectors)
- SMPLSGHT-22 — WHOIS / domain registration collector · OSINT011
- SMPLSGHT-23 — DNS record enumeration collector · OSINT011
- SMPLSGHT-24 — Subdomain discovery collector · OSINT013
- SMPLSGHT-25 — Certificate transparency collector · OSINT013
- SMPLSGHT-26 — Public technology fingerprinting collector · OSINT018
- SMPLSGHT-27 — Historical / public domain records collector · OSINT012

### SMPLSGHT-4 · Collection Framework & Job Orchestration
- SMPLSGHT-18 — Background job queue and worker scaffolding
- SMPLSGHT-19 — Uniform collector adapter interface
- SMPLSGHT-20 — Per-provider rate limiting and usage accounting
- SMPLSGHT-21 — Provenance envelope for all collector results
- SMPLSGHT-28 — Partial-result and failure reporting

### SMPLSGHT-5 · Intelligence Model, Normalization & Findings
- SMPLSGHT-29 — Asset data model with org attribution
- SMPLSGHT-30 — Normalize collector output into canonical assets
- SMPLSGHT-31 — Deduplicate and consolidate discoveries
- SMPLSGHT-32 — Finding model (severity, confidence, status, evidence)
- SMPLSGHT-33 — Confirmed-vs-unverified classification

### SMPLSGHT-6 · Dashboards & Findings UX
- SMPLSGHT-34 — App shell and authentication UI
- SMPLSGHT-35 — Main dashboard with summary metrics · OSINT001
- SMPLSGHT-36 — Findings list with filters
- SMPLSGHT-37 — Finding detail with evidence
- SMPLSGHT-38 — Investigation status surfacing in UI

### SMPLSGHT-7 · Executive Reporting (PDF)
- SMPLSGHT-39 — Executive Intelligence Report template
- SMPLSGHT-40 — Server-side PDF generation
- SMPLSGHT-41 — Report download from UI

## Test-case coverage (Phase 1)

| Test case | Story |
|---|---|
| OSINT001 (Preview/summary) | SMPLSGHT-35 |
| OSINT002 (Methodology) | SMPLSGHT-14 |
| OSINT004 (Organization) | SMPLSGHT-13 |
| OSINT011 (Domain Information) | SMPLSGHT-22, -23 |
| OSINT012 (Public Domain Records) | SMPLSGHT-27 |
| OSINT013 (Domain Structure) | SMPLSGHT-24, -25 |
| OSINT018 (Technologies in Use) | SMPLSGHT-26 |

Remaining test cases (OSINT003, 005–010, 014–017, 019–023) map to Phase 2–4 and are not
yet scheduled.

## Implementation status

Two slices landed: (1) the collection-framework spine + first passive collectors, and
(2) persistence, auth, tenancy, and the full investigation flow. The API now has real
auth and tenant isolation, and investigations persist their assets.

| Story | Status | Notes |
|---|---|---|
| SMPLSGHT-8 User authentication | ✅ done | signup/login/me, JWT, bcrypt (`app/api/auth.py`) |
| SMPLSGHT-9 Tenant isolation | ✅ done | every row tenant-scoped; cross-tenant test |
| SMPLSGHT-10 RBAC | ✅ done | Admin/Analyst/Read-only (`app/deps.py`, `app/api/users.py`) |
| SMPLSGHT-12 Audit logging | 🟡 partial | writes `audit_logs`; no read API yet |
| SMPLSGHT-13 Organization CRUD | ✅ done | `app/api/organizations.py` |
| SMPLSGHT-14 Create investigation | ✅ done | draft → authorize → run flow |
| SMPLSGHT-15 Authorization gate | ✅ done | run blocked without attestation |
| SMPLSGHT-17 Investigation lifecycle | ✅ done | draft/running/complete/partial/failed |
| SMPLSGHT-29 Asset model + persistence | ✅ done | `app/models.py` + persisted on run |
| SMPLSGHT-19 Collector adapter interface | ✅ done | `collectors/base.py` |
| SMPLSGHT-21 Provenance envelope | ✅ done | `Provenance` on every result |
| SMPLSGHT-28 Partial/failure reporting | ✅ done | `collectors/runner.py` outcome roll-up |
| SMPLSGHT-23 DNS records collector | ✅ done | `collectors/dns_records.py` |
| SMPLSGHT-25 Certificate transparency collector | ✅ done | crt.sh |
| SMPLSGHT-22 WHOIS / registration collector | ✅ done | RDAP (`collectors/whois_rdap.py`) |
| SMPLSGHT-27 Historical records collector | ✅ done | Wayback CDX (`collectors/historical_records.py`) |
| SMPLSGHT-24 Subdomain discovery | 🟡 partial | CT-powered; add passive-DNS sources later |
| SMPLSGHT-30 Normalize to canonical assets | ✅ done | `app/services/assets.py` |
| SMPLSGHT-31 Deduplicate/consolidate | ✅ done | noisy-OR confidence merge |
| SMPLSGHT-16 Discovery-plan generation | ⬜ not started | — |
| SMPLSGHT-11 Secrets management | ⬜ not started | env vars for now; no secrets manager |
| SMPLSGHT-18 Job queue | ✅ done | RQ worker; `/run` returns 202, `QUEUE_EAGER` for dev |

**Known MVP shortcuts** (tracked, not hidden): tables are created via
`Base.metadata.create_all()` on startup — Alembic migrations are a follow-up; provider keys
come from env, not a secrets manager; collection now runs on an RQ worker (SMPLSGHT-18).
