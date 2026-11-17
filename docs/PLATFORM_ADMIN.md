# Platform administration, tenant operations and audit review

Batch 11 added a platform console at `/platform` that is deliberately separate
from the organisation workspace. Batch 12 adds the governance layer: operator
TOTP MFA, session policy, two-person approval for tenant suspension and
reactivation, and bounded audit export. This document describes the access
model, the endpoints, suspension and approval semantics, MFA and recovery, the
session policy, the audit journal and export, and the known limitations.

## 1. Access model

Platform authority is **one explicit user-level flag**: `users.is_platform_admin`.
There is no endpoint, role update or membership scope that can set it; it is
granted out of band (bootstrap CLI or another platform administrator).

Three independent facts must agree on every platform request:

1. `is_platform_admin` is true, and
2. the principal holds the platform capability the route demands, and
3. the browser session has verified a second factor and is inside both platform
   session limits.

`ActorContext.require_platform()` enforces the first; each route then calls
`require(<permission>)`, and `require_platform()` itself refuses a session with
no `mfa_verified_at` (`403 mfa_required`) or one past its idle/absolute limit
(`401 platform_session_expired`). The MFA gate lives in that one method, so
every present and future platform route inherits it; it is not a UI check. A
`scope=platform` membership grants cross-tenant
*reach*, never console access. Organisation administrators, coordinators and
platform-scoped members without the flag are refused with
`403 platform_scope_required`.

`PLATFORM_PERMISSIONS` is disjoint from every entry in `ROLE_PERMISSIONS`; an
import-time assertion (and a test) fails the application if that ever stops
being true. A platform administrator resolves to all permissions through
`permissions_for(..., platform_admin=True)`.

### Capability matrix

| Capability | Grants | Console route |
| --- | --- | --- |
| `platform.admin` | The operator marker required alongside the flag; no route reads it directly | — |
| `platform.dashboard.view` | Aggregate estate metrics, recent tenants and recent privileged events | `/platform` |
| `platform.organizations.view` | Tenant register, detail, counts and health checks | `/platform/organizations`, `/platform/organizations/{id}` |
| `platform.organizations.manage` | Suspend and reactivate a tenant | status control on the detail page |
| `platform.health.view` | Tenant health table | `/platform/health` |
| `platform.audit.view` | Platform-wide audit search | `/platform/audit` |
| `platform.audit.export` | Download a bounded CSV/JSON audit export | export controls on `/platform/audit` |
| `platform.audit.verify` | Verify audit hash-chain integrity and record a verification event | `GET /api/v1/platform/audit/integrity` |
| `platform.audit.archive` | Perform audited external archive/retention-policy operations where supported by tooling | `app.scripts.security_ops audit-archive` / retention-policy |
| `platform.approvals.view` | Read approval requests | `/platform/approvals`, `/platform/approvals/{id}` |
| `platform.approvals.request` | Create and cancel one's own approval request | request form and detail page |
| `platform.approvals.decide` | Approve or reject another operator's request | detail review screen |
| `platform.approvals.execute` | Execute an approved tenant lifecycle change | detail review screen |
| `platform.sessions.manage` | List and revoke platform operator sessions | `/platform/security` |

Creating and executing an approval additionally require
`platform.organizations.manage`; the approval capabilities alone cannot change
a tenant. All of these are platform permissions, never organisation roles.

Navigation is filtered by the same capabilities, but the API re-checks every
request: hiding a link is never the authorisation.

## 2. Endpoint inventory

Base path `/api/v1`. All routes are read-only except the status patch. Every
mutation requires the session CSRF header (`X-CSRF-Token`).

