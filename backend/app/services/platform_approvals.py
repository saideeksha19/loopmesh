"""Two-person approval workflow for protected platform operations.

Security properties are enforced here, not in the UI:

* the requester can never decide their own request;
* a decision is bound to the immutable target/action/reason of the request;
* only an approved, unexpired request can execute, exactly once;
* execution and both audit events share one transaction;
* state drift (the tenant changed underneath the approval) invalidates it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.actors import ActorContext
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.enums import (
    ActorRole,
    ApprovalAction,
    ApprovalStatus,
    AuditSeverity,
    OrganizationStatus,
)
from app.db.models.organization import Organization
from app.db.models.platform_approval import PlatformApprovalRequest
from app.services import audit as audit_service


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


TARGET_STATUS: dict[ApprovalAction, OrganizationStatus] = {
    ApprovalAction.SUSPEND: OrganizationStatus.SUSPENDED,
    ApprovalAction.REACTIVATE: OrganizationStatus.ACTIVE,
}

SOURCE_STATUS: dict[ApprovalAction, OrganizationStatus] = {
    ApprovalAction.SUSPEND: OrganizationStatus.ACTIVE,
    ApprovalAction.REACTIVATE: OrganizationStatus.SUSPENDED,
}


def _actor_label(actor: ActorContext) -> str:
    return actor.email or actor.display_name or actor.actor_id


def _audit(
    db: Session,
    approval: PlatformApprovalRequest,
    *,
    event_type: str,
    actor: ActorContext,
    summary: str,
    severity: AuditSeverity = AuditSeverity.INFO,
    reason: str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
) -> None:
    audit_service.record_event(
        db,
        event_type=event_type,
        entity_type="platform_approval",
        entity_id=approval.id,
        organization_id=approval.organization_id,
        actor=_actor_label(actor),
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        severity=severity,
        summary=summary,
        reason=reason,
        previous_state=previous_state,
        new_state=new_state,
        payload={
            "approval_id": str(approval.id),
            "action": approval.action.value,
            "organization_id": str(approval.organization_id),
            "requested_by_user_id": str(approval.requested_by_user_id),
            "expires_at": as_utc(approval.expires_at).isoformat()
            if approval.expires_at
            else None,
        },
    )


def _mark_expired(db: Session, approval: PlatformApprovalRequest, *, now: datetime) -> bool:
    """Expire one pending request that has passed its deadline."""
    if approval.status != ApprovalStatus.PENDING:
        return False
    expires = as_utc(approval.expires_at)
    if expires is None or expires > now:
        return False
    approval.status = ApprovalStatus.EXPIRED
    approval.decision_reason = "expired"
    _audit(
        db,
        approval,
        event_type="platform.approval.expired",
        actor=ActorContext(
            actor_id="system",
            display_name="system",
            role=ActorRole.ADMIN,
        ),
        summary="Platform approval expired before a decision.",
        severity=AuditSeverity.WARNING,
        previous_state="pending",
        new_state="expired",
    )
    return True


def expire_pending(db: Session, *, now: datetime | None = None) -> int:
    """Expire every pending request past its deadline, auditing each one."""
    moment = now or utcnow()
    rows = db.scalars(
        select(PlatformApprovalRequest)
        .where(
            PlatformApprovalRequest.status == ApprovalStatus.PENDING,
            PlatformApprovalRequest.expires_at <= moment,
        )
    ).all()
    for row in rows:
        _mark_expired(db, row, now=moment)
    return len(rows)


def get_approval(db: Session, approval_id: uuid.UUID) -> PlatformApprovalRequest:
    approval = db.get(PlatformApprovalRequest, approval_id)
    if approval is None:
        raise NotFoundError("Approval request not found.")
    return approval


def create_approval(
    db: Session,
    *,
    actor: ActorContext,
    organization_id: uuid.UUID,
    action: ApprovalAction,
    reason: str | None,
    now: datetime | None = None,
) -> PlatformApprovalRequest:
    moment = now or utcnow()
    organisation = db.get(Organization, organization_id, with_for_update=True)
    if organisation is None:
        raise NotFoundError("Organization not found.")

    if organisation.status != SOURCE_STATUS[action]:
        raise ConflictError(
            f"This organisation is already {organisation.status.value}.",
            details={
                "reason": "invalid_state_transition",
                "current_status": organisation.status.value,
                "requested_status": TARGET_STATUS[action].value,
            },
        )

    text = (reason or "").strip() or None
    if action == ApprovalAction.SUSPEND and (text is None or len(text) < 8):
        raise ValidationError(
            "Suspending an organisation requires a written reason of at least 8 characters.",
            details={"field": "reason", "reason": "reason_required"},
        )

    existing = db.scalar(
        select(PlatformApprovalRequest).where(
            PlatformApprovalRequest.organization_id == organization_id,
            PlatformApprovalRequest.status.in_(
                [ApprovalStatus.PENDING, ApprovalStatus.APPROVED]
            ),
        )
    )
    if existing is not None:
        raise ConflictError(
            "An open approval request already exists for this organisation.",
            details={
                "reason": "approval_exists",
                "approval_id": str(existing.id),
                "status": existing.status.value,
            },
        )

    approval = PlatformApprovalRequest(
        organization_id=organization_id,
        action=action,
        reason=text,
        status=ApprovalStatus.PENDING,
        requested_by_user_id=actor.user_id or uuid.UUID(int=0),
        expires_at=moment
        + timedelta(minutes=settings.platform_approval_ttl_minutes),
    )
    db.add(approval)
    db.flush()
    _audit(
        db,
        approval,
        event_type="platform.approval.requested",
        actor=actor,
        summary="Two-person approval requested for a tenant lifecycle change.",
        previous_state=organisation.status.value,
        new_state=TARGET_STATUS[action].value,
        reason=text,
    )
    return approval


def _locked_pending(
    db: Session, approval_id: uuid.UUID, *, now: datetime
) -> PlatformApprovalRequest:
    approval = db.scalar(
        select(PlatformApprovalRequest)
        .where(PlatformApprovalRequest.id == approval_id)
        .with_for_update()
    )
    if approval is None:
        raise NotFoundError("Approval request not found.")
    if _mark_expired(db, approval, now=now):
        db.commit()
        raise ConflictError(
            "This approval request has expired.",
            details={"reason": "approval_expired", "approval_id": str(approval.id)},
        )
    return approval


def approve(
    db: Session,
    *,
    actor: ActorContext,
    approval_id: uuid.UUID,
    reason: str | None = None,
    now: datetime | None = None,
) -> PlatformApprovalRequest:
    moment = now or utcnow()
    approval = _locked_pending(db, approval_id, now=moment)
    if approval.status != ApprovalStatus.PENDING:
        raise ConflictError(
            "This approval request is no longer pending.",
            details={
                "reason": "approval_not_pending",
                "status": approval.status.value,
            },
        )
    if approval.requested_by_user_id == actor.user_id:
        raise ForbiddenError(
            "The operator who requested an approval cannot approve it.",
            details={"reason": "self_approval_forbidden"},
        )

    approval.status = ApprovalStatus.APPROVED
    approval.decided_by_user_id = actor.user_id
    approval.decided_at = moment
    approval.decision_reason = (reason or "").strip() or None
    _audit(
        db,
        approval,
        event_type="platform.approval.approved",
        actor=actor,
        summary="Platform approval approved by a second operator.",
        previous_state="pending",
        new_state="approved",
        reason=approval.decision_reason,
    )
    return approval


def reject(
    db: Session,
    *,
    actor: ActorContext,
    approval_id: uuid.UUID,
    reason: str | None = None,
    now: datetime | None = None,
) -> PlatformApprovalRequest:
    moment = now or utcnow()
    approval = _locked_pending(db, approval_id, now=moment)
    if approval.status != ApprovalStatus.PENDING:
        raise ConflictError(
            "This approval request is no longer pending.",
            details={"reason": "approval_not_pending", "status": approval.status.value},
        )
    if approval.requested_by_user_id == actor.user_id:
        raise ForbiddenError(
            "The operator who requested an approval cannot decide it.",
            details={"reason": "self_approval_forbidden"},
        )
    text = (reason or "").strip() or None
    if text is not None and len(text) < 4:
        raise ValidationError(
            "Give a slightly longer rejection reason or leave it empty.",
            details={"field": "reason", "reason": "reason_too_short"},
        )

    approval.status = ApprovalStatus.REJECTED
    approval.decided_by_user_id = actor.user_id
    approval.decided_at = moment
    approval.decision_reason = text
    _audit(
        db,
        approval,
        event_type="platform.approval.rejected",
        actor=actor,
        summary="Platform approval rejected.",
        severity=AuditSeverity.WARNING,
        previous_state="pending",
        new_state="rejected",
        reason=text,
    )
    return approval


def cancel(
    db: Session,
    *,
    actor: ActorContext,
    approval_id: uuid.UUID,
    now: datetime | None = None,
) -> PlatformApprovalRequest:
    moment = now or utcnow()
    approval = _locked_pending(db, approval_id, now=moment)
    if approval.status not in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
        raise ConflictError(
            "This approval request can no longer be cancelled.",
            details={"reason": "approval_not_cancellable", "status": approval.status.value},
        )
    if approval.requested_by_user_id != actor.user_id:
        raise ForbiddenError(
            "Only the requesting operator can cancel this approval.",
            details={"reason": "requester_only"},
        )
    previous = approval.status.value
    approval.status = ApprovalStatus.CANCELLED
    approval.decision_reason = "cancelled_by_requester"
    _audit(
        db,
        approval,
        event_type="platform.approval.cancelled",
        actor=actor,
        summary="Platform approval cancelled by its requester.",
        previous_state=previous,
        new_state="cancelled",
    )
    return approval


def execute(
    db: Session,
    *,
    actor: ActorContext,
    approval_id: uuid.UUID,
    expected_action: ApprovalAction | None = None,
    expected_organization_id: uuid.UUID | None = None,
    expected_reason: str | None = None,
    now: datetime | None = None,
) -> tuple[PlatformApprovalRequest, Organization]:
    """Execute an approved request atomically, exactly once."""
    moment = now or utcnow()
    approval = _locked_pending(db, approval_id, now=moment)

    if approval.status == ApprovalStatus.EXECUTED:
        raise ConflictError(
            "This approval request has already been executed.",
            details={"reason": "approval_already_executed", "status": "executed"},
        )
    if approval.status != ApprovalStatus.APPROVED:
        raise ConflictError(
            "Only an approved request can be executed.",
            details={"reason": "approval_not_approved", "status": approval.status.value},
        )

    # Binding checks: the execution must match the approved tenant, action and
    # reason. They run before anything is mutated.
    if (
        expected_organization_id is not None
        and expected_organization_id != approval.organization_id
    ):
        raise ConflictError(
            "This approval request belongs to a different organisation.",
            details={"reason": "approval_mismatch", "field": "organization_id"},
        )
    if expected_action is not None and expected_action != approval.action:
        raise ConflictError(
            "The requested action does not match the approved request.",
            details={"reason": "approval_mismatch", "field": "action"},
        )
    approved_reason = (approval.reason or "").strip() or None
    supplied_reason = (expected_reason or "").strip() or None
    if supplied_reason is not None and supplied_reason != approved_reason:
        raise ConflictError(
            "The supplied reason does not match the approved request.",
            details={"reason": "approval_mismatch", "field": "reason"},
        )

    organisation = db.scalar(
        select(Organization)
        .where(Organization.id == approval.organization_id)
        .with_for_update()
    )
    if organisation is None:
        raise NotFoundError("Organization not found.")

    if organisation.status != SOURCE_STATUS[approval.action]:
        approval.status = ApprovalStatus.CANCELLED
        approval.decision_reason = "target_state_changed"
        _audit(
            db,
            approval,
            event_type="platform.approval.invalidated",
            actor=actor,
            summary="Approval invalidated because the tenant state changed before execution.",
            severity=AuditSeverity.WARNING,
            previous_state="approved",
            new_state="cancelled",
            reason="target_state_changed",
        )
        db.commit()
        raise ConflictError(
            "The organisation changed before execution; this approval is no longer valid.",
            details={"reason": "approval_invalidated"},
        )

    target = TARGET_STATUS[approval.action]
    previous = organisation.status
    organisation.status = target
    organisation.suspended_at = (
        moment if target == OrganizationStatus.SUSPENDED else None
    )

    claim = db.execute(
        update(PlatformApprovalRequest)
        .where(
            PlatformApprovalRequest.id == approval.id,
            PlatformApprovalRequest.status == ApprovalStatus.APPROVED,
        )
        .values(
            status=ApprovalStatus.EXECUTED,
            executed_at=moment,
            executed_by_user_id=actor.user_id,
            execution_attempts=PlatformApprovalRequest.execution_attempts + 1,
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    if claim != 1:  # pragma: no cover - row lock makes this unreachable on PG
        db.rollback()
        raise ConflictError(
            "This approval request was executed by another operator.",
            details={"reason": "approval_already_executed"},
        )
    db.expire(approval)
    approval = db.get(PlatformApprovalRequest, approval_id)

    audit_service.record_event(
        db,
        event_type=(
            "platform.organization.suspended"
            if target == OrganizationStatus.SUSPENDED
            else "platform.organization.reactivated"
        ),
        entity_type="organization",
        entity_id=organisation.id,
        organization_id=organisation.id,
        actor=_actor_label(actor),
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        severity=(
            AuditSeverity.WARNING
            if target == OrganizationStatus.SUSPENDED
            else AuditSeverity.INFO
        ),
        summary=(
            "Organisation suspended by platform administration."
            if target == OrganizationStatus.SUSPENDED
            else "Organisation reactivated by platform administration."
        ),
        reason=approval.reason,
        previous_state=previous.value,
        new_state=target.value,
        payload={
            "organization_id": str(organisation.id),
            "slug": organisation.slug,
            "reason": approval.reason,
            "approval_id": str(approval.id),
            "requested_by_user_id": str(approval.requested_by_user_id),
            "decided_by_user_id": str(approval.decided_by_user_id)
            if approval.decided_by_user_id
            else None,
        },
    )
    _audit(
        db,
        approval,
        event_type="platform.approval.executed",
        actor=actor,
        summary="Approved platform action executed.",
        previous_state=previous.value,
        new_state=target.value,
        reason=approval.reason,
    )
    db.flush()
    return approval, organisation
