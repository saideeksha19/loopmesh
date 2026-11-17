"""organisation lifecycle status for platform administration

Batch 11 needs an explicit tenant state so a platform operator can suspend and
reactivate an organisation. Phase 1 had no such column: an organisation simply
existed.

The change is additive and forward-only in intent: ``status`` is added with the
server default ``active``, so every existing row keeps its current behaviour and
no membership, session, invitation or business record is touched. ``suspended_at``
records when a suspension began so the platform console and the audit journal
agree on the timestamp.

Revision ID: b7d2e4f6a8c1
Revises: c3e5f7a9b1d2
Create Date: 2026-11-15 20:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e4f6a8c1"
down_revision: Union[str, None] = "c3e5f7a9b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORGANIZATION_STATUSES = ("active", "suspended")


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "status",
            sa.Enum(
                *ORGANIZATION_STATUSES,
                name="organization_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"])


def downgrade() -> None:
    """Drop the lifecycle columns.

    Safe for a rollback of Batch 11: the platform console is the only reader, and
    dropping the columns restores the exact pre-Batch-11 organisation schema.
    Business rows and memberships are untouched. A tenant that was suspended
    before the rollback becomes reachable again, which is why the downgrade is
    documented as an escape hatch rather than an operational procedure.
    """
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_column("organizations", "suspended_at")
    op.drop_column("organizations", "status")
