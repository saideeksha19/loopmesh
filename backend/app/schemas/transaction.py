"""Transaction lifecycle API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.enums import VerificationMethod


class TransactionCreate(BaseModel):
    proposal_id: UUID
    carrier_name: str | None = Field(default=None, max_length=160)
    transport_distance_km: float | None = Field(default=None, ge=0, le=20_000)
    transfer_reference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class RecordTransferRequest(BaseModel):
    transferred_quantity: float = Field(gt=0, le=1_000_000)
    transfer_reference: str = Field(
        min_length=3,
        max_length=120,
        description="Weighbridge ticket or delivery note reference.",
    )
    material_identification: str = Field(
        min_length=3, max_length=200, description="Material / batch identification."
    )
    transferred_at: datetime | None = None
    carrier_name: str | None = Field(default=None, max_length=160)
    transport_distance_km: float | None = Field(default=None, ge=0, le=20_000)
    evidence: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=0)


class VerifyTransactionRequest(BaseModel):
    verified_quantity: float = Field(gt=0, le=1_000_000)
    verification_method: VerificationMethod
    evidence_reference: str = Field(
        min_length=3,
        max_length=200,
        description="Ticket, assay or audit reference supporting the verified quantity.",
    )
    evidence: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=0)


class TransactionExceptionRequest(BaseModel):
    """Reject or cancel a transaction with a mandatory reason."""

    reason: str = Field(min_length=5, max_length=1000)
    expected_version: int | None = Field(default=None, ge=0)


class ProposalActionReference(BaseModel):
    """Minimal proposal reference returned alongside a transaction."""

    id: UUID
    status: str
