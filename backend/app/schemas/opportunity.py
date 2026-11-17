"""Recovery opportunity schemas, including rule-level evidence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from app.db.enums import (
    CompatibilityStatus,
    MaterialCategory,
    MaterialUnit,
    OpportunityStatus,
)
from app.schemas.common import ApiModel
from app.schemas.organization import OrganizationSummary


class CompatibilityRuleRead(ApiModel):
    rule_id: str
    label: str
    status: str
    severity: str
    detail: str
    observed: str
    required: str
    weight: int


class OpportunityMaterial(ApiModel):
    id: UUID
    reference_code: str
    name: str
    category: MaterialCategory


class OpportunityDemand(ApiModel):
    id: UUID
    title: str
    min_quantity: float
    max_quantity: float | None = None


class RecoveryOpportunityRead(ApiModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supplier: OrganizationSummary
    consumer: OrganizationSummary
    material: OpportunityMaterial
    demand: OpportunityDemand
    compatibility_status: CompatibilityStatus
    compatibility_score: int
    compatibility_rules: list[CompatibilityRuleRead] = []
    score_breakdown: dict = {}
    match_quantity: float
    unit: MaterialUnit
    distance_km: float | None = None
    transport_required: bool
    status: OpportunityStatus
    discovery_method: str
    is_demo: bool
    created_at: datetime


class DiscoveryRunRequest(ApiModel):
    min_score: int | None = None
    max_pairs: int | None = None


class DiscoveryRunResult(ApiModel):
    pairs_evaluated: int
    opportunities_created: int
    opportunities_updated: int
    skipped_incompatible: int
    skipped_below_threshold: int
    skipped_frozen: int
    truncated: bool
    created_ids: list[UUID]
    min_score: int
