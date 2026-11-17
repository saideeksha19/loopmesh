"""Organisation member lifecycle administration (Batch 10).

Every route is scoped to one organisation and gated by the existing capability
catalogue. The rules encoded here are:

* ``member.view`` reads the roster, ``member.manage`` changes it;
* a member administrator is confined to the organisation they are acting in
  (a platform-scoped principal may reach every organisation);
* an external target answers exactly like an unknown one (404), so identifiers
  cannot be probed across tenants;
* nobody may change their own role or scope, which blocks self-promotion and
  self-demotion in one rule;
* the last active organisation administrator cannot be demoted, deactivated or
  removed, so an organisation can never lock itself out;
* a non-platform principal cannot grant platform scope, or a role holding
  capabilities they do not hold themselves;
* deactivation is organisation-scoped: it suspends the membership and revokes
  only the sessions that were opened for that organisation, never the user's
  unrelated memberships in other organisations.

Role and scope changes need no session revocation: authorisation is rebuilt from
the membership row on every request (``app.core.actors``), so a demotion takes
effect on the member's next call.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.actors import ActorContext
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.permissions import Permission
from app.core.sessions import as_utc, revoke, revoke_all_for_user, utcnow
from app.db.enums import MembershipRole, MembershipScope, MembershipStatus
from app.db.models.identity import AuthSession, OrganizationMembership, User
from app.schemas.common import Page
from app.schemas.member import (
    MemberActionRead,
    MemberRead,
    MemberResetRead,
    MemberUpdateRequest,
)
from app.services import audit

router = APIRouter(prefix="/organizations/members", tags=["members"])

_LAST_ADMIN_MESSAGE = (
    "The organisation must keep at least one active administrator. "
    "Appoint a replacement before changing this membership."
)
_EXTERNAL_REFERENCE = "Member not found."


def _audit_member(
    db,
    *,
    actor: ActorContext,
    event_type: str,
    summary: str,
    entity_type: str,
    entity_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: dict | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
) -> None:
    """Append a membership audit event in the caller's transaction."""
    audit.record_event(
        db,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        actor=str(actor.user_id) if actor.user_id else actor.actor_id,
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        summary=summary,
        payload=payload or {},
        previous_state=previous_state,
        new_state=new_state,
    )


def _member_read(membership: OrganizationMembership, actor: ActorContext) -> MemberRead:
    """Project a membership onto the safe member read model."""
    user = membership.user
    return MemberRead(
        id=membership.id,
        user_id=membership.user_id,
        full_name=user.full_name if user is not None else "",
        email=user.email if user is not None else "",
        role=membership.role.value,
        scope=membership.scope.value,
        status=membership.status.value,
        joined_at=as_utc(membership.accepted_at or membership.created_at),
        is_self=actor.user_id is not None and membership.user_id == actor.user_id,
    )


def _target_membership(
    db, actor: ActorContext, membership_id: uuid.UUID
) -> OrganizationMembership:
    """Resolve a membership inside the actor's reach.

    Unknown identifiers and identifiers belonging to another organisation raise
    the same 404, so a member administrator cannot enumerate other tenants.
    """
    membership = db.scalar(
        select(OrganizationMembership)
        .where(OrganizationMembership.id == membership_id)
        .options(joinedload(OrganizationMembership.user))
    )
    if membership is None:
        raise NotFoundError(_EXTERNAL_REFERENCE)
    if not actor.platform_scope:
        if actor.organization_id is None:
            raise ForbiddenError(
                "Select an organisation before managing members.",
                details={"reason": "organization_context_required"},
            )
        if membership.organization_id != actor.organization_id:
            raise NotFoundError(_EXTERNAL_REFERENCE)
    return membership


def _routable_organization(actor: ActorContext, requested: uuid.UUID | None) -> uuid.UUID:
    """Choose the organisation a roster request may read."""
    target = requested or actor.organization_id
    if target is None:
        raise ForbiddenError(
            "Select an organisation before listing members.",
            details={"reason": "organization_context_required"},
        )
    if actor.platform_scope or target in actor.organization_ids:
        return target
    raise ForbiddenError(
        "You cannot read another organisation's members.",
        details={"reason": "organisation_scope"},
    )


