"""Recovery opportunity endpoints and the deterministic discovery trigger."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.authorization import ensure_visible_parties, resolve_requested_organization
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import Permission
from app.db.enums import (
    CompatibilityStatus,
    MaterialCategory,
    OpportunityStatus,
)
from app.db.models.opportunity import RecoveryOpportunity
from app.schemas.common import Page
from app.schemas.opportunity import (
    DiscoveryRunRequest,
    DiscoveryRunResult,
    RecoveryOpportunityRead,
)
from app.services import discovery

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _opportunity_options():
    return (
        joinedload(RecoveryOpportunity.supplier),
        joinedload(RecoveryOpportunity.consumer),
        joinedload(RecoveryOpportunity.material),
        joinedload(RecoveryOpportunity.demand),
    )


@router.get("", response_model=Page[RecoveryOpportunityRead], summary="List opportunities")
def list_opportunities(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    opportunity_status: OpportunityStatus | None = Query(None, alias="status"),
    compatibility: CompatibilityStatus | None = None,
    category: MaterialCategory | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    organization_id: UUID | None = Query(
        None, description="Filter by supplier or consumer organization"
    ),
    demo_only: bool = Query(False),
) -> Page[RecoveryOpportunityRead]:
    actor.require(Permission.OPPORTUNITY_VIEW)
    requested_org = resolve_requested_organization(
        actor, organization_id, operation="list_opportunities"
    )
    stmt = select(RecoveryOpportunity).options(*_opportunity_options())
    if opportunity_status is not None:
        stmt = stmt.where(RecoveryOpportunity.status == opportunity_status)
    if compatibility is not None:
        stmt = stmt.where(RecoveryOpportunity.compatibility_status == compatibility)
    if category is not None:
        stmt = stmt.where(RecoveryOpportunity.material.has(category=category))
    if min_score is not None:
        stmt = stmt.where(RecoveryOpportunity.compatibility_score >= min_score)
    if requested_org is not None:
        stmt = stmt.where(
            (RecoveryOpportunity.supplier_organization_id == requested_org)
            | (RecoveryOpportunity.consumer_organization_id == requested_org)
        )
    elif not actor.sees_all_records:
        if not actor.organization_ids:
            stmt = stmt.where(RecoveryOpportunity.id.is_(None))
        else:
            stmt = stmt.where(
                (RecoveryOpportunity.supplier_organization_id.in_(actor.organization_ids))
                | (RecoveryOpportunity.consumer_organization_id.in_(actor.organization_ids))
            )
    if demo_only:
        stmt = stmt.where(RecoveryOpportunity.is_demo.is_(True))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    opportunities = (
        session.scalars(
            stmt.order_by(
                RecoveryOpportunity.compatibility_score.desc(),
                RecoveryOpportunity.created_at.desc(),
            )
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .unique()
        .all()
    )
    items = [RecoveryOpportunityRead.model_validate(item) for item in opportunities]
    return build_page(RecoveryOpportunityRead, items, total, pagination)


@router.get(
    "/{opportunity_id}",
    response_model=RecoveryOpportunityRead,
    summary="Opportunity detail with rule evidence",
)
def get_opportunity(
    opportunity_id: UUID, session: DbSession, actor: ActorDep
) -> RecoveryOpportunityRead:
    actor.require(Permission.OPPORTUNITY_VIEW)
    opportunity = session.scalar(
        select(RecoveryOpportunity)
        .where(RecoveryOpportunity.id == opportunity_id)
        .options(*_opportunity_options())
    )
    if opportunity is None:
        raise NotFoundError(
            "Recovery opportunity not found.", details={"opportunity_id": str(opportunity_id)}
        )
    ensure_visible_parties(
        actor,
        {opportunity.supplier_organization_id, opportunity.consumer_organization_id},
        not_found="Recovery opportunity not found.",
    )
    return RecoveryOpportunityRead.model_validate(opportunity)


@router.post(
    "/discovery",
    response_model=DiscoveryRunResult,
    summary="Run deterministic discovery",
    description=(
        "Evaluates every open demand against every available supply stream using the "
        "deterministic compatibility rules and persists explainable opportunities. "
        "Idempotent: existing opportunities are rescored, frozen ones are preserved."
    ),
)
def run_discovery(
    actor: ActorDep,
    session: DbSession,
    payload: DiscoveryRunRequest | None = None,
) -> DiscoveryRunResult:
    actor.require(Permission.OPPORTUNITY_DISCOVER)
    request = payload or DiscoveryRunRequest()
    scope_organization_ids = None if actor.sees_all_records else set(actor.organization_ids)
    if not actor.sees_all_records and not scope_organization_ids:
        raise ForbiddenError(
            "Select an active organisation before running discovery.",
            details={"reason": "organization_context_required"},
        )
    summary = discovery.discover_opportunities(
        session,
        min_score=request.min_score,
        max_pairs=request.max_pairs,
        actor=actor.actor_id,
        actor_organization_id=actor.organization_id,
        scope_organization_ids=scope_organization_ids,
    )
    return DiscoveryRunResult.model_validate(summary.as_dict())
