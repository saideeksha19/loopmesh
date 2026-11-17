# Audit Retention and Integrity Runbook (Batch 13)

## Retention policy

- Audit rows are retained indefinitely by default. Batch 13 does **not** deploy
  a purge/delete path and does not silently delete source records.
- External archival copies a bounded time range to JSONL with a SHA-256 sidecar
  and records `AuditArchiveBatch` metadata plus a `platform.audit.archived`
  audit event. Source rows remain in the database.
- **Legal hold**: indefinite retention with no purge path satisfies hold by
  default. If a future purge capability is introduced, it must be explicitly
  permissioned, audited, and refuse rows under a documented hold marker.

Record the deployment's policy acknowledgement:

```bash
python -m app.scripts.security_ops retention-policy \
  --approved-by <operator> --approval-reference <ticket>
```

This emits `platform.audit.retention_policy_recorded` (no rows deleted).

## Integrity mechanism (tamper evidence)

- Each audit event is sealed with `integrity_sequence`, `previous_hash` and
  `event_hash` (SHA-256 over canonical, security-relevant content including the
  chain link). A single-row chain head (`audit_integrity_state`) is advanced in
  the same append transaction.
- Appends lock the chain head on PostgreSQL (`SELECT ... FOR UPDATE`) so
  concurrent workers cannot reuse a sequence; SQLite serializes writers.
- Verification walks the chain in bounded batches, checking sequence continuity,
  previous hash linkage, recomputed event hash and chain-head consistency. It
  reports the first invalid sequence/reason when tampering or gaps are detected.
- **Important**: this is tamper **evidence**, not database-level immutability.
  A database administrator can rewrite rows, but cannot do so without breaking
  the chain. Verification and operational controls are required.

## Verification

API (requires `platform.audit.view` and `platform.audit.verify`):

```http
GET /api/v1/platform/audit/integrity
```

CLI:

```bash
python -m app.scripts.security_ops audit-verify
```

Each API verification records `platform.audit.integrity_verified` with outcome
(valid/invalid, checked count, reason, chain head). Bounded memory: verification
and archival stream rows in batches (`AUDIT_VERIFY_BATCH_SIZE`,
`AUDIT_ARCHIVE_BATCH_SIZE`).

## Archival

```bash
python -m app.scripts.security_ops audit-archive \
  --from 2026-01-01T00:00:00Z --to 2026-01-31T23:59:59Z \
  --out /secure/archive/audit-2026-01.jsonl \
  --performed-by <operator> --approval-reference <ticket>
```

- Requires operator identity and approval reference.
- Refuses to overwrite an existing destination; writes file then `.sha256`
  sidecar then metadata/event.
- Exported payloads are redacted using the same rules as the audit export API.
- Source records are never deleted; the archive is an external evidence copy.

Permissions: `PLATFORM_AUDIT_VERIFY` (verify) and `PLATFORM_AUDIT_ARCHIVE` (future
archive-capable operations/policy actions) are granted to platform administrators
by the platform permission set.

## Recovery after restore

Run `audit-verify` on the restored disposable/production database. A valid result
means the restored chain is internally consistent. Investigate any mismatch
before relying on the restored journal for compliance evidence.
