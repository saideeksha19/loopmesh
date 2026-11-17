# LOOPMESH architecture

> What one industry throws away, another industry can use.

LOOPMESH is an industrial symbiosis operating system. It ingests structured
material and demand data, discovers feasible recovery relationships, explains
*why* a relationship is feasible, and keeps an auditable ledger that only counts
verified recovery as impact.

## 1. System shape

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Browser                                                                 │
│  Next.js App Router (server components by default, client islands)       │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ REST / JSON (no secrets in the bundle)
┌───────────────────────────────▼──────────────────────────────────────────┐
│  FastAPI  /api/v1                                                        │
│  ├── routers      thin HTTP layer, schemas in / schemas out               │
│  ├── services     deterministic domain logic (no framework imports)      │
│  └── db           SQLAlchemy 2.0 typed models + session management       │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          │ PostgreSQL (target)                       │
          │ SQLite file (local development fallback)  │
          └───────────────────────────────────────────┘
```

Layer rules:

- **Routers** never contain domain rules. They validate input, call services or
  queries, and shape responses.
- **Services** (`app/services/*`) contain all deterministic logic and are
  unit-testable without HTTP: rule engine, discovery, ledger aggregation,
  geo/unit maths.
- **Models** own persistence invariants. Anything that must never be true
  (negative quantity, verified transaction without evidence, self-matching
  opportunity) is also a database `CHECK` constraint, not only a Pydantic rule.

## 2. The five intelligence stages

| Stage | Phase 1 status | Implementation |
| --- | --- | --- |
| Material DNA | Implemented | `Material` + `MaterialSpecification`, forms and CSV intake |
| Resource discovery | Implemented | `app/services/discovery.py` — exhaustive, capped pair evaluation |
| Compatibility | Implemented (v1 policy) | `app/services/compatibility.py` — nine weighted deterministic rules |
| Optimization | Designed, not implemented | `GET /optimization` publishes the CP-SAT contract |
| Agentic coordination | Designed, not implemented | `GET /agents` publishes the registry and guardrails |

### 2.1 Compatibility rules

Every rule returns one of `pass`, `warning`, `fail`, `unknown` plus the observed
value, the requirement and a human reason. Weights sum to 100.

| Rule | Weight | Blocks when | Notes |
| --- | --- | --- | --- |
| `CAT-01` Category acceptance | 20 | Category outside accepted set | Accepted substitutions grade to advisory |
| `HAZ-01` Hazard prohibition | 15 | Hazard explicitly prohibited | Undeclared hazard is `unknown` |
| `PUR-01` Minimum purity | 15 | Declared purity below floor | Missing measurement is `unknown` |
| `CON-01` Maximum contamination | 12 | Overshoot beyond tolerance | ≤25% overshoot becomes pre-treatment advisory |
| `MOI-01` Maximum moisture | 6 | >2× the ceiling | Within 2× becomes a drying advisory |
| `QTY-01` Quantity sufficiency | 15 | Below intake minimum | Dimension-checked conversion; partial allocation is advisory |
| `GEO-01` Transport radius | 10 | Distance beyond radius | Missing coordinates are `unknown` |
| `TIM-01` Availability overlap | 4 | No overlap with need window | Partial coverage is advisory |
| `COND-01` Condition suitability | 3 | Never | Degraded/mixed raise an inspection advisory |

Verdict aggregation is intentionally conservative:

1. Any blocking `fail` → **incompatible**
2. Otherwise any `unknown` → **unverified**
3. Otherwise any `warning` → **conditional**
4. Otherwise → **compatible**

Consequences: absent evidence can never produce `compatible`, and the AI layer
(Phase 2) may only *describe* these outcomes. It has no code path that can
produce a verdict.

### 2.2 Discovery

`discover_opportunities()` evaluates every open demand against every available
stream, skipping same-organisation pairs and pairs that fail a blocking rule.
It is idempotent: existing opportunities are rescored, while
`converted`/`rejected`/`expired` rows are frozen so history cannot be rewritten.
A configurable pair cap prevents runaway evaluation.

### 2.3 Ledger accounting

Since Phase 2A the ledger publishes seven exclusive stages. Every record sits in
exactly one stage, so nothing can be counted twice:

```
stage                 sources                                          counts as impact
draft                 proposal draft/submitted/under_review/approved    no
submitted             (pipeline proposals, no transaction yet)         no
approved              proposal approved, no transaction                no
in_progress           transaction created                              no
completed_unverified  transaction transferred                          no
verified              transaction verified                             yes
rejected_cancelled    proposal rejected/withdrawn/cancelled/failed,     no
                      transaction rejected/cancelled/failed
```

Quantity-bearing records are counted once, through their transaction when one
exists and through their proposal status otherwise. The legacy four-state view
(`proposed`/`accepted`/`transported`/`verified`) is still returned for existing
consumers.

- Verified totals use `verified_quantity`, never the proposed quantity.
- `recovery_transactions` has a database `CHECK` requiring both
  `verified_quantity` and `verified_at` when status is `verified`.
- No CO₂e or landfill-diversion factors exist in Phase 1, so no environmental
  savings are reported.

## 3. Data model

Nine tables, all with UUID primary keys and `created_at` / `updated_at`.

```
organizations 1─┬─* materials 1──1 material_specifications
                ├─* resource_demands
                ├─* recovery_opportunities (as supplier)
                └─* recovery_opportunities (as consumer)

materials 1──* recovery_opportunities *──1 resource_demands
recovery_opportunities 1──* recovery_proposals 1──1 recovery_transactions
agent_executions            (standalone, Phase 2 runtime)
audit_events                (standalone journal)
```

| Table | Purpose | Notable constraints |
| --- | --- | --- |
| `organizations` | Industrial actors with coordinates and sector | unique slug, lat/long range |
| `materials` | Offered streams ("Material DNA") | quantity > 0, availability window ordered, unique reference code |
| `material_specifications` | Measured/declared properties (1:1) | all percentages 0–100, pH 0–14 |
| `resource_demands` | Consumer intake requirements | min > 0, max ≥ min, positive radius |
| `recovery_opportunities` | Screened supply/demand links + evidence | unique `(material, demand)`, score 0–100, distinct parties, quantity > 0 |
| `recovery_proposals` | Commercial offers + lifecycle evidence | quantity > 0, non-negative price, status/version checks, approval evidence required when approved |
| `recovery_transactions` | Physical movement + evidence | verified requires quantity, evidence and timestamp, one per proposal |
| `status_transitions` | Append-only state-change log per entity | entity type/id, action, previous/new state, actor, reason |
| `agent_executions` | Agent run records | completed ≥ started, success requires completion |
| `audit_events` | Immutable activity journal | typed event, actor, severity, previous/new state, reason, organisation |

Provenance is explicit: `data_source` (`demo`/`form`/`csv`/`document`) and
`is_demo` on organisations, materials, demands, opportunities, proposals and
transactions. The API reports `data_mode` and `contains_demo_data`, and the UI
renders a banner rather than presenting synthetic rows as real.

### Portable types

- Enumerations are `VARCHAR(32)` + `CHECK IN (...)` (`native_enum=False`) so the
  schema behaves identically on PostgreSQL and SQLite and adding a value is a
  simple migration.
- JSON columns use `sa.JSON` (Postgres `json`). Moving hot JSON paths to `JSONB`
  with GIN indexes is a later optimisation, not a Phase 1 need.
- Quantities are `NUMERIC(14,3)`; API responses expose floats for clean JSON.

## 4. API surface

Base path `/api/v1`. Interactive docs at `/docs` (Swagger) and `/redoc`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` (root) | Liveness, no database access |
| GET | `/api/v1/health` | Readiness, includes database reachability |
| GET | `/api/v1/overview` | Dashboard aggregate |
| GET | `/api/v1/overview/activity` | Audit journal |
| GET | `/api/v1/organizations` · `/{id}` | Network participants |
| GET | `/api/v1/materials` · `/{id}` | Inventory and profiles |
| POST | `/api/v1/materials` | Register a stream (form intake) |
| POST | `/api/v1/materials/import` | Validated CSV intake with row-level report |
| GET | `/api/v1/demands` · `/{id}` | Intake specifications |
| GET | `/api/v1/opportunities` · `/{id}` | Screened links with rule evidence |
| POST | `/api/v1/opportunities/discovery` | Re-run deterministic discovery |
| GET | `/api/v1/network` | Nodes, lanes, confirmed vs potential |
| GET | `/api/v1/ledger` | Seven-stage ledger + legacy four-state view |
| GET | `/api/v1/agents` | Registry, orchestration plan, run history |
| GET | `/api/v1/optimization` | Solver contract and status |
| GET/POST | `/api/v1/proposals` · `/{id}` · `/{id}/history` | Proposal list, detail, transitions |
| POST | `/api/v1/proposals/{id}/{submit,review,approve,reject,withdraw}` | Lifecycle transitions |
| GET/POST | `/api/v1/transactions` · `/{id}` · `/{id}/history` | Transaction list, detail, history, create |
| POST | `/api/v1/transactions/{id}/{record-transfer,verify,reject,cancel}` | Execution and verification |
| GET | `/api/v1/audit` | Read-only tenant-scoped audit journal |
| GET | `/api/v1/actors` | Development actor registry |
| GET | `/api/v1/platform/dashboard` | Platform estate aggregates |
| GET | `/api/v1/platform/organizations` · `/{id}` | Platform-only tenant register and detail |
| PATCH | `/api/v1/platform/organizations/{id}` | Suspend or reactivate a tenant |
| GET | `/api/v1/platform/audit` | Platform-wide audit search |
| GET | `/api/v1/platform/health` | Tenant health overview |

There is deliberately **no** `PATCH /proposals/{id}` or generic status setter:
the only way to change state is a named transition endpoint, which applies the
state machine, the role rules, the evidence rules and the audit write.

All errors share one envelope:

```json
{ "error": { "code": "validation_error", "message": "…",
             "details": { "fields": [] }, "request_id": "…" } }
```

## 5. Cross-cutting concerns

**Configuration** — `pydantic-settings` reads environment variables and an
optional `backend/.env`. `DATABASE_URL` is validated to an allowlist of drivers.
Gemini credentials are backend-only and unused in Phase 1.

**Security** — no secrets in the frontend, no `.env` in version control, CORS
restricted to configured origins, strict input validation, SQL through the ORM
with bound parameters, and no credential defaults. The authenticated platform
resolves the principal from an HTTP-only session cookie, enforces organisation
scope and server-side capabilities on every route, and keeps platform authority
separate from organisation roles. Platform operator access additionally
requires a verified TOTP factor and a session inside its idle and absolute
limits; tenant lifecycle changes require a second operator's approval. See
[`PLATFORM_ADMIN.md`](PLATFORM_ADMIN.md).

**Observability** — one JSON log line per event (request id, method, path,
status, duration), correlation ids propagated via `X-Request-ID`, and
`X-Response-Time-ms`. Every mutation appends an `audit_events` row.

**Determinism** — no randomness in the domain path. Discovery order is stable,
rule evaluation is pure, and ledger aggregation is a pure function of rows.

## 6. Lifecycle workflow (Phase 2A)

### 6.1 State machines

Proposals: `draft → submitted → under_review → approved → in_progress →
completed`, with terminal side exits `rejected`, `withdrawn`, `cancelled`,
`failed`. Transactions: `created → in_progress → transferred → verified`, with
terminal `rejected`, `cancelled`, `failed`.

All rules live in `app/services/lifecycle.py` as data: for each (entity, action)
the rule names the allowed source statuses, the target status, the roles that may
perform it, the required evidence and whether the target is terminal.
`app/services/workflow.py` applies it — version check, role check, party check,
evidence check, status write, `status_transitions` row and `audit_events` row in
one database transaction. A failed audit write rolls the whole change back.

Side effects keep the two records consistent: creating a transaction moves the
proposal to `in_progress`; verification moves it to `completed`; a rejected
transaction moves it to `failed`; a cancelled transaction moves it to
`cancelled`.

### 6.2 Authorisation

Requests carry `X-Actor-Id`. `app/core/actors.py` resolves it against a fixed
development registry and derives the role server-side — the browser never sends
a role or an organisation id it is trusted with. Roles: `admin`, `coordinator`,
`reviewer`, `approver`, `auditor`, `viewer`. The registry is refused outright
when `ENVIRONMENT=production`, and the UI labels it "development identity — no
real auth".

Two rules apply to every role, including admin:

- **Segregation of duties** — an approver cannot be the submitter; a verifier
  cannot be the actor who recorded the transfer.
- **Evidence** — approval needs a decision reference; transfer needs a
  weighbridge reference, a material identification and a positive quantity;
  verification needs a method, an evidence reference and a quantity no larger
  than the transferred quantity.

Party membership (supplier or receiver) is enforced for coordinators only;
reviewers, approvers and auditors act as platform functions. Record visibility
is organisation-scoped for coordinators and unfiltered for other roles.

Authenticated routes resolve their principal from the session cookie rather
than trusting `X-Actor-Id`; the registry above remains a stand-in for local
tooling and is refused in production. Platform administration is a separate
authority: it requires the explicit `users.is_platform_admin` flag *and* a
platform capability on every request, plus a session with `mfa_verified_at`;
no organisation role implies any of them. `ActorContext.require_platform()` is
the single gate, so every current and future platform route inherits the MFA
and session-limit checks. See [`PLATFORM_ADMIN.md`](PLATFORM_ADMIN.md) for the
capability matrix, approval state machine, MFA and recovery procedure, session
policy, audit filtering and export controls.

### 6.3 Audit integrity

The audit journal is append-only by construction: there is no write, update or
delete endpoint, and the service is the only writer. Denied attempts are recorded
too, so a refused transition leaves a trace. `status_transitions` provides the
human-readable per-record history the workspaces render, while `audit_events`
carries the cross-record journal with severity and metadata.

Audit export is a read path: it serialises the same stored rows through the
same redaction boundary, orders them deterministically, caps the range and row
count, and appends a separate `platform.audit.exported` event. It has no code
path that updates or deletes a source event.

### 6.4 Platform governance (Batch 12)

Four mechanisms share one audit journal:

- **Two-person approval** — an immutable request binds tenant, action and
  reason. A different operator decides; only an approved, unexpired request can
  execute; a row lock plus conditional update makes execution exactly-once, and
  tenant drift cancels the approval.
- **Operator MFA** — TOTP secrets are Fernet-encrypted with an application key
  and never stored in plaintext; recovery codes are SHA-256 hashes consumed
  once; durable lockout and an in-process limiter slow brute force; a missing
  key fails closed.
- **Session policy** — platform routes check MFA verification plus idle and
  absolute limits; operators can revoke each other's sessions but not their own
  through the governance endpoint; ordinary organisation sessions are unchanged.
- **Bounded export** — both dates required, configured day and row caps, fixed
  columns, CSV formula neutralisation, safe filenames, `no-store`, and an audit
  event recording actor, filters, range and row count. Audit retention is
  indefinite by default; archival deletion is an out-of-band reviewed process.

## 7. Deliberate boundaries (Phase 1–2A)

Not built, on purpose:

- OR-Tools allocation, NetworkX graph analytics, Gemini calls, LangGraph agents
- Email/SMS MFA delivery (only TOTP and hashed recovery codes are implemented)
- Automatic audit retention or deletion
- Emission-factor accounting
- Computer vision of any kind — material data is structured by construction

These are recorded in the API as `implemented: false` rather than mocked so no
screenshot can imply capability that does not exist.
