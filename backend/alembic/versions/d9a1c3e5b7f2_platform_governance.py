"""platform governance: operator MFA, two-person approvals and session state

Batch 12 adds three related pieces of state, all additive:

* platform operator MFA (encrypted TOTP secret, enrolment marker, replay
  counter, failed-attempt counter and lockout) plus hashed single-use recovery
  codes;
* session-level proof of a second factor so a refresh cannot drop MFA;
* immutable two-person approval requests for protected tenant lifecycle
  actions.

No existing column is changed and no business row is rewritten, so every
organisation, membership, session and audit record keeps its meaning. MFA is
inactive until an operator confirms enrolment; the platform gate then requires
verification on the session.

Revision ID: d9a1c3e5b7f2
Revises: b7d2e4f6a8c1
Create Date: 2026-11-15 23:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9a1c3e5b7f2"
down_revision: Union[str, None] = "b7d2e4f6a8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPROVAL_ACTIONS = ("suspend", "reactivate")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "cancelled", "expired", "executed")
MFA_METHODS = ("totp", "recovery")


def upgrade() -> None:
    # --- operator MFA on users ---------------------------------------------
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("mfa_last_counter", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "mfa_failed_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("mfa_locked_until", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "mfa_failed_attempts_non_negative", "mfa_failed_attempts >= 0"
        )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="user_recovery_code"),
    )
    op.create_index(
        "ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"]
    )
    op.create_index(
        "ix_mfa_recovery_codes_code_hash", "mfa_recovery_codes", ["code_hash"]
    )
    op.create_index(
        "ix_mfa_recovery_codes_user_used",
        "mfa_recovery_codes",
        ["user_id", "used_at"],
    )

    # --- proof of MFA on the session ---------------------------------------
    op.add_column(
        "auth_sessions",
        sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "auth_sessions",
        sa.Column("mfa_method", sa.String(length=16), nullable=True),
    )

    # --- two-person approvals ----------------------------------------------
    op.create_table(
        "platform_approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                *APPROVAL_ACTIONS,
                name="approval_action",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                *APPROVAL_STATUSES,
                name="approval_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("executed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "execution_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        sa.CheckConstraint(
            "decided_at IS NULL OR decided_at >= created_at",
            name="decision_after_creation",
        ),
        sa.CheckConstraint(
            "executed_at IS NULL OR executed_at >= created_at",
            name="execution_after_creation",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["executed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_approval_requests_organization_id",
        "platform_approval_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_platform_approval_requests_status",
        "platform_approval_requests",
        ["status"],
    )
    op.create_index(
        "ix_platform_approvals_status_expiry",
        "platform_approval_requests",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_platform_approvals_organization_status",
        "platform_approval_requests",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_platform_approvals_requester",
        "platform_approval_requests",
        ["requested_by_user_id", "created_at"],
    )


def downgrade() -> None:
    """Remove Batch 12 state.

    Operator sessions stay valid as ordinary authenticated sessions, but lose
    their second-factor proof; approvals and recovery codes are dropped, as are
    the MFA columns. This is a rollback escape hatch: an operator who had MFA
    before the downgrade will need to enrol again after re-upgrading.
    """
    op.drop_index(
        "ix_platform_approvals_requester", table_name="platform_approval_requests"
    )
    op.drop_index(
        "ix_platform_approvals_organization_status",
        table_name="platform_approval_requests",
    )
    op.drop_index(
        "ix_platform_approvals_status_expiry",
        table_name="platform_approval_requests",
    )
    op.drop_index(
        "ix_platform_approval_requests_status",
        table_name="platform_approval_requests",
    )
    op.drop_index(
        "ix_platform_approval_requests_organization_id",
        table_name="platform_approval_requests",
    )
    op.drop_table("platform_approval_requests")

    op.drop_column("auth_sessions", "mfa_method")
    op.drop_column("auth_sessions", "mfa_verified_at")

    op.drop_index("ix_mfa_recovery_codes_user_used", table_name="mfa_recovery_codes")
    op.drop_index("ix_mfa_recovery_codes_code_hash", table_name="mfa_recovery_codes")
    op.drop_index("ix_mfa_recovery_codes_user_id", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("mfa_failed_attempts_non_negative", type_="check")
        batch_op.drop_column("mfa_locked_until")
        batch_op.drop_column("mfa_failed_attempts")
        batch_op.drop_column("mfa_last_counter")
        batch_op.drop_column("mfa_enrolled_at")
        batch_op.drop_column("mfa_secret_encrypted")
