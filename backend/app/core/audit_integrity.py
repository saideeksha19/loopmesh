"""Cryptographic audit-chain primitives.

The chain is deliberately independent of a database vendor and does not rely on
database-level immutability: a database administrator can still rewrite rows,
but cannot do so without invalidating every later hash.  This is tamper
*evidence*, not tamper prevention.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

AUDIT_HASH_VERSION = 1
GENESIS_HASH = hashlib.sha256(b"loopmesh.audit.genesis.v1").hexdigest()


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize timestamps to timezone-aware UTC for stable hashing.

    Naive datetimes are treated as UTC (existing contract). Aware datetimes are
    converted to UTC so the same instant hashes identically regardless of the
    original offset or database session timezone (e.g. PostgreSQL timestamptz
    read back in a non-UTC session).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def timestamp_text(value: datetime | None) -> str | None:
    moment = as_utc(value)
    return moment.isoformat(timespec="microseconds") if moment else None


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def audit_event_hash(event) -> str:
    """Hash the complete security-relevant content of one journal row."""
    severity = getattr(event.severity, "value", event.severity)
    material = {
        "version": AUDIT_HASH_VERSION,
        "sequence": int(event.integrity_sequence),
        "id": str(event.id),
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "previous_state": event.previous_state,
        "new_state": event.new_state,
        "actor": event.actor,
        "actor_id": event.actor_id,
        "organization_id": str(event.organization_id) if event.organization_id else None,
        "severity": severity,
        "summary": event.summary,
        "reason": event.reason,
        "detail": event.detail,
        "payload": event.payload or {},
        "created_at": timestamp_text(event.created_at),
        "updated_at": timestamp_text(event.updated_at),
        "previous_hash": event.previous_hash,
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()
