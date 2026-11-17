"""Audit journal endpoints (read-only by construction)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.db.enums import AuditSeverity
from app.db.models.audit import AuditEvent
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.schemas.audit import AuditRecordRead
from app.schemas.common import Page

router = APIRouter(prefix="/audit", tags=["audit"])


def _visible(statement, actor: ActorDep):
    """Organisation actors only see events recorded against their organisations."""
    if actor.sees_all_records:
        return statement
    if not actor.organization_ids:
        return statement.where(AuditEvent.id.is_(None))
    return statement.where(AuditEvent.organization_id.in_(actor.organization_ids))


def _serialise(event: AuditEvent) -> AuditRecordRead:
    return AuditRecordRead(
        id=event.id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        previous_state=event.previous_state,
        new_state=event.new_state,
        actor=event.actor,
        actor_id=event.actor_id,
        organization_id=event.organization_id,
        severity=event.severity.value if hasattr(event.severity, "value") else str(event.severity),
        summary=event.summary,
        reason=event.reason,
        detail=event.detail,
        payload=dict(event.payload or {}),
        created_at=event.created_at,
    )


def _can_view_entity_timeline(session: DbSession, actor: ActorDep, entity_type: str, entity_id: UUID) -> bool:
    if actor.sees_all_records:
        return True
    org_ids = set(actor.organization_ids)
    if not org_ids:
        return False
    if entity_type in {"proposal", "recovery_proposal"}:
        proposal = session.get(RecoveryProposal, entity_id)
        if proposal is None:
            return False
        return bool(org_ids & {proposal.proposed_by_organization_id, proposal.receiving_organization_id})
    if entity_type in {"transaction", "recovery_transaction"}:
        tx = session.get(RecoveryTransaction, entity_id)
        if tx is None:
            return False
        return bool(org_ids & {tx.source_organization_id, tx.destination_organization_id})
    # For other entity types, fall back to organisation-owned events only.
    event = session.scalar(
        select(AuditEvent.id).where(
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
            AuditEvent.organization_id.in_(org_ids),
        )
    )
    return event is not None


@router.get("", response_model=Page[AuditRecordRead], summary="Query the audit journal")
def list_audit(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    entity_type: str | None = Query(None, max_length=64),
    entity_id: UUID | None = None,
    event_type: str | None = Query(None, max_length=64),
    actor_id: str | None = Query(None, max_length=120),
    severity: AuditSeverity | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> Page[AuditRecordRead]:
    actor.require(Permission.AUDIT_VIEW)
    stmt = _visible(select(AuditEvent), actor)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
        # If filtering to a specific cross-org workflow entity the actor can see,
        # include all timeline events for that entity.
        if not actor.sees_all_records and entity_type and _can_view_entity_timeline(
            session, actor, entity_type, entity_id
        ):
            stmt = select(AuditEvent).where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            if event_type:
                stmt = stmt.where(AuditEvent.event_type == event_type)
            if actor_id:
                stmt = stmt.where(AuditEvent.actor_id == actor_id)
            if severity is not None:
                stmt = stmt.where(AuditEvent.severity == severity)
            if created_from is not None:
                stmt = stmt.where(AuditEvent.created_at >= created_from)
            if created_to is not None:
                stmt = stmt.where(AuditEvent.created_at <= created_to)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if severity is not None:
        stmt = stmt.where(AuditEvent.severity == severity)
    if created_from is not None:
        stmt = stmt.where(AuditEvent.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(AuditEvent.created_at <= created_to)

    total = int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    ordering = AuditEvent.created_at.asc() if order == "asc" else AuditEvent.created_at.desc()
    events = session.scalars(
        stmt.order_by(ordering).offset(pagination.offset).limit(pagination.page_size)
    ).all()
    items = [_serialise(event) for event in events]
    return build_page(AuditRecordRead, items, total, pagination)


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=list[AuditRecordRead],
    summary="Audit timeline for one entity",
)
def entity_audit_timeline(
    entity_type: str,
    entity_id: UUID,
    session: DbSession,
    actor: ActorDep,
    limit: int = Query(200, ge=1, le=500),
) -> list[AuditRecordRead]:
    actor.require(Permission.AUDIT_VIEW)
    if not _can_view_entity_timeline(session, actor, entity_type, entity_id):
        # 404 avoids confirming entity existence across tenants.
        raise NotFoundError("Audit timeline not found.")

    if actor.sees_all_records or entity_type in {"proposal", "recovery_proposal", "transaction", "recovery_transaction"}:
        stmt = select(AuditEvent).where(
            AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id
        )
    else:
        stmt = _visible(select(AuditEvent), actor).where(
            AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id
        )
    events = session.scalars(
        stmt.order_by(AuditEvent.created_at.asc()).limit(limit)
    ).all()
    return [_serialise(event) for event in events]
