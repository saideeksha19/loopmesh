"""Circular Impact Ledger aggregation.

Hard accounting rule: **only verified transactions contribute to recovered
material**. Nothing else — not draft proposals, not approved contracts, not
transfers awaiting verification — may appear in ``verified_recovered``.

Each record is placed in exactly one stage, so no quantity can be counted twice
and moving a record between stages can never increase the verified total.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.enums import LedgerState, ProposalStatus, TransactionStatus
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction

LEDGER_STATES: tuple[LedgerState, ...] = (
    LedgerState.PROPOSED,
    LedgerState.ACCEPTED,
    LedgerState.TRANSPORTED,
    LedgerState.VERIFIED,
)

# Granular accounting stages (Phase 2A). Legacy four-state view is derived from
# these so existing consumers keep working.
STAGES: tuple[str, ...] = (
    "draft",
    "submitted",
    "approved",
    "in_progress",
    "completed_unverified",
    "verified",
    "rejected_cancelled",
)

_STAGE_TO_STATE: dict[str, LedgerState | None] = {
    "draft": LedgerState.PROPOSED,
    "submitted": LedgerState.PROPOSED,
    "approved": LedgerState.ACCEPTED,
    "in_progress": LedgerState.ACCEPTED,
    "completed_unverified": LedgerState.TRANSPORTED,
    "verified": LedgerState.VERIFIED,
    "rejected_cancelled": None,
}

_EXCEPTION_PROPOSAL_STATES = {
    ProposalStatus.REJECTED,
    ProposalStatus.WITHDRAWN,
    ProposalStatus.CANCELLED,
    ProposalStatus.FAILED,
}

_EXCEPTION_TRANSACTION_STATES = {
    TransactionStatus.REJECTED,
    TransactionStatus.CANCELLED,
    TransactionStatus.FAILED,
}


def _stage_for(
    proposal: RecoveryProposal, transaction: RecoveryTransaction | None
) -> str:
    if transaction is not None:
        if transaction.status == TransactionStatus.VERIFIED:
            return "verified"
        if transaction.status == TransactionStatus.TRANSFERRED:
            return "completed_unverified"
        if transaction.status in _EXCEPTION_TRANSACTION_STATES:
            return "rejected_cancelled"
        return "in_progress"

    status = proposal.status
    if status == ProposalStatus.DRAFT:
        return "draft"
    if status in {ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW}:
        return "submitted"
    if status == ProposalStatus.APPROVED:
        return "approved"
    if status == ProposalStatus.IN_PROGRESS:
        return "in_progress"
    if status == ProposalStatus.COMPLETED:
        # Verified evidence is missing, so this can never count as impact.
        return "completed_unverified"
    if status in _EXCEPTION_PROPOSAL_STATES:
        return "rejected_cancelled"
    return "submitted"


def _quantity_for(
    stage: str,
    proposal: RecoveryProposal,
    transaction: RecoveryTransaction | None,
) -> float:
    if stage == "verified":
        return float(transaction.verified_quantity or 0.0) if transaction else 0.0
    if stage == "completed_unverified":
        if transaction is not None:
            return float(
                transaction.transferred_quantity
                or transaction.accepted_quantity
                or proposal.quantity
            )
        return float(proposal.quantity)
    if stage == "in_progress" and transaction is not None:
        return float(transaction.transferred_quantity or proposal.quantity)
    return float(proposal.quantity)


def _aggregate(entries: list[dict[str, Any]], *, verified: bool) -> list[dict[str, Any]]:
    """Sum either verified quantities or not-yet-recovered pipeline quantities.

    The two sets never overlap, so a record can never be counted both as
    pipeline and as recovered material.
    """
    totals: dict[str, float] = defaultdict(float)
    for entry in entries:
        if verified:
            if entry["state"] == LedgerState.VERIFIED.value:
                totals[entry["unit"]] += float(entry["verified_quantity"] or 0.0)
        elif entry["state"] != LedgerState.VERIFIED.value:
            totals[entry["unit"]] += float(entry["quantity"])
    return [
        {"unit": unit, "quantity": round(quantity, 3)}
        for unit, quantity in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def build_ledger(session: Session, actor: Any | None = None) -> dict[str, Any]:
    """Assemble the ledger report consumed by ``/api/v1/ledger``."""
    stmt = (
        select(RecoveryProposal)
        .options(
            joinedload(RecoveryProposal.transaction),
            joinedload(RecoveryProposal.opportunity).joinedload(RecoveryOpportunity.material),
            joinedload(RecoveryProposal.opportunity).joinedload(RecoveryOpportunity.supplier),
            joinedload(RecoveryProposal.opportunity).joinedload(RecoveryOpportunity.consumer),
        )
        .order_by(RecoveryProposal.created_at.desc())
    )
    if actor is not None and not getattr(actor, "sees_all_records", False):
        org_ids = set(getattr(actor, "organization_ids", set()) or [])
        if not org_ids:
            stmt = stmt.where(RecoveryProposal.id.is_(None))
        else:
            stmt = stmt.where(
                (RecoveryProposal.proposed_by_organization_id.in_(org_ids))
                | (RecoveryProposal.receiving_organization_id.in_(org_ids))
            )
    proposals = session.scalars(stmt).unique().all()

    entries: list[dict[str, Any]] = []
    stage_entries: list[dict[str, Any]] = []

    for proposal in proposals:
        opportunity = proposal.opportunity
        material = opportunity.material if opportunity else None
        supplier = opportunity.supplier if opportunity else None
        consumer = opportunity.consumer if opportunity else None
        transaction: RecoveryTransaction | None = proposal.transaction

        stage = _stage_for(proposal, transaction)
        state = _STAGE_TO_STATE[stage]
        quantity = _quantity_for(stage, proposal, transaction)
        transaction_updated = (
            (transaction.updated_at or transaction.created_at) if transaction else None
        )

        record = {
            "proposal_id": str(proposal.id),
            "transaction_id": str(transaction.id) if transaction else None,
            "opportunity_id": str(proposal.opportunity_id),
            "material_name": material.name if material else "Unknown material",
            "material_reference": material.reference_code if material else None,
            "category": material.category.value if material else "other",
            "supplier": supplier.name if supplier else "Unknown supplier",
            "consumer": consumer.name if consumer else "Unknown consumer",
            "stage": stage,
            "state": state.value if state else "rejected_cancelled",
            "status": (
                transaction.status.value if transaction is not None else proposal.status.value
            ),
            "quantity": round(quantity, 3),
            "unit": proposal.unit.value,
            "verified_quantity": (
                round(float(transaction.verified_quantity), 3)
                if transaction and transaction.verified_quantity is not None
                else None
            ),
            "is_verified": stage == "verified",
            "verification_method": (
                transaction.verification_method.value
                if transaction and transaction.verification_method
                else None
            ),
            "verified_at": (
                transaction.verified_at.isoformat()
                if transaction and transaction.verified_at
                else None
            ),
            "transport_distance_km": (
                float(transaction.transport_distance_km)
                if transaction and transaction.transport_distance_km is not None
                else None
            ),
            "proposed_at": proposal.created_at.isoformat() if proposal.created_at else None,
            "last_updated": transaction_updated.isoformat() if transaction_updated else None,
            "is_demo": proposal.is_demo,
        }
        stage_entries.append(record)
        # Terminal records stay in the stage report but out of the pipeline view.
        if state is not None:
            entries.append(record)

    state_order = {state.value: index for index, state in enumerate(LEDGER_STATES)}
    entries.sort(key=lambda entry: (state_order.get(entry["state"], 99), entry["proposed_at"] or ""))

    states: list[dict[str, Any]] = []
    for state in LEDGER_STATES:
        state_entries = [entry for entry in entries if entry["state"] == state.value]
        totals: dict[str, float] = defaultdict(float)
        for entry in state_entries:
            totals[entry["unit"]] += float(entry["quantity"])
        states.append(
            {
                "state": state.value,
                "count": len(state_entries),
                "quantity_by_unit": [
                    {"unit": unit, "quantity": round(quantity, 3)}
                    for unit, quantity in sorted(
                        totals.items(), key=lambda item: item[1], reverse=True
                    )
                ],
                "counted_as_impact": state == LedgerState.VERIFIED,
            }
        )

    stages: list[dict[str, Any]] = []
    for stage in STAGES:
        stage_rows = [entry for entry in stage_entries if entry["stage"] == stage]
        totals: dict[str, float] = defaultdict(float)
        for entry in stage_rows:
            totals[entry["unit"]] += float(entry["quantity"])
        stages.append(
            {
                "stage": stage,
                "count": len(stage_rows),
                "quantity_by_unit": [
                    {"unit": unit, "quantity": round(quantity, 3)}
                    for unit, quantity in sorted(
                        totals.items(), key=lambda item: item[1], reverse=True
                    )
                ],
                "counted_as_impact": stage == "verified",
            }
        )

    return {
        "states": states,
        "stages": stages,
        "entries": entries,
        "verified_recovered": _aggregate(entries, verified=True),
        "proposed_pipeline": _aggregate(entries, verified=False),
        "accounting_rule": (
            "Only quantities from verified transactions are counted as recovered material. "
            "Draft, submitted, approved, in-progress and transferred quantities remain pipeline."
        ),
        "contains_demo_data": any(entry["is_demo"] for entry in stage_entries),
    }
