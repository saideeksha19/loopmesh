"""Agent execution records for the planned agentic coordination layer."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import AgentName, AgentRunStatus, enum_column_type


class AgentExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One run of a specialised agent.

    Phase 1 ships the table and the read API but does not execute agents. An
    empty table is the honest state: no fabricated AI activity exists.
    """

    __tablename__ = "agent_executions"
    __table_args__ = (
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="execution_window_valid",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR completed_at IS NOT NULL",
            name="success_requires_completion",
        ),
    )

    agent: Mapped[AgentName] = mapped_column(
        enum_column_type(AgentName), nullable=False, index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column_type(AgentRunStatus),
        nullable=False,
        default=AgentRunStatus.NOT_ENABLED,
        index=True,
    )
    objective: Mapped[str | None] = mapped_column(Text)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    model_name: Mapped[str | None] = mapped_column(String(80))
    orchestration: Mapped[str] = mapped_column(String(64), nullable=False, default="langgraph-planned")
    triggered_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AgentExecution {self.agent} {self.status}>"
