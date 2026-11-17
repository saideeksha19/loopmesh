"""Batch 13 operational commands.

Examples (never paste key material or recovery codes into shell history):

    python -m app.scripts.security_ops mfa-status
    python -m app.scripts.security_ops mfa-rotate --batch-size 100
    python -m app.scripts.security_ops audit-verify
    python -m app.scripts.security_ops audit-archive --from ... --to ... --out ...
    python -m app.scripts.security_ops retention-policy --approved-by ... --approval-reference ...
    python -m app.scripts.security_ops break-glass --email ... --performed-by ... \
        --approval-reference ... --evidence-file ... --reason ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core import mfa as mfa_core
from app.core.config import settings
from app.db.enums import AuditSeverity
from app.db.session import SessionLocal
from app.services import audit as audit_service
from app.services import mfa_recovery
from app.services import mfa as mfa_service


def _iso(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _status(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        status = mfa_core.rotation_status(db)
    print(
        json.dumps(
            {
                "active_key_id": status.active_key_id,
                "previous_key_ids": list(status.previous_key_ids),
                "total_secrets": status.total_secrets,
                "active": status.active,
                "legacy": status.legacy,
                "previous": status.previous,
                "unknown": status.unknown,
                "needs_rotation": status.needs_rotation,
                "complete": status.complete,
            },
            indent=2,
        )
    )
    return 0 if not status.unknown else 2


def _rotate(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        result = mfa_core.rotate_mfa_secrets(
            db,
            batch_size=args.batch_size or settings.mfa_rotation_batch_size,
        )
        status = mfa_core.rotation_status(db)
        audit_service.record_event(
            db,
            event_type="platform.mfa.key_rotated",
            entity_type="mfa_keyring",
            actor=args.performed_by,
            actor_id=args.performed_by,
            severity=AuditSeverity.WARNING,
            summary="MFA secrets re-encrypted under the active key.",
            payload={
                "total": result.total,
                "rotated": result.rotated,
                "already_active": result.already_active,
                "complete": status.complete,
                "active_key_id": status.active_key_id,
            },
        )
        db.commit()
    print(
        json.dumps(
            {
                "total": result.total,
                "rotated": result.rotated,
                "already_active": result.already_active,
                "batches": result.batches,
                "complete": status.complete,
            },
            indent=2,
        )
    )
    return 0 if status.complete else 2


def _verify(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        result = audit_service.verify_integrity(
            db, batch_size=settings.audit_verify_batch_size
        )
    print(
        json.dumps(
            {
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in result.items()
            },
            indent=2,
        )
    )
    return 0 if result["valid"] else 2


def _archive(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        batch = audit_service.archive_events(
            db,
            destination=Path(args.out),
            created_from=_iso(args.created_from),
            created_to=_iso(args.created_to),
            created_by=args.performed_by,
            approval_reference=args.approval_reference,
            batch_size=settings.audit_archive_batch_size,
        )
        # Read-only operational metadata; no event payloads are printed.
        print(
            json.dumps(
                {
                    "archive_id": str(batch.id),
                    "event_count": batch.event_count,
                    "first_sequence": batch.first_sequence,
                    "last_sequence": batch.last_sequence,
                    "archive_sha256": batch.archive_sha256,
                    "file_name": batch.file_name,
                    "source_records_deleted": False,
                },
                indent=2,
            )
        )
        del db
    return 0


def _retention_policy(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        audit_service.record_event(
            db,
            event_type="platform.audit.retention_policy_recorded",
            entity_type="audit_retention_policy",
            actor=args.approved_by,
            actor_id=args.approved_by,
            severity=AuditSeverity.WARNING,
            summary="Audit retention policy acknowledged for this deployment.",
            payload={
                "approval_reference": args.approval_reference,
                "policy": args.policy,
                "purge_supported": False,
                "legal_hold": "indefinite retention; no purge path is deployed",
            },
        )
        db.commit()
    print("Retention policy acknowledgement recorded; no audit rows were deleted.")
    return 0


def _limit_prune(args: argparse.Namespace) -> int:
    from app.core.security_limiter import prune_expired

    with SessionLocal() as db:
        removed = prune_expired(
            db, retention_seconds=settings.security_limiter_retention_hours * 3600
        )
    print(json.dumps({"removed_counter_rows": removed}, indent=2))
    return 0


def _break_glass(args: argparse.Namespace) -> int:
    evidence = Path(args.evidence_file)
    if not evidence.is_file():
        print("Evidence file not found; no recovery was attempted.")
        return 2
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    if args.confirm != args.email.strip().lower():
        print("Refusing: --confirm must equal the target email exactly.")
        return 2
    with SessionLocal() as db:
        result = mfa_recovery.break_glass_reset(
            db,
            email=args.email,
            performed_by=args.performed_by,
            approval_reference=args.approval_reference,
            evidence_sha256=digest,
            reason=args.reason,
        )
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LOOPMESH Batch 13 security operations")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("mfa-status", help="Report key IDs and rotation completeness")
    status.set_defaults(func=_status)

    rotate = sub.add_parser("mfa-rotate", help="Re-encrypt stored MFA secrets")
    rotate.add_argument("--batch-size", type=int, default=None)
    rotate.add_argument("--performed-by", default="infrastructure-operator")
    rotate.set_defaults(func=_rotate)

    verify = sub.add_parser("audit-verify", help="Verify the audit sequence/hash chain")
    verify.set_defaults(func=_verify)

    archive = sub.add_parser("audit-archive", help="Copy a range to an external JSONL archive")
    archive.add_argument("--from", dest="created_from", required=True)
    archive.add_argument("--to", dest="created_to", required=True)
    archive.add_argument("--out", required=True)
    archive.add_argument("--performed-by", required=True)
    archive.add_argument("--approval-reference", required=True)
    archive.set_defaults(func=_archive)

    policy = sub.add_parser("retention-policy", help="Record the deployment retention policy")
    policy.add_argument("--approved-by", required=True)
    policy.add_argument("--approval-reference", required=True)
    policy.add_argument(
        "--policy",
        default="Audit rows are retained indefinitely by default; archive copies are never source deletions; no purge path is deployed.",
    )
    policy.set_defaults(func=_retention_policy)

    prune = sub.add_parser("limit-prune", help="Delete expired shared limiter rows")
    prune.set_defaults(func=_limit_prune)

    glass = sub.add_parser("break-glass", help="Documented MFA recovery for one operator")
    glass.add_argument("--email", required=True)
    glass.add_argument("--performed-by", required=True)
    glass.add_argument("--approval-reference", required=True)
    glass.add_argument("--evidence-file", required=True)
    glass.add_argument("--reason", required=True)
    glass.add_argument("--confirm", required=True)
    glass.set_defaults(func=_break_glass)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
