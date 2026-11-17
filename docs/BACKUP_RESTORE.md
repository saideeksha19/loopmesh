# Backup and Restore Runbook (Batch 13)

This runbook covers database backup/restore and the security material required
to recover MFA-protected operator access. It does **not** include or generate
real secrets; operators must substitute their deployment's values and store them
in approved secret storage.

## 1. Database backup

### PostgreSQL (production target)

Create a consistent logical backup:

```bash
pg_dump -Fc --no-owner --no-privileges "$DATABASE_URL" -f loopmesh-$(date +%F).dump
sha256sum loopmesh-*.dump > loopmesh-*.dump.sha256
```

Store the dump in encrypted, access-controlled backup storage. Restrict access
to infrastructure operators; backups contain hashed credentials, hashed tokens,
audit records and encrypted MFA secrets.

### SQLite (local/dev disposable proof)

Use the online backup API, never a plain file copy while writers may exist:

```bash
python -m app.scripts.security_ops backup-sqlite --source <db> --out <backup.db>
```

(For ad hoc use, `app.core.backup.backup_sqlite` performs the same operation and
writes a `.sha256` sidecar.)

## 2. Encryption-key backup requirements

`MFA_ENCRYPTION_KEY` encrypts TOTP secrets at rest (`users.mfa_secret_encrypted`,
versioned envelope `v1.<key-id>.<ciphertext>`). Previous keys may be configured
during rotation as `MFA_ENCRYPTION_PREVIOUS_KEYS`.

- Back up the **active** key and, while rotation is in progress, every
  configured previous key in the same secret manager/versioned vault entry used
  for deployment configuration.
- Never store keys in the database, source control, chat, tickets, logs or test
  artifacts.
- Record the key ID/fingerprint shown by `python -m app.scripts.security_ops mfa-status`
  (fingerprint only, never key material) alongside the change record.
- Without a matching key, stored MFA secrets are unreadable and verification
  fails closed; recovery then requires the documented break-glass procedure.

## 3. Recovery-code and MFA recovery implications

- Recovery codes are stored only as hashes and are single-use. A backup restores
  their consumed/unconsumed state as of the backup point.
- Restoring to an older backup can make an already-used recovery code appear
  usable again in the restored environment; treat restored environments as
  isolated recovery targets, not as a way to roll back production security state.
- TOTP replay protection (`mfa_last_counter`) is also restored from backup;
  clock drift after restore must be corrected before operator sign-in.
- If an operator loses both authenticator and recovery codes, use the break-glass
  procedure in `docs/MFA_KEY_MANAGEMENT.md`. There is no self-service bypass.

## 4. Restore to a disposable environment

### PostgreSQL

```bash
createdb loopmesh_restore_test
pg_restore --clean --if-exists --no-owner --no-privileges \
  -d postgresql+psycopg://.../loopmesh_restore_test loopmesh-YYYY-MM-DD.dump
```

### SQLite

```bash
python - <<'PY'
from app.core.backup import restore_sqlite
restore_sqlite('backup.db', 'restored.db')
PY
```

`restore_sqlite` refuses if the checksum sidecar is missing or mismatched and
fails if `PRAGMA integrity_check` is not `ok`.

## 5. Post-restore verification

After restore, run on the disposable restored database:

```bash
# Alembic revision matches the expected application head for that deployment
python -m alembic current
python -m alembic heads

# Audit chain is intact
python -m app.scripts.security_ops audit-verify

# MFA key status (no secret material printed)
python -m app.scripts.security_ops mfa-status
```

`audit-verify` exits non-zero if sequence/hash state is invalid. A valid chain
after restore proves the restored rows still match the chain head recorded in the
backup; it does **not** prove the backup predates any compromise, nor that the
database is immutable against administrators.

## 6. Backup frequency and restore validation

- Back up before every production migration and on the deployment's regular
  schedule (at least daily for active environments; align with RPO).
- Validate restore in a disposable environment after backup-process changes, key
  rotation, schema migrations and on a regular cadence (at least quarterly).
- Keep backup verification evidence (checksum, restore target, Alembic revision,
  audit-verify result, timestamp, operator) without storing secrets or raw audit
  payloads in the evidence artifact.