| Method | Path | Permission | Notes |
| --- | --- | --- | --- |
| GET | `/platform/dashboard` | `platform.dashboard.view` | Aggregate counts, `window_days` (30), `failure_window_hours` (24), newest 6 organisations, newest 8 privileged events |
| GET | `/platform/organizations` | `platform.organizations.view` | `q` (name/slug/city, ≤120 chars), `status` (`active`/`suspended`), `page`, `page_size` (≤200, default 25) |
| GET | `/platform/organizations/{organization_id}` | `platform.organizations.view` | Safe fields, membership and invitation counts, `checks`, `warnings`, `state`, recent events |
| PATCH | `/platform/organizations/{organization_id}` | `platform.organizations.manage` | Direct status change is refused: body must carry `approval_id` for an approved request bound to this organisation, action and reason (`409 approval_required`, `409 approval_mismatch`, `409 approval_invalidated`) |
| POST | `/platform/approvals` | `platform.approvals.request` + `platform.organizations.manage` | Body `{organization_id, action: suspend\|reactivate, reason?}`; suspend reason ≥8 characters |
| GET | `/platform/approvals` | `platform.approvals.view` | Filters `status`, `organization_id`, pagination; newest first |
| GET | `/platform/approvals/{id}` | `platform.approvals.view` | Binding details, current state, history; lazily expires pending requests |
| POST | `/platform/approvals/{id}/approve` | `platform.approvals.decide` | Optional decision reason; requester is refused with `403 self_approval_forbidden` |
| POST | `/platform/approvals/{id}/reject` | `platform.approvals.decide` | Optional decision reason; requester is refused |
| POST | `/platform/approvals/{id}/cancel` | `platform.approvals.request` | Requester only; pending or approved requests only |
| POST | `/platform/approvals/{id}/execute` | `platform.approvals.execute` + `platform.organizations.manage` | Exactly once; execution and audit share one transaction |
| GET | `/platform/sessions` | `platform.sessions.manage` | Operator sessions only; no IP or device fields are stored or returned |
| POST | `/platform/sessions/{id}/revoke` | `platform.sessions.manage` | One other operator session; current session refused |
| POST | `/platform/sessions/revoke-all` | `platform.sessions.manage` | Every other operator session; the current one is kept |
| GET | `/platform/audit` | `platform.audit.view` | Filters below; stable order `created_at DESC, id DESC` |
| GET | `/platform/audit/export` | `platform.audit.view` + `platform.audit.export` | Both dates required, ≤ configured days and rows, `format=csv\|json`, stable oldest-first order |
| GET | `/platform/audit/integrity` | `platform.audit.view` + `platform.audit.verify` | Bounded hash-chain verification; records `platform.audit.integrity_verified` with outcome/count/reason |
| GET | `/platform/health` | `platform.health.view` | Paginated tenant health rows |

MFA endpoints live under `/auth/mfa` (not `/platform`) so an operator can
enrol before the platform gate opens: `GET status`, `POST enroll`, `POST
confirm`, `POST verify`, `POST recovery-codes/regenerate`, `POST disable`.
Enrolment, regeneration and disable require the current password; a missing or
invalid `MFA_ENCRYPTION_KEY` fails closed with `503 mfa_unavailable`.

Audit filters: `created_from`, `created_to` (ISO dates/timestamps, inclusive),
`actor` (substring, LIKE-escaped), `actor_id` (exact), `organization_id`,
`event_type`, `entity_type`, `entity_id`, `target_user_id` (matches a `user`
entity directly, or the `membership`/`organization_membership` entity holding
that user), plus `page`/`page_size`.

The register exposes name, slug, sector, country, city, lifecycle state, demo
flag, creation and suspension timestamps and aggregate counts. It never returns
contact details, descriptions, coordinates or tenant business records.
Deletion is not offered by the API or the console.

## 3. Organisation suspension

Suspension required a schema change because the model had no lifecycle state:
`organizations.status` (`active`/`suspended`, default `active`, indexed) and
`organizations.suspended_at`. Migration `b7d2e4f6a8c1` (revises
`c3e5f7a9b1d2`) is additive and forward-only.

Exact effects, enforced centrally in `active_memberships()` and used by login,
organisation switching and per-request authentication:

- **Existing sessions** stay valid but stop granting the suspended organisation.
  Members with another active membership continue there.
- **New sign-ins** authenticate the account but the suspended organisation is
  not offered as active context; the session carries no authority for it.
- **Organisation switching** cannot select a suspended organisation.
- **API access** scoped to the suspended organisation returns `403`.
- **Other memberships** held by the same user are untouched. No user account is
  suspended, no membership row changes state, no invitation is deleted and no
  business record is removed.