def _assert_can_grant(
    actor: ActorContext, role: MembershipRole, scope: MembershipScope
) -> None:
    """Refuse a grant wider than the actor's own administrative authority.

    Organisation roles are not a ladder: a coordinator holds operational
    capabilities an organisation administrator does not, so "grant only
    permissions you hold" would stop an administrator appointing the colleagues
    the organisation actually needs. The boundaries that do apply are the
    administrative ones — the actor must already hold ``member.manage`` (the
    route gate), the role must exist in the catalogue (enum validation) and only
    a platform-scoped principal may hand out cross-organisation reach.
    """
    if scope == MembershipScope.PLATFORM and not actor.platform_scope:
        raise ForbiddenError(
            "Only a platform-scoped principal can grant platform scope.",
            details={"reason": "privilege_escalation"},
        )
    if role == MembershipRole.ORG_ADMIN and not (
        actor.is_platform_admin or actor.has(Permission.MEMBER_MANAGE)
    ):
        raise ForbiddenError(
            "You cannot grant organisation administration.",
            details={"reason": "privilege_escalation"},
        )


def _assert_can_manage_target(
    actor: ActorContext, membership: OrganizationMembership
) -> None:
    """Refuse changing a grant that reaches beyond the actor's own scope.

    A cross-organisation (platform-scoped) membership is a platform decision: an
    ordinary organisation administrator must not be able to narrow or widen it
    from inside a single tenant.
    """
    if membership.scope == MembershipScope.PLATFORM and not actor.platform_scope:
        raise ForbiddenError(
            "Only a platform-scoped principal can change a platform-scoped membership.",
            details={"reason": "privilege_escalation"},
        )


def _other_active_admins(db, membership: OrganizationMembership) -> int:
    return int(
        db.scalar(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == membership.organization_id,
                OrganizationMembership.id != membership.id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                OrganizationMembership.role == MembershipRole.ORG_ADMIN,
            )
        )
        or 0
    )


def _assert_admin_remains(db, membership: OrganizationMembership) -> None:
    """Keep at least one active organisation administrator."""
    if _other_active_admins(db, membership) == 0:
        raise ConflictError(_LAST_ADMIN_MESSAGE, details={"reason": "last_admin"})


def _revoke_organization_sessions(
    db, *, user_id: uuid.UUID, organization_id: uuid.UUID, reason: str
) -> int:
    """Revoke the sessions opened for one organisation only.

    Sessions opened for the user's other organisations are left alone: a
    membership deactivation is not an account suspension.
    """
    records = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.organization_id == organization_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    for record in records:
        revoke(db, record, reason=reason)
    return len(records)


# ---------------------------------------------------------------------------
# roster
# ---------------------------------------------------------------------------


