"""operational security hardening: shared limits, audit chain and archive metadata

Batch 13 is additive:

* ``security_rate_limits`` is the cross-worker fixed-window counter;
* ``audit_events`` gains a sequence and SHA-256 chain, backfilled in append
  order for every existing row;
* ``audit_integrity_state`` stores the single chain head;
* ``audit_archive_batches`` records external archive evidence, not contents.

No business row is rewritten and no existing audit meaning changes.  The demo
databases are intentionally not migrated by this repository's tests.

Revision ID: e1c3a5b7d9f4
Revises: d9a1c3e5b7f2
Create Date: 2026-11-15 23:55:00.000000
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1c3a5b7d9f4"
down_revision: Union[str, None] = "d9a1c3e5b7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GENESIS_HASH = hashlib.sha256(b"loopmesh.audit.genesis.v1").hexdigest()


def _as_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _stamp(value) -> str | None:
    moment = _as_utc(value)
    return moment.isoformat(timespec="microseconds") if moment else None


def _canonical(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _hash_material(row, sequence: int, previous_hash: str) -> str:
    material = {
        "version": 1,
        "sequence": sequence,
        "id": str(uuid.UUID(str(row["id"]))),
        "event_type": row["event_type"],
        "entity_type": row["entity_type"],
        "entity_id": str(uuid.UUID(str(row["entity_id"]))) if row["entity_id"] else None,
        "previous_state": row["previous_state"],
        "new_state": row["new_state"],
        "actor": row["actor"],
        "actor_id": row["actor_id"],
        "organization_id": str(uuid.UUID(str(row["organization_id"])))
        if row["organization_id"]
        else None,
        "severity": row["severity"],
        "summary": row["summary"],
        "reason": row["reason"],
        "detail": row["detail"],
        "payload": json.loads(row["payload"]) if isinstance(row["payload"], str) else (row["payload"] or {}),
        "created_at": _stamp(row["created_at"]),
        "updated_at": _stamp(row["updated_at"]),
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "security_rate_limits",
        sa.Column("bucket_key", sa.String(length=255), nullable=False),
        sa.Column("window_started_at", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("updated_at_epoch", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name="ck_security_rate_limits_attempt_count_non_negative"),
        sa.PrimaryKeyConstraint("bucket_key"),
    )

    op.create_table(
        "audit_integrity_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_archive_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("approval_reference", sa.String(length=200), nullable=False),
        sa.Column("created_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("first_sequence", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("integrity_sequence", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("previous_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("event_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    events = bind.execute(
        sa.text(
            "SELECT id, event_type, entity_type, entity_id, previous_state, new_state, "
            "actor, actor_id, organization_id, severity, summary, reason, detail, payload, "
            "created_at, updated_at FROM audit_events ORDER BY created_at ASC, id ASC"
        )
    ).mappings().all()

    previous_hash = GENESIS_HASH
    for sequence, row in enumerate(events, start=1):
        event_hash = _hash_material(row, sequence, previous_hash)
        bind.execute(
            sa.text(
                "UPDATE audit_events SET integrity_sequence = :sequence, "
                "previous_hash = :previous_hash, event_hash = :event_hash WHERE id = :id"
            ),
            {
                "sequence": sequence,
                "previous_hash": previous_hash,
                "event_hash": event_hash,
                "id": row["id"],
            },
        )
        previous_hash = event_hash

    bind.execute(
        sa.text(
            "INSERT INTO audit_integrity_state (id, last_sequence, last_hash, updated_at) "
            "VALUES (1, :last_sequence, :last_hash, :updated_at)"
        ),
        {
            "last_sequence": len(events),
            "last_hash": previous_hash,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_audit_events_integrity_sequence", ["integrity_sequence"]
        )
        batch_op.create_index("ix_audit_events_integrity_sequence", ["integrity_sequence"])
        batch_op.create_index("ix_audit_events_event_hash", ["event_hash"])


def downgrade() -> None:
    """Remove Batch 13 state; business and audit content rows are retained."""
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_events_event_hash")
        batch_op.drop_index("ix_audit_events_integrity_sequence")
        batch_op.drop_constraint("uq_audit_events_integrity_sequence", type_="unique")
        batch_op.drop_column("event_hash")
        batch_op.drop_column("previous_hash")
        batch_op.drop_column("integrity_sequence")

    op.drop_table("audit_archive_batches")
    op.drop_table("audit_integrity_state")
    op.drop_table("security_rate_limits")
