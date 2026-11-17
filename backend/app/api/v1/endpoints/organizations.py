"""Organization endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.db.enums import DemandStatus, MaterialStatus, OrganizationSector
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material
from app.db.models.organization import Organization
from app.schemas.common import Page
from app.schemas.organization import OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=Page[OrganizationRead], summary="List organizations")
def list_organizations(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    sector: OrganizationSector | None = None,
    q: str | None = Query(None, max_length=120, description="Search name, city or slug"),
    demo_only: bool = Query(False, description="Restrict to demo-seeded organizations"),
) -> Page[OrganizationRead]:
    actor.require(Permission.ORGANIZATION_VIEW)
    stmt = select(Organization)
    if sector is not None:
        stmt = stmt.where(Organization.sector == sector)
    if demo_only:
        stmt = stmt.where(Organization.is_demo.is_(True))
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Organization.name).like(pattern),
                func.lower(Organization.slug).like(pattern),
                func.lower(func.coalesce(Organization.city, "")).like(pattern),
            )
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    organizations = session.scalars(
        stmt.order_by(Organization.name.asc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()

    material_counts = dict(
        session.execute(
            select(Material.organization_id, func.count(Material.id)).group_by(
                Material.organization_id
            )
        ).all()
    )
    demand_counts = dict(
        session.execute(
            select(ResourceDemand.organization_id, func.count(ResourceDemand.id))
            .where(ResourceDemand.status == DemandStatus.OPEN)
            .group_by(ResourceDemand.organization_id)
        ).all()
    )

    items = []
    for organization in organizations:
        payload = OrganizationRead.model_validate(organization)
        payload.material_streams = int(material_counts.get(organization.id, 0))
        payload.open_demands = int(demand_counts.get(organization.id, 0))
        items.append(payload)

    return build_page(OrganizationRead, items, total, pagination)


@router.get("/{organization_id}", response_model=OrganizationRead, summary="Organization detail")
def get_organization(
    organization_id: UUID, session: DbSession, actor: ActorDep
) -> OrganizationRead:
    actor.require(Permission.ORGANIZATION_VIEW)
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise NotFoundError("Organization not found.")

    payload = OrganizationRead.model_validate(organization)
    payload.material_streams = int(
        session.scalar(
            select(func.count(Material.id)).where(
                Material.organization_id == organization_id,
                Material.status != MaterialStatus.ARCHIVED,
            )
        )
        or 0
    )
    payload.open_demands = int(
        session.scalar(
            select(func.count(ResourceDemand.id)).where(
                ResourceDemand.organization_id == organization_id,
                ResourceDemand.status == DemandStatus.OPEN,
            )
        )
        or 0
    )
    return payload
