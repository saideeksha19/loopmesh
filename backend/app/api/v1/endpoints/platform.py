"""Platform administration, tenant operations and platform-wide audit review.

This router is the only place where cross-tenant records are read. It is
deliberately separate from ``/organizations`` and ``/organizations/members``:

* the principal must be a platform operator (``is_platform_admin``) *and* hold
  the platform capability the route demands, so an organisation administrator,
  coordinator or platform-scoped membership cannot reach it;
* responses contain aggregate counts and operational metadata only — never
  materials, demands, proposals, transactions or credentials;
* every mutation is audited inside the same transaction as the change.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.actors import ActorContext
from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.permissions import Permission
from app.core.sessions import as_utc, revoke as revoke_session_record
from app.db.enums import (
    ApprovalAction,
    ApprovalStatus,
    AuditSeverity,
    OrganizationStatus,
)
from app.db.models.identity import AuthSession, User
from app.db.models.organization import Organization
from app.db.models.platform_approval import PlatformApprovalRequest
from app.schemas.common import Page
from app.schemas.platform import (
    PlatformApprovalCreate,
    PlatformApprovalDecision,
    PlatformApprovalExecuteResult,
    PlatformApprovalRead,
    PlatformAuditEvent,
    PlatformAuditIntegrity,
    PlatformAuditSummary,
    PlatformDashboard,
    PlatformDashboardCounts,
    PlatformMembershipCounts,
    PlatformOperatorSession,
    PlatformOrganizationDetail,
    PlatformOrganizationRead,
    PlatformOrganizationSummary,
    PlatformOrganizationUpdate,
    PlatformSessionRevocation,
    PlatformTenantHealth,
    PlatformUserCounts,
)
from app.services import audit as audit_service
from app.services import platform as platform_service
from app.services import platform_approvals as approval_service

router = APIRouter(prefix="/platform", tags=["platform"])


def _require_operator(actor: ActorContext, permission: Permission) -> None:
    """Refuse unless this request is a platform operator with the capability."""
    actor.require_platform()
    actor.require(permission)


def _summary(event, names: dict[uuid.UUID, str]) -> PlatformAuditSummary:
    return PlatformAuditSummary(
        id=event.id,
        created_at=event.created_at,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        actor=event.actor,
        severity=event.severity.value if hasattr(event.severity, "value") else str(event.severity),
        summary=event.summary,
        organization_id=event.organization_id,
        organization_name=names.get(event.organization_id) if event.organization_id else None,
    )


def _organisation_read(
    organisation: Organization, counts: dict[str, int] | None
) -> PlatformOrganizationRead:
    payload = PlatformOrganizationRead.model_validate(organisation)
    if counts:
        payload.active_members = counts.get("active_members", 0)
        payload.suspended_members = counts.get("suspended_members", 0)
        payload.pending_invitations = counts.get("pending_invitations", 0)
    return payload


@router.get(
    "/dashboard",
    response_model=PlatformDashboard,
    summary="Platform operational dashboard",
)
def platform_dashboard(session: DbSession, actor: ActorDep) -> PlatformDashboard:
    _require_operator(actor, Permission.PLATFORM_DASHBOARD_VIEW)
    data = platform_service.dashboard_data(session)
    names = platform_service.organization_names(session, data.recent_events)

    organisation_counts = PlatformDashboardCounts(
        total=sum(data.organisation_counts.values()),
        active=data.organisation_counts.get(OrganizationStatus.ACTIVE.value, 0),
        suspended=data.organisation_counts.get(OrganizationStatus.SUSPENDED.value, 0),
        created_in_window=data.organisations_created_window,
    )
    memberships = PlatformMembershipCounts(
        active=data.membership_counts.get("active", 0),
        suspended=data.membership_counts.get("suspended", 0),
        invited=data.membership_counts.get("invited", 0),
        removed=data.membership_counts.get("removed", 0),
    )

    return PlatformDashboard(
        generated_at=platform_service.utcnow(),
        window_days=30,
        failure_window_hours=24,
        organisations=organisation_counts,
        users=PlatformUserCounts(
            total=data.user_counts.get("total", 0),
            active=data.user_counts.get("active", 0),
        ),
        memberships=memberships,
        pending_invitations=data.pending_invitations,
        failed_logins_window=data.failed_logins_window,
        recent_organisations=[
            PlatformOrganizationSummary.model_validate(row) for row in data.recent_organisations
        ],
        recent_events=[_summary(event, names) for event in data.recent_events],
    )


@router.get(
    "/organizations",
    response_model=Page[PlatformOrganizationRead],
    summary="Platform organisation register",
)
def list_platform_organizations(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    q: str | None = Query(None, max_length=120, description="Search name, slug or city"),
    status: OrganizationStatus | None = Query(None, description="Tenant lifecycle state"),
) -> Page[PlatformOrganizationRead]:
    _require_operator(actor, Permission.PLATFORM_ORGANIZATIONS_VIEW)
    organisations, total, counts = platform_service.list_organisations(
        session,
        offset=pagination.offset,
        limit=pagination.page_size,
        q=q,
        status=status,
    )
    items = [_organisation_read(org, counts.get(org.id)) for org in organisations]
    return build_page(PlatformOrganizationRead, items, total, pagination)


@router.get(
    "/organizations/{organization_id}",
    response_model=PlatformOrganizationDetail,
    summary="Platform organisation detail",
)
def get_platform_organization(
    organization_id: uuid.UUID, session: DbSession, actor: ActorDep
) -> PlatformOrganizationDetail:
    _require_operator(actor, Permission.PLATFORM_ORGANIZATIONS_VIEW)
    organisation = session.get(Organization, organization_id)
    if organisation is None:
        raise NotFoundError("Organization not found.")

    detail = platform_service.organisation_detail(session, organisation)
    names = platform_service.organization_names(session, detail["recent_events"])
    base = PlatformOrganizationSummary.model_validate(organisation).model_dump()
    return PlatformOrganizationDetail(
        **base,
        members=detail["members"],
        invitations=detail["invitations"],
        administrators=detail["administrators"],
        last_activity_at=detail["last_activity_at"],
        state=detail["state"],
        warnings=detail["warnings"],
        checks=detail["checks"],
        recent_events=[_summary(event, names) for event in detail["recent_events"]],
    )


@router.patch(
    "/organizations/{organization_id}",
    response_model=PlatformOrganizationDetail,
    summary="Suspend or reactivate an organisation",
)
def update_platform_organization(
    organization_id: uuid.UUID,
    payload: PlatformOrganizationUpdate,
    session: DbSession,
    actor: ActorDep,
) -> PlatformOrganizationDetail:
    _require_operator(actor, Permission.PLATFORM_ORGANIZATIONS_MANAGE)

    organisation = session.get(Organization, organization_id, with_for_update=True)
    if organisation is None:
        raise NotFoundError("Organization not found.")

    target = payload.status
    previous = organisation.status
    if target == previous:
        raise ConflictError(
            f"This organisation is already {previous.value}.",
            details={
                "reason": "invalid_state_transition",
                "current_status": previous.value,
                "requested_status": target.value,
            },
        )

    reason = (payload.reason or "").strip() or None
    if target == OrganizationStatus.SUSPENDED and (reason is None or len(reason) < 8):
        raise ValidationError(
            "Suspending an organisation requires a written reason of at least 8 characters.",
            details={"field": "reason", "reason": "reason_required"},
        )

    if payload.approval_id is None:
        raise ConflictError(
            "This operation needs an approved request from a second operator.",
            details={"reason": "approval_required"},
        )

    action = (
        ApprovalAction.SUSPEND
        if target == OrganizationStatus.SUSPENDED
        else ApprovalAction.REACTIVATE
    )
    approval, organisation = approval_service.execute(
        session,
        actor=actor,
        approval_id=payload.approval_id,
        expected_action=action,
        expected_organization_id=organization_id,
        expected_reason=reason,
    )
    session.commit()

    detail = platform_service.organisation_detail(session, organisation)
    names = platform_service.organization_names(session, detail["recent_events"])
    base = PlatformOrganizationSummary.model_validate(organisation).model_dump()
    return PlatformOrganizationDetail(
        **base,
        members=detail["members"],
        invitations=detail["invitations"],
        administrators=detail["administrators"],
        last_activity_at=detail["last_activity_at"],
        state=detail["state"],
        warnings=detail["warnings"],
        checks=detail["checks"],
        recent_events=[_summary(event, names) for event in detail["recent_events"]],
    )


def _approval_read(
    approval: PlatformApprovalRequest,
    *,
    actor: ActorContext,
    organisations: dict[uuid.UUID, Organization],
    users: dict[uuid.UUID, User],
) -> PlatformApprovalRead:
    now = approval_service.utcnow()
    expires_at = approval_service.as_utc(approval.expires_at)
    expired = (
        approval.status == ApprovalStatus.PENDING
        and expires_at is not None
        and expires_at <= now
    )
    organisation = organisations.get(approval.organization_id)
    requester = users.get(approval.requested_by_user_id)
    decider = users.get(approval.decided_by_user_id) if approval.decided_by_user_id else None
    executor = users.get(approval.executed_by_user_id) if approval.executed_by_user_id else None

    can_view = Permission.PLATFORM_APPROVALS_VIEW in actor.permissions
    can_decide = (
        can_view
        and Permission.PLATFORM_APPROVALS_DECIDE in actor.permissions
        and not expired
        and approval.status == ApprovalStatus.PENDING
        and approval.requested_by_user_id != actor.user_id
    )
    can_execute = (
        can_view
        and Permission.PLATFORM_APPROVALS_EXECUTE in actor.permissions
        and Permission.PLATFORM_ORGANIZATIONS_MANAGE in actor.permissions
        and not expired
        and approval.status == ApprovalStatus.APPROVED
    )
    return PlatformApprovalRead(
        id=approval.id,
        organization_id=approval.organization_id,
        organization_name=organisation.name if organisation else None,
        organization_slug=organisation.slug if organisation else None,
        organization_status=organisation.status if organisation else None,
        action=approval.action,
        reason=approval.reason,
        status=approval.status,
        requested_by_user_id=approval.requested_by_user_id,
        requested_by=requester.email if requester else None,
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        decided_by_user_id=approval.decided_by_user_id,
        decided_by=decider.email if decider else None,
        decided_at=approval.decided_at,
        decision_reason=approval.decision_reason,
        executed_by_user_id=approval.executed_by_user_id,
        executed_by=executor.email if executor else None,
        executed_at=approval.executed_at,
        is_expired=expired,
        can_decide=can_decide,
        can_execute=can_execute,
        can_cancel=(
            approval.requested_by_user_id == actor.user_id
            and approval.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}
            and not expired
        ),
    )


def _approval_context(
    session: DbSession, approvals: list[PlatformApprovalRequest]
) -> tuple[dict[uuid.UUID, Organization], dict[uuid.UUID, User]]:
    org_ids = {row.organization_id for row in approvals}
    user_ids = {row.requested_by_user_id for row in approvals}
    for row in approvals:
        for candidate in (row.decided_by_user_id, row.executed_by_user_id):
            if candidate is not None:
                user_ids.add(candidate)
    organisations = (
        {row.id: row for row in session.scalars(select(Organization).where(Organization.id.in_(org_ids))).all()}
        if org_ids
        else {}
    )
    users = (
        {row.id: row for row in session.scalars(select(User).where(User.id.in_(user_ids))).all()}
        if user_ids
        else {}
    )
    return organisations, users


@router.post(
    "/approvals",
    response_model=PlatformApprovalRead,
    status_code=201,
    summary="Request two-person approval for a protected platform action",
)
def create_platform_approval(
    payload: PlatformApprovalCreate, session: DbSession, actor: ActorDep
) -> PlatformApprovalRead:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_REQUEST)
    actor.require(Permission.PLATFORM_ORGANIZATIONS_MANAGE)
    approval = approval_service.create_approval(
        session,
        actor=actor,
        organization_id=payload.organization_id,
        action=payload.action,
        reason=payload.reason,
    )
    session.commit()
    organisations, users = _approval_context(session, [approval])
    return _approval_read(
        approval, actor=actor, organisations=organisations, users=users
    )


@router.get(
    "/approvals",
    response_model=Page[PlatformApprovalRead],
    summary="List platform approval requests",
)
def list_platform_approvals(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    status: ApprovalStatus | None = Query(None),
    action: ApprovalAction | None = Query(None),
    organization_id: uuid.UUID | None = Query(None),
) -> Page[PlatformApprovalRead]:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_VIEW)
    if approval_service.expire_pending(session) > 0:
        session.commit()

    filters = []
    if status is not None:
        filters.append(PlatformApprovalRequest.status == status)
    if action is not None:
        filters.append(PlatformApprovalRequest.action == action)
    if organization_id is not None:
        filters.append(PlatformApprovalRequest.organization_id == organization_id)

    base = select(PlatformApprovalRequest).where(*filters)
    total = int(
        session.scalar(
            select(func.count())
            .select_from(PlatformApprovalRequest)
            .where(*filters)
        )
        or 0
    )
    rows = list(
        session.scalars(
            base.order_by(
                PlatformApprovalRequest.created_at.desc(),
                PlatformApprovalRequest.id.desc(),
            )
            .offset(pagination.offset)
            .limit(pagination.page_size)
        ).all()
    )
    organisations, users = _approval_context(session, rows)
    items = [
        _approval_read(row, actor=actor, organisations=organisations, users=users)
        for row in rows
    ]
    return build_page(PlatformApprovalRead, items, total, pagination)


@router.get(
    "/approvals/{approval_id}",
    response_model=PlatformApprovalRead,
    summary="Read one approval request",
)
def get_platform_approval(
    approval_id: uuid.UUID, session: DbSession, actor: ActorDep
) -> PlatformApprovalRead:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_VIEW)
    approval = approval_service.get_approval(session, approval_id)
    if approval_service.expire_pending(session) > 0:
        session.commit()
        session.refresh(approval)
    organisations, users = _approval_context(session, [approval])
    return _approval_read(
        approval, actor=actor, organisations=organisations, users=users
    )


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=PlatformApprovalRead,
    summary="Approve a request as a different operator",
)
def approve_platform_approval(
    approval_id: uuid.UUID,
    payload: PlatformApprovalDecision,
    session: DbSession,
    actor: ActorDep,
) -> PlatformApprovalRead:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_DECIDE)
    approval = approval_service.approve(
        session, actor=actor, approval_id=approval_id, reason=payload.reason
    )
    session.commit()
    organisations, users = _approval_context(session, [approval])
    return _approval_read(
        approval, actor=actor, organisations=organisations, users=users
    )


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=PlatformApprovalRead,
    summary="Reject a request as a different operator",
)
def reject_platform_approval(
    approval_id: uuid.UUID,
    payload: PlatformApprovalDecision,
    session: DbSession,
    actor: ActorDep,
) -> PlatformApprovalRead:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_DECIDE)
    approval = approval_service.reject(
        session, actor=actor, approval_id=approval_id, reason=payload.reason
    )
    session.commit()
    organisations, users = _approval_context(session, [approval])
    return _approval_read(
        approval, actor=actor, organisations=organisations, users=users
    )


@router.post(
    "/approvals/{approval_id}/cancel",
    response_model=PlatformApprovalRead,
    summary="Cancel your own pending or approved request",
)
def cancel_platform_approval(
    approval_id: uuid.UUID, session: DbSession, actor: ActorDep
) -> PlatformApprovalRead:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_REQUEST)
    approval = approval_service.cancel(session, actor=actor, approval_id=approval_id)
    session.commit()
    organisations, users = _approval_context(session, [approval])
    return _approval_read(
        approval, actor=actor, organisations=organisations, users=users
    )


@router.post(
    "/approvals/{approval_id}/execute",
    response_model=PlatformApprovalExecuteResult,
    summary="Execute an approved tenant lifecycle change exactly once",
)
def execute_platform_approval(
    approval_id: uuid.UUID, session: DbSession, actor: ActorDep
) -> PlatformApprovalExecuteResult:
    _require_operator(actor, Permission.PLATFORM_APPROVALS_EXECUTE)
    actor.require(Permission.PLATFORM_ORGANIZATIONS_MANAGE)
    approval, organisation = approval_service.execute(
        session, actor=actor, approval_id=approval_id
    )
    session.commit()
    organisations, users = _approval_context(session, [approval])
    return PlatformApprovalExecuteResult(
        approval=_approval_read(
            approval, actor=actor, organisations=organisations, users=users
        ),
        organization=PlatformOrganizationSummary.model_validate(organisation),
    )


@router.get(
    "/sessions",
    response_model=Page[PlatformOperatorSession],
    summary="Platform operator sessions",
)
def platform_sessions(
    session: DbSession, actor: ActorDep, pagination: PageParams
) -> Page[PlatformOperatorSession]:
    _require_operator(actor, Permission.PLATFORM_SESSIONS_MANAGE)
    operator_ids = select(User.id).where(User.is_platform_admin.is_(True))
    total = int(
        session.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.user_id.in_(operator_ids))
        )
        or 0
    )
    rows = session.execute(
        select(AuthSession, User.email)
        .join(User, User.id == AuthSession.user_id)
        .where(User.is_platform_admin.is_(True))
        .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    items = [
        PlatformOperatorSession(
            id=session_row.id,
            user_id=session_row.user_id,
            user_email=email,
            created_at=session_row.created_at,
            last_seen_at=session_row.last_seen_at,
            mfa_verified_at=session_row.mfa_verified_at,
            revoked_at=session_row.revoked_at,
            revoked_reason=session_row.revoked_reason,
            is_current=(session_row.id == actor.session_id),
            user_agent=None,
        )
        for session_row, email in rows
    ]
    return build_page(PlatformOperatorSession, items, total, pagination)


@router.post(
    "/sessions/{session_id}/revoke",
    response_model=PlatformSessionRevocation,
    summary="Revoke one platform operator session",
)
def revoke_platform_session(
    session_id: uuid.UUID, session: DbSession, actor: ActorDep
) -> PlatformSessionRevocation:
    _require_operator(actor, Permission.PLATFORM_SESSIONS_MANAGE)
    if session_id == actor.session_id:
        raise ConflictError(
            "Use sign out to end the session you are currently using.",
            details={"reason": "cannot_revoke_current"},
        )
    target = session.get(AuthSession, session_id)
    owner = session.get(User, target.user_id) if target is not None else None
    if target is None or owner is None or not owner.is_platform_admin:
        raise NotFoundError("Platform operator session not found.")
    if target.revoked_at is not None:
        return PlatformSessionRevocation(
            message="Session was already revoked.", revoked_count=0
        )
    revoke_session_record(session, target, reason="platform_operator_revoked")
    audit_service.record_event(
        session,
        event_type="platform.session.revoked",
        entity_type="auth_session",
        entity_id=target.id,
        actor=actor.email or actor.display_name or actor.actor_id,
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        severity=AuditSeverity.WARNING,
        summary="Platform operator session revoked by an operator.",
        payload={"session_id": str(target.id), "target_user_id": str(target.user_id)},
    )
    session.commit()
    return PlatformSessionRevocation(
        message="Platform operator session revoked.", revoked_count=1
    )


@router.post(
    "/sessions/revoke-all",
    response_model=PlatformSessionRevocation,
    summary="Revoke every other platform operator session",
)
def revoke_all_platform_sessions(
    session: DbSession, actor: ActorDep
) -> PlatformSessionRevocation:
    _require_operator(actor, Permission.PLATFORM_SESSIONS_MANAGE)
    operator_ids = select(User.id).where(User.is_platform_admin.is_(True))
    rows = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id.in_(operator_ids),
            AuthSession.revoked_at.is_(None),
            AuthSession.id != actor.session_id,
        )
    ).all()
    for row in rows:
        revoke_session_record(session, row, reason="platform_all_revoked")
    audit_service.record_event(
        session,
        event_type="platform.session.revoked_all",
        entity_type="auth_session",
        actor=actor.email or actor.display_name or actor.actor_id,
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        severity=AuditSeverity.WARNING,
        summary="All other platform operator sessions revoked.",
        payload={
            "revoked_count": len(rows),
            "kept_session_id": str(actor.session_id) if actor.session_id else None,
        },
    )
    session.commit()
    return PlatformSessionRevocation(
        message=(
            f"Revoked {len(rows)} other platform session(s). "
            "The current session was kept."
        ),
        revoked_count=len(rows),
    )


@router.get(
    "/audit",
    response_model=Page[PlatformAuditEvent],
    summary="Search the platform-wide audit journal",
)
def platform_audit(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    created_from: datetime | None = Query(None, description="Inclusive lower bound"),
    created_to: datetime | None = Query(None, description="Inclusive upper bound"),
    actor_id: str | None = Query(None, max_length=120, description="Exact actor identifier"),
    actor_search: str | None = Query(
        None, max_length=120, alias="actor", description="Actor email or label substring"
    ),
    organization_id: uuid.UUID | None = Query(None, description="Tenant filter"),
    event_type: str | None = Query(None, max_length=64),
    entity_type: str | None = Query(None, max_length=64),
    entity_id: uuid.UUID | None = Query(None),
    target_user_id: uuid.UUID | None = Query(
        None, description="Account whose user/membership events are returned"
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> Page[PlatformAuditEvent]:
    _require_operator(actor, Permission.PLATFORM_AUDIT_VIEW)
    if created_from and created_to and created_from > created_to:
        raise ValidationError(
            "The start of the range must not be after its end.",
            details={"field": "created_from", "reason": "invalid_range"},
        )

    events, total = platform_service.audit_events(
        session,
        offset=pagination.offset,
        limit=pagination.page_size,
        created_from=created_from,
        created_to=created_to,
        actor_id=actor_id,
        actor=actor_search,
        organization_id=organization_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        target_user_id=target_user_id,
        order=order,
    )
    names = platform_service.organization_names(session, events)
    items = []
    for event in events:
        payload, redacted = platform_service.redact_payload(event.event_type, event.payload)
        items.append(
            PlatformAuditEvent(
                id=event.id,
                created_at=event.created_at,
                event_type=event.event_type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                actor=event.actor,
                actor_id=event.actor_id,
                organization_id=event.organization_id,
                organization_name=names.get(event.organization_id) if event.organization_id else None,
                severity=(
                    event.severity.value
                    if hasattr(event.severity, "value")
                    else str(event.severity)
                ),
                summary=event.summary,
                reason=event.reason,
                previous_state=event.previous_state,
                new_state=event.new_state,
                payload=payload,
                redacted_fields=redacted,
            )
        )
    return build_page(PlatformAuditEvent, items, total, pagination)


def _export_cell(value) -> str:
    """Neutralise spreadsheet formula injection in CSV cells.

    A leading ``=``, ``+``, ``-`` or ``@`` (optionally after whitespace) is
    treated as a formula by Excel and LibreOffice. Prefixing an apostrophe keeps
    the value literal; the CSV writer then quotes it as needed.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    if text.lstrip()[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + text
    return text


def _export_rows(
    session: DbSession,
    events: list,
    names: dict[uuid.UUID, str],
) -> list[dict]:
    rows: list[dict] = []
    for event in events:
        payload, redacted = platform_service.redact_payload(
            event.event_type, event.payload
        )
        rows.append(
            {
                "id": str(event.id),
                "created_at": as_utc(event.created_at).isoformat()
                if as_utc(event.created_at)
                else None,
                "event_type": event.event_type,
                "severity": (
                    event.severity.value
                    if hasattr(event.severity, "value")
                    else str(event.severity)
                ),
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id) if event.entity_id else None,
                "actor": event.actor,
                "actor_id": event.actor_id,
                "organization_id": str(event.organization_id)
                if event.organization_id
                else None,
                "organization_name": names.get(event.organization_id)
                if event.organization_id
                else None,
                "summary": event.summary,
                "reason": event.reason,
                "previous_state": event.previous_state,
                "new_state": event.new_state,
                "payload": payload,
                "redacted_fields": ",".join(redacted),
            }
        )
    return rows


