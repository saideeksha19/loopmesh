"""Resource demand endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.authorization import ensure_read_organization, resolve_requested_organization
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.db.enums import DemandStatus, MaterialCategory, MaterialUnit
from app.db.models.demand import ResourceDemand
from app.schemas.common import Page
from app.schemas.demand import ResourceDemandRead

router = APIRouter(prefix="/demands", tags=["demands"])


@router.get("", response_model=Page[ResourceDemandRead], summary="List resource demands")
def list_demands(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    demand_status: DemandStatus | None = Query(None, alias="status"),
    category: MaterialCategory | None = None,
    unit: MaterialUnit | None = None,
    organization_id: UUID | None = None,
) -> Page[ResourceDemandRead]:
    actor.require(Permission.DEMAND_VIEW)
    requested_org = resolve_requested_organization(
        actor, organization_id, operation="list_demands"
    )
    stmt = select(ResourceDemand).options(joinedload(ResourceDemand.organization))
    if demand_status is not None:
        stmt = stmt.where(ResourceDemand.status == demand_status)
    if category is not None:
        stmt = stmt.where(ResourceDemand.category == category)
    if unit is not None:
        stmt = stmt.where(ResourceDemand.unit == unit)
    if requested_org is not None:
        stmt = stmt.where(ResourceDemand.organization_id == requested_org)
    elif not actor.sees_all_records:
        if not actor.organization_ids:
            stmt = stmt.where(ResourceDemand.organization_id.is_(None))
        else:
            stmt = stmt.where(ResourceDemand.organization_id.in_(actor.organization_ids))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    demands = (
        session.scalars(
            stmt.order_by(ResourceDemand.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .unique()
        .all()
    )
    items = [ResourceDemandRead.model_validate(demand) for demand in demands]
    return build_page(ResourceDemandRead, items, total, pagination)


@router.get("/{demand_id}", response_model=ResourceDemandRead, summary="Demand detail")
def get_demand(demand_id: UUID, session: DbSession, actor: ActorDep) -> ResourceDemandRead:
    actor.require(Permission.DEMAND_VIEW)
    demand = session.scalar(
        select(ResourceDemand)
        .where(ResourceDemand.id == demand_id)
        .options(joinedload(ResourceDemand.organization))
    )
    if demand is None:
        raise NotFoundError("Resource demand not found.", details={"demand_id": str(demand_id)})
    ensure_read_organization(
        actor, demand.organization_id, not_found="Resource demand not found."
    )
    return ResourceDemandRead.model_validate(demand)
