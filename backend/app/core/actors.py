"""Authenticated principal and record-level authorisation.

Phase 2A resolved an actor from a development registry keyed by a client
header. Phase 2B removes that path entirely: an :class:`ActorContext` can only
be built from a live server-side session plus an active organisation
membership.

Two layers decide every request:

1. **Capability** — does the principal's role grant the permission at all
   (``app/core/permissions.py``)?
2. **Reach** — is this record inside the organisations the principal may act
   for? Organisation members are limited to records where one of their
   organisations is a party; a platform-scope membership or platform
   administrator may act across organisations, and that grant is explicit
   data, not a role name.

Deny by default: an unknown role, an inactive membership or a missing
organisation context produces an empty capability set.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.permissions import Permission, permissions_for
from app.core.sessions import as_utc
from app.db.enums import ActorRole, MembershipRole, MembershipScope, MembershipStatus
from app.db.models.identity import AuthSession, OrganizationMembership, User

#: Header that Phase 2A trusted. It is now rejected outright so a stray client
#: cannot resurrect the old identity mechanism.
LEGACY_ACTOR_HEADER = "X-Actor-Id"

_ROLE_MAP: dict[MembershipRole, ActorRole] = {
    MembershipRole.ORG_ADMIN: ActorRole.ORG_ADMIN,
    MembershipRole.COORDINATOR: ActorRole.COORDINATOR,
    MembershipRole.REVIEWER: ActorRole.REVIEWER,
    MembershipRole.APPROVER: ActorRole.APPROVER,
    MembershipRole.AUDITOR: ActorRole.AUDITOR,
    MembershipRole.VIEWER: ActorRole.VIEWER,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Resolved identity and authority for one authenticated request."""

    actor_id: str
    display_name: str
    role: ActorRole
    organization_id: uuid.UUID | None = None
    organization_slug: str | None = None
    organization_name: str | None = None

    user_id: uuid.UUID | None = None
    email: str | None = None
    session_id: uuid.UUID | None = None
    membership_id: uuid.UUID | None = None
    membership_role: MembershipRole | None = None
    membership_scope: MembershipScope = MembershipScope.ORGANIZATION

    organization_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    is_platform_admin: bool = False
    is_development: bool = False
    must_change_password: bool = False
    session_expires_at: datetime | None = None

    # Platform MFA and session governance. These are resolved from the live
    # session row, never from a client claim.
    mfa_verified: bool = False
    mfa_method: str | None = None
    mfa_verified_at: datetime | None = None
    session_created_at: datetime | None = None
    session_last_seen_at: datetime | None = None

    # -- capability -----------------------------------------------------
    @property
    def platform_scope(self) -> bool:
        return self.is_platform_admin or self.membership_scope == MembershipScope.PLATFORM

    @property
    def sees_all_records(self) -> bool:
        """Cross-organisation read reach.

        Only an explicit platform scope (or the platform administrator flag)
        widens reads beyond the principal's own organisations.
        """
        return self.platform_scope

    @property
    def has_organization_context(self) -> bool:
        return self.organization_id is not None or self.is_platform_admin

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        """Raise 403 unless the principal holds a capability."""
        if permission in self.permissions:
            return
        raise ForbiddenError(
            "You do not have permission to perform this action.",
            details={"required_permission": permission.value, "reason": "insufficient_permission"},
        )

    def require_organization(self) -> uuid.UUID:
        """Return the active organisation, or refuse the request."""
        if self.organization_id is None:
            raise ForbiddenError(
                "Select an organisation before performing this action.",
                details={"reason": "organization_context_required"},
            )
        return self.organization_id

    def require_platform(self) -> None:
        """Refuse unless this principal is a verified platform operator.

        Three independent facts must agree: the explicit user-level flag (the
        only way to obtain platform authority), the capability it resolves to,
        and a session that has proved a second factor. A bug that one day added
        a platform permission to an organisation role would still not open the
        console, and no role or scope update can set the flag.

        The MFA and session-limit checks live here rather than in the router so
        every present and future platform route inherits them.
        """
        if not (self.is_platform_admin and Permission.PLATFORM_ADMIN in self.permissions):
            raise ForbiddenError(
                "Platform administration is restricted to platform operators.",
                details={"reason": "platform_scope_required"},
            )
        if not self.mfa_verified:
            raise ForbiddenError(
                "Platform access requires a verified second factor.",
                details={"reason": "mfa_required"},
            )

        now = utcnow()
        verified_at = self.mfa_verified_at
        last_seen = self.session_last_seen_at
        created = self.session_created_at
        idle_limit = settings.platform_session_idle_minutes * 60
        absolute_limit = settings.platform_session_absolute_hours * 3600

        if verified_at is None or created is None:
            raise AuthenticationError(
                "Sign in again to continue platform administration.",
                details={"reason": "platform_session_expired"},
            )
        if last_seen is not None and (now - last_seen).total_seconds() > idle_limit:
            raise AuthenticationError(
                "Your platform session was idle for too long. Sign in again.",
                details={"reason": "platform_session_expired", "limit": "idle"},
            )
        if (now - verified_at).total_seconds() > absolute_limit:
            raise AuthenticationError(
                "Your platform session reached its absolute limit. Sign in again.",
                details={"reason": "platform_session_expired", "limit": "absolute"},
            )

    # -- reach ----------------------------------------------------------
    def may_read_organization(self, organization_id: uuid.UUID | None) -> bool:
        if organization_id is None:
            return True
        if self.sees_all_records:
            return True
        return organization_id in self.organization_ids

    def may_read_parties(self, organization_ids: set[uuid.UUID]) -> bool:
        if self.sees_all_records:
            return True
        return bool(self.organization_ids & organization_ids)

    def require_parties(self, organization_ids: set[uuid.UUID]) -> None:
        if self.may_read_parties(organization_ids):
            return
        raise ForbiddenError(
            "Your organisation is not a counterparty to this record.",
            details={"reason": "organisation_scope"},
        )

    def require_party_scope(self, allowed: set[uuid.UUID]) -> None:
        """Raise 403 unless the principal may act for one of these organisations."""
        if self.platform_scope:
            return
        if self.organization_ids & allowed:
            return
        raise ForbiddenError(
            "Your organisation is not authorised to act on this record.",
            details={"reason": "organisation_scope"},
        )


