# LOOPMESH

**The AI operating system for industrial symbiosis.**

> What one industry throws away, another industry can use.

LOOPMESH is an industrial resource recovery platform. It turns structured
material profiles and intake requirements into **explainable recovery
relationships**, screens every candidate pair with **deterministic engineering
rules**, and keeps a ledger in which **only verified recovery counts as impact**.

This repository contains the **Phase 1 foundation plus the Phase 2A lifecycle
layer**: a real, tested full-stack system — not a clickable mock-up. Proposals
and transactions move through an explicit, server-authorised state machine with
an append-only audit trail. Authenticated organisation workspaces and a
separate platform console add tenant governance: TOTP-protected operator
sessions, two-person approval for suspension/reactivation, and bounded audit
export.

---

## What makes it different

- **The compatibility verdict is deterministic.** Nine weighted engineering rules
  produce `compatible`, `conditional`, `unverified` or `incompatible`, with an
  evidence row per rule. No model can override a blocking rule.
- **Missing evidence never becomes a pass.** A stream without an assay is
  `unverified`, not compatible.
- **Impact accounting is honest.** Proposed, accepted and transported quantities
  stay pipeline; only transactions with verification evidence enter recovered
  totals. There are no invented CO₂e savings.
- **AI has explicit boundaries.** Agent responsibilities and guardrails ship as a
  registry; no agent runs, and no AI activity is simulated anywhere in the UI.
- **No computer vision.** Material characteristics arrive through forms, CSV
  files and specification documents only.

---

## Application pages

| Route | Page | What it shows |
| --- | --- | --- |
| `/` | Overview | Organisations, streams, opportunities, pending proposals, verified recovered mass, network preview, recovery funnel, audit activity |
| `/materials` | Material intelligence | Inventory table, searchable/filterable, profile drawer, add-material workflow, CSV import with row-level reporting |
| `/network` | Resource network | Interactive force-laid-out graph, potential vs confirmed lanes, node inspector, lane register |
| `/opportunities` | Recovery opportunities | Scored matches with expandable nine-rule evidence, quantities, distance, transport requirement |
| `/optimization` | Optimization centre | Published CP-SAT contract, live vs planned stages, constraints — explicitly not implemented |
| `/agents` | Agent control | Planned specialists, responsibilities, guardrails, orchestration plan, empty execution history |
| `/ledger` | Impact ledger | Seven lifecycle stages (one bucket per record), verification evidence, verified-only totals, pipeline separated |
| `/proposals` | Recovery proposals | Paginated proposal list, status filter, material/org search, draft creation |
| `/proposals/[id]` | Proposal workspace | Parties, material, compatibility evidence, decision record, transition history, audit timeline, lifecycle actions |
| `/transactions` | Recovery transactions | Status filters, transfer quantities, verification state, linked proposals |
| `/transactions/[id]` | Transaction workspace | Linked approved proposal, transfer evidence, weighbridge reference, verification history, execution actions |
| `/audit` | Audit journal | Append-only event timeline across proposals and transactions, filterable by entity and severity |

The separate platform console is documented in
[`docs/PLATFORM_ADMIN.md`](docs/PLATFORM_ADMIN.md): `/platform` (estate),
`/platform/organizations`, `/platform/approvals`, `/platform/audit`,
`/platform/security` and `/platform/health`. Organisation administrators cannot
reach it; platform authority requires `users.is_platform_admin`, the matching
capability and an MFA-verified session.

Every screen carries a demo-data disclosure when the dataset is synthetic.

---

## Architecture

```
Next.js App Router ──REST/JSON──▶ FastAPI /api/v1 ──SQLAlchemy──▶ PostgreSQL
   (server components)              routers → services → db        (SQLite fallback locally)
```

- **Frontend** uses server components for data fetching and small client islands
  for interaction (graph, tables, forms). Charts and the network graph are
  hand-built SVG — no chart dependency.