- **Invitations** cannot be created into a suspended organisation (any caller,
  `409 organization_suspended`), and pending invitations cannot be accepted
  while it is suspended.
- **Account-only** actions such as `/auth/me`, password change and session
  listing remain available to the signed-in user.
- Reactivation restores access with no data repair step.

Only a platform operator with `platform.organizations.manage` can change the
state, and since Batch 12 the change must consume an approved two-person
request (section 4). Repeating the current state is rejected (`409
invalid_state_transition`); a suspension reason of at least 8 characters is
required (`422 reason_required`) and is recorded in the audit journal. The row
is read with `with_for_update()` and the state change and audit write share one
transaction.

## 4. Two-person approval

Suspension and reactivation are protected operations: one operator requests,
a **different** operator decides, and only an approved request can be executed.
The request is an immutable `platform_approval_requests` row (migration
`d9a1c3e5b7f2`); there is no update endpoint and no API that edits the target,
action or reason after creation.

### State machine

| From | Event | To | Who | Guard |
| --- | --- | --- | --- | --- |
| — | create | `pending` | requester | capability, tenant in the source state for the action, suspend reason ≥8 chars, no other open request for that tenant |
| `pending` | approve | `approved` | different operator | `platform.approvals.decide`; requester refused (`403 self_approval_forbidden`) |
| `pending` | reject | `rejected` | different operator | same capability and separation rule; terminal |
| `pending` | cancel | `cancelled` | requester | own request only; terminal |
| `pending` | TTL passes | `expired` | system | lazy expiry on read/decision; terminal, never revived |
| `approved` | cancel | `cancelled` | requester | own request only |
| `approved` | execute | `executed` | operator | `platform.approvals.execute` + `platform.organizations.manage`, exact target/action/reason, target still in the expected source state |
| `approved` | target drift | `cancelled` | system | tenant changed before execution; audited as `platform.approval.invalidated` |

`expired`, `rejected`, `cancelled` and `executed` have no outgoing transitions.
A second approval, rejection, cancellation or execution returns `409` with a
reason (`approval_not_pending`, `approval_already_executed`,
`approval_not_approved`, …). Concurrent decisions and executions take a row
lock, and execution also performs a conditional `UPDATE … WHERE status =
'approved'`; only one caller can claim the transition. The tenant update, the
approval claim and both audit events commit together, so a rollback leaves no
state change.

### Binding and expiry

The approval binds the exact `organization_id`, `action` (suspend/reactivate)
and normalised reason. Execution re-checks all three. The PATCH endpoint cannot
change status directly: it requires `approval_id`, loads that approved request
and refuses a mismatch (`409 approval_mismatch`, fields `organization_id`,
`action` or `reason`). If the tenant's state moved since approval, the request
is cancelled and the PATCH returns `409 approval_invalidated`. Changing the
request itself is impossible because the row is not editable; a different
target or action needs a new request.

Requests expire after `PLATFORM_APPROVAL_TTL_MINUTES` (default 60, bounded
5–1440). Only one `pending` or `approved` request may exist per organisation
(`409 approval_exists`, with the existing id), which prevents two approved
actions racing on the same tenant.

Every transition writes an audit event in the same transaction:
`platform.approval.requested`, `.approved`, `.rejected`, `.cancelled`,
`.expired`, `.invalidated`, `.executed`, followed by the existing
`platform.organization.suspended` / `.reactivated` event. Events record actor,
actor id, tenant, previous/new state and the reason, never a secret.

## 5. Operator MFA

MFA is required for **platform access only**; ordinary organisation login is
unchanged. The implementation is TOTP (RFC 6238, HMAC-SHA1, 30-second step,
6 digits, ±1 step) using Python's standard library, with these properties:

- **Enrolment:** `POST /auth/mfa/enroll` requires the current password and
  platform capability, generates a 160-bit secret from `secrets.token_bytes`,
  encrypts it with Fernet using `MFA_ENCRYPTION_KEY`, and returns the secret and
  `otpauth://` URI once. Pending secrets are not active until confirmed.
- **Confirmation:** `POST /auth/mfa/confirm` requires a valid code, marks the
  factor active, records `mfa_enrolled_at` and returns **10 recovery codes once**.
