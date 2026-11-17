"""Optimization centre endpoint.

The optimisation engine is a later-phase deliverable. This endpoint publishes
the exact contract it will satisfy so the frontend can be honest about status.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActorDep
from app.schemas.agents import OptimizationConstraint, OptimizationStatus

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("", response_model=OptimizationStatus, summary="Optimization engine status and contract")
def get_optimization_status(actor: ActorDep) -> OptimizationStatus:
    _ = actor
    return OptimizationStatus(
        implemented=False,
        engine="Google OR-Tools CP-SAT",
        phase="Phase 3",
        objective=(
            "Maximise verified recoverable mass while minimising transport distance and "
            "unmet demand, subject to hard engineering constraints."
        ),
        inputs=[
            "feasible opportunities with compatibility scores",
            "supply quantities per stream",
            "demand intake minimum, maximum and frequency",
            "transport distance and vehicle capacity",
            "availability windows and processing requirements",
        ],
        constraints=[
            OptimizationConstraint(
                id="ALLOC-01",
                description="A supply stream cannot be allocated beyond its available quantity.",
                enforced_by="planned CP-SAT quantity constraint",
                implemented=False,
            ),
            OptimizationConstraint(
                id="ALLOC-02",
                description="A demand cannot receive more than its maximum intake per period.",
                enforced_by="planned CP-SAT intake constraint",
                implemented=False,
            ),
            OptimizationConstraint(
                id="COMPAT-01",
                description=(
                    "Only opportunities that passed deterministic compatibility may be allocated; "
                    "AI cannot relax this filter."
                ),
                enforced_by="deterministic pre-filter (rule engine)",
                implemented=False,
            ),
            OptimizationConstraint(
                id="LOG-01",
                description="Transport radius and vehicle capacity limit each lane.",
                enforced_by="planned capacity constraint",
                implemented=False,
            ),
            OptimizationConstraint(
                id="TIME-01",
                description="Availability and delivery windows must overlap for an allocation.",
                enforced_by="planned interval constraint",
                implemented=False,
            ),
        ],
        outputs=[
            "allocation plan per supply/demand pair",
            "binding constraints and infeasibility explanation",
            "unmet demand and idle supply report",
        ],
        status_note=(
            "Not implemented in Phase 1. Opportunities are deterministic matches, not an "
            "optimised allocation plan."
        ),
        compatibility_prerequisite=(
            "Only opportunities with compatibility status 'compatible' or 'conditional' are "
            "eligible; 'unverified' and 'incompatible' opportunities are excluded."
        ),
    )
