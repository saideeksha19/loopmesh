"""Agent control centre endpoint.

Phase 1 reports a registry and the run-record table, and nothing else: no agent
is executing, and the API never synthesises activity.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import ActorDep, DbSession
from app.core.permissions import Permission
from app.db.enums import AgentRunStatus
from app.db.models.agent import AgentExecution
from app.schemas.agents import AgentExecutionRead, AgentRegistryResponse
from app.services.agents import registry_payload

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentRegistryResponse, summary="Agent registry and run history")
def get_agents(session: DbSession, actor: ActorDep) -> AgentRegistryResponse:
    # Registry and run history are platform operational metadata: the model has
    # no organisation column and never carries tenant business records, so there
    # is nothing to scope. A capability check is still required.
    actor.require(Permission.AGENT_VIEW)
    payload = registry_payload()
    executions = (
        session.scalars(
            select(AgentExecution).order_by(AgentExecution.created_at.desc()).limit(20)
        ).all()
    )
    running = int(
        session.scalar(
            select(func.count(AgentExecution.id)).where(
                AgentExecution.status == AgentRunStatus.RUNNING
            )
        )
        or 0
    )
    payload["running_agents"] = running
    payload["executions"] = [
        AgentExecutionRead(
            id=str(execution.id),
            agent=execution.agent.value,
            status=execution.status.value,
            objective=execution.objective,
            model_name=execution.model_name,
            started_at=execution.started_at.isoformat() if execution.started_at else None,
            completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
            error_message=execution.error_message,
        )
        for execution in executions
    ]
    return AgentRegistryResponse(**payload)
