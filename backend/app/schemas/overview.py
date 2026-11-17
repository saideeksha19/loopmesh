"""Overview dashboard aggregate schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import AuditEventRead, UnitQuantity
from app.schemas.ledger import LedgerStageSummary, LedgerStateSummary


class CountByKey(BaseModel):
    key: str
    count: int


class OrganizationStats(BaseModel):
    total: int
    suppliers: int
    consumers: int
    demo_records: int


class MaterialStats(BaseModel):
    total: int
    available: int
    by_category: list[CountByKey]
    by_unit: list[UnitQuantity]


class OpportunityStats(BaseModel):
    total: int
    by_status: list[CountByKey]
    by_compatibility: list[CountByKey]
    pending_proposals: int


class LedgerStats(BaseModel):
    states: list[LedgerStateSummary]
    stages: list[LedgerStageSummary]
    verified_recovered: list[UnitQuantity]
    proposed_pipeline: list[UnitQuantity]


class NetworkStats(BaseModel):
    organizations: int
    potential_links: int
    confirmed_links: int


class OverviewStats(BaseModel):
    generated_at: datetime
    data_mode: str
    organizations: OrganizationStats
    materials: MaterialStats
    opportunities: OpportunityStats
    ledger: LedgerStats
    network: NetworkStats
    recent_activity: list[AuditEventRead]
    contains_demo_data: bool