- **Backend** keeps HTTP concerns thin and domain logic in
  `app/services/` (compatibility, discovery, ledger, geo, units).
- **Database invariants** are enforced with `CHECK` constraints, not only schema
  validation: `quantity > 0`, `max ≥ min`, distinct counterparties,
  `verified` requires a verified quantity **and** timestamp.

Full detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
Platform administration: [`docs/PLATFORM_ADMIN.md`](docs/PLATFORM_ADMIN.md) ·
Phases: [`docs/ROADMAP.md`](docs/ROADMAP.md) ·
Deployment: [`docs/DEPLOYMENT_RENDER.md`](docs/DEPLOYMENT_RENDER.md).

### Technology stack

| Layer | Technology | Version used |
| --- | --- | --- |
| Frontend | Next.js (App Router), React, TypeScript | 16.4.6 / 19.3.1 / 5.9.3 |
| Styling | Tailwind CSS v4 (PostCSS) | 4.3.5 |
| Backend | FastAPI, Uvicorn | 0.140.0 / 0.51.0 |
| Validation | Pydantic v2, pydantic-settings | 2.13.4 / 2.14.2 |
| Data | SQLAlchemy 2.0, Alembic | 2.0.51 / 1.18.5 |
| Database | PostgreSQL (target), SQLite (local fallback) | psycopg 3.3.9 |
| Quality | pytest, httpx, TypeScript, Next build | 8.4.2 / 0.28.1 |

Planned for later phases (intentionally **not** installed or used yet):
Google OR-Tools, NetworkX, Pandas, Gemini API, LangGraph.

---

## Repository layout

```
.
├── backend/
│   ├── alembic/                 Alembic environment + initial migration
│   ├── app/
│   │   ├── api/v1/endpoints/    HTTP routers
│   │   ├── core/                config, logging, errors, middleware
│   │   ├── db/                  base, enums, session, models/
│   │   ├── schemas/             Pydantic request/response contracts
│   │   ├── scripts/seed_demo.py Demo dataset loader
│   │   ├── services/            compatibility, discovery, ledger, geo, units, audit
│   │   └── main.py              application entrypoint
│   ├── tests/                   41 tests
│   ├── requirements.txt / requirements-dev.txt
│   └── pyproject.toml
├── frontend/
│   ├── app/(workspace)/         dashboard routes + shared shell layout
│   ├── components/              shell, ui primitives, feature workspaces
│   ├── lib/                     typed API client, formats, types
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT_RENDER.md
│   ├── PLATFORM_ADMIN.md
│   └── ROADMAP.md
├── sample-data/                 synthetic CSV import example
├── .env.example
├── .gitignore
└── README.md
```

---

## Quick start

Requirements: **Node.js ≥ 20**, **Python ≥ 3.11**, and (optionally) PostgreSQL 14+.
The verified environment for this build was Node 22.22, Python 3.14.4, Git 2.56.

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.scripts.seed_demo --reset
uvicorn app.main:app --reload --port 8000
```

- API: <http://127.0.0.1:8000>
- Swagger: <http://127.0.0.1:8000/docs>
- Readiness: <http://127.0.0.1:8000/api/v1/health>

Without `DATABASE_URL` the backend uses the SQLite fallback
`backend/loopmesh_dev.db`. This exists so the demo runs without a database
server; **PostgreSQL is the target for any shared or deployed environment.**

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The default API base is
`http://127.0.0.1:8000`.

### 3. PostgreSQL (recommended)

```bash
# example with Docker
docker run --name loopmesh-pg -e POSTGRES_USER=loopmesh -e POSTGRES_PASSWORD=loopmesh \
  -e POSTGRES_DB=loopmesh -p 5432:5432 -d postgres:16
```

Then set `DATABASE_URL` in `backend/.env`:

```
DATABASE_URL=postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh
```

and run `alembic upgrade head` followed by the seed script.

