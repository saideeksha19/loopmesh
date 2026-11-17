"""Requirement-based resource discovery.

The pass is deterministic: same inputs and same policy ⇒ same opportunities.
It evaluates every open demand against every available supply stream, applies
the rule engine, and persists explainable opportunities. No LLM is involved.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.enums import (
    CompatibilityStatus,
    DemandStatus,
    MaterialStatus,
    OpportunityStatus,
)
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material
from app.db.models.opportunity import RecoveryOpportunity
from app.services import audit
from app.services.compatibility import evaluate_compatibility
from app.services.geo import haversine_km

logger = logging.getLogger("loopmesh.discovery")

FROZEN_STATUSES = frozenset(
    {OpportunityStatus.CONVERTED, OpportunityStatus.REJECTED, OpportunityStatus.EXPIRED}
)


@dataclass(slots=True)
class DiscoverySummary:
    pairs_evaluated: int = 0
    opportunities_created: int = 0
    opportunities_updated: int = 0
    skipped_incompatible: int = 0
    skipped_below_threshold: int = 0
    skipped_frozen: int = 0
    truncated: bool = False
    created_ids: list[uuid.UUID] = field(default_factory=list)
    min_score: int = 0

    def as_dict(self) -> dict:
        return {
            "pairs_evaluated": self.pairs_evaluated,
            "opportunities_created": self.opportunities_created,
            "opportunities_updated": self.opportunities_updated,
            "skipped_incompatible": self.skipped_incompatible,
            "skipped_below_threshold": self.skipped_below_threshold,
            "skipped_frozen": self.skipped_frozen,
            "truncated": self.truncated,
            "created_ids": [str(oid) for oid in self.created_ids],
            "min_score": self.min_score,
        }


def discover_opportunities(
    session: Session,
    *,
    min_score: int | None = None,
    max_pairs: int | None = None,
    actor: str = "system",
    actor_organization_id: uuid.UUID | None = None,
    scope_organization_ids: set[uuid.UUID] | None = None,
) -> DiscoverySummary:
    """Evaluate supply/demand pairs and persist new or refreshed opportunities."""
    threshold = settings.discovery_min_score if min_score is None else min_score
    pair_cap = settings.discovery_max_pairs if max_pairs is None else max_pairs
    summary = DiscoverySummary(min_score=threshold)

    material_stmt = (
        select(Material)
        .where(Material.status == MaterialStatus.AVAILABLE)
        .options(joinedload(Material.organization), joinedload(Material.specification))
        .order_by(Material.created_at.asc())
    )
    demand_stmt = (
        select(ResourceDemand)
        .where(ResourceDemand.status == DemandStatus.OPEN)
        .options(joinedload(ResourceDemand.organization))
        .order_by(ResourceDemand.created_at.asc())
    )
    materials = session.scalars(material_stmt).all()
    demands = session.scalars(demand_stmt).all()

    # Pair selection is the tenant-isolation boundary for discovery.
    #
    # A platform-scope principal may sweep the whole network. An organisation
    # actor may only evaluate pairs in which one side is its own organisation:
    # its supply against open demand, and its demand against available supply.
    # It can therefore never create or rescore an opportunity that belongs
    # exclusively to two other tenants, and the raw counterparty records are
    # never returned - only the derived opportunity, which both participants
    # are entitled to see.
    pairs: list[tuple[Material, ResourceDemand]] = []
    if scope_organization_ids is None:
        pairs = [(material, demand) for material in materials for demand in demands]
    else:
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        for material in materials:
            for demand in demands:
                if (
                    material.organization_id not in scope_organization_ids
                    and demand.organization_id not in scope_organization_ids
                ):
                    continue
                key = (material.id, demand.id)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append((material, demand))

    existing = {
        (opportunity.material_id, opportunity.resource_demand_id): opportunity
        for opportunity in session.scalars(select(RecoveryOpportunity)).all()
    }

    for material, demand in pairs:
        supplier = material.organization
        consumer = demand.organization
        if supplier.id == consumer.id:
            continue
        if summary.pairs_evaluated >= pair_cap:
            summary.truncated = True
            break

        summary.pairs_evaluated += 1
        distance = haversine_km(
            supplier.latitude,
            supplier.longitude,
            consumer.latitude,
            consumer.longitude,
        )
        assessment = evaluate_compatibility(material, demand, distance_km=distance)

        key = (material.id, demand.id)
        current = existing.get(key)

        if assessment.status == CompatibilityStatus.INCOMPATIBLE:
            summary.skipped_incompatible += 1
            continue
        if assessment.score < threshold:
            summary.skipped_below_threshold += 1
            continue
        if current is not None and current.status in FROZEN_STATUSES:
            summary.skipped_frozen += 1
            continue

        if current is None:
            opportunity = RecoveryOpportunity(
                material_id=material.id,
                resource_demand_id=demand.id,
                supplier_organization_id=supplier.id,
                consumer_organization_id=consumer.id,
                compatibility_status=assessment.status,
                compatibility_score=assessment.score,
                compatibility_rules=assessment.rules_as_dicts(),
                score_breakdown={
                    "policy": "deterministic_rules_v1",
                    "rule_count": len(assessment.rules),
                    "blocking_failures": list(assessment.blocking_rule_ids),
                },
                match_quantity=assessment.match_quantity,
                unit=assessment.unit,
                distance_km=assessment.distance_km,
                transport_required=(assessment.distance_km or 0) > 0,
                status=OpportunityStatus.IDENTIFIED,
                discovery_method="deterministic_rule_match",
                is_demo=material.is_demo or demand.is_demo,
            )
            session.add(opportunity)
            session.flush()  # assign the UUID before recording it
            existing[key] = opportunity
            summary.opportunities_created += 1
            summary.created_ids.append(opportunity.id)
        else:
            current.compatibility_status = assessment.status
            current.compatibility_score = assessment.score
            current.compatibility_rules = assessment.rules_as_dicts()
            current.match_quantity = assessment.match_quantity
            current.unit = assessment.unit
            current.distance_km = assessment.distance_km
            summary.opportunities_updated += 1

        if summary.truncated:
            logger.warning(
                "discovery truncated at the configured pair cap",
                extra={"pair_cap": pair_cap},
            )
            break

    session.flush()
    audit.record_event(
        session,
        event_type="discovery.run",
        entity_type="recovery_opportunity",
        summary=(
            f"Deterministic discovery evaluated {summary.pairs_evaluated} supply/demand pairs and "
            f"created {summary.opportunities_created} opportunities."
        ),
        actor=actor,
        actor_id=actor if actor not in {"system", "api"} else None,
        organization_id=actor_organization_id,
        payload=summary.as_dict(),
    )
    session.commit()
    return summary
