"""Audit journal helpers used by every mutation path.

Two rules keep the journal trustworthy:

* events are appended through the same :class:`~sqlalchemy.orm.Session` as the
  change they describe, so a rolled-back operation leaves no event behind;
* failed authorization attempts are recorded in their own transaction, because
  the operation they attempted did not happen but the attempt is still material.

Batch 13 adds a sequence + SHA-256 chain.  Appending locks the single chain-head
row on PostgreSQL, so concurrent workers cannot reuse a sequence.  The archive
helper copies a bounded range to an external file without deleting the source.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit_integrity import (
    GENESIS_HASH,
    as_utc,
    audit_event_hash,
    canonical_json,
)
from app.core.exceptions import ValidationError
from app.db.base import utcnow
from app.db.enums import AuditSeverity
from app.db.models.audit import AuditEvent, AuditIntegrityState
from app.db.models.security import AuditArchiveBatch


def _insert_state_if_missing(session: Session) -> None:
    """Create the chain head without racing another first append."""
    dialect = session.get_bind().dialect.name
    values = {
        "id": 1,
        "last_sequence": 0,
        "last_hash": GENESIS_HASH,
        "updated_at": utcnow(),
    }
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        session.execute(insert(AuditIntegrityState).values(**values).on_conflict_do_nothing())
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        session.execute(insert(AuditIntegrityState).values(**values).on_conflict_do_nothing())
    else:  # pragma: no cover - the project supports PostgreSQL and SQLite
        if session.get(AuditIntegrityState, 1) is None:
            session.add(AuditIntegrityState(**values))
            session.flush()


def _chain_state(session: Session) -> AuditIntegrityState:
    _insert_state_if_missing(session)
    state = session.get(AuditIntegrityState, 1, with_for_update=True)
    if state is None:  # pragma: no cover - defensive
        raise RuntimeError("Audit integrity state is unavailable.")
    return state


def record_event(
    session: Session,
    *,
    event_type: str,
    entity_type: str,
    summary: str,
    actor: str = "system",
    entity_id: uuid.UUID | None = None,
    severity: AuditSeverity = AuditSeverity.INFO,
    detail: str | None = None,
    payload: dict[str, Any] | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    reason: str | None = None,
    actor_id: str | None = None,
    organization_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> AuditEvent:
    """Append one journal entry and seal it into the hash chain.

    The event insert is flushed first so its UUID default exists, then the
    chain head is locked and advanced.  A caller's transaction still controls
    the event: a rollback removes both the event and its chain update.
    """
    moment = as_utc(created_at) or utcnow()
    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        actor_id=actor_id,
        organization_id=organization_id,
        severity=severity,
        summary=summary,
        detail=detail,
        reason=reason,
        previous_state=previous_state,
        new_state=new_state,
        payload=payload or {},
        created_at=moment,
        updated_at=as_utc(updated_at) or moment,
    )
    session.add(event)
    session.flush()

    state = _chain_state(session)
    sequence = int(state.last_sequence) + 1
    previous_hash = state.last_hash
    # ``updated_at`` has an ORM ``onupdate``.  Seal the row with an explicit
    # SQL UPDATE (including the final timestamp) so appending chain fields
    # cannot change the content that was just hashed.
    sealed = event.updated_at
    provisional = AuditEvent(
        id=event.id,
        integrity_sequence=sequence,
        previous_hash=previous_hash,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        previous_state=event.previous_state,
        new_state=event.new_state,
        actor=event.actor,
        actor_id=event.actor_id,
        organization_id=event.organization_id,
        severity=event.severity,
        summary=event.summary,
        reason=event.reason,
        detail=event.detail,
        payload=event.payload,
        created_at=event.created_at,
        updated_at=sealed,
    )
    event_hash = audit_event_hash(provisional)
    session.execute(
        update(AuditEvent)
        .where(AuditEvent.id == event.id)
        .values(
            integrity_sequence=sequence,
            previous_hash=previous_hash,
            event_hash=event_hash,
            updated_at=sealed,
        )
    )
    session.expire(event)
    session.refresh(event)
    state.last_sequence = sequence
    state.last_hash = event_hash
    state.updated_at = utcnow()
    session.flush()
    return event


def record_authorization_failure(
    session: Session,
    *,
    actor_id: str,
    actor_role: str,
    organization_id: uuid.UUID | None,
    operation: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    required: list[str] | None = None,
) -> AuditEvent:
    """Record a denied attempt without leaking credentials or record contents."""
    return record_event(
        session,
        event_type="authorization.denied",
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor_id,
        actor_id=actor_id,
        organization_id=organization_id,
        severity=AuditSeverity.WARNING,
        summary=f"Denied {operation} on {entity_type}: insufficient authority.",
        payload={
            "operation": operation,
            "actor_role": actor_role,
            "required_roles": required or [],
            "outcome": "denied",
        },
    )


def recent_events(session: Session, limit: int = 12) -> list[AuditEvent]:
    """Most recent journal entries, newest first."""
    return list(
        session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        ).all()
    )


def verify_integrity(session: Session, *, batch_size: int = 500) -> dict[str, Any]:
    """Walk the chain in bounded batches and report the first divergence."""
    checked = 0
    expected_sequence = 1
    previous_hash = GENESIS_HASH
    last_hash = GENESIS_HASH

    statement = (
        select(AuditEvent)
        .where(AuditEvent.integrity_sequence.is_not(None))
        .order_by(AuditEvent.integrity_sequence.asc())
        .execution_options(yield_per=batch_size)
    )

    first_invalid_sequence: int | None = None
    reason: str | None = None

    for event in session.scalars(statement):
        if event.integrity_sequence != expected_sequence:
            first_invalid_sequence = event.integrity_sequence
            reason = "sequence_gap"
            break
        if event.previous_hash != previous_hash:
            first_invalid_sequence = event.integrity_sequence
            reason = "previous_hash_mismatch"
            break
        recomputed = audit_event_hash(event)
        if event.event_hash != recomputed:
            first_invalid_sequence = event.integrity_sequence
            reason = "event_hash_mismatch"
            break
        checked += 1
        last_hash = event.event_hash
        previous_hash = event.event_hash
        expected_sequence += 1

    null_count = int(
        session.scalar(
            select(AuditEvent.id)
            .where(AuditEvent.integrity_sequence.is_(None))
            .limit(1)
        )
        is not None
    )
    if first_invalid_sequence is None and null_count:
        first_invalid_sequence = None
        reason = "unsealed_event"

    state = session.get(AuditIntegrityState, 1)
    state_sequence = int(state.last_sequence) if state else 0
    state_hash = state.last_hash if state else GENESIS_HASH
    if first_invalid_sequence is None and state is not None:
        if state_sequence != checked:
            reason = "chain_head_sequence_mismatch"
        elif state_hash != last_hash:
            reason = "chain_head_hash_mismatch"

    if first_invalid_sequence is None and state is None and checked:
        reason = "chain_head_missing"

    valid = reason is None and not null_count
    return {
        "valid": bool(valid),
        "checked": checked,
        "first_invalid_sequence": first_invalid_sequence,
        "reason": reason,
        "chain_head": last_hash,
        "state_sequence": state_sequence,
        "state_hash": state_hash,
        "verified_at": utcnow(),
    }


def archive_events(
    session: Session,
    *,
    destination: Path | str,
    created_from: datetime,
    created_to: datetime,
    created_by: str,
    approval_reference: str,
    batch_size: int = 500,
    commit: bool = True,
) -> AuditArchiveBatch:
    """Copy an audit range to a JSONL file and record the archive evidence.

    Source rows are never updated or deleted.  The destination and its SHA-256
    sidecar are written before the metadata row, so a reported archive always
    has a file to match.  An existing destination is refused, never replaced.
    """
    start = as_utc(created_from)
    end = as_utc(created_to)
    if start is None or end is None or start > end:
        raise ValidationError(
            "Audit archive requires an ordered inclusive time range.",
            details={"reason": "invalid_audit_archive_range"},
        )
    operator = (created_by or "").strip()
    approval = (approval_reference or "").strip()
    if not operator or not approval:
        raise ValidationError(
            "Audit archive requires the operator and an approval reference.",
            details={"reason": "audit_archive_evidence_required"},
        )

    path = Path(destination)
    if path.exists():
        raise ValidationError(
            "The archive destination already exists; refusing to replace it.",
            details={"reason": "audit_archive_exists"},
        )
    path.parent.mkdir(parents=True, exist_ok=True)

    statement = (
        select(AuditEvent)
        .where(
            AuditEvent.created_at >= start,
            AuditEvent.created_at <= end,
            AuditEvent.integrity_sequence.is_not(None),
        )
        .order_by(AuditEvent.integrity_sequence.asc())
        .execution_options(yield_per=batch_size)
    )

    digest = hashlib.sha256()
    count = 0
    first_sequence: int | None = None
    last_sequence: int | None = None
    try:
        with path.open("xb") as handle:
            for event in session.scalars(statement):
                from app.services.platform import redact_payload

                payload, redacted = redact_payload(event.event_type, event.payload)
                record = {
                    "id": str(event.id),
                    "integrity_sequence": event.integrity_sequence,
                    "created_at": as_utc(event.created_at).isoformat()
                    if as_utc(event.created_at)
                    else None,
                    "event_type": event.event_type,
                    "entity_type": event.entity_type,
                    "entity_id": str(event.entity_id) if event.entity_id else None,
                    "actor": event.actor,
                    "actor_id": event.actor_id,
                    "organization_id": str(event.organization_id)
                    if event.organization_id
                    else None,
                    "severity": getattr(event.severity, "value", str(event.severity)),
                    "summary": event.summary,
                    "reason": event.reason,
                    "previous_state": event.previous_state,
                    "new_state": event.new_state,
                    "payload": payload,
                    "redacted_fields": redacted,
                    "previous_hash": event.previous_hash,
                    "event_hash": event.event_hash,
                }
                line = (canonical_json(record) + "\n").encode("utf-8")
                handle.write(line)
                digest.update(line)
                count += 1
                if first_sequence is None:
                    first_sequence = int(event.integrity_sequence)
                last_sequence = int(event.integrity_sequence)
    except FileExistsError as exc:
        raise ValidationError(
            "The archive destination already exists; refusing to replace it.",
            details={"reason": "audit_archive_exists"},
        ) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise

    if count == 0 or first_sequence is None or last_sequence is None:
        path.unlink(missing_ok=True)
        raise ValidationError(
            "No audit events fall inside that range.",
            details={"reason": "audit_archive_empty"},
        )

    archive_hash = digest.hexdigest()
    sidecar = path.with_name(f"{path.name}.sha256")
    sidecar.write_text(f"{archive_hash}  {path.name}\n", encoding="utf-8")

    batch = AuditArchiveBatch(
        created_by=operator,
        approval_reference=approval,
        created_from=start,
        created_to=end,
        event_count=count,
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        archive_sha256=archive_hash,
        file_name=path.name,
        format="jsonl",
    )
    session.add(batch)
    session.flush()
    record_event(
        session,
        event_type="platform.audit.archived",
        entity_type="audit_archive",
        entity_id=batch.id,
        actor=operator,
        actor_id=operator,
        severity=AuditSeverity.WARNING,
        summary="Audit journal range archived without deleting source records.",
        payload={
            "archive_id": str(batch.id),
            "approval_reference": approval,
            "event_count": count,
            "first_sequence": first_sequence,
            "last_sequence": last_sequence,
            "archive_sha256": archive_hash,
            "file_name": path.name,
            "format": "jsonl",
            "created_from": start.isoformat(),
            "created_to": end.isoformat(),
        },
    )
    if commit:
        session.commit()
    else:
        session.flush()
    return batch
