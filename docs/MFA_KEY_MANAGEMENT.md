# MFA Key Rotation and Recovery Runbook (Batch 13)

## Encryption model

- TOTP secrets are encrypted at rest with authenticated Fernet encryption.
- Stored envelope format: `v1.<key-id>.<ciphertext>`.
- `key-id` is a truncated SHA-256 fingerprint (not key material) for status
  reporting and mixed-version detection.
- Legacy unversioned Batch 12 Fernet tokens remain readable when the matching
  key is configured; rotation rewrites them to the active versioned envelope.
- Primary key: `MFA_ENCRYPTION_KEY` (required). Previous keys during rotation:
  `MFA_ENCRYPTION_PREVIOUS_KEYS` (comma separated). Keys are never stored in the
  database and never logged.

Fail-closed behaviour:
- Missing/invalid primary key: enrol, confirm, verify and rotation operations
  fail with `503 mfa_unavailable`.
- Missing/unknown key for an existing envelope, malformed envelope, or corrupted
  ciphertext: verification/rotation fails closed; unreadable secrets are never
  replaced.

## Controlled rotation (no forced re-enrolment)

1. **Prepare**: generate a new Fernet key in approved secret storage:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. **Configure**: set `MFA_ENCRYPTION_KEY=<new>` and move the old key into
   `MFA_ENCRYPTION_PREVIOUS_KEYS=<old>[,<older>...]`. Deploy/restart workers so
   all processes share the same keyring.
3. **Re-encrypt** in batches (transactional per batch, resumable):
   `python -m app.scripts.security_ops mfa-rotate --performed-by <operator> --batch-size 100`
   Repeat until complete. An interrupted batch is rolled back; committed batches
   remain rotated.
4. **Verify status** (no key material): `python -m app.scripts.security_ops mfa-status`
   Confirm `complete: true`, `unknown: 0`, all secrets active.
5. **Remove previous keys** from configuration once complete and redeploy.
6. **Audit**: rotation records `platform.mfa.key_rotated` with counts and active
   key ID fingerprint.

Existing MFA verification continues during rotation because previous keys remain
configured for decryption until re-encryption completes.

## Rollback

- If rotation has not started, revert `MFA_ENCRYPTION_KEY` to the original key.
- If rotation is partially complete, keep **both** the new primary key and the
  previous key configured; do not remove the previous key until status is
  complete. Resume `mfa-rotate` after fixing the underlying issue.
- Never delete key material while any stored secret depends on it.

## Secure backup

Store the active key (and any in-use previous keys) in versioned, access-
controlled secret storage with change history. Back up keys separately from
database dumps but retain enough metadata (key ID fingerprint, rotation ticket)
to match a restore. Do not export keys into repository files or test fixtures.

## Break-glass recovery procedure

There is **no HTTP endpoint** and no hidden bypass for MFA. Recovery is a server-
side, infrastructure-operator procedure:

1. **Authorization and evidence**: obtain documented approval from authorized
   infrastructure/security operators (outside the ordinary platform operator
   role). Preserve the approval record and export/save the evidence file.
2. **Access**: the operator must have server shell and database access to the
   deployment environment; this is intentionally not available to ordinary
   platform users.
3. **Execute**:
   ```bash
   python -m app.scripts.security_ops break-glass \
     --email <operator@example.com> \
     --performed-by <infrastructure-operator-id> \
     --approval-reference <ticket-or-approval-id> \
     --evidence-file <path-to-approval-evidence> \
     --reason "<documented reason>" \
     --confirm <operator@example.com>
   ```
   The command hashes the evidence file (SHA-256) and requires explicit
   confirmation of the target email.
4. **Effects**: clears only the target operator's MFA secret/recovery codes and
   revokes that operator's sessions. The `is_platform_admin` flag is **not**
   changed. The action is audited as `platform.mfa.break_glass` (critical) with
   operator identity, target, approval reference, evidence hash, reason and
   revoked-session count — never secret material.
5. **Post-recovery**: the operator signs in and completes MFA enrolment again
   under the current active key. Review the operator's platform authority and
   rotate/revoke any related credentials as policy requires.

Ordinary platform operators cannot invoke this procedure because it requires
infrastructure access and is not exposed through the API or UI.