---

## Environment variables

Copy `.env.example` to `backend/.env` (backend values) and, if needed,
`frontend/.env.local` (browser-visible API URL). Never commit either file.

| Variable | Default | Scope | Purpose |
| --- | --- | --- | --- |
| `ENVIRONMENT` | `development` | backend | `development` / `test` / `staging` / `production` |
| `DEBUG` | `false` | backend | FastAPI debug mode |
| `DATABASE_URL` | SQLite file | backend | `postgresql+psycopg://…` (target) or `sqlite://…` |
| `DATABASE_ECHO` | `false` | backend | SQL echo |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | backend | Allowed browser origins |
| `LOG_LEVEL` | `INFO` | backend | Log verbosity |
| `LOG_JSON` | `true` | backend | JSON lines vs human-readable logs |
| `DISCOVERY_MIN_SCORE` | `55` | backend | Minimum score persisted by discovery |
| `DISCOVERY_MAX_PAIRS` | `2000` | backend | Safety cap per discovery run |
| `MFA_ENCRYPTION_KEY` | **required for MFA** | backend | URL-safe base64 Fernet key encrypting TOTP secrets; absent/invalid fails closed with `503 mfa_unavailable` |
| `MFA_MAX_FAILED_ATTEMPTS` | `5` | backend | Durable failed-factor attempts before lockout (3–20) |
| `MFA_LOCKOUT_MINUTES` | `15` | backend | Lockout duration (1–240) |
| `MFA_ATTEMPTS_PER_5_MINUTES` | `10` | backend | In-process factor-attempt limiter |
| `PLATFORM_APPROVAL_TTL_MINUTES` | `60` | backend | Two-person approval lifetime (5–1440) |
| `PLATFORM_SESSION_IDLE_MINUTES` | `30` | backend | Platform operator idle limit (5–120) |
| `PLATFORM_SESSION_ABSOLUTE_HOURS` | `8` | backend | Platform operator absolute limit from MFA verification (1–24) |
| `PLATFORM_AUDIT_EXPORT_MAX_ROWS` | `5000` | backend | Maximum rows in one audit export (100–20,000) |
| `PLATFORM_AUDIT_EXPORT_MAX_RANGE_DAYS` | `90` | backend | Maximum export date span (1–365 days) |
| `GEMINI_API_KEY` | empty | backend | Reserved for Phase 2 — **unused in Phase 1** |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | backend | Comma-separated `Host` header allow-list enforced by `TrustedHostMiddleware`. Local defaults include `testserver` for tests; **in production this must be an explicit, non-empty list of real hostnames** (no `*`, no whitespace entries). |
| `TRUST_PROXY_HEADERS` | `false` | backend | Only when `true` **and** the direct peer is in `TRUSTED_PROXY_IPS` are forwarded headers honoured; the client IP is resolved from `X-Forwarded-For` right-to-left to the first non-trusted hop. **Keep `false` unless your deployment topology and proxy hops are explicitly known.** |
| `TRUSTED_PROXY_IPS` | empty | backend | Comma-separated trusted proxy IPs and/or CIDRs (for example the actual reverse-proxy/load-balancer hop addresses in your environment). Required when `TRUST_PROXY_HEADERS=true`. Wildcards (`*`, `0.0.0.0/0`, `::/0`) are rejected; list only the proxies you operate. Do not guess values. |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | frontend (browser) | Browser-visible API base |
| `API_INTERNAL_URL` | falls back to the above | frontend (server) | Server-side API base |
| `E2E_MFA_KEY` | none — **required for browser E2E** | Playwright harness (shell) | Disposable test-only Fernet key; validated in `frontend/playwright.config.ts` and passed to the throwaway E2E backend as `MFA_ENCRYPTION_KEY`. Never a production key, never committed |

Secrets stay on the backend. The frontend only ever receives the public API URL.

### Production security configuration