- **Storage:** the TOTP secret is never stored in plaintext; recovery codes are
  stored only as SHA-256 hashes, each with `used_at`. Recovery codes are
  single-use and are never deleted, so their use stays inspectable.
- **Verification:** `POST /auth/mfa/verify` accepts a TOTP code or a recovery
  code and sets `auth_sessions.mfa_verified_at` / `mfa_method` for that session.
  A successful TOTP also advances `users.mfa_last_counter`, so a code from the
  current or an earlier step cannot be replayed.
- **Recovery:** `POST /auth/mfa/recovery-codes/regenerate` requires the current
  password **and** a valid TOTP or recovery code; old hashes are deleted and a
  new set is shown once. `POST /auth/mfa/disable` requires the password and a
  valid factor, clears enrolment and revokes every session.
- **Lockout:** five failed factor attempts (configurable, 3–20) set
  `mfa_locked_until` for 15 minutes (1–240), durably in the database. An
  in-process limiter also caps attempts per 5 minutes. Failures are audited as
  `auth.mfa.verification_failed`; secrets, codes and hashes are never logged.
- **Fail closed:** with no `MFA_ENCRYPTION_KEY`, or a value too short to be a
  Fernet key, MFA operations return `503 mfa_unavailable`. There is no plaintext
  fallback and no bypass. Existing sessions without `mfa_verified_at` are
  refused platform access with `403 mfa_required`.

### Enrolment procedure

1. Sign in as the platform operator and open `/platform/security`.
2. Enter the current password under **Authenticator app**. The page shows the
   `otpauth://` URI and secret once; add it to a TOTP authenticator.
3. Enter the current six-digit code to confirm. The page then displays ten
   recovery codes **once**. Store them offline, separately from the
   authenticator; the console cannot show them again.
4. The session becomes MFA-verified; every subsequent platform request is
   checked against that session's verification time and limits.

If the code is lost before confirmation, start enrolment again. If recovery
codes are lost but the authenticator still works, regenerate them from the same
page (password plus factor) and destroy the old copy.

### Lost-factor reset (deployment operator)

There is deliberately no unauthenticated reset endpoint. The following
out-of-band procedure is the only recovery when both the authenticator and all
recovery codes are lost:

1. Verify the operator's identity and authority through an independent channel;
   do not accept a chat or email request alone.
2. Revoke all of the account's sessions and remove or suspend
   `is_platform_admin` until re-enrolment is complete.
3. With reviewed database access, clear the account's TOTP material (encrypted
   secret, enrolment timestamp and last accepted counter), reset failed-attempt
   and lockout fields, and delete its recovery-code rows.
4. Force a password change, require re-enrolment, then restore the flag only
   after the operator confirms a new factor and stores new recovery codes.
5. Record the reset in the deployment's operational log; the application's
   audit journal records the subsequent session revocations, enrolment and
   flag changes, but cannot audit a direct database edit.

There is no email or SMS delivery: LOOPMESH does not send MFA codes and claims
no provider. An operator who loses both authenticator and recovery codes has no
self-service bypass. A deployment operator must use this server-side procedure
with database access, and should review the
account's `is_platform_admin` flag at the same time.

## 6. Platform session governance

Platform operator sessions are the sessions of users with
`is_platform_admin = true`. `require_platform()` enforces, on every platform
request:

- a verified factor (`mfa_verified_at`) for the session;
- idle limit `PLATFORM_SESSION_IDLE_MINUTES` (default 30, bounded 5–120),
  measured from the session's last request;
- absolute limit `PLATFORM_SESSION_ABSOLUTE_HOURS` (default 8, bounded 1–24),
  measured from MFA verification.

Revocation sets `auth_sessions.revoked_at`, so the next request is refused.
`POST /platform/sessions/{id}/revoke` revokes another operator's session and
refuses the caller's own (`409 cannot_revoke_current`); sign out is the way to
end the current session. `POST /platform/sessions/revoke-all` revokes every
other operator session and deliberately keeps the caller's. Both actions write
`platform.session.revoked` audit events with the session and target user ids.

