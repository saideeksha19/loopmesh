"""Planned agent registry.

Phase 1 deliberately contains **no agent runtime**. This module describes the
specialists that will be orchestrated with LangGraph in a later phase, together
with their boundaries. Nothing here executes, and no run records are created.
"""

from __future__ import annotations

from typing import Any

PLANNED_AGENTS: tuple[dict[str, Any], ...] = (
    {
        "key": "material_analyst",
        "name": "Material Analyst",
        "phase": "Phase 2",
        "status": "not_enabled",
        "responsibility": (
            "Normalise structured material descriptions, propose missing specification "
            "fields for human confirmation and flag data-quality gaps."
        ),
        "inputs": ["material profile", "CSV import batch", "uploaded specification document"],
        "outputs": ["normalised profile draft", "data-quality findings"],
        "guardrails": [
            "Cannot write measurements without a declared source.",
            "Cannot mark a material available; a human publishes it.",
        ],
    },
    {
        "key": "resource_scout",
        "name": "Resource Scout",
        "phase": "Phase 2",
        "status": "not_enabled",
        "responsibility": (
            "Explain and rank the candidate links produced by the deterministic discovery "
            "pass, and surface missing data that blocks a confident match."
        ),
        "inputs": ["open demands", "available streams", "opportunity evidence"],
        "outputs": ["ranked shortlist", "evidence requests"],
        "guardrails": [
            "May only rank opportunities that already exist in the database.",
            "Cannot invent organisations or quantities.",
        ],
    },
    {
        "key": "compatibility_assessor",
        "name": "Compatibility Assessor",
        "phase": "Phase 2",
        "status": "not_enabled",
        "responsibility": (
            "Translate deterministic rule outcomes and technical documents into a "
            "reviewer-facing brief, and recommend which evidence is missing."
        ),
        "inputs": ["rule results", "material specification", "demand thresholds"],
        "outputs": ["review brief", "evidence checklist"],
        "guardrails": [
            "Never overrides a blocking rule outcome.",
            "Cannot declare a material safe or compatible on its own.",
        ],
    },
    {
        "key": "optimization_planner",
        "name": "Optimization Planner",
        "phase": "Phase 3",
        "status": "not_enabled",
        "responsibility": (
            "Formulate allocation scenarios for the OR-Tools solver, explain binding "
            "constraints and summarise trade-offs between feasible plans."
        ),
        "inputs": ["feasible opportunities", "capacity and transport limits"],
        "outputs": ["solver scenario", "constraint narrative"],
        "guardrails": [
            "Solver output is authoritative; the agent cannot relax constraints.",
            "Every allocation must reference persisted capacities.",
        ],
    },
    {
        "key": "recovery_coordinator",
        "name": "Recovery Coordinator",
        "phase": "Phase 3",
        "status": "not_enabled",
        "responsibility": (
            "Draft coordination steps for accepted recoveries (documentation checklist, "
            "scheduling prompts) for human approval."
        ),
        "inputs": ["accepted proposal", "transaction state"],
        "outputs": ["coordination checklist", "draft messages"],
        "guardrails": [
            "Cannot change transaction state or verify quantities.",
            "Cannot contact external parties without explicit human approval.",
        ],
    },
)

ORCHESTRATION_PLAN: dict[str, Any] = {
    "framework": "LangGraph",
    "implemented": False,
    "phase": "Phase 2",
    "pattern": "supervisor with specialist sub-agents and a human approval gate",
    "persistence": "agent_executions table (created in Phase 1)",
    "model_provider": "Gemini (server-side only)",
    "notes": (
        "The graph, tools and prompt contracts are intentionally not implemented yet. "
        "Phase 1 only establishes the registry, the run-record schema and the guardrails."
    ),
}


def registry_payload() -> dict[str, Any]:
    return {
        "agents": [dict(agent) for agent in PLANNED_AGENTS],
        "orchestration": dict(ORCHESTRATION_PLAN),
        "executions_enabled": False,
        "running_agents": 0,
    }
