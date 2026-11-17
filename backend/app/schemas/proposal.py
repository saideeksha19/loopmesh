"""Proposal lifecycle API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ApiModel


class ProposalCreate(BaseModel):
    opportunity_id: UUID
    quantity: float = Field(gt=0, le=1_000_000, description="Proposed transfer quantity")
    price_per_unit: float | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    terms: dict[str, Any] = Field(default_factory=dict)
    valid_until: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ProposalTransitionRequest(BaseModel):
    """Body accepted by every proposal action endpoint."""

    reason: str | None = Field(default=None, max_length=1000)
    approval_reference: str | None = Field(
        default=None,
        max_length=200,
        description="Evidence reference for approval decisions (required to approve).",
    )
    evidence: dict[str, Any] | None = Field(
        default=None, description="Structured approval evidence; never contains secrets."
    )
    expected_version: int | None = Field(
        default=None,
        ge=0,
        description="Optimistic concurrency token from the record you are acting on.",
    )


class TransitionRead(ApiModel):
    id: UUID
    action: str
    from_state: str
    to_state: str
    actor_id: str
    actor_role: str
    organization_id: UUID | None = None
    reason: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class TransactionSummary(BaseModel):
    id: UUID
    proposal_id: UUID
    status: str
    accepted_quantity: float | None = None
    transferred_quantity: float | None = None
    verified_quantity: float | None = None
    unit: str
    carrier_name: str | None = None
    transport_distance_km: float | None = None
    transfer_reference: str | None = None
    material_identification: str | None = None
    transferred_at: datetime | None = None
    verified_at: datetime | None = None
    verification_method: str | None = None
    source_organization_id: UUID
    destination_organization_id: UUID
    source_organization_name: str | None = None
    destination_organization_name: str | None = None
    material_name: str | None = None
    material_reference: str | None = None
    is_demo: bool
    version: int
    created_at: datetime
    available_actions: list[str] = Field(default_factory=list)


class TransactionDetail(TransactionSummary):
    evidence: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    transfer_recorded_by: str | None = None
    verified_by: str | None = None
    rejection_reason: str | None = None
    cancelled_by: str | None = None
    cancellation_reason: str | None = None
    history: list[TransitionRead] = Field(default_factory=list)


class ProposalSummary(BaseModel):
    id: UUID
    status: str
    quantity: float
    unit: str
    price_per_unit: float | None = None
    currency: str
    compatibility_status: str
    version: int
    is_demo: bool
    opportunity_id: UUID
    proposed_by_organization_id: UUID
    receiving_organization_id: UUID
    material_name: str | None = None
    material_reference: str | None = None
    supplier_name: str | None = None
    consumer_name: str | None = None
    transaction_id: UUID | None = None
    transaction_status: str | None = None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    available_actions: list[str] = Field(default_factory=list)


class ProposalDetail(ProposalSummary):
    terms: dict[str, Any] = Field(default_factory=dict)
    valid_until: datetime | None = None
    notes: str | None = None
    submitted_by: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    approved_by: str | None = None
    approval_reference: str | None = None
    approval_evidence: dict[str, Any] = Field(default_factory=dict)
    rejected_by: str | None = None
    rejection_reason: str | None = None
    withdrawn_by: str | None = None
    withdrawn_at: datetime | None = None
    started_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    transaction: TransactionDetail | None = None
    history: list[TransitionRead] = Field(default_factory=list)


class ActorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actor_id: str
    display_name: str
    role: str
    organization_id: UUID | None = None
    organization_slug: str | None = None
    organization_name: str | None = None
    is_development: bool