Removing `is_platform_admin` takes effect on the next request regardless of
live sessions, because the flag is read from the account each time. Ordinary
organisation sessions keep their existing idle/absolute policy and are not
revoked by platform session controls. No IP address or device detail is
collected, stored or displayed; the list shows email, timestamps, MFA state and
revocation state only.

## 7. Audit export

`GET /platform/audit/export` requires `platform.audit.view` **and**
`platform.audit.export`. It accepts the same filters as the journal and applies
the same serialisation redaction.

- **Required, bounded range:** both `created_from` and `created_to`; inverted
  ranges are rejected; the span may not exceed
  `PLATFORM_AUDIT_EXPORT_MAX_RANGE_DAYS` (default 90).
- **Bounded rows:** at most `PLATFORM_AUDIT_EXPORT_MAX_ROWS` (default 5,000). The
  service requests the cap + 1 and refuses with `422 export_too_large` rather
  than materialising an unbounded result.
- **Formats:** `format=csv` (UTF-8 with BOM, CRLF) or `format=json` (metadata +
  events). Columns are fixed; rows are ordered `created_at ASC, id ASC`.
- **CSV injection:** cells beginning with `=`, `+`, `-`, `@`, tab or carriage
  return (after leading whitespace) are prefixed with an apostrophe.
- **Filenames and headers:** `loopmesh-audit-<UTC timestamp>.csv|.json`,
  `Content-Disposition: attachment`, `Cache-Control: no-store`, `nosniff`.
- **Audit of the export:** `platform.audit.exported` records actor, format,
  filters, date range, row count and the configured cap. Reading never modifies
  or deletes source records.

### Retention policy

Audit records are **retained indefinitely by default**. LOOPMESH implements no
automatic purge, no API deletion and no console deletion. The operational
policy for a deployment is: retain online audit data for the life of the
tenant relationship plus the organisation's contractual/regulatory period,
take periodic bounded exports into write-once or access-controlled archive
storage, and delete online records only through a documented, reviewed
administrative database procedure after that period. Such a procedure is
outside the application, must not be run ad hoc, and must record who authorised
it and which date range was removed. This document does not silently prescribe
or perform deletion.

## 8. Tenant health

Each row reports three checks computed from records — `tenant_active`,
`membership_present`, `active_administrator_present` — plus bounded signals:
active/suspended membership counts, pending (unexpired) invitations, active
administrators, administrative changes in 30 days, security events in 30 days,
failed authentications attributed through the account's memberships in 24 hours,
and last activity.

Warnings (`organization_suspended`, `no_active_members`,
`no_active_administrator`) and states (`ok`, `attention`, `suspended`) are
derived only from those checks. “Operational” means the three checks passed; it
is not a claim of application health, and unavailable signals are counted as
zero only when the underlying event count is genuinely zero.

Limitation: a sign-in event is not tenant-scoped, so failed logins are
attributed through the account's memberships; an account in several tenants is
counted in each. Counts are grouped queries over the requested page of tenants,
not an unbounded scan.

## 9. Audit journal

The platform journal reads the existing `audit_events` table. There is no second
audit system, and nothing in the console or API can update or delete an event.

Administrative actions recorded by Batch 11: `platform.organization.suspended`
and `platform.organization.reactivated`, with actor label, `actor_id`, previous
and new state, the reason and a slug payload. Existing privileged membership,
invitation and account events remain queryable through the same endpoint.

### Redaction at the serialisation boundary

Payloads are sanitised when serialised, never in storage:

- `auth.*` events are reduced to an allow-list: `outcome`, `reason`,
  `known_account`, `delivery`, `method`.
- Keys matching the sensitive pattern (password, token, secret, hash,
  credential, key, cookie, session, …) become `[redacted]`, recursively.
- Strings longer than 500 characters are truncated.
- Nesting deeper than 5 levels is truncated.
- The names of redacted fields are returned in `redacted_fields`.

The event itself (actor, type, entity, organisation, severity, summary, reason,
states) is a safe representation; no endpoint returns password hashes, session
tokens or invitation tokens.

## 10. Frontend console

