"""Recovery transaction endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.api.v1.endpoints.proposals import transaction_detail
from app.db.enums import TransactionStatus
from app.db.models.proposal import RecoveryTransaction
from app.schemas.common import Page
from app.schemas.proposal import TransactionDetail, TransitionRead
from app.schemas.transaction import (
    RecordTransferRequest,
    TransactionCreate,
    TransactionExceptionRequest,
    VerifyTransactionRequest,
)
from app.services.workflow import WorkflowService, transaction_list_statement

router = APIRouter(prefix="/transactions", tags=["transactions"])

SORTS = {
    "created_at": RecoveryTransaction.created_at,
    "updated_at": RecoveryTransaction.updated_at,
    "status": RecoveryTransaction.status,
}


def _summary(service: WorkflowService, transaction: RecoveryTransaction) -> TransactionDetail:
    """List rows reuse the detail shape minus history/evidence weight."""
    detail = transaction_detail(service, transaction)
    detail.history = []
    return detail


@router.post(
    "",
    response_model=TransactionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a transaction from an approved proposal",
)
def create_transaction(
    payload: TransactionCreate, session: DbSession, actor: ActorDep
) -> TransactionDetail:
    service = WorkflowService(session, actor)
    transaction = service.create_transaction(
        proposal_id=payload.proposal_id,
        carrier_name=payload.carrier_name,
        transport_distance_km=payload.transport_distance_km,
        transfer_reference=payload.transfer_reference,
        notes=payload.notes,
    )
    return transaction_detail(service, service.get_transaction(transaction.id))


@router.get("", response_model=Page[TransactionDetail], summary="List transactions")
def list_transactions(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    transaction_status: TransactionStatus | None = Query(None, alias="status"),
    proposal_id: UUID | None = None,
    organization_id: UUID | None = None,
    demo_only: bool = Query(False),
    sort: str = Query("created_at", pattern="^(created_at|updated_at|status)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> Page[TransactionDetail]:
    service = WorkflowService(session, actor)
    stmt = service.scope_transactions(
        transaction_list_statement(), organization_id=organization_id
    )
    if transaction_status is not None:
        stmt = stmt.where(RecoveryTransaction.status == transaction_status)
    if proposal_id is not None:
        stmt = stmt.where(RecoveryTransaction.proposal_id == proposal_id)
    if demo_only:
        stmt = stmt.where(RecoveryTransaction.is_demo.is_(True))

    total = int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    column = SORTS[sort]
    ordering = column.asc() if order == "asc" else column.desc()
    transactions = (
        session.scalars(
            stmt.order_by(ordering).offset(pagination.offset).limit(pagination.page_size)
        )
        .unique()
        .all()
    )
    items = [_summary(service, transaction) for transaction in transactions]
    return build_page(TransactionDetail, items, total, pagination)


@router.get("/{transaction_id}", response_model=TransactionDetail, summary="Transaction detail")
def get_transaction(
    transaction_id: UUID, session: DbSession, actor: ActorDep
) -> TransactionDetail:
    service = WorkflowService(session, actor)
    transaction = service.get_transaction(transaction_id)
    return transaction_detail(service, transaction)


@router.post(
    "/{transaction_id}/record-transfer",
    response_model=TransactionDetail,
    summary="Record the physical transfer (quantity, material, parties, dates, evidence)",
)
def record_transfer(
    transaction_id: UUID,
    payload: RecordTransferRequest,
    session: DbSession,
    actor: ActorDep,
) -> TransactionDetail:
    service = WorkflowService(session, actor)
    service.record_transfer(
        transaction_id,
        transferred_quantity=payload.transferred_quantity,
        transfer_reference=payload.transfer_reference,
        material_identification=payload.material_identification,
        transferred_at=payload.transferred_at,
        carrier_name=payload.carrier_name,
        transport_distance_km=payload.transport_distance_km,
        evidence=payload.evidence,
        notes=payload.notes,
        expected_version=payload.expected_version,
    )
    return transaction_detail(service, service.get_transaction(transaction_id))


@router.post(
    "/{transaction_id}/verify",
    response_model=TransactionDetail,
    summary="Verify a transfer with evidence (authorized actor, non-recorder)",
)
def verify_transaction(
    transaction_id: UUID,
    payload: VerifyTransactionRequest,
    session: DbSession,
    actor: ActorDep,
) -> TransactionDetail:
    service = WorkflowService(session, actor)
    service.verify_transaction(
        transaction_id,
        verified_quantity=payload.verified_quantity,
        verification_method=payload.verification_method,
        evidence_reference=payload.evidence_reference,
        evidence=payload.evidence,
        notes=payload.notes,
        expected_version=payload.expected_version,
    )
    return transaction_detail(service, service.get_transaction(transaction_id))


@router.post(
    "/{transaction_id}/reject",
    response_model=TransactionDetail,
    summary="Reject a transaction (reason required)",
)
def reject_transaction(
    transaction_id: UUID,
    payload: TransactionExceptionRequest,
    session: DbSession,
    actor: ActorDep,
) -> TransactionDetail:
    service = WorkflowService(session, actor)
    service.reject_transaction(
        transaction_id, reason=payload.reason, expected_version=payload.expected_version
    )
    return transaction_detail(service, service.get_transaction(transaction_id))


@router.post(
    "/{transaction_id}/cancel",
    response_model=TransactionDetail,
    summary="Cancel a transaction before verification (reason required)",
)
def cancel_transaction(
    transaction_id: UUID,
    payload: TransactionExceptionRequest,
    session: DbSession,
    actor: ActorDep,
) -> TransactionDetail:
    service = WorkflowService(session, actor)
    service.cancel_transaction(
        transaction_id, reason=payload.reason, expected_version=payload.expected_version
    )
    return transaction_detail(service, service.get_transaction(transaction_id))


@router.get(
    "/{transaction_id}/history",
    response_model=list[TransitionRead],
    summary="Transaction transition history",
)
def transaction_history(
    transaction_id: UUID, session: DbSession, actor: ActorDep
) -> list[TransitionRead]:
    service = WorkflowService(session, actor)
    service.get_transaction(transaction_id)
    return [
        TransitionRead.model_validate(row)
        for row in service.transaction_history(transaction_id)
    ]
