"""Recovery proposal endpoints.

Every state change goes through :class:`~app.services.workflow.WorkflowService`;
there is deliberately no generic status update endpoint.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.exceptions import NotFoundError
from app.db.enums import ProposalStatus
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.schemas.common import Page
from app.schemas.proposal import (
    ProposalCreate,
    ProposalDetail,
    ProposalSummary,
    ProposalTransitionRequest,
    TransactionDetail,
    TransitionRead,
)
from app.services.workflow import WorkflowService, proposal_list_statement

router = APIRouter(prefix="/proposals", tags=["proposals"])

SORTS = {
    "created_at": RecoveryProposal.created_at,
    "updated_at": RecoveryProposal.updated_at,
    "status": RecoveryProposal.status,
    "quantity": RecoveryProposal.quantity,
}


def _summary(service: WorkflowService, proposal: RecoveryProposal) -> ProposalSummary:
    opportunity = proposal.opportunity
    material = opportunity.material if opportunity else None
    supplier = opportunity.supplier if opportunity else None
    consumer = opportunity.consumer if opportunity else None
    transaction = proposal.transaction
    return ProposalSummary(
        id=proposal.id,
        status=proposal.status.value,
        quantity=float(proposal.quantity),
        unit=proposal.unit.value,
        price_per_unit=(
            float(proposal.price_per_unit) if proposal.price_per_unit is not None else None
        ),
        currency=proposal.currency,
        compatibility_status=proposal.compatibility_status.value,
        version=proposal.version,
        is_demo=proposal.is_demo,
        opportunity_id=proposal.opportunity_id,
        proposed_by_organization_id=proposal.proposed_by_organization_id,
        receiving_organization_id=proposal.receiving_organization_id,
        material_name=material.name if material else None,
        material_reference=material.reference_code if material else None,
        supplier_name=supplier.name if supplier else None,
        consumer_name=consumer.name if consumer else None,
        transaction_id=transaction.id if transaction else None,
        transaction_status=transaction.status.value if transaction else None,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
        approved_at=proposal.approved_at,
        completed_at=proposal.completed_at,
        available_actions=service.available_actions(proposal),
    )


def transaction_detail(
    service: WorkflowService, transaction: RecoveryTransaction
) -> TransactionDetail:
    source = transaction.source_organization
    destination = transaction.destination_organization
    opportunity = transaction.proposal.opportunity if transaction.proposal else None
    material = opportunity.material if opportunity else None
    return TransactionDetail(
        id=transaction.id,
        proposal_id=transaction.proposal_id,
        status=transaction.status.value,
        accepted_quantity=(
            float(transaction.accepted_quantity)
            if transaction.accepted_quantity is not None
            else None
        ),
        transferred_quantity=(
            float(transaction.transferred_quantity)
            if transaction.transferred_quantity is not None
            else None
        ),
        verified_quantity=(
            float(transaction.verified_quantity)
            if transaction.verified_quantity is not None
            else None
        ),
        unit=transaction.unit.value,
        carrier_name=transaction.carrier_name,
        transport_distance_km=(
            float(transaction.transport_distance_km)
            if transaction.transport_distance_km is not None
            else None
        ),
        transfer_reference=transaction.transfer_reference,
        material_identification=transaction.material_identification,
        transferred_at=transaction.transferred_at,
        verified_at=transaction.verified_at,
        verification_method=(
            transaction.verification_method.value
            if transaction.verification_method
            else None
        ),
        source_organization_id=transaction.source_organization_id,
        destination_organization_id=transaction.destination_organization_id,
        source_organization_name=source.name if source else None,
        destination_organization_name=destination.name if destination else None,
        material_name=material.name if material else None,
        material_reference=material.reference_code if material else None,
        is_demo=transaction.is_demo,
        version=transaction.version,
        created_at=transaction.created_at,
        available_actions=service.available_actions(transaction),
        evidence=dict(transaction.evidence or {}),
        notes=transaction.notes,
        transfer_recorded_by=transaction.transfer_recorded_by,
        verified_by=transaction.verified_by,
        rejection_reason=transaction.rejection_reason,
        cancelled_by=transaction.cancelled_by,
        cancellation_reason=transaction.cancellation_reason,
        history=[
            TransitionRead.model_validate(row)
            for row in service.transaction_history(transaction.id)
        ],
    )


def _detail(
    session: DbSession, service: WorkflowService, proposal_id: UUID
) -> ProposalDetail:
    proposal = (
        session.scalars(
            proposal_list_statement().where(RecoveryProposal.id == proposal_id)
        )
        .unique()
        .one_or_none()
    )
    if proposal is None:
        raise NotFoundError("Proposal not found.")
    summary = _summary(service, proposal)
    return ProposalDetail(
        **summary.model_dump(),
        terms=dict(proposal.terms or {}),
        valid_until=proposal.valid_until,
        notes=proposal.notes,
        submitted_by=proposal.submitted_by,
        reviewed_by=proposal.reviewed_by,
        reviewed_at=proposal.reviewed_at,
        approved_by=proposal.approved_by,
        approval_reference=proposal.approval_reference,
        approval_evidence=dict(proposal.approval_evidence or {}),
        rejected_by=proposal.rejected_by,
        rejection_reason=proposal.rejection_reason,
        withdrawn_by=proposal.withdrawn_by,
        withdrawn_at=proposal.withdrawn_at,
        started_at=proposal.started_at,
        cancelled_at=proposal.cancelled_at,
        cancellation_reason=proposal.cancellation_reason,
        failed_at=proposal.failed_at,
        failure_reason=proposal.failure_reason,
        transaction=(
            transaction_detail(service, proposal.transaction)
            if proposal.transaction is not None
            else None
        ),
        history=[
            TransitionRead.model_validate(row)
            for row in service.proposal_history(proposal.id)
        ],
    )


def _run_action(
    session: DbSession,
    actor: ActorDep,
    proposal_id: UUID,
    action: str,
    payload: ProposalTransitionRequest,
) -> ProposalDetail:
    service = WorkflowService(session, actor)
    service.apply_proposal_action(
        proposal_id,
        action=action,
        reason=payload.reason,
        approval_reference=payload.approval_reference,
        evidence=payload.evidence,
        expected_version=payload.expected_version,
    )
    return _detail(session, service, proposal_id)


@router.post(
    "",
    response_model=ProposalDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft proposal from a screened opportunity",
)
def create_proposal(
    payload: ProposalCreate, session: DbSession, actor: ActorDep
) -> ProposalDetail:
    service = WorkflowService(session, actor)
    proposal = service.create_proposal(
        opportunity_id=payload.opportunity_id,
        quantity=payload.quantity,
        price_per_unit=payload.price_per_unit,
        currency=payload.currency,
        terms=payload.terms,
        valid_until=payload.valid_until,
        notes=payload.notes,
    )
    return _detail(session, service, proposal.id)


@router.get("", response_model=Page[ProposalSummary], summary="List proposals")
def list_proposals(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    proposal_status: ProposalStatus | None = Query(None, alias="status"),
    opportunity_id: UUID | None = None,
    organization_id: UUID | None = None,
    demo_only: bool = Query(False),
    sort: str = Query("created_at", pattern="^(created_at|updated_at|status|quantity)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> Page[ProposalSummary]:
    service = WorkflowService(session, actor)
    stmt = service.scope_proposals(proposal_list_statement(), organization_id=organization_id)
    if proposal_status is not None:
        stmt = stmt.where(RecoveryProposal.status == proposal_status)
    if opportunity_id is not None:
        stmt = stmt.where(RecoveryProposal.opportunity_id == opportunity_id)
    if demo_only:
        stmt = stmt.where(RecoveryProposal.is_demo.is_(True))

    total = int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    column = SORTS[sort]
    ordering = column.asc() if order == "asc" else column.desc()
    proposals = (
        session.scalars(
            stmt.order_by(ordering).offset(pagination.offset).limit(pagination.page_size)
        )
        .unique()
        .all()
    )
    items = [_summary(service, proposal) for proposal in proposals]
    return build_page(ProposalSummary, items, total, pagination)


@router.get("/{proposal_id}", response_model=ProposalDetail, summary="Proposal detail")
def get_proposal(proposal_id: UUID, session: DbSession, actor: ActorDep) -> ProposalDetail:
    service = WorkflowService(session, actor)
    service.get_proposal(proposal_id)
    return _detail(session, service, proposal_id)


@router.post("/{proposal_id}/submit", response_model=ProposalDetail, summary="Submit a draft")
def submit_proposal(
    proposal_id: UUID,
    payload: ProposalTransitionRequest,
    session: DbSession,
    actor: ActorDep,
) -> ProposalDetail:
    return _run_action(session, actor, proposal_id, "submit", payload)


@router.post(
    "/{proposal_id}/review", response_model=ProposalDetail, summary="Move to under review"
)
def review_proposal(
    proposal_id: UUID,
    payload: ProposalTransitionRequest,
    session: DbSession,
    actor: ActorDep,
) -> ProposalDetail:
    return _run_action(session, actor, proposal_id, "review", payload)


@router.post(
    "/{proposal_id}/approve",
    response_model=ProposalDetail,
    summary="Approve a reviewed proposal (evidence required)",
)
def approve_proposal(
    proposal_id: UUID,
    payload: ProposalTransitionRequest,
    session: DbSession,
    actor: ActorDep,
) -> ProposalDetail:
    return _run_action(session, actor, proposal_id, "approve", payload)


@router.post(
    "/{proposal_id}/reject",
    response_model=ProposalDetail,
    summary="Reject a proposal (reason required)",
)
def reject_proposal(
    proposal_id: UUID,
    payload: ProposalTransitionRequest,
    session: DbSession,
    actor: ActorDep,
) -> ProposalDetail:
    return _run_action(session, actor, proposal_id, "reject", payload)


@router.post(
    "/{proposal_id}/withdraw",
    response_model=ProposalDetail,
    summary="Withdraw a proposal before it is decided",
)
def withdraw_proposal(
    proposal_id: UUID,
    payload: ProposalTransitionRequest,
    session: DbSession,
    actor: ActorDep,
) -> ProposalDetail:
    return _run_action(session, actor, proposal_id, "withdraw", payload)


@router.get(
    "/{proposal_id}/history",
    response_model=list[TransitionRead],
    summary="Proposal transition history",
)
def proposal_history(
    proposal_id: UUID, session: DbSession, actor: ActorDep
) -> list[TransitionRead]:
    service = WorkflowService(session, actor)
    service.get_proposal(proposal_id)
    return [TransitionRead.model_validate(row) for row in service.proposal_history(proposal_id)]
