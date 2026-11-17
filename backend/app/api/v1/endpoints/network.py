"""Resource network graph endpoint."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import ActorDep, DbSession
from app.core.permissions import Permission
from app.db.enums import DemandStatus, TransactionStatus
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.organization import Organization
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.schemas.network import NetworkEdge, NetworkGraph, NetworkNode, NetworkSummary

router = APIRouter(prefix="/network", tags=["network"])


@router.get("", response_model=NetworkGraph, summary="Resource network graph")
def get_network(session: DbSession, actor: ActorDep) -> NetworkGraph:
    actor.require(Permission.NETWORK_VIEW)
    org_ids = None if actor.sees_all_records else set(actor.organization_ids)

    opp_stmt = select(RecoveryOpportunity).options(joinedload(RecoveryOpportunity.material))
    if org_ids is not None:
        if not org_ids:
            opp_stmt = opp_stmt.where(RecoveryOpportunity.id.is_(None))
        else:
            opp_stmt = opp_stmt.where(
                or_(
                    RecoveryOpportunity.supplier_organization_id.in_(org_ids),
                    RecoveryOpportunity.consumer_organization_id.in_(org_ids),
                )
            )
    opportunities = session.scalars(opp_stmt).unique().all()

    if org_ids is None:
        organizations = session.scalars(
            select(Organization).order_by(Organization.name.asc())
        ).all()
    else:
        visible_org_id_set: set = set(org_ids)
        for opportunity in opportunities:
            visible_org_id_set.add(opportunity.supplier_organization_id)
            visible_org_id_set.add(opportunity.consumer_organization_id)
        if visible_org_id_set:
            organizations = session.scalars(
                select(Organization)
                .where(Organization.id.in_(visible_org_id_set))
                .order_by(Organization.name.asc())
            ).all()
        else:
            organizations = []

    material_counts_stmt = select(Material.organization_id, func.count(Material.id)).group_by(
        Material.organization_id
    )
    demand_counts_stmt = (
        select(ResourceDemand.organization_id, func.count(ResourceDemand.id))
        .where(ResourceDemand.status == DemandStatus.OPEN)
        .group_by(ResourceDemand.organization_id)
    )
    if org_ids is not None:
        if not org_ids:
            material_counts_stmt = material_counts_stmt.where(Material.id.is_(None))
            demand_counts_stmt = demand_counts_stmt.where(ResourceDemand.id.is_(None))
        else:
            material_counts_stmt = material_counts_stmt.where(Material.organization_id.in_(org_ids))
            demand_counts_stmt = demand_counts_stmt.where(ResourceDemand.organization_id.in_(org_ids))

    material_counts = dict(session.execute(material_counts_stmt).all())
    demand_counts = dict(session.execute(demand_counts_stmt).all())

    verified_counts: dict[tuple, int] = defaultdict(int)
    verified_stmt = (
        select(
            RecoveryOpportunity.supplier_organization_id,
            RecoveryOpportunity.consumer_organization_id,
            Material.category,
            func.count(RecoveryTransaction.id),
        )
        .join(RecoveryProposal, RecoveryProposal.opportunity_id == RecoveryOpportunity.id)
        .join(RecoveryTransaction, RecoveryTransaction.proposal_id == RecoveryProposal.id)
        .join(Material, Material.id == RecoveryOpportunity.material_id)
        .where(RecoveryTransaction.status == TransactionStatus.VERIFIED)
        .group_by(
            RecoveryOpportunity.supplier_organization_id,
            RecoveryOpportunity.consumer_organization_id,
            Material.category,
        )
    )
    if org_ids is not None:
        if not org_ids:
            verified_stmt = verified_stmt.where(RecoveryOpportunity.id.is_(None))
        else:
            verified_stmt = verified_stmt.where(
                or_(
                    RecoveryOpportunity.supplier_organization_id.in_(org_ids),
                    RecoveryOpportunity.consumer_organization_id.in_(org_ids),
                )
            )
    for supplier_id, consumer_id, category, count in session.execute(verified_stmt).all():
        verified_counts[(supplier_id, consumer_id, category.value)] = int(count)

    edge_groups: dict[tuple, dict] = {}
    for opportunity in opportunities:
        category = opportunity.material.category.value
        key = (opportunity.supplier_organization_id, opportunity.consumer_organization_id, category)
        group = edge_groups.setdefault(
            key,
            {
                "opportunity_count": 0,
                "quantities": defaultdict(float),
                "status": "potential",
            },
        )
        group["opportunity_count"] += 1
        group["quantities"][opportunity.unit.value] += float(opportunity.match_quantity or 0)

    edges: list[NetworkEdge] = []
    for (supplier_id, consumer_id, category), group in edge_groups.items():
        confirmed = verified_counts.get((supplier_id, consumer_id, category), 0)
        edges.append(
            NetworkEdge(
                id=f"{supplier_id}->{consumer_id}:{category}",
                source=supplier_id,
                target=consumer_id,
                category=category,
                status="confirmed" if confirmed else "potential",
                opportunity_count=group["opportunity_count"],
                confirmed_transactions=confirmed,
                quantity_by_unit=[
                    {"unit": unit, "quantity": round(quantity, 3)}
                    for unit, quantity in sorted(group["quantities"].items())
                ],
            )
        )
    edges.sort(key=lambda edge: (edge.status != "confirmed", -edge.opportunity_count, edge.category))

    outbound: dict = defaultdict(int)
    inbound: dict = defaultdict(int)
    for edge in edges:
        outbound[edge.source] += 1
        inbound[edge.target] += 1

    nodes = [
        NetworkNode(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            sector=organization.sector.value,
            city=organization.city,
            country=organization.country,
            is_demo=organization.is_demo,
            material_streams=int(material_counts.get(organization.id, 0)),
            open_demands=int(demand_counts.get(organization.id, 0)),
            outbound_links=outbound.get(organization.id, 0),
            inbound_links=inbound.get(organization.id, 0),
        )
        for organization in organizations
    ]

    confirmed_links = sum(1 for edge in edges if edge.status == "confirmed")
    return NetworkGraph(
        nodes=nodes,
        edges=edges,
        summary=NetworkSummary(
            organizations=len(nodes),
            potential_links=len(edges),
            confirmed_links=confirmed_links,
            total_material_streams=sum(material_counts.values()),
            unlinked_organizations=sum(
                1 for node in nodes if node.outbound_links == 0 and node.inbound_links == 0
            ),
        ),
        legend={
            "potential": "Modelled link from deterministic screening — no physical transfer recorded.",
            "confirmed": "At least one recovery transaction has been verified for this link.",
        },
    )