@router.get(
    "/audit/integrity",
    response_model=PlatformAuditIntegrity,
    summary="Verify the audit sequence and hash chain",
)
def verify_platform_audit(
    session: DbSession,
    actor: ActorDep,
) -> PlatformAuditIntegrity:
    """Walk the chain in bounded batches and record the verification attempt."""
    _require_operator(actor, Permission.PLATFORM_AUDIT_VIEW)
    actor.require(Permission.PLATFORM_AUDIT_VERIFY)
    result = audit_service.verify_integrity(
        session, batch_size=settings.audit_verify_batch_size
    )
    audit_service.record_event(
        session,
        event_type="platform.audit.integrity_verified",
        entity_type="audit_chain",
        actor=actor.email or actor.display_name or actor.actor_id,
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        severity=AuditSeverity.WARNING if not result["valid"] else AuditSeverity.INFO,
        summary=(
            "Audit chain verification failed."
            if not result["valid"]
            else "Audit chain verified."
        ),
        payload={
            "valid": result["valid"],
            "checked": result["checked"],
            "reason": result["reason"],
            "first_invalid_sequence": result["first_invalid_sequence"],
            "chain_head": result["chain_head"],
            "state_sequence": result["state_sequence"],
        },
    )
    session.commit()
    return PlatformAuditIntegrity(**result)


