# Deploying LOOPMESH on Render

This runbook deploys the application to [Render](https://render.com) using
[`render.yaml`](../render.yaml). It is preparation only: nothing here has been
applied to a live environment, and no paid resource is created by reading it.

## Topology

```
browser ──https──▶ loopmesh-web (public, Next.js)
                        │  /api/v1/* proxied server-side
                        ▼
                   loopmesh-api (private service, FastAPI)
                        │
                        ▼
                   loopmesh-db (PostgreSQL, same region)
```

The browser only ever sees one origin. Next.js route handlers
(`frontend/app/api/v1/[...path]/route.ts`) forward cookies to the private API,
so authentication stays same-site: no `SameSite=None` cookies, no cross-origin
credential CORS, and no public API hostname to leak or protect separately.

`loopmesh-api` has **no public URL**. Its `/docs`, `/openapi.json` and every
endpoint are reachable only from inside Render's private network.

## What must be true before deploying

These are implemented in the repository; listed so the deploy can be reviewed
against them.

| Requirement | Where |
|---|---|
| A provider-issued `postgresql://` URL selects the installed psycopg 3 driver | `backend/app/core/config.py` (`_select_postgres_driver`) |
| The frontend start command binds `$PORT` | `frontend/package.json` (`start: next start`) |
| A scheme-less private hostname such as `loopmesh-api:8000` becomes a valid base URL | `frontend/lib/api-base.ts` (`normaliseApiBase`) |
| Production refuses SQLite, wildcard CORS, wildcard hosts and `DEBUG` | `backend/app/core/config.py` (`validate_runtime_security`) |
| Schema migrations are applied before traffic | `preDeployCommand: alembic upgrade head` |

Copying the connection string out of a hosting dashboard must not require
hand-editing it. `postgresql://`, `postgres://` and `postgresql+psycopg://` are
all accepted; the first two are rewritten.

## Prerequisites

1. The repository is pushed to a Git remote Render can read (GitHub, GitLab or
   Bitbucket). Render deploys from a branch, not from a local folder.
2. A Render account with billing enabled. This topology needs paid instance
   types: private services are not available on the free plan, and a free
   PostgreSQL instance is deleted automatically after 30 days.
3. `MFA_ENCRYPTION_KEY` generated for this environment only:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Lose this value and every enrolled TOTP secret becomes unreadable — see
   [`MFA_KEY_MANAGEMENT.md`](MFA_KEY_MANAGEMENT.md). Never commit it, never
   reuse a key from another environment.

Approximate monthly cost with the plans in the blueprint: web Starter + private
service Starter + PostgreSQL Basic ≈ **$20**. Confirm current pricing in the
dashboard; plans change. If Render rejects a plan slug, pick the equivalent
plan interactively — the blueprint values are indicative, not a quote.

## Step 1 — create the blueprint

Dashboard → **New → Blueprint** → select the repository and branch. Render
reads `render.yaml`, shows `loopmesh-web`, `loopmesh-api` and `loopmesh-db`, and
asks for the values marked `sync: false` before the first deploy.

Set all three services and the database to **the same region** (the blueprint
omits `region`, so everything lands in the account's default region — acceptable
only if that is the region you want).

### Secrets and deployment-specific values

| Variable | Service | Value |
|---|---|---|
| `ALLOWED_HOSTS` | `loopmesh-api` | `loopmesh-api,<frontend-host>` — the private service name plus the public frontend host, no scheme, no port, no wildcard |
| `CORS_ORIGINS` | `loopmesh-api` | `https://<frontend-host>` — exactly one explicit origin |
| `MFA_ENCRYPTION_KEY` | `loopmesh-api` | the Fernet key generated above |
| `DATABASE_URL` | `loopmesh-api` | wired from `loopmesh-db` `connectionString` |
| `API_INTERNAL_URL` | `loopmesh-web` | wired from `loopmesh-api` `hostport` |

Do **not** set `NEXT_PUBLIC_API_URL` in production. It is inlined into the
browser bundle and would point the browser directly at a second hostname.

`<frontend-host>` is known only after `loopmesh-web` is created (for example
`loopmesh-web.onrender.com`), so expect to fill these in on the first pass and
redeploy the API once.

## Step 2 — first deploy and migrations

The API's `preDeployCommand` runs `alembic upgrade head` before the new instance
takes traffic. If the selected plan does not offer pre-deploy commands, remove
that line and run the command once from the service shell:

```bash
cd /opt/render/project/src/backend && alembic upgrade head
```

Confirm the schema matches the code:

```bash
alembic current   # must equal the head revision
```

## Step 3 — provision the first organisation and administrator

A migrated database has no tenant, so nobody can sign in: authentication
resolves an active organisation membership. From the `loopmesh-api` shell (an
interactive terminal — the password is read with `getpass`):

```bash
cd /opt/render/project/src/backend
python scripts/provision_tenant.py \
  --email admin@example.com \
  --name "Ada Admin" \
  --organization "Acme Recovery" \
  --sector steel_metals \
  --country IN
```

The script is idempotent and safe to re-run:

* the organisation is matched by slug and reused,
* the user is matched by email and reused (no password prompt on a re-run),
* the membership is created or corrected, never duplicated,
* `--no-platform-admin` omits platform rights; `--dry-run` reports the changes
  and rolls them back.

A password is requested only when the account does not exist yet and must pass
the platform policy (length, mixed case, a number or symbol). No password,
token or hash is ever printed.

`provision_admin.py` remains available for a bare platform administrator with
no organisation; it refuses to run once any user exists, so use it only on an
empty database.

## Step 4 — verify

Run these against the **public** frontend origin.

| Check | Expected |
|---|---|
| `GET https://<frontend>/` | 200 and the real landing page |
| `GET https://<frontend>/api/v1/health` | readiness `ok` (proves proxy → API → database) |
| Sign in with the provisioned account | lands in the workspace, no CORS or cookie errors |
| Cookie inspection in devtools | `HttpOnly`, `Secure`, `SameSite=Lax`; no token in `localStorage` |
| Reload a workspace page after >15 minutes idle | one silent refresh, no redirect loop |
| One mutation (create a draft proposal) | succeeds (CSRF and write path both work) |
| `GET https://<frontend>/platform` as the admin | platform console loads; MFA enrolment is offered |
| `GET https://loopmesh-api.onrender.com` or any public API URL | does not resolve — the service is private |
| `alembic current` in the shell | head revision |

If `/api/v1/health` fails while `/` works, the proxy cannot reach the API:
check `API_INTERNAL_URL` first, then `ALLOWED_HOSTS` (the proxy sends
`Host: loopmesh-api:8000`, and the allow-list compares hosts without the port).

## Operational notes

* **Rate limiting.** Authentication limits are stored in the database
  (`security_rate_limits`), so they survive restarts and are shared across
  workers. They fail closed if the table is unreachable.
* **Client IPs.** The frontend proxy does not forward the client address;
  `TRUST_PROXY_HEADERS` must stay `false`. Attempts are therefore counted per
  account rather than per address, which is the intended control here. Do not
  enable proxy-header trust without forwarding a real client IP and listing the
  actual proxy hops in `TRUSTED_PROXY_IPS`.
* **No persistent disk.** Nothing durable may be written to the service
  filesystem; uploads belong in object storage. All application data lives in
  PostgreSQL.
* **Single instance each.** A deploy briefly interrupts the API; there is no
  horizontal scaling. Scale up, not out, if needed.
* **Backups.** Render's paid PostgreSQL plans include daily backups. Exercise a
  restore before trusting them — see [`BACKUP_RESTORE.md`](BACKUP_RESTORE.md).
* **Unpublish vs delete.** Taking an environment offline in Render stops serving
  but keeps code, data and secrets. Deleting the PostgreSQL instance deletes the
  data permanently.

## Rollback

1. Redeploy the previous commit from Render's **Deploys** tab (migrations are
   forward-only: inspect the revision before rolling back code across a schema
   change).
2. Rotate `MFA_ENCRYPTION_KEY` only with the procedure in
   [`MFA_KEY_MANAGEMENT.md`](MFA_KEY_MANAGEMENT.md); never silently replace it.
3. If the API is unusable, unpublish `loopmesh-web` rather than deleting
   anything — data and configuration survive.
