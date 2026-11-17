"""reconcile status transition actor_role check

Revision ID: c3e5f7a9b1d2
Revises: 9b7f2c4e1a30
Create Date: 2026-11-15 17:40:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c3e5f7a9b1d2"
down_revision = "9b7f2c4e1a30"
branch_labels = None
depends_on = None


ACTOR_ROLES = (
    "admin",
    "org_admin",
    "coordinator",
    "reviewer",
    "approver",
    "auditor",
    "viewer",
)


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _sqlite_table_sql() -> str:
    bind = op.get_bind()
    row = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='status_transitions'"
    ).fetchone()
    return (row[0] or "") if row else ""


def upgrade() -> None:
    if _is_sqlite():
        sql = _sqlite_table_sql()
        # Fresh databases built from the corrected full chain already have the
        # reconciled names and vocabulary; avoid a pointless rebuild.
        if (
            "CONSTRAINT ck_status_transitions_actorrole CHECK" in sql
            and "CONSTRAINT ck_status_transitions_transitionentity CHECK" in sql
            and "'org_admin'" in sql
            and "ck_status_transitions_ck_status_transitions_actorrole" not in sql
        ):
            return

        bind = op.get_bind()
        # Manual table rebuild: SQLite cannot ALTER a CHECK constraint, and
        # batch-mode name resolution interacts badly with historically
        # double-prefixed constraint names. The rebuilt table is identical to
        # the current one except for the two reconciled CHECK constraints.
        # SQLite DDL auto-commits; run the rebuild as explicit statements.
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
        bind.exec_driver_sql(
            """
            CREATE TABLE _alembic_tmp_status_transitions (
                id CHAR(32) NOT NULL,
                entity_type VARCHAR(32) NOT NULL,
                entity_id CHAR(32) NOT NULL,
                action VARCHAR(32) NOT NULL,
                from_state VARCHAR(32) NOT NULL,
                to_state VARCHAR(32) NOT NULL,
                actor_id VARCHAR(120) NOT NULL,
                actor_role VARCHAR(32) NOT NULL,
                organization_id CHAR(32),
                reason TEXT,
                context JSON NOT NULL,
                occurred_at DATETIME NOT NULL,
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                CONSTRAINT pk_status_transitions PRIMARY KEY (id),
                CONSTRAINT ck_status_transitions_transitionentity CHECK (entity_type IN ('proposal', 'transaction')),
                CONSTRAINT ck_status_transitions_actorrole CHECK (actor_role IN ('admin', 'org_admin', 'coordinator', 'reviewer', 'approver', 'auditor', 'viewer')),
                CONSTRAINT fk_status_transitions_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE SET NULL
            )
            """
        )
        bind.exec_driver_sql(
            """
            INSERT INTO _alembic_tmp_status_transitions (
                id, entity_type, entity_id, action, from_state, to_state,
                actor_id, actor_role, organization_id, reason, context,
                occurred_at, created_at, updated_at
            )
            SELECT
                id, entity_type, entity_id, action, from_state, to_state,
                actor_id, actor_role, organization_id, reason, context,
                occurred_at, created_at, updated_at
            FROM status_transitions
            """
        )
        bind.exec_driver_sql("DROP TABLE status_transitions")
        bind.exec_driver_sql(
            "ALTER TABLE _alembic_tmp_status_transitions RENAME TO status_transitions"
        )
        bind.exec_driver_sql(
            "CREATE INDEX ix_status_transitions_entity_type ON status_transitions (entity_type)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX ix_status_transitions_entity_id ON status_transitions (entity_id)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX ix_status_transitions_organization_id ON status_transitions (organization_id)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX ix_status_transitions_entity ON status_transitions (entity_type, entity_id, occurred_at)"
        )
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")
        fk_violations = bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(f"foreign key violations after rebuild: {fk_violations}")
    else:
        bind = op.get_bind()
        rows = bind.execute(
            sa.text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'status_transitions'::regclass AND contype = 'c'"
            )
        ).fetchall()
        names = {row[0]: row[1] for row in rows}
        actor_current = None
        for candidate in (
            "ck_status_transitions_actorrole",
            "ck_status_transitions_ck_status_transitions_actorrole",
        ):
            if candidate in names:
                actor_current = candidate
                break
        if actor_current is None:
            return
        # Fresh databases built from the corrected chain already have the
        # reconciled name and vocabulary.
        if actor_current == "ck_status_transitions_actorrole" and "org_admin" in (
            names[actor_current] or ""
        ):
            return
        op.drop_constraint(actor_current, "status_transitions", type_="check")
        op.create_check_constraint(
            op.f("ck_status_transitions_actorrole"),
            "status_transitions",
            _in_clause("actor_role", ACTOR_ROLES),
        )


def downgrade() -> None:
    # Restoring the narrower vocabulary would reject any status transition recorded
    # with actor_role='org_admin'. Downgrade is intentionally unsupported for this
    # forward-only reconciliation; raise to prevent silent data-invalidating rollback.
    raise RuntimeError(
        "Irreversible: downgrading would reject existing/valid org_admin transitions."
    )