| Route | Contents |
| --- | --- |
| `/platform` | Estate metrics with their windows, newest tenants, recent privileged events, empty states |
| `/platform/organizations` | Searchable/filterable/paginated register; empty, error and reset states |
| `/platform/organizations/[id]` | Identity banner with name/slug/id, counts, health, recent events, metadata, approval-request control and exact semantics, 404 panel |
| `/platform/approvals` | Request form (target, action, reason), queue filtered by status, requested/approved/executed distinction, pagination |
| `/platform/approvals/[id]` | Bound target/action/reason, state and expiry, cancel, approve/reject, execute when approved, transition history, stale-state explanation |
| `/platform/audit` | Filters (date, organisation, event, actor, entity, target user), redacted event list, pagination, bounded export controls |
| `/platform/security` | TOTP status and enrolment, one-time recovery-code display, password-plus-factor disable, operator session list and revocation |
| `/platform/health` | Tenant health table with warnings and checks |

The layout is a server component: anonymous users are redirected to sign-in,
offline users see an API-unavailable screen, forced-password-change users go to
the password page, and non-operators are redirected to `/`. No platform content
is rendered before that decision. The console uses its own dark header and
navigation, with an “Organisation workspace” link, so the two areas cannot be
confused. Suspension is confirmed in a modal that states the effects and
requires a written reason (at least 8 characters) before the confirm button
enables. The security and approvals links are hidden without the matching
capability, and every action is authorised again by the API. Secrets, recovery
codes and session tokens are never written to localStorage; recovery codes are
shown in the page response once and are not persisted by the console.

## 11. Security assumptions and limitations

- The flag is the only source of platform authority; it must be provisioned
  carefully because it grants every permission.
- Platform operators can read cross-tenant operational metadata and the audit
  journal by design. Those responses exclude tenant business content.
- Platform sessions expose no IP address or device fingerprint because none is
  collected. Revocation and audit events identify sessions by id and user only.
- If `MFA_ENCRYPTION_KEY` is lost, enrolled operators cannot verify and must be
  reset through the out-of-band procedure; the database alone cannot decrypt
  their TOTP secrets. Back the key up in the deployment secret store.
- Audit export is bounded by the application, but an operator with both audit
  permissions can still copy up to the configured cap per request. Treat every
  export as sensitive operational data and store it accordingly.
- Audit retention is indefinite by default and has no application-level purge.
  Any archival deletion is a reviewed database procedure, never a UI action.
- Direct database edits to MFA, approval or audit rows bypass application
  auditing; restrict database access to deployment operators.
- **SQLite upgrade caveat:** adding the `status` column to an existing SQLite
  database cannot add the enum `CHECK` (SQLite's `ALTER TABLE` limitation, which
  Alembic warns about). Fresh databases and PostgreSQL have
  `ck_organizations_organization_status`; on an upgraded SQLite file validity is
  enforced by the ORM and API. PostgreSQL creates the constraint as part of the
  migration.
- Audit events written before Batch 11 may carry a user id in `actor` instead of
  an email. They are immutable; use `actor_id` for exact matching.
- Health metrics are operational signals, not an SLA; there is no historical
  trend store.
- Approval TTL and session/export limits are deployment settings; a restart is
  required to change them, and existing approvals keep the expiry stored on the
  row.
- **Deployment prerequisites:** PostgreSQL with `alembic upgrade head`, HTTPS
  with secure cookies in front of the app, `MFA_ENCRYPTION_KEY` in the secret
  store (not in the image or repository), a backed-up copy of that key, a
  trusted clock for TOTP, and restricted database access. The in-process MFA
  attempt limiter is per worker; the durable failed-attempt lockout in the
  database remains effective across workers, but a shared rate limiter is a
  deployment concern if the API scales horizontally.
- No production-readiness claim is made.

## 12. Tests and commands

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q -o addopts=""

# Batch 11 only
.venv/Scripts/python.exe -m pytest -q -o addopts="" tests/test_platform_batch11.py

# Batch 12 only (SQLite)
.venv/Scripts/python.exe -m pytest -q -o addopts="" tests/test_platform_batch12.py