`ENVIRONMENT=production` enables startup validation (`Settings.validate_runtime_security()` in the API lifespan) and fails fast on unsafe configuration:

- **Host validation vs CORS:** `ALLOWED_HOSTS` controls which HTTP `Host` headers the FastAPI app will accept (`TrustedHostMiddleware`, rejected before routing with HTTP 400). This is distinct from `CORS_ORIGINS`, which controls which browser origins may make cross-origin requests. In production both must be explicit allow-lists: `ALLOWED_HOSTS` set to your real hostnames (no wildcard) and `CORS_ORIGINS` set to your real `https://` origins (no wildcard, no `http://`).
- **Proxy and client IP:** rate limiting and session/IP attribution derive the client from the resolved peer IP. Forwarded headers are **not** trusted by default (`TRUST_PROXY_HEADERS=false`). Only enable `TRUST_PROXY_HEADERS=true` when the API is reached through known proxy hops **and** you have configured `TRUSTED_PROXY_IPS` to the explicit IPs/CIDRs of those hops; the resolver uses `X-Forwarded-For` right-to-left and returns the first non-trusted hop, so untrusted peers and arbitrary/spoofed forwarded headers are ignored. Wildcard trust is never accepted. Do not invent proxy topology or trusted IP ranges — if they are unknown, leave proxy-header trust disabled.
- **Safe defaults:** keep `DEBUG=false`, use PostgreSQL, keep auth cookies secure in production, and treat proxy-header trust as opt-in with an explicit, reviewed allow-list. Validate the full request path (TLS termination, reverse proxy, forwarded headers, and the actual `Host` seen by the backend) in your deployment environment before relying on client-IP-dependent controls.

---

## API

Base path `/api/v1`; interactive docs at `/docs`.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness (no database) |
| GET | `/api/v1/health` | Readiness incl. database reachability |
| GET | `/api/v1/overview` | Dashboard aggregate |
| GET | `/api/v1/overview/activity` | Audit journal |
| GET | `/api/v1/organizations` | List, filter by sector/search, paginated |
| GET | `/api/v1/organizations/{id}` | Detail with participation counts |
| GET | `/api/v1/materials` | Inventory: category, status, org, sector, search |
| GET | `/api/v1/materials/{id}` | Profile with specification |
| POST | `/api/v1/materials` | Register a stream (validated) |
| POST | `/api/v1/materials/import` | CSV intake, 2 MB cap, row-level report |
| GET | `/api/v1/demands` | Intake requirements |
| GET | `/api/v1/demands/{id}` | Demand detail |
| GET | `/api/v1/opportunities` | Screened links with rule evidence |
| GET | `/api/v1/opportunities/{id}` | Detail with full rule trail |
| POST | `/api/v1/opportunities/discovery` | Run deterministic discovery |
| GET | `/api/v1/network` | Nodes, lanes, confirmed vs potential |
| GET | `/api/v1/ledger` | Seven-stage recovery ledger plus legacy four-state view |
| GET | `/api/v1/agents` | Registry, orchestration plan, run history |
| GET | `/api/v1/optimization` | Solver contract and status |
| GET | `/api/v1/proposals` · `/{id}` | Proposal list (paginated) and detail with transitions |
| POST | `/api/v1/proposals` | Create a draft proposal |
| POST | `/api/v1/proposals/{id}/submit` · `/review` · `/approve` · `/reject` · `/withdraw` | Lifecycle transitions |
| GET | `/api/v1/transactions` · `/{id}` · `/{id}/history` | Transaction list, detail and transition history |
| POST | `/api/v1/transactions` | Create a transaction from an approved proposal |
| POST | `/api/v1/transactions/{id}/record-transfer` · `/verify` · `/reject` · `/cancel` | Execution and verification transitions |
| GET | `/api/v1/audit` | Append-only audit journal (read only) |
| GET | `/api/v1/actors` | Development actor registry (development only) |
| GET/POST | `/api/v1/platform/approvals` … `/{id}/approve\|reject\|cancel\|execute` | Two-person tenant lifecycle approval |
| GET/POST | `/api/v1/platform/sessions` … `/revoke`, `/revoke-all` | Operator session governance |
| GET | `/api/v1/platform/audit/export` | Bounded, redacted CSV/JSON export |
| GET/POST | `/api/v1/auth/mfa/status\|enroll\|confirm\|verify\|recovery-codes/regenerate\|disable` | Operator TOTP lifecycle |

