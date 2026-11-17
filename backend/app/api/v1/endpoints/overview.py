"""Overview dashboard aggregate endpoint."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import func, or_, select

from app.api.deps import ActorDep, DbSession
from app.core.permissions import Permission
from app.db.enums import (
    DemandStatus,
    MaterialStatus,
    OpportunityStatus,
    ProposalStatus,
    TransactionStatus,
)
from app.db.models.audit import AuditEvent
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.organization import Organization
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.schemas.common import AuditEventRead
from app.schemas.overview import (
    CountByKey,
    LedgerStats,
    MaterialStats,
    NetworkStats,
    OpportunityStats,
    OrganizationStats,
    OverviewStats,
)
from app.services.ledger import build_ledger

router = APIRouter(prefix="/overview", tags=["overview"])


def _visible_org_ids(actor: ActorDep) -> set | None:
    return None if actor.sees_all_records else set(actor.organization_ids)


def _visible_opportunity_stmt(actor: ActorDep):
    stmt = select(RecoveryOpportunity)
    org_ids = _visible_org_ids(actor)
    if org_ids is None:
        return stmt
    if not org_ids:
        return stmt.where(RecoveryOpportunity.id.is_(None))
    return stmt.where(
        or_(
            RecoveryOpportunity.supplier_organization_id.in_(org_ids),
            RecoveryOpportunity.consumer_organization_id.in_(org_ids),
        )
    )


@router.get("", response_model=OverviewStats, summary="Aggregated dashboard metrics")
def get_overview(session: DbSession, actor: ActorDep) -> OverviewStats:
    actor.require(Permission.DASHBOARD_VIEW)
    org_ids = _visible_org_ids(actor)

    org_stmt = select(Organization)
    if org_ids is not None:
        if not org_ids:
            org_stmt = org_stmt.where(Organization.id.is_(None))
        else:
            # Include own orgs and counterparties present in visible opportunities.
            visible_counterparty_ids = select(RecoveryOpportunity.supplier_organization_id).where(
                RecoveryOpportunity.consumer_organization_id.in_(org_ids)
            ).union(
                select(RecoveryOpportunity.consumer_organization_id).where(
                    RecoveryOpportunity.supplier_organization_id.in_(org_ids)
                )
            )
            org_stmt = org_stmt.where(
                or_(Organization.id.in_(org_ids), Organization.id.in_(visible_counterparty_ids))
            )
    organizations = session.scalars(org_stmt).all()

    material_stmt = select(Material)
    demand_stmt = select(ResourceDemand)
    if org_ids is not None:
        if not org_ids:
            material_stmt = material_stmt.where(Material.id.is_(None))
            demand_stmt = demand_stmt.where(ResourceDemand.id.is_(None))
        else:
            material_stmt = material_stmt.where(Material.organization_id.in_(org_ids))
            demand_stmt = demand_stmt.where(ResourceDemand.organization_id.in_(org_ids))
    materials = session.scalars(material_stmt).all()
    demands = session.scalars(demand_stmt).all()

    supplier_ids = {m.organization_id for m in materials}
    consumer_ids = {d.organization_id for d in demands}

    material_total = len(materials)
    material_available = sum(1 for item in materials if item.status == MaterialStatus.AVAILABLE)
    category_counts = Counter(item.category.value for item in materials)
    unit_totals: dict[str, float] = defaultdict(float)
    for item in materials:
        unit_totals[item.unit.value] += float(item.quantity_available)

    opportunities = session.scalars(_visible_opportunity_stmt(actor)).all()
    status_counts = Counter(item.status.value for item in opportunities)
    compatibility_counts = Counter(item.compatibility_status.value for item in opportunities)

    pending_stmt = select(func.count(RecoveryProposal.id)).where(
        RecoveryProposal.status.in_([ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW])
    )
    if org_ids is not None:
        if not org_ids:
            pending_stmt = pending_stmt.where(RecoveryProposal.id.is_(None))
        else:
            pending_stmt = pending_stmt.where(
                or_(
                    RecoveryProposal.proposed_by_organization_id.in_(org_ids),
                    RecoveryProposal.receiving_organization_id.in_(org_ids),
                )
            )
    pending_proposals = int(session.scalar(pending_stmt) or 0)

    ledger = build_ledger(session, actor=actor)

    confirmed_stmt = (
        select(func.count(func.distinct(RecoveryOpportunity.id)))
        .join(RecoveryProposal, RecoveryProposal.opportunity_id == RecoveryOpportunity.id)
        .join(RecoveryTransaction, RecoveryTransaction.proposal_id == RecoveryProposal.id)
        .where(RecoveryTransaction.status == TransactionStatus.VERIFIED)
    )
    if org_ids is not None:
        if not org_ids:
            confirmed_stmt = confirmed_stmt.where(RecoveryOpportunity.id.is_(None))
        else:
            confirmed_stmt = confirmed_stmt.where(
                or_(
                    RecoveryOpportunity.supplier_organization_id.in_(org_ids),
                    RecoveryOpportunity.consumer_organization_id.in_(org_ids),
                )
            )
    confirmed_links = int(session.scalar(confirmed_stmt) or 0)

    activity_stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(8)
    if org_ids is not None:
        if not org_ids:
            activity_stmt = activity_stmt.where(AuditEvent.id.is_(None))
        else:
            activity_stmt = activity_stmt.where(AuditEvent.organization_id.in_(org_ids))
    events = session.scalars(activity_stmt).all()
    activity = [
        AuditEventRead(
            id=event.id,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor=event.actor,
            severity=event.severity.value if hasattr(event.severity, "value") else str(event.severity),
            summary=event.summary,
            detail=event.detail,
            created_at=event.created_at,
            is_demo=bool(event.payload.get("demo")) if event.payload else False,
        )
        for event in events
    ]

    demo_records = sum(1 for organization in organizations if organization.is_demo)
    contains_demo = (
        demo_records > 0
        or any(material.is_demo for material in materials)
        or any(demand.is_demo for demand in demands)
    )

    return OverviewStats(
        generated_at=datetime.now(timezone.utc),
        data_mode="demo" if contains_demo else "operational",
        organizations=OrganizationStats(
            total=len(organizations),
            suppliers=len(supplier_ids),
            consumers=len(consumer_ids),
            demo_records=demo_records,
        ),
        materials=MaterialStats(
            total=material_total,
            available=material_available,
            by_category=[
                CountByKey(key=key, count=count)
                for key, count in sorted(category_counts.items(), key=lambda item: -item[1])
            ],
            by_unit=[
                {"unit": unit, "quantity": round(quantity, 3)}
                for unit, quantity in sorted(unit_totals.items(), key=lambda item: -item[1])
            ],
        ),
        opportunities=OpportunityStats(
            total=len(opportunities),
            by_status=[
                CountByKey(key=key, count=count)
                for key, count in sorted(status_counts.items(), key=lambda item: -item[1])
            ],
            by_compatibility=[
                CountByKey(key=key, count=count)
                for key, count in sorted(compatibility_counts.items(), key=lambda item: -item[1])
            ],
            pending_proposals=pending_proposals,
        ),
        ledger=LedgerStats(
            states=ledger["states"],
            stages=ledger["stages"],
            verified_recovered=ledger["verified_recovered"],
            proposed_pipeline=ledger["proposed_pipeline"],
        ),
        network=NetworkStats(
            organizations=len(organizations),
            potential_links=len(
                {
                    (
                        opportunity.supplier_organization_id,
                        opportunity.consumer_organization_id,
                        opportunity.material.category,
                    )
                    for opportunity in opportunities
                }
            ),
            confirmed_links=confirmed_links,
        ),
        recent_activity=activity,
        contains_demo_data=contains_demo,
    )


@router.get(
    "/activity",
    response_model=list[AuditEventRead],
    summary="Recent audit activity",
)
def get_activity(session: DbSession, actor: ActorDep, limit: int = 20) -> list[AuditEventRead]:
    actor.require(Permission.DASHBOARD_VIEW)
    limit = max(1, min(limit, 100))
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    org_ids = _visible_org_ids(actor)
    if org_ids is not None:
        if not org_ids:
            stmt = stmt.where(AuditEvent.id.is_(None))
        else:
            stmt = stmt.where(AuditEvent.organization_id.in_(org_ids))
    events = session.scalars(stmt).all()
    return [
        AuditEventRead(
            id=event.id,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor=event.actor,
            severity=event.severity.value if hasattr(event.severity, "value") else str(event.severity),
            summary=event.summary,
            detail=event.detail,
            created_at=event.created_at,
            is_demo=bool(event.payload.get("demo")) if event.payload else False,
        )
        for event in events
    ]
