"""Agent control-plane and optimization readiness schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AgentDescriptor(BaseModel):
    key: str
    name: str
    phase: str
    status: str
    responsibility: str
    inputs: list[str]
    outputs: list[str]
    guardrails: list[str]


class OrchestrationPlan(BaseModel):
    framework: str
    implemented: bool
    phase: str
    pattern: str
    persistence: str
    model_provider: str
    notes: str


class AgentExecutionRead(BaseModel):
    id: str
    agent: str
    status: str
    objective: str | None = None
    model_name: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class AgentRegistryResponse(BaseModel):
    agents: list[AgentDescriptor]
    orchestration: OrchestrationPlan
    executions_enabled: bool
    running_agents: int
    executions: list[AgentExecutionRead]


class OptimizationConstraint(BaseModel):
    id: str
    description: str
    enforced_by: str
    implemented: bool


class OptimizationStatus(BaseModel):
    implemented: bool
    engine: str
    phase: str
    objective: str
    inputs: list[str]
    constraints: list[OptimizationConstraint]
    outputs: list[str]
    status_note: str
    compatibility_prerequisite: str