Errors use a single envelope with `code`, `message`, `details` and `request_id`.
Every response carries `X-Request-ID` and `X-Response-Time-ms`.

### Try the intelligence layer

```bash
# 1. register a stream through the API
curl -X POST http://127.0.0.1:8000/api/v1/materials \
  -H "Content-Type: application/json" \
  -d '{"organization_id":"<org-uuid>","reference_code":"LM-1001",
       "name":"Demo slag fines","category":"minerals","quantity_available":900,
       "unit":"tonne","specification":{"purity_pct":94,"moisture_pct":8,
       "contamination_pct":0.7}}'

# 2. re-run deterministic discovery
curl -X POST http://127.0.0.1:8000/api/v1/opportunities/discovery \
  -H "Content-Type: application/json" -d '{"min_score":55}'
```

---

## Demo dataset

`python -m app.scripts.seed_demo --reset` loads a synthetic industrial cluster:
12 organisations, 21 material streams, 16 demands, 24 screened opportunities and
7 proposals spread across the lifecycle (draft, submitted, under review,
in progress, completed) plus 3 transactions (created, transferred, verified).
The verified entry carries a weighbridge record of 2,410 t, which is the only
quantity that counts as recovered material.

All of it is labelled demo data: `is_demo=true`, `data_source=demo`,
`.example` contact domains, and the UI banner states that no real partnership,
delivery or environmental saving is claimed. Delete it at any time with
`--reset` or by dropping the database.

`sample-data/materials.csv` is an importable example using the same demo
organisation slugs.

---

## Testing and verification

```bash
# backend
cd backend
.venv\Scripts\python -m pytest            # or: python -m pytest

# migrations
alembic upgrade head
DATABASE_URL=postgresql+psycopg://… alembic upgrade head --sql   # compile Postgres DDL offline

# frontend
cd frontend
npx tsc --noEmit
npm run build
```

### Browser end-to-end tests

The Playwright suite (`frontend/e2e`) seeds a disposable SQLite database and
starts its own backend, so it needs a test-only MFA encryption key. There is no
default and the key is never generated for you: export a fresh throwaway value in
the shell that runs the tests.

```bash
cd frontend
export E2E_MFA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
npm run test:e2e
```

`playwright.config.ts` passes the value to the temporary backend as both
`E2E_MFA_KEY` and `MFA_ENCRYPTION_KEY`; the seed script refuses to run without
it, and the config fails before any server starts if it is missing or not a
valid Fernet key. Never use a production or shared key here, and never commit
the value — a lost key only invalidates that disposable test database.

Verified in this build:

- **72 backend tests pass**: 41 Phase 1 tests plus 31 lifecycle tests covering
  every transition, invalid transitions, duplicate submission, terminal-state
  reopening, evidence requirements, mass-balance over-verification,
  segregation of duties, organisation scoping, optimistic-concurrency
  conflicts, audit rollback, and the DB `CHECK` constraints
- **Alembic** upgrades and downgrades cleanly on SQLite (`096363408627` →
  `4c1a0f2b7d95`), preserving all existing rows while adding lifecycle columns,
  evidence fields and the `status_transitions` table; the PostgreSQL DDL still
  compiles offline