@router.get(
    "/audit/export",
    summary="Bounded, redacted audit journal export (CSV or JSON)",
    response_class=Response,
)
def export_platform_audit(
    session: DbSession,
    actor: ActorDep,
    created_from: datetime | None = Query(None, description="Required inclusive lower bound"),
    created_to: datetime | None = Query(None, description="Required inclusive upper bound"),
    format: str = Query("csv", pattern="^(csv|json)$"),
    actor_id: str | None = Query(None, max_length=120),
    actor_search: str | None = Query(
        None, max_length=120, alias="actor", description="Actor email or label substring"
    ),
    organization_id: uuid.UUID | None = Query(None),
    event_type: str | None = Query(None, max_length=64),
    entity_type: str | None = Query(None, max_length=64),
    entity_id: uuid.UUID | None = Query(None),
    target_user_id: uuid.UUID | None = Query(None),
) -> Response:
    _require_operator(actor, Permission.PLATFORM_AUDIT_VIEW)
    actor.require(Permission.PLATFORM_AUDIT_EXPORT)

    if created_from is None or created_to is None:
        raise ValidationError(
            "Audit export requires both created_from and created_to.",
            details={"reason": "export_range_required"},
        )
    if created_from > created_to:
        raise ValidationError(
            "The start of the range must not be after its end.",
            details={"field": "created_from", "reason": "invalid_range"},
        )
    if created_to - created_from > timedelta(
        days=settings.platform_audit_export_max_range_days
    ):
        raise ValidationError(
            "The requested range is larger than this deployment allows.",
            details={
                "reason": "export_range_too_large",
                "max_days": settings.platform_audit_export_max_range_days,
            },
        )

    # Fetch at most one row beyond the cap so the count is exact enough to
    # refuse without ever materialising an unbounded result set.
    events, total = platform_service.audit_events(
        session,
        offset=0,
        limit=settings.platform_audit_export_max_rows + 1,
        created_from=created_from,
        created_to=created_to,
        actor_id=actor_id,
        actor=actor_search,
        organization_id=organization_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        target_user_id=target_user_id,
        order="asc",
    )
    if total > settings.platform_audit_export_max_rows:
        raise ValidationError(
            "This export has too many rows. Narrow the date range or filters.",
            details={
                "reason": "export_too_large",
                "max_rows": settings.platform_audit_export_max_rows,
                "matching_rows": total,
            },
        )

    names = platform_service.organization_names(session, events)
    rows = _export_rows(session, events, names)
    generated = platform_service.utcnow()
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")

    if format == "csv":
        columns = list(rows[0].keys()) if rows else [
            "id",
            "created_at",
            "event_type",
            "severity",
            "entity_type",
            "entity_id",
            "actor",
            "actor_id",
            "organization_id",
            "organization_name",
            "summary",
            "reason",
            "previous_state",
            "new_state",
            "payload",
            "redacted_fields",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _export_cell(row.get(key)) for key in columns})
        body = buffer.getvalue().encode("utf-8-sig")
        media_type = "text/csv; charset=utf-8"
        filename = f"loopmesh-audit-{stamp}.csv"
    else:
        body = json.dumps(
            {
                "generated_at": generated.isoformat(),
                "created_from": created_from.isoformat(),
                "created_to": created_to.isoformat(),
                "row_count": len(rows),
                "events": rows,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        media_type = "application/json; charset=utf-8"
        filename = f"loopmesh-audit-{stamp}.json"

    audit_service.record_event(
        session,
        event_type="platform.audit.exported",
        entity_type="audit_export",
        actor=actor.email or actor.display_name or actor.actor_id,
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        severity=AuditSeverity.WARNING,
        summary="Audit journal exported.",
        payload={
            "format": format,
            "row_count": len(rows),
            "created_from": created_from.isoformat(),
            "created_to": created_to.isoformat(),
            "filters": {
                "actor_id": actor_id,
                "actor": actor_search,
                "organization_id": str(organization_id) if organization_id else None,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "target_user_id": str(target_user_id) if target_user_id else None,
            },
            "max_rows": settings.platform_audit_export_max_rows,
        },
    )
    session.commit()

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/health",
    response_model=Page[PlatformTenantHealth],
    summary="Tenant health overview",
)
def platform_health(
    session: DbSession, actor: ActorDep, pagination: PageParams
) -> Page[PlatformTenantHealth]:
    _require_operator(actor, Permission.PLATFORM_HEALTH_VIEW)
    rows, total = platform_service.tenant_health_page(
        session, offset=pagination.offset, limit=pagination.page_size
    )
    items = [
        PlatformTenantHealth(
            organization=PlatformOrganizationSummary.model_validate(row["organization"]),
            active_members=row["active_members"],
            suspended_members=row["suspended_members"],
            pending_invitations=row["pending_invitations"],
            active_administrators=row["active_administrators"],
            admin_changes_window=row["admin_changes_window"],
            security_events_window=row["security_events_window"],
            member_auth_failures_window=row["member_auth_failures_window"],
            last_activity_at=row["last_activity_at"],
            state=row["state"],
            warnings=row["warnings"],
            checks=row["checks"],
        )
        for row in rows
    ]
    return build_page(PlatformTenantHealth, items, total, pagination)