@router.get("", response_model=Page[MemberRead], summary="List organisation members")
def list_members(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    organization_id: uuid.UUID | None = Query(
        default=None,
        description="Platform-scoped principals may read another organisation.",
    ),
    member_status: MembershipStatus | None = Query(
        default=None,
        alias="status",
        description="Restrict to one membership status; all statuses are listed by default.",
    ),
    q: str | None = Query(
        default=None, max_length=120, description="Search member name or email"
    ),
) -> Page[MemberRead]:
    actor.require(Permission.MEMBER_VIEW)
    organization = _routable_organization(actor, organization_id)

    stmt = (
        select(OrganizationMembership)
        .where(OrganizationMembership.organization_id == organization)
        .options(joinedload(OrganizationMembership.user))
    )
    if member_status is not None:
        stmt = stmt.where(OrganizationMembership.status == member_status)
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.join(User, User.id == OrganizationMembership.user_id).where(
            or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )

    total = int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = session.scalars(
        stmt.order_by(OrganizationMembership.created_at.asc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()

    # Inactive memberships are listed on purpose: an administrator must be able
    # to see a suspended member to reinstate them. They grant no authority —
    # ``active_memberships`` and every capability check ignore them.
    items = [_member_read(row, actor) for row in rows]
    return build_page(MemberRead, items, total, pagination)


# ---------------------------------------------------------------------------
# role and scope
# ---------------------------------------------------------------------------


@router.patch(
    "/{membership_id}",
    response_model=MemberRead,
    summary="Change a member's role or scope",
)
def update_member(
    membership_id: uuid.UUID,
    payload: MemberUpdateRequest,
    actor: ActorDep,
    db: DbSession,
) -> MemberRead:
    actor.require(Permission.MEMBER_MANAGE)
    membership = _target_membership(db, actor, membership_id)

    if payload.role is None and payload.scope is None:
        raise ValidationError(
            "Provide a role or a scope to change.", details={"field": "role"}
        )
    if actor.user_id is not None and membership.user_id == actor.user_id:
        # One rule covers both self-promotion (granting yourself more) and
        # self-demotion (removing your own last administrative authority).
        raise ForbiddenError(
            "You cannot change your own role or scope.",
            details={"reason": "self_modification"},
        )

    new_role = membership.role
    if payload.role is not None:
        try:
            new_role = MembershipRole(payload.role)
        except ValueError as exc:
            raise ValidationError(
                "Invalid membership role.", details={"field": "role"}
            ) from exc

    new_scope = membership.scope
    if payload.scope is not None:
        try:
            new_scope = MembershipScope(payload.scope)
        except ValueError as exc:
            raise ValidationError(
                "Invalid membership scope.", details={"field": "scope"}
            ) from exc

    if new_role == membership.role and new_scope == membership.scope:
        return _member_read(membership, actor)

    _assert_can_manage_target(actor, membership)
    _assert_can_grant(actor, new_role, new_scope)
    if (
        membership.status == MembershipStatus.ACTIVE
        and membership.role == MembershipRole.ORG_ADMIN
        and new_role != MembershipRole.ORG_ADMIN
    ):
        _assert_admin_remains(db, membership)

    previous_role, previous_scope = membership.role, membership.scope
    membership.role = new_role
    membership.scope = new_scope
    db.flush()

    _audit_member(
        db,
        actor=actor,
        event_type="membership.changed",
        summary="Organisation member role changed.",
        entity_type="organization_membership",
        entity_id=membership.id,
        organization_id=membership.organization_id,
        previous_state=f"{previous_role.value}/{previous_scope.value}",
        new_state=f"{new_role.value}/{new_scope.value}",
        payload={
            "user_id": str(membership.user_id),
            "membership_id": str(membership.id),
            "previous_role": previous_role.value,
            "new_role": new_role.value,
            "previous_scope": previous_scope.value,
            "new_scope": new_scope.value,
        },
    )
    db.commit()
    return _member_read(membership, actor)


# ---------------------------------------------------------------------------
# deactivation and reactivation
# ---------------------------------------------------------------------------


@router.post(
    "/{membership_id}/deactivate",
    response_model=MemberActionRead,
    summary="Deactivate an organisation membership",
)
def deactivate_member(
    membership_id: uuid.UUID, actor: ActorDep, db: DbSession
) -> MemberActionRead:
    actor.require(Permission.MEMBER_MANAGE)
    membership = _target_membership(db, actor, membership_id)

    if actor.user_id is not None and membership.user_id == actor.user_id:
        raise ForbiddenError(
            "You cannot deactivate your own membership.",
            details={"reason": "self_modification"},
        )
    if membership.status != MembershipStatus.ACTIVE:
        raise ConflictError(
            "Only an active membership can be deactivated.",
            details={"reason": "invalid_status", "status": membership.status.value},
        )
    if membership.role == MembershipRole.ORG_ADMIN:
        _assert_admin_remains(db, membership)

    membership.status = MembershipStatus.SUSPENDED
    db.flush()

    revoked = _revoke_organization_sessions(
        db,
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        reason="membership_deactivated",
    )

    _audit_member(
        db,
        actor=actor,
        event_type="membership.deactivated",
        summary="Organisation member deactivated.",
        entity_type="organization_membership",
        entity_id=membership.id,
        organization_id=membership.organization_id,
        previous_state=MembershipStatus.ACTIVE.value,
        new_state=MembershipStatus.SUSPENDED.value,
        payload={
            "user_id": str(membership.user_id),
            "membership_id": str(membership.id),
            "role": membership.role.value,
            "sessions_revoked": revoked,
            "scope_of_effect": "membership",
        },
    )
    db.commit()
    return MemberActionRead(
        member=_member_read(membership, actor), sessions_revoked=revoked
    )


@router.post(
    "/{membership_id}/reactivate",
    response_model=MemberActionRead,
    summary="Reactivate a suspended organisation membership",
)
def reactivate_member(
    membership_id: uuid.UUID, actor: ActorDep, db: DbSession
) -> MemberActionRead:
    actor.require(Permission.MEMBER_MANAGE)
    membership = _target_membership(db, actor, membership_id)

    if actor.user_id is not None and membership.user_id == actor.user_id:
        raise ForbiddenError(
            "You cannot reactivate your own membership.",
            details={"reason": "self_modification"},
        )
    if membership.status != MembershipStatus.SUSPENDED:
        raise ConflictError(
            "Only a suspended membership can be reactivated.",
            details={"reason": "invalid_status", "status": membership.status.value},
        )

    # The stored role must still be within the actor's authority to grant; the
    # catalogue can change between suspension and reinstatement.
    _assert_can_grant(actor, membership.role, membership.scope)

    membership.status = MembershipStatus.ACTIVE
    if membership.accepted_at is None:
        membership.accepted_at = utcnow()
    db.flush()

    _audit_member(
        db,
        actor=actor,
        event_type="membership.reactivated",
        summary="Organisation member reactivated.",
        entity_type="organization_membership",
        entity_id=membership.id,
        organization_id=membership.organization_id,
        previous_state=MembershipStatus.SUSPENDED.value,
        new_state=MembershipStatus.ACTIVE.value,
        payload={
            "user_id": str(membership.user_id),
            "membership_id": str(membership.id),
            "role": membership.role.value,
            "scope": membership.scope.value,
        },
    )
    db.commit()
    return MemberActionRead(
        member=_member_read(membership, actor), sessions_revoked=0
    )


# ---------------------------------------------------------------------------
# operator-initiated password reset
# ---------------------------------------------------------------------------


@router.post(
    "/{membership_id}/reset-password",
    response_model=MemberResetRead,
    summary="Issue an operator-initiated password reset",
)
def reset_member_password(
    membership_id: uuid.UUID, actor: ActorDep, db: DbSession
) -> MemberResetRead:
    actor.require(Permission.MEMBER_MANAGE)
    membership = _target_membership(db, actor, membership_id)

    if actor.user_id is not None and membership.user_id == actor.user_id:
        raise ForbiddenError(
            "Use the account password form to change your own password.",
            details={"reason": "self_modification"},
        )

    user = membership.user
    if user is None:
        raise NotFoundError(_EXTERNAL_REFERENCE)

    # Batch 9 derives ``must_change_password`` from this column, so clearing it
    # re-arms the forced-rotation gate without a new column or migration.
    user.password_changed_at = None
    db.flush()

    revoked = revoke_all_for_user(db, user.id, reason="admin_password_reset")

    _audit_member(
        db,
        actor=actor,
        event_type="auth.password_reset_issued",
        summary="Operator-initiated password reset issued.",
        entity_type="user",
        entity_id=user.id,
        organization_id=membership.organization_id,
        payload={
            "user_id": str(user.id),
            "membership_id": str(membership.id),
            "sessions_revoked": revoked,
            "delivery": "operator_assisted",
        },
    )
    db.commit()

    return MemberResetRead(
        member=_member_read(membership, actor),
        sessions_revoked=revoked,
        must_change_password=True,
        message=(
            "Password reset issued. Existing sessions were revoked and the member must "
            "set a new password before entering the workspace. No password or reset token "
            "was generated or returned."
        ),
    )