- **`tsc --noEmit` passes**, **`next build` succeeds** for all 12 routes
- One complete lifecycle was driven through the running UI: draft → submitted
  → under review → approved → transaction → transfer (118 t, weighbridge ref)
  → verified, with every step confirmed against the API, the transition
  history, the audit journal and the ledger totals (2,410 t → 2,528 t)

Not verified: real PostgreSQL execution (no server available in the build
environment), and mobile/narrow-viewport layouts.

---

## Implementation status

| Capability | Status |
| --- | --- |
| Material DNA profiles + specification | ✅ Phase 1 |
| CSV intake with validation reporting | ✅ Phase 1 |
| Deterministic compatibility engine (9 rules) | ✅ Phase 1 |
| Deterministic discovery (idempotent) | ✅ Phase 1 |
| Resource network graph (potential vs confirmed) | ✅ Phase 1 |
| Impact ledger with verification evidence (seven lifecycle stages) | ✅ Phase 1 + 2A |
| Audit journal + request correlation | ✅ Phase 1 + 2A (state changes, reasons, denials) |
| Optimization (OR-Tools CP-SAT) | 🧭 Designed, not implemented |
| Agentic coordination (LangGraph + Gemini) | 🧭 Designed, not implemented |
| Proposal/transaction lifecycle workflow | ✅ Phase 2A (state machine, evidence, audit) |
| Role-aware authorisation | ✅ Server-side capabilities and organisation scope |
| Auth, tenancy, real sessions | ✅ HTTP-only session cookies, refresh rotation, organisation scope |
| Platform governance (MFA, two-person approval, bounded export) | ✅ Batch 12 |
| Environmental impact factors (CO₂e) | 🧭 Deliberately absent |
| NetworkX graph analytics | 🧭 Not started |

---

## Known limitations

1. **SQLite is a development fallback.** The schema and migrations target
   PostgreSQL and were verified against a disposable PostgreSQL database, but
   the local demo can run on SQLite. Run `alembic upgrade head` against a real
   Postgres instance before any shared deployment.
2. **MFA recovery is out-of-band.** There is no email/SMS delivery and no
   self-service reset when both authenticator and recovery codes are lost; a
   deployment operator must follow the reviewed database procedure in
   `docs/PLATFORM_ADMIN.md`.
3. **Compatibility policy v1 lives in code.** Thresholds and tolerances are
   explicit and testable but not yet editable per tenant.
4. **Discovery is exhaustive with a cap.** Fine for thousands of pairs, not for
   millions; indexing and incremental rescoring belong to Phase 2.
5. **No environmental impact numbers.** Without verified emission factors, any
   figure would be fabricated, so none is shown.
6. **CSV import is flat.** Composition and contaminant maps are only available
   through the JSON form flow.
7. **Opportunities are screening results, not plans.** No quantities are
   optimised or reserved; that is the solver's job in Phase 3.
8. **Audit retention is indefinite.** The application offers no purge; archival
   deletion is an out-of-band, reviewed operational procedure.
9. **Party membership is enforced for coordinators only.** Reviewers,
   approvers and auditors are treated as platform functions, so a reviewer may
   act on a proposal from any organisation. Organisation-scoped tenancy arrives
   with real authentication.
10. **Pre-Phase-2A demo rows have no transition history.** The migration records
    where approval evidence came from (`system:phase1-migration`) but cannot
    invent the transitions that produced the old state, so those rows start
    their history at migration time.

---

## Next development phase

**Phase 2 — Coordination and workflow**. Step 1 shipped as Phase 2A; the
remaining work, in order:

1. ~~Proposal and transaction state machine with write endpoints and audit
   events~~ — delivered (Phase 2A)
2. Organisation-scoped authentication and tenancy, replacing the development
   actor registry
3. Document intake with Gemini extraction and mandatory human confirmation
4. LangGraph supervisor + the five registered specialists, restricted to the
   deterministic services

Then Phase 3 adds OR-Tools allocation, NetworkX analytics and cited emission
factors. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for exit criteria.