def active_memberships(db: Session, user_id: uuid.UUID) -> list[OrganizationMembership]:
    """Memberships that can actually authorise a request.

    A membership row stays ``active`` when its organisation is suspended: the
    tenant, not the person, is suspended, and the membership must survive so
    reactivation restores access without an administrator rebuilding the roster.
    Filtering here is what makes suspension effective everywhere at once, since
    login, organisation switching and per-request authentication all resolve
    authority through this one function.
    """
    from app.db.enums import OrganizationStatus
    from app.db.models.organization import Organization

    return list(
        db.scalars(
            select(OrganizationMembership)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                Organization.status == OrganizationStatus.ACTIVE,
            )
            .options(joinedload(OrganizationMembership.user))
            .order_by(OrganizationMembership.created_at)
        ).all()
    )


def _pick_membership(
    memberships: list[OrganizationMembership], active_organization_id: uuid.UUID | None
) -> OrganizationMembership | None:
    if not memberships:
        return None
    if active_organization_id is not None:
        for membership in memberships:
            if membership.organization_id == active_organization_id:
                return membership
    return memberships[0]


def build_principal(
    db: Session,
    *,
    user: User,
    auth_session: AuthSession | None = None,
    membership: OrganizationMembership | None = None,
    memberships: list[OrganizationMembership] | None = None,
) -> ActorContext:
    """Assemble the request principal from authoritative database rows."""
    owned = memberships if memberships is not None else active_memberships(db, user.id)
    if membership is None and auth_session is not None:
        membership = _pick_membership(owned, auth_session.organization_id)
    if membership is None:
        membership = _pick_membership(owned, None)

    organization = None
    if membership is not None:
        # ``joinedload`` is not used here on purpose: the organisation is needed
        # for naming only, and a miss must not fabricate context.
        from app.db.models.organization import Organization

        organization = db.get(Organization, membership.organization_id)

    role = ActorRole.ADMIN if user.is_platform_admin else (
        _ROLE_MAP.get(membership.role, ActorRole.VIEWER) if membership else ActorRole.VIEWER
    )
    permissions = permissions_for(
        membership.role if membership else None, platform_admin=user.is_platform_admin
    )

    return ActorContext(
        actor_id=str(user.id),
        display_name=user.full_name,
        role=role,
        organization_id=organization.id if organization else None,
        organization_slug=organization.slug if organization else None,
        organization_name=organization.name if organization else None,
        user_id=user.id,
        email=user.email,
        session_id=auth_session.id if auth_session else None,
        membership_id=membership.id if membership else None,
        membership_role=membership.role if membership else None,
        membership_scope=(
            membership.scope if membership else MembershipScope.ORGANIZATION
        ),
        organization_ids=frozenset(
            row.organization_id for row in owned if row.status == MembershipStatus.ACTIVE
        ),
        permissions=permissions,
        is_platform_admin=user.is_platform_admin,
        is_development=False,
        # A password that the user has never chosen themselves — an initial
        # credential issued by an operator or a provisioning script — must be
        # replaced before the workspace opens. ``password_changed_at`` is
        # written only when the account owner sets their own password, so no
        # extra column or migration is needed to express the state.
        must_change_password=user.password_changed_at is None,
        session_expires_at=as_utc(auth_session.access_expires_at) if auth_session else None,
        mfa_verified=bool(auth_session and auth_session.mfa_verified_at),
        mfa_method=auth_session.mfa_method if auth_session else None,
        mfa_verified_at=as_utc(auth_session.mfa_verified_at) if auth_session else None,
        session_created_at=as_utc(auth_session.created_at) if auth_session else None,
        session_last_seen_at=as_utc(auth_session.last_seen_at) if auth_session else None,
    )
