# LOOPMESH development phases

Each phase ends with something demonstrable and verifiable. Later phases do not
replace earlier guarantees: deterministic compatibility remains the gate, and
verified evidence remains the only source of impact.

## Phase 1 — Foundation (implemented)

**Delivered**

- Monorepo: Next.js frontend, FastAPI backend, docs and sample data
- Nine-table PostgreSQL-targeted schema with Alembic migration
- Health, overview, organizations, materials, demands, opportunities, network,
  ledger, agents and optimization endpoints
- Deterministic compatibility engine (nine rules, explainable, no AI)
- Deterministic discovery with idempotent rescoring
- CSV material intake with row-level validation reporting
- Verification-only impact ledger
- Seven-page enterprise UI with demo provenance labelling
- 41 backend tests, TypeScript check and production build

**Exit criteria** — `pytest` green, `npm run build` green, demo dataset loads,
every screen renders from live API data with zero fabricated AI activity.

**Open risks**

- Live demo runs on the SQLite fallback because no PostgreSQL server exists in
  the development environment. PostgreSQL DDL is verified by offline
  `alembic upgrade head --sql`, but a real Postgres deployment must be exercised
  before launch.
- API is unauthenticated; fine for a local hackathon demo, unacceptable hosted.

## Phase 2 — Coordination and workflow

1. **Proposal and transaction workflow — delivered as Phase 2A**
   - Shipped: explicit proposal and transaction state machines in
     `services/lifecycle.py`; named transition endpoints (no generic status
     setter); `POST /proposals`; `POST /transactions`; optimistic concurrency
     via `expected_version`; role checks, segregation of duties and evidence
     requirements; `status_transitions` history and append-only audit events
     written in the same transaction; seven-stage ledger buckets; proposal,
     transaction and audit workspaces with real actions
   - Still open: replace the development actor registry with real
     authentication and organisation-scoped tenancy; enforce party membership
     for every role, not only coordinators
2. **Document intake**
   - Upload a specification PDF/text, extract candidate fields with Gemini,
     require human confirmation before persisting
   - Never auto-publish a material or mark it available
3. **Agentic coordination (LangGraph)**
   - Supervisor + five specialists defined in the Phase 1 registry
   - All tool calls go through the deterministic services
   - Hard refusal: no compatibility verdict, no ledger transition, no external
     communication without approval
   - Every run persisted to `agent_executions` with model, inputs and outputs
4. **Auth and tenancy** — organisation-scoped access, server-side sessions,
   per-tenant row filtering
5. **Discovery hardening** — blocking indexes by category + radius, background
   job execution, incremental rescoring of affected pairs only

**Exit criteria** — a proposal can be created, accepted, transported and verified
entirely through the API with audit trails; agents can be disabled without
losing functionality; two tenants cannot read each other's rows.

## Phase 3 — Optimization and network analytics

1. **OR-Tools CP-SAT allocation**
   - Decision variables per eligible opportunity lane
   - Constraints already published by `GET /optimization`: quantity, intake,
     compatibility pre-filter, radius/capacity, timing
   - Objective: maximise verified recoverable mass, minimise distance, report
     unmet demand
   - Persist allocation plans and binding-constraint explanations
2. **NetworkX analytics**
   - Centrality for broker organisations, community detection for clusters
   - Critical-lane analysis and single-point-of-failure supply chains
   - Graph metrics exposed alongside the existing node/edge payload
3. **Impact accounting**
   - Verified emission factors per material and route, with source citations
   - Only verified transactions may consume factors
   - Uncertainty ranges instead of single point estimates

**Exit criteria** — solver output reproducible for a fixed dataset, infeasible
scenarios explained, every reported kilogram traceable to a verified transaction
and a cited factor.

## Phase 4 — Operating system

- Live webhooks and ERP/MES connectors for quantity updates
- Contract and compliance document generation
- Logistics partner integration with route-level distance and capacity
- Multi-region regulatory rule packs
- Role-based approvals and segregation of duties
- Public impact disclosures with third-party verification

## Engineering rules that must survive every phase

1. AI never overrides a deterministic compatibility verdict.
2. Missing evidence produces `unverified`, never `compatible`.
3. Only verified transactions count as recovered material.
4. Demo and imported data are labelled at the record level.
5. Units are converted only within compatible dimensions.
6. Every mutation writes an audit event.