# PostgreSQL concurrency suite against the Alembic-migrated disposable DB
LOOPMESH_PG_URL="postgresql+psycopg://loopmesh_test@127.0.0.1:55432/loopmesh_b12_fresh" \
  .venv/Scripts/python.exe -m pytest -q -o addopts="" \
  tests/test_refresh_concurrency_pg.py tests/test_platform_batch12_pg.py

cd ../frontend
npx vitest run
node node_modules/typescript/bin/tsc --noEmit
npm run build
```

Batch 11 verification: backend `241 passed, 14 skipped`; PostgreSQL `14 passed`;
frontend `96 passed` across 13 files; TypeScript clean; production build
succeeded; 48/48 live API checks and browser checks on a disposable database
copy.

Batch 12 verification: backend `273 passed, 16 skipped` (32 in the Batch 12
SQLite suite); PostgreSQL `16 passed` (including the Batch 12 PG suite);
frontend `104 passed` across 14 files;
TypeScript clean; production build succeeded; 70/70 live API checks on a
disposable SQLite copy; browser checks at 1440 px and 390×844 on a disposable
copy covering approvals list/detail, request creation, audit export, security
and no horizontal overflow. The development and E2E databases were not used for
Batch 12 verification; they remain at Alembic `c3e5f7a9b1d2` and contain no
Batch 12 tables.


## Batch 13 operational security hardening

- **Migration:** `e1c3a5b7d9f4` (revises `d9a1c3e5b7f2`) adds `security_rate_limits`, `audit_archive_batches`, `audit_integrity_state`, and audit hash-chain columns (`integrity_sequence`, `previous_hash`, `event_hash`) with deterministic backfill of existing rows.
- **Shared auth/MFA rate limiting:** login, password reset request/confirm and MFA enroll/confirm/verify/regenerate/disable consume a database-backed atomic fixed-window limiter (`security_rate_limits`) scoped by operation and pseudonymous hashed account/client principals. Limit exceeded returns `429 rate_limited`; limiter/storage unavailable fails closed with `503 security_limiter_unavailable` for auth/MFA operations. Durable MFA lockout remains in `users`/factor state.
- **MFA encryption and rotation:** TOTP secrets use versioned envelope encryption `v1.<key-id>.<ciphertext>` with primary plus previous keys (`MFA_ENCRYPTION_PREVIOUS_KEYS`). `python -m app.scripts.security_ops mfa-status|mfa-rotate` reports status and performs transactional, resumable batched re-encryption without forced re-enrolment. Missing/wrong/corrupt keys fail closed.
- **Break-glass recovery:** there is no HTTP endpoint. `python -m app.scripts.security_ops break-glass` requires infrastructure access, operator identity, approval reference, SHA-256 of an evidence file, reason and explicit confirmation; it clears only the target MFA factor, revokes that user's sessions, and records `platform.mfa.break_glass` (critical) without secret material. See `docs/MFA_KEY_MANAGEMENT.md`.
- **Audit integrity and retention:** every audit append is chained (`integrity_sequence`, `previous_hash`, `event_hash`) with a locked head; `GET /api/v1/platform/audit/integrity` verifies in bounded batches and records `platform.audit.integrity_verified`. Archive is external copy-only JSONL with SHA-256 sidecar and `platform.audit.archived` metadata (`app.scripts.security_ops audit-archive`); source rows are never silently deleted and no purge path is deployed (indefinite retention/legal hold by default). This provides tamper evidence, not database-level immutability against DBAs. See `docs/AUDIT_RETENTION_INTEGRITY.md`.
- **Database integrity baseline:** protected demo DBs are guarded by `backend/db_baseline.json` and `python scripts/verify_database_integrity.py` (read-only). Approved updates require `--write --approval-reference`. See `docs/DATABASE_INTEGRITY.md`.
- **Backup/restore:** documented in `docs/BACKUP_RESTORE.md`; `app.core.backup` provides SQLite checksum/integrity restore helpers and `tests/test_backup_restore.py` proves disposable restore + audit verification.
- **Operational CLI:** `python -m app.scripts.security_ops` (`mfa-status`, `mfa-rotate`, `audit-verify`, `audit-archive`, `retention-policy`, `limit-prune`, `break-glass`).
