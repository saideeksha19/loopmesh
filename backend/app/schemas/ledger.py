"""Circular Impact Ledger schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import UnitQuantity


class LedgerStateSummary(BaseModel):
    """Legacy four-state view (kept for existing consumers)."""

    state: str
    count: int
    quantity_by_unit: list[UnitQuantity]
    counted_as_impact: bool


class LedgerStageSummary(BaseModel):
    """Phase 2A accounting stage: exactly one per record, never double counted."""

    stage: str
    count: int
    quantity_by_unit: list[UnitQuantity]
    counted_as_impact: bool


class LedgerEntry(BaseModel):
    proposal_id: str
    transaction_id: str | None = None
    opportunity_id: str
    material_name: str
    material_reference: str | None = None
    category: str
    supplier: str
    consumer: str
    stage: str
    state: str
    status: str
    quantity: float
    unit: str
    verified_quantity: float | None = None
    is_verified: bool
    verification_method: str | None = None
    verified_at: str | None = None
    transport_distance_km: float | None = None
    proposed_at: str | None = None
    last_updated: str | None = None
    is_demo: bool


class LedgerReport(BaseModel):
    states: list[LedgerStateSummary]
    stages: list[LedgerStageSummary]
    entries: list[LedgerEntry]
    verified_recovered: list[UnitQuantity]
    # Quantities in any non-verified stage. Never impact.
    proposed_pipeline: list[UnitQuantity]
    accounting_rule: str
    contains_demo_data: bool
