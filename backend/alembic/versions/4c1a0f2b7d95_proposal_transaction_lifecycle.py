"""proposal and transaction lifecycle

Adds the Phase 2A lifecycle:

* new status vocabulary for proposals and transactions (data-migrated),
* lifecycle evidence columns (submission, review, approval, verification),
* an optimistic-concurrency ``version`` column on both entities,
* the append-only ``status_transitions`` history table,
* lifecycle fields on ``audit_events``,
* the ``CHECK`` constraints that make an unapproved or unevidenced
  verification impossible at the database level.

Revision ID: 4c1a0f2b7d95
Revises: 096363408627
Create Date: 2026-11-15 14:05:00.000000

SQLite has no ``ALTER TABLE ... DROP CONSTRAINT``, so the constraint changes
rebuild the two tables through Alembic batch mode. PostgreSQL receives ordinary
``ALTER TABLE`` statements. No expectations about PostgreSQL execution are
claimed: only SQLite has been run against this revision.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4c1a0f2b7d95"
down_revision: Union[str, None] = "096363408627"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROPOSAL_STATUSES = (
    "draft",
    "submitted",
    "under_review",
    "approved",
    "in_progress",
    "completed",
    "rejected",
    "withdrawn",
    "cancelled",
    "failed",
)
LEGACY_PROPOSAL_STATUSES = (
    "draft",
    "proposed",
    "under_review",
    "accepted",
    "declined",
    "withdrawn",
    "expired",
)
TRANSACTION_STATUSES = (
    "created",
    "in_progress",
    "transferred",
    "verified",
    "rejected",
    "cancelled",
    "failed",
)
LEGACY_TRANSACTION_STATUSES = (
    "accepted",
    "in_transit",
    "transported",
    "verified",
    "cancelled",
    "failed",
)
MATERIAL_UNITS = ("kg", "tonne", "m3", "litre", "mwh")
VERIFICATION_METHODS = (
    "weighbridge_ticket",
    "third_party_audit",
    "supplier_declaration",
    "laboratory_assay",
    "other",
)
COMPATIBILITY_STATUSES = ("compatible", "conditional", "incompatible", "unverified")

MIGRATION_ACTOR = "system:phase1-migration"

# Checks that must only exist once legacy rows have been migrated.
_PROPOSAL_LIFECYCLE_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_recovery_proposals_approved_requires_authority",
        "status <> 'approved' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL "
        "AND approval_reference IS NOT NULL)",
    ),
    (
        "ck_recovery_proposals_submitted_requires_timestamp",
        "status NOT IN ('submitted', 'under_review', 'approved', 'in_progress', 'completed') "
        "OR submitted_at IS NOT NULL",
    ),
    (
        "ck_recovery_proposals_rejected_requires_reason",
        "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejected_by IS NOT NULL "
        "AND rejection_reason IS NOT NULL)",
    ),
    (
        "ck_recovery_proposals_completed_requires_timestamp",
        "status <> 'completed' OR completed_at IS NOT NULL",
    ),
    (
        "ck_recovery_proposals_failed_requires_reason",
        "status <> 'failed' OR failure_reason IS NOT NULL",
    ),
    (
        "ck_recovery_proposals_cancelled_requires_reason",
        "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
    ),
)

_TRANSACTION_LIFECYCLE_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_recovery_transactions_verified_requires_evidence",
        "status <> 'verified' OR (verified_quantity IS NOT NULL AND verified_at IS NOT NULL "
        "AND verified_by IS NOT NULL)",
    ),
    (
        "ck_recovery_transactions_transferred_requires_quantity",
        "status <> 'transferred' OR (transferred_quantity IS NOT NULL AND transferred_at IS NOT NULL)",
    ),
    (
        "ck_recovery_transactions_rejected_requires_reason",
        "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejection_reason IS NOT NULL)",
    ),
    (
        "ck_recovery_transactions_cancelled_requires_reason",
        "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
    ),
)


def _in_clause(column: str, values: Sequence[str]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


# ---------------------------------------------------------------------------
# table definitions used by the SQLite batch rebuild
# ---------------------------------------------------------------------------


def _proposals_table(*, final: bool = True) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "recovery_proposals",
        metadata,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_by_organization_id", sa.Uuid(), nullable=False),
        sa.Column("receiving_organization_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("compatibility_status", sa.String(32), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("submitted_by", sa.String(120), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reference", sa.String(200), nullable=True),
        sa.Column(
            "approval_evidence",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("rejected_by", sa.String(120), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("withdrawn_by", sa.String(120), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_recovery_proposals_quantity_positive"),
        sa.CheckConstraint(
            "price_per_unit IS NULL OR price_per_unit >= 0",
            name="ck_recovery_proposals_price_non_negative",
        ),
        sa.CheckConstraint("version >= 0", name="ck_recovery_proposals_version_non_negative"),
        sa.CheckConstraint(
            _in_clause("unit", MATERIAL_UNITS), name="ck_recovery_proposals_materialunit"
        ),
        sa.CheckConstraint(
            _in_clause("compatibility_status", COMPATIBILITY_STATUSES),
            name="ck_recovery_proposals_compatibilitystatus",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["recovery_opportunities.id"],
            name="fk_recovery_proposals_opportunity_id_recovery_opportunities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by_organization_id"],
            ["organizations.id"],
            name="fk_recovery_proposals_proposed_by_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["receiving_organization_id"],
            ["organizations.id"],
            name="fk_recovery_proposals_receiving_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recovery_proposals"),
    )
    if final:
        for name, condition in _PROPOSAL_LIFECYCLE_CHECKS:
            table.append_constraint(sa.CheckConstraint(condition, name=name))
        table.append_constraint(
            sa.CheckConstraint(
                _in_clause("status", PROPOSAL_STATUSES),
                name="ck_recovery_proposals_proposalstatus",
            )
        )
    sa.Index("ix_recovery_proposals_opportunity_id", table.c.opportunity_id)
    sa.Index(
        "ix_recovery_proposals_proposed_by_organization_id",
        table.c.proposed_by_organization_id,
    )
    sa.Index(
        "ix_recovery_proposals_receiving_organization_id",
        table.c.receiving_organization_id,
    )
    sa.Index("ix_recovery_proposals_status", table.c.status)
    return table


def _transactions_table(*, final: bool = True) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "recovery_transactions",
        metadata,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_organization_id", sa.Uuid(), nullable=not final),
        sa.Column("destination_organization_id", sa.Uuid(), nullable=not final),
        sa.Column("accepted_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("transferred_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("verified_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("transport_distance_km", sa.Numeric(8, 1), nullable=True),
        sa.Column("carrier_name", sa.String(160), nullable=True),
        sa.Column("transfer_reference", sa.String(120), nullable=True),
        sa.Column("material_identification", sa.String(200), nullable=True),
        sa.Column("transfer_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_recorded_by", sa.String(120), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(120), nullable=True),
        sa.Column("verification_method", sa.String(32), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(120), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(120), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.CheckConstraint(
            "accepted_quantity IS NULL OR accepted_quantity > 0",
            name="ck_recovery_transactions_accepted_quantity_positive",
        ),
        sa.CheckConstraint(
            "transferred_quantity IS NULL OR transferred_quantity > 0",
            name="ck_recovery_transactions_transferred_quantity_positive",
        ),
        sa.CheckConstraint(
            "verified_quantity IS NULL OR verified_quantity > 0",
            name="ck_recovery_transactions_verified_quantity_positive",
        ),
        sa.CheckConstraint(
            "source_organization_id <> destination_organization_id",
            name="ck_recovery_transactions_distinct_parties",
        ),
        sa.CheckConstraint(
            "transport_distance_km IS NULL OR transport_distance_km >= 0",
            name="ck_recovery_transactions_distance_non_negative",
        ),
        sa.CheckConstraint("version >= 0", name="ck_recovery_transactions_version_non_negative"),
        sa.CheckConstraint(
            _in_clause("unit", MATERIAL_UNITS), name="ck_recovery_transactions_materialunit"
        ),
        sa.CheckConstraint(
            _in_clause("verification_method", VERIFICATION_METHODS),
            name="ck_recovery_transactions_verificationmethod",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["recovery_proposals.id"],
            name="fk_recovery_transactions_proposal_id_recovery_proposals",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_organization_id"],
            ["organizations.id"],
            name="fk_recovery_transactions_source_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_organization_id"],
            ["organizations.id"],
            name="fk_recovery_transactions_destination_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recovery_transactions"),
        sa.UniqueConstraint(
            "proposal_id", name="uq_recovery_transactions_proposal_id"
        ),
    )
    if final:
        for name, condition in _TRANSACTION_LIFECYCLE_CHECKS:
            table.append_constraint(sa.CheckConstraint(condition, name=name))
        table.append_constraint(
            sa.CheckConstraint(
                _in_clause("status", TRANSACTION_STATUSES),
                name="ck_recovery_transactions_transactionstatus",
            )
        )
    sa.Index("ix_recovery_transactions_status", table.c.status)
    sa.Index(
        "ix_recovery_transactions_source_organization_id", table.c.source_organization_id
    )
    sa.Index(
        "ix_recovery_transactions_destination_organization_id",
        table.c.destination_organization_id,
    )
    return table


def _legacy_proposals_table() -> sa.Table:
    return _proposals_table_with(
        columns=[
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("opportunity_id", sa.Uuid(), nullable=False),
            sa.Column("proposed_by_organization_id", sa.Uuid(), nullable=False),
            sa.Column("receiving_organization_id", sa.Uuid(), nullable=False),
            sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("unit", sa.String(32), nullable=False),
            sa.Column("price_per_unit", sa.Numeric(12, 2), nullable=True),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("compatibility_status", sa.String(32), nullable=False),
            sa.Column("terms", sa.JSON(), nullable=False),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_demo", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
            ),
        ],
        constraints=[
            sa.CheckConstraint(
                "quantity > 0", name="ck_recovery_proposals_quantity_positive"
            ),
            sa.CheckConstraint(
                "price_per_unit IS NULL OR price_per_unit >= 0",
                name="ck_recovery_proposals_price_non_negative",
            ),
            sa.CheckConstraint(
                _in_clause("unit", MATERIAL_UNITS),
                name="ck_recovery_proposals_materialunit",
            ),
            sa.CheckConstraint(
                _in_clause("compatibility_status", COMPATIBILITY_STATUSES),
                name="ck_recovery_proposals_compatibilitystatus",
            ),
            sa.CheckConstraint(
                _in_clause("status", LEGACY_PROPOSAL_STATUSES),
                name="ck_recovery_proposals_proposalstatus",
            ),
            sa.ForeignKeyConstraint(
                ["opportunity_id"],
                ["recovery_opportunities.id"],
                name="fk_recovery_proposals_opportunity_id_recovery_opportunities",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["proposed_by_organization_id"],
                ["organizations.id"],
                name="fk_recovery_proposals_proposed_by_organization_id_organizations",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["receiving_organization_id"],
                ["organizations.id"],
                name="fk_recovery_proposals_receiving_organization_id_organizations",
                ondelete="CASCADE",
            ),
        ],
        indexes=[
            ("ix_recovery_proposals_opportunity_id", "opportunity_id"),
            ("ix_recovery_proposals_proposed_by_organization_id", "proposed_by_organization_id"),
            ("ix_recovery_proposals_receiving_organization_id", "receiving_organization_id"),
            ("ix_recovery_proposals_status", "status"),
        ],
    )


def _legacy_transactions_table() -> sa.Table:
    return _transactions_table_with(
        columns=[
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("proposal_id", sa.Uuid(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("accepted_quantity", sa.Numeric(14, 3), nullable=True),
            sa.Column("verified_quantity", sa.Numeric(14, 3), nullable=True),
            sa.Column("unit", sa.String(32), nullable=False),
            sa.Column("transport_distance_km", sa.Numeric(8, 1), nullable=True),
            sa.Column("carrier_name", sa.String(160), nullable=True),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verification_method", sa.String(32), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_demo", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
            ),
        ],
        constraints=[
            sa.CheckConstraint(
                "accepted_quantity IS NULL OR accepted_quantity > 0",
                name="ck_recovery_transactions_accepted_quantity_positive",
            ),
            sa.CheckConstraint(
                "verified_quantity IS NULL OR verified_quantity > 0",
                name="ck_recovery_transactions_verified_quantity_positive",
            ),
            sa.CheckConstraint(
                "status <> 'verified' OR (verified_quantity IS NOT NULL AND verified_at IS NOT NULL)",
                name="ck_recovery_transactions_verified_requires_evidence",
            ),
            sa.CheckConstraint(
                "transport_distance_km IS NULL OR transport_distance_km >= 0",
                name="ck_recovery_transactions_distance_non_negative",
            ),
            sa.CheckConstraint(
                _in_clause("unit", MATERIAL_UNITS),
                name="ck_recovery_transactions_materialunit",
            ),
            sa.CheckConstraint(
                _in_clause("verification_method", VERIFICATION_METHODS),
                name="ck_recovery_transactions_verificationmethod",
            ),
            sa.CheckConstraint(
                _in_clause("status", LEGACY_TRANSACTION_STATUSES),
                name="ck_recovery_transactions_transactionstatus",
            ),
            sa.ForeignKeyConstraint(
                ["proposal_id"],
                ["recovery_proposals.id"],
                name="fk_recovery_transactions_proposal_id_recovery_proposals",
                ondelete="CASCADE",
            ),
        ],
        indexes=[("ix_recovery_transactions_status", "status")],
        unique=[sa.UniqueConstraint("proposal_id", name="uq_recovery_transactions_proposal_id")],
    )


def _proposals_table_with(*, columns, constraints, indexes) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "recovery_proposals",
        metadata,
        *columns,
        *constraints,
        sa.PrimaryKeyConstraint("id", name="pk_recovery_proposals"),
    )
    for name, column in indexes:
        sa.Index(name, table.c[column])
    return table


def _transactions_table_with(*, columns, constraints, indexes, unique) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "recovery_transactions",
        metadata,
        *columns,
        *constraints,
        *unique,
        sa.PrimaryKeyConstraint("id", name="pk_recovery_transactions"),
    )
    for name, column in indexes:
        sa.Index(name, table.c[column])
    return table


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _drop_stale_batch_tables() -> None:
    """Remove batch-mode scratch tables left behind by an interrupted run."""
    inspector = sa.inspect(op.get_bind())
    for name in inspector.get_table_names():
        if name.startswith("_alembic_tmp_"):
            op.execute(sa.text(f'DROP TABLE "{name}"'))


def _rebuild(table_name: str, table: sa.Table) -> None:
    """SQLite: rebuild the table with an explicit target schema."""
    _drop_stale_batch_tables()
    with op.batch_alter_table(table_name, copy_from=table, recreate="always"):
        pass


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def _create_status_transitions() -> None:
    op.create_table(
        "status_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_state", sa.String(32), nullable=False),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(120), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.CheckConstraint(
            _in_clause("entity_type", ("proposal", "transaction")),
            name=op.f("ck_status_transitions_transitionentity"),
        ),
        # ``org_admin`` is a first-class ActorRole (organisation administrators
        # perform workflow transitions), so the vocabulary must include it.
        sa.CheckConstraint(
            _in_clause(
                "actor_role",
                (
                    "admin",
                    "org_admin",
                    "coordinator",
                    "reviewer",
                    "approver",
                    "auditor",
                    "viewer",
                ),
            ),
            name=op.f("ck_status_transitions_actorrole"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_status_transitions_organization_id_organizations",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_status_transitions"),
    )
    op.create_index("ix_status_transitions_entity_type", "status_transitions", ["entity_type"])
    op.create_index("ix_status_transitions_entity_id", "status_transitions", ["entity_id"])
    op.create_index(
        "ix_status_transitions_organization_id", "status_transitions", ["organization_id"]
    )
    op.create_index(
        "ix_status_transitions_entity",
        "status_transitions",
        ["entity_type", "entity_id", "occurred_at"],
    )


def _add_audit_columns() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.add_column(sa.Column("previous_state", sa.String(32), nullable=True))
        batch.add_column(sa.Column("new_state", sa.String(32), nullable=True))
        batch.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("actor_id", sa.String(120), nullable=True))
        batch.add_column(sa.Column("organization_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_audit_events_organization_id_organizations",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_audit_events_actor_id", ["actor_id"])
        batch.create_index("ix_audit_events_organization_id", ["organization_id"])


def _add_proposal_columns() -> None:
    with op.batch_alter_table("recovery_proposals") as batch:
        batch.add_column(sa.Column("submitted_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("reviewed_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("approved_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("approval_reference", sa.String(200), nullable=True))
        batch.add_column(
            sa.Column(
                "approval_evidence",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.add_column(sa.Column("rejected_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("withdrawn_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cancellation_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("failure_reason", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )

def _add_transaction_columns() -> None:
    with op.batch_alter_table("recovery_transactions") as batch:
        batch.add_column(sa.Column("source_organization_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("destination_organization_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("transferred_quantity", sa.Numeric(14, 3), nullable=True))
        batch.add_column(sa.Column("transfer_reference", sa.String(120), nullable=True))
        batch.add_column(sa.Column("material_identification", sa.String(200), nullable=True))
        batch.add_column(
            sa.Column("transfer_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("transfer_recorded_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("verified_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("rejected_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cancelled_by", sa.String(120), nullable=True))
        batch.add_column(sa.Column("cancellation_reason", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    # SQLite DDL is not transactional, so a failed run can leave part of the
    # migration applied. Every structural step is idempotent, so a partially
    # applied upgrade can simply be re-run.
    _drop_stale_batch_tables()
    if not _has_table("status_transitions"):
        _create_status_transitions()
    if not _has_column("audit_events", "previous_state"):
        _add_audit_columns()
    if not _has_column("recovery_proposals", "version"):
        _add_proposal_columns()
    if not _has_column("recovery_transactions", "version"):
        _add_transaction_columns()

    # The legacy status CHECK constraints reject the new vocabulary, so both
    # tables must be relaxed before any row is rewritten.
    if _is_sqlite():
        _rebuild("recovery_proposals", _proposals_table(final=False))
        _rebuild("recovery_transactions", _transactions_table(final=False))
    else:
        # These names are already fully resolved by the naming convention, so
        # they must be marked with op.f() or Alembic prefixes them a second time.
        op.drop_constraint(
            op.f("ck_recovery_proposals_proposalstatus"), "recovery_proposals", type_="check"
        )
        op.drop_constraint(
            op.f("ck_recovery_transactions_transactionstatus"),
            "recovery_transactions",
            type_="check",
        )

    _migrate_data_up()

    if _is_sqlite():
        _rebuild("recovery_proposals", _proposals_table(final=True))
        _rebuild("recovery_transactions", _transactions_table(final=True))
    else:
        _apply_constraints_upgrade()


def _migrate_data_up() -> None:
    # --- status vocabulary --------------------------------------------------
    op.execute(
        """
        UPDATE recovery_proposals
           SET status = CASE status
                 WHEN 'proposed' THEN 'submitted'
                 WHEN 'accepted' THEN 'approved'
                 WHEN 'declined' THEN 'rejected'
                 WHEN 'expired' THEN 'cancelled'
                 ELSE status
               END
        """
    )
    # Proposals that already had a transaction are further along than "approved".
    op.execute(
        """
        UPDATE recovery_proposals
           SET status = 'completed',
               completed_at = COALESCE(
                   (SELECT t.verified_at FROM recovery_transactions t
                     WHERE t.proposal_id = recovery_proposals.id),
                   updated_at, created_at
               )
         WHERE status = 'approved'
           AND EXISTS (
               SELECT 1 FROM recovery_transactions t
                WHERE t.proposal_id = recovery_proposals.id AND t.status = 'verified'
           )
        """
    )
    op.execute(
        """
        UPDATE recovery_proposals
           SET status = 'in_progress',
               started_at = COALESCE(
                   (SELECT t.created_at FROM recovery_transactions t
                     WHERE t.proposal_id = recovery_proposals.id),
                   updated_at, created_at
               )
         WHERE status = 'approved'
           AND EXISTS (
               SELECT 1 FROM recovery_transactions t
                WHERE t.proposal_id = recovery_proposals.id
                  AND t.status IN ('accepted', 'in_transit', 'transported')
           )
        """
    )

    # --- lifecycle evidence backfill ---------------------------------------
    # Legacy records predate the lifecycle. Their provenance is recorded
    # explicitly as migration-derived rather than invented approval evidence.
    op.execute(
        f"""
        UPDATE recovery_proposals
           SET submitted_at = COALESCE(submitted_at, updated_at, created_at),
               submitted_by = COALESCE(submitted_by, '{MIGRATION_ACTOR}')
         WHERE status IN ('submitted', 'under_review', 'approved', 'in_progress', 'completed')
        """
    )
    op.execute(
        f"""
        UPDATE recovery_proposals
           SET reviewed_at = COALESCE(reviewed_at, updated_at, created_at),
               reviewed_by = COALESCE(reviewed_by, '{MIGRATION_ACTOR}')
         WHERE status IN ('approved', 'in_progress', 'completed')
        """
    )
    op.execute(
        f"""
        UPDATE recovery_proposals
           SET approved_at = COALESCE(approved_at, updated_at, created_at),
               approved_by = COALESCE(approved_by, '{MIGRATION_ACTOR}'),
               approval_reference = COALESCE(approval_reference, 'legacy:phase1-acceptance'),
               approval_evidence = '{{"source": "phase1_migration"}}'
         WHERE status IN ('approved', 'in_progress', 'completed')
        """
    )
    op.execute(
        f"""
        UPDATE recovery_proposals
           SET withdrawn_at = COALESCE(withdrawn_at, updated_at, created_at),
               withdrawn_by = COALESCE(withdrawn_by, '{MIGRATION_ACTOR}')
         WHERE status = 'withdrawn'
        """
    )
    op.execute(
        f"""
        UPDATE recovery_proposals
           SET rejected_at = COALESCE(rejected_at, updated_at, created_at),
               rejected_by = COALESCE(rejected_by, '{MIGRATION_ACTOR}'),
               rejection_reason = COALESCE(rejection_reason,
                   'Legacy declined status migrated from Phase 1.')
         WHERE status = 'rejected'
        """
    )
    op.execute(
        f"""
        UPDATE recovery_proposals
           SET cancelled_at = COALESCE(cancelled_at, updated_at, created_at),
               cancellation_reason = COALESCE(cancellation_reason,
                   'Legacy expired status migrated from Phase 1.')
         WHERE status = 'cancelled'
        """
    )

    # --- transactions -------------------------------------------------------
    op.execute(
        """
        UPDATE recovery_transactions
           SET status = CASE status
                 WHEN 'accepted' THEN 'created'
                 WHEN 'in_transit' THEN 'in_progress'
                 WHEN 'transported' THEN 'transferred'
                 ELSE status
               END
        """
    )
    op.execute(
        """
        UPDATE recovery_transactions
           SET source_organization_id = (
                   SELECT p.proposed_by_organization_id FROM recovery_proposals p
                    WHERE p.id = recovery_transactions.proposal_id),
               destination_organization_id = (
                   SELECT p.receiving_organization_id FROM recovery_proposals p
                    WHERE p.id = recovery_transactions.proposal_id)
         WHERE source_organization_id IS NULL OR destination_organization_id IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE recovery_transactions
           SET transferred_quantity = COALESCE(transferred_quantity, accepted_quantity),
               transferred_at = COALESCE(transferred_at, delivered_at, updated_at, created_at),
               transfer_recorded_by = COALESCE(transfer_recorded_by, '{MIGRATION_ACTOR}'),
               transfer_reference = COALESCE(transfer_reference, 'legacy:phase1-transfer'),
               material_identification = COALESCE(material_identification,
                   'Legacy Phase 1 transfer record')
         WHERE status IN ('transferred', 'verified')
        """
    )
    op.execute(
        f"""
        UPDATE recovery_transactions
           SET verified_by = COALESCE(verified_by, '{MIGRATION_ACTOR}')
         WHERE status = 'verified'
        """
    )
    op.execute(
        f"""
        UPDATE recovery_transactions
           SET cancellation_reason = COALESCE(cancellation_reason,
                   'Legacy cancelled transaction migrated from Phase 1.'),
               cancelled_at = COALESCE(cancelled_at, updated_at, created_at),
               cancelled_by = COALESCE(cancelled_by, '{MIGRATION_ACTOR}')
         WHERE status = 'cancelled'
        """
    )


def _apply_constraints_upgrade() -> None:
    """PostgreSQL path: constraint and nullability changes via ALTER TABLE."""
    with op.batch_alter_table("recovery_proposals") as batch:
        # The legacy status CHECK was dropped before the data rewrite; the new
        # vocabulary has to be enforced again, exactly as the SQLite rebuild does.
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_proposalstatus"),
            _in_clause("status", PROPOSAL_STATUSES),
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_version_non_negative"), "version >= 0"
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_approved_requires_authority"),
            "status <> 'approved' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL "
            "AND approval_reference IS NOT NULL)",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_submitted_requires_timestamp"),
            "status NOT IN ('submitted', 'under_review', 'approved', 'in_progress', 'completed') "
            "OR submitted_at IS NOT NULL",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_rejected_requires_reason"),
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejected_by IS NOT NULL "
            "AND rejection_reason IS NOT NULL)",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_completed_requires_timestamp"),
            "status <> 'completed' OR completed_at IS NOT NULL",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_failed_requires_reason"),
            "status <> 'failed' OR failure_reason IS NOT NULL",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_proposals_cancelled_requires_reason"),
            "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
        )

    with op.batch_alter_table("recovery_transactions") as batch:
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_transactionstatus"),
            _in_clause("status", TRANSACTION_STATUSES),
        )
    with op.batch_alter_table("recovery_transactions") as batch:
        batch.drop_constraint(
            op.f("ck_recovery_transactions_verified_requires_evidence"), type_="check"
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_verified_requires_evidence"),
            "status <> 'verified' OR (verified_quantity IS NOT NULL AND verified_at IS NOT NULL "
            "AND verified_by IS NOT NULL)",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_transferred_requires_quantity"),
            "status <> 'transferred' OR (transferred_quantity IS NOT NULL AND transferred_at IS NOT NULL)",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_transferred_quantity_positive"),
            "transferred_quantity IS NULL OR transferred_quantity > 0",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_rejected_requires_reason"),
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejection_reason IS NOT NULL)",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_cancelled_requires_reason"),
            "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_distinct_parties"),
            "source_organization_id <> destination_organization_id",
        )
        batch.create_check_constraint(
            op.f("ck_recovery_transactions_version_non_negative"), "version >= 0"
        )
        batch.alter_column(
            "source_organization_id", existing_type=sa.Uuid(), nullable=False
        )
        batch.alter_column(
            "destination_organization_id", existing_type=sa.Uuid(), nullable=False
        )
        batch.create_foreign_key(
            "fk_recovery_transactions_source_organization_id_organizations",
            "organizations",
            ["source_organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        # The convention-generated name for this constraint is 66 characters,
        # beyond PostgreSQL's 63-byte identifier limit, so SQLAlchemy silently
        # emits the truncated form (last 4 characters replaced by a hash). Use
        # that exact name here so migration-built and model-built schemas agree.
        batch.create_foreign_key(
            op.f("fk_recovery_transactions_destination_organization_id_or_fe3a"),
            "organizations",
            ["destination_organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_recovery_transactions_source_organization_id", ["source_organization_id"]
        )
        batch.create_index(
            "ix_recovery_transactions_destination_organization_id",
            ["destination_organization_id"],
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Map back to the Phase 1 vocabulary before restoring the old constraints.
    if _is_sqlite():
        _rebuild("recovery_transactions", _transactions_table(final=False))
        _rebuild("recovery_proposals", _proposals_table(final=False))
    else:
        # These names are already fully resolved by the naming convention, so
        # they must be marked with op.f() or Alembic prefixes them a second time.
        op.drop_constraint(
            op.f("ck_recovery_proposals_proposalstatus"), "recovery_proposals", type_="check"
        )
        op.drop_constraint(
            op.f("ck_recovery_transactions_transactionstatus"),
            "recovery_transactions",
            type_="check",
        )

    op.execute(
        """
        UPDATE recovery_proposals
           SET status = CASE status
                 WHEN 'submitted' THEN 'proposed'
                 WHEN 'approved' THEN 'accepted'
                 WHEN 'in_progress' THEN 'accepted'
                 WHEN 'completed' THEN 'accepted'
                 WHEN 'rejected' THEN 'declined'
                 WHEN 'failed' THEN 'declined'
                 WHEN 'cancelled' THEN 'expired'
                 ELSE status
               END
        """
    )
    op.execute(
        """
        UPDATE recovery_transactions
           SET status = CASE status
                 WHEN 'created' THEN 'accepted'
                 WHEN 'in_progress' THEN 'in_transit'
                 WHEN 'transferred' THEN 'transported'
                 WHEN 'rejected' THEN 'cancelled'
                 ELSE status
               END
        """
    )

    if _is_sqlite():
        _rebuild("recovery_proposals", _legacy_proposals_table())
        _rebuild("recovery_transactions", _legacy_transactions_table())
    else:
        with op.batch_alter_table("recovery_proposals") as batch:
            # The status CHECK was already dropped above, before the row rewrite.
            for name in (
                "ck_recovery_proposals_version_non_negative",
                "ck_recovery_proposals_approved_requires_authority",
                "ck_recovery_proposals_submitted_requires_timestamp",
                "ck_recovery_proposals_rejected_requires_reason",
                "ck_recovery_proposals_completed_requires_timestamp",
                "ck_recovery_proposals_failed_requires_reason",
                "ck_recovery_proposals_cancelled_requires_reason",
            ):
                batch.drop_constraint(op.f(name), type_="check")
            batch.create_check_constraint(
                op.f("ck_recovery_proposals_proposalstatus"),
                _in_clause("status", LEGACY_PROPOSAL_STATUSES),
            )
            for column in (
                "submitted_by",
                "submitted_at",
                "reviewed_by",
                "reviewed_at",
                "approved_by",
                "approved_at",
                "approval_reference",
                "approval_evidence",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
                "withdrawn_by",
                "withdrawn_at",
                "started_at",
                "completed_at",
                "cancelled_at",
                "cancellation_reason",
                "failed_at",
                "failure_reason",
                "version",
            ):
                batch.drop_column(column)

        with op.batch_alter_table("recovery_transactions") as batch:
            # The status CHECK was already dropped above, before the row rewrite.
            for name in (
                "ck_recovery_transactions_verified_requires_evidence",
                "ck_recovery_transactions_transferred_requires_quantity",
                "ck_recovery_transactions_transferred_quantity_positive",
                "ck_recovery_transactions_rejected_requires_reason",
                "ck_recovery_transactions_cancelled_requires_reason",
                "ck_recovery_transactions_distinct_parties",
                "ck_recovery_transactions_version_non_negative",
            ):
                batch.drop_constraint(op.f(name), type_="check")
            batch.create_check_constraint(
                op.f("ck_recovery_transactions_transactionstatus"),
                _in_clause("status", LEGACY_TRANSACTION_STATUSES),
            )
            batch.create_check_constraint(
                op.f("ck_recovery_transactions_verified_requires_evidence"),
                "status <> 'verified' OR (verified_quantity IS NOT NULL AND verified_at IS NOT NULL)",
            )
            batch.drop_index("ix_recovery_transactions_source_organization_id")
            batch.drop_index("ix_recovery_transactions_destination_organization_id")
            batch.drop_constraint(
                op.f("fk_recovery_transactions_source_organization_id_organizations"),
                type_="foreignkey",
            )
            batch.drop_constraint(
                op.f("fk_recovery_transactions_destination_organization_id_or_fe3a"),
                type_="foreignkey",
            )
            for column in (
                "source_organization_id",
                "destination_organization_id",
                "transferred_quantity",
                "transfer_reference",
                "material_identification",
                "transfer_started_at",
                "transferred_at",
                "transfer_recorded_by",
                "verified_by",
                "rejected_at",
                "rejected_by",
                "rejection_reason",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "version",
            ):
                batch.drop_column(column)

    op.drop_index("ix_status_transitions_entity", table_name="status_transitions")
    op.drop_index("ix_status_transitions_organization_id", table_name="status_transitions")
    op.drop_index("ix_status_transitions_entity_id", table_name="status_transitions")
    op.drop_index("ix_status_transitions_entity_type", table_name="status_transitions")
    op.drop_table("status_transitions")

    with op.batch_alter_table("audit_events") as batch:
        batch.drop_index("ix_audit_events_organization_id")
        batch.drop_index("ix_audit_events_actor_id")
        batch.drop_constraint(
            op.f("fk_audit_events_organization_id_organizations"), type_="foreignkey"
        )
        batch.drop_column("organization_id")
        batch.drop_column("actor_id")
        batch.drop_column("reason")
        batch.drop_column("new_state")
        batch.drop_column("previous_state")
