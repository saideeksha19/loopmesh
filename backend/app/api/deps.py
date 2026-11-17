"""Shared API dependencies: pagination, authentication and authorisation."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Sequence

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.actors import ActorContext, active_memberships, build_principal, utcnow
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.permissions import Permission
from app.core.sessions import (
    access_is_valid,
    as_utc,
    find_by_access_token,
)
from app.core.security import tokens_match
from app.db.enums import MembershipStatus
from app.db.models.identity import AuthSession, User
from app.db.session import get_db
from app.schemas.common import Page
from app.services import audit

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, ge=1, le=200, description="Items per page"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


DbSession = Annotated[Session, Depends(get_db)]
PageParams = Annotated[Pagination, Depends(pagination_params)]


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


def _session_token(request: Request) -> tuple[str | None, str]:
    """Return (token, transport) where transport is ``cookie`` or ``bearer``."""
    cookie = request.cookies.get(settings.auth_session_cookie)
    if cookie:
        return cookie, "cookie"
    bearer = _bearer_token(request)
    if bearer:
        return bearer, "bearer"
    return None, "none"


def _csrf_failure() -> AuthenticationError:
    return AuthenticationError(
        "This request is missing a valid CSRF token.",
        status_code=403,
        code="csrf_failed",
    )


def _check_csrf(request: Request, record: AuthSession) -> None:
    """Double-submit validation for cookie-authenticated mutations.

    Bearer-token clients are not vulnerable to CSRF (a browser cannot attach
    that header cross-site), so the check applies to cookies only.
    """
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get(settings.auth_csrf_header)
    cookie = request.cookies.get(settings.auth_csrf_cookie)
    if not header or not cookie or header != cookie:
        raise _csrf_failure()
    if not tokens_match(header, record.csrf_token_hash):
        raise _csrf_failure()


#: Endpoints an account awaiting a password change may still call. Everything
#: else is refused with ``password_change_required`` so the requirement cannot
#: be bypassed by calling the API directly instead of using the browser.
_PASSWORD_ROTATION_ALLOWED = frozenset(
    {
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/auth/logout",
        "/api/v1/auth/refresh",
        "/api/v1/auth/sessions",
        "/api/v1/auth/sessions/revoke-others",
    }
)


def password_rotation_allows(request: Request) -> bool:
    """Whether this path stays available while a rotation is outstanding."""
    path = request.url.path.rstrip("/") or "/"
    if path in _PASSWORD_ROTATION_ALLOWED:
        return True
    # ``/auth/sessions/{id}/revoke`` — revoking a device is part of securing
    # the account and never exposes workspace data.
    return path.startswith("/api/v1/auth/sessions/") and path.endswith("/revoke")


def enforce_password_rotation(request: Request, principal: ActorContext) -> None:
    """Refuse workspace access until an initial password has been replaced."""
    if not principal.must_change_password:
        return
    if password_rotation_allows(request):
        return
    raise ForbiddenError(
        "Choose a new password before continuing.",
        code="password_change_required",
        details={"reason": "password_change_required"},
    )


def get_actor(request: Request, session: DbSession) -> ActorContext:
    """Resolve the authenticated principal, or raise 401."""
    # The Phase 2A identity header is never a credential again. Rejecting it
    # loudly (rather than ignoring it) makes a stale client fail visibly.
    if request.headers.get("X-Actor-Id"):
        raise AuthenticationError(
            "The X-Actor-Id development header is no longer accepted. Sign in instead.",
            status_code=400,
            code="legacy_actor_header_rejected",
            details={"header": "X-Actor-Id"},
        )

    token, transport = _session_token(request)
    if token is None:
        raise AuthenticationError(
            "Authentication required.",
            details={"reason": "session_required"},
        )

    record = find_by_access_token(session, token)
    if record is None:
        raise AuthenticationError(
            "Your session is no longer valid.", details={"reason": "session_unknown"}
        )
    if record.revoked_at is not None:
        raise AuthenticationError(
            "Your session has been revoked.", details={"reason": "session_revoked"}
        )
    if not access_is_valid(record):
        raise AuthenticationError(
            "Your session has expired.", details={"reason": "session_expired"}
        )

    if transport == "cookie":
        _check_csrf(request, record)

    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError(
            "This account is not active.", details={"reason": "account_inactive"}
        )

    memberships = active_memberships(session, user.id)
    membership_ids = {row.organization_id for row in memberships}
    active = record.organization_id if record.organization_id in membership_ids else None

    principal = build_principal(
        session,
        user=user,
        auth_session=record,
        membership=next(
            (row for row in memberships if row.organization_id == active), None
        )
        if active
        else None,
        memberships=memberships,
    )

    # Touch the session at most once a minute; a write per request would be a
    # pointless load and a write-amplification vector.
    #
    # ``last_seen_at`` comes back naive from SQLite (the dialect does not keep
    # the offset), so it must be normalised before arithmetic or every
    # authenticated request fails with a naive/aware subtraction.
    last_seen = as_utc(record.last_seen_at)
    if last_seen is None or (utcnow() - last_seen).total_seconds() > 60:
        record.last_seen_at = utcnow()
        session.commit()

    enforce_password_rotation(request, principal)
    return principal


ActorDep = Annotated[ActorContext, Depends(get_actor)]


def require_permission(
    session: Session,
    actor: ActorContext,
    permission: Permission,
    *,
    operation: str,
    entity_type: str = "organization",
    entity_id: uuid.UUID | None = None,
) -> None:
    """Enforce a capability and journal the refusal when it is missing."""
    if actor.has(permission):
        return
    audit.record_authorization_failure(
        session,
        actor_id=actor.actor_id,
        actor_role=actor.role.value,
        organization_id=actor.organization_id,
        operation=operation,
        entity_type=entity_type,
        entity_id=entity_id,
        required=[permission.value],
    )
    session.commit()
    raise ForbiddenError(
        "You do not have permission to perform this action.",
        details={"required_permission": permission.value},
    )


def build_page(schema: type, items: Sequence[Any], total: int, pagination: Pagination) -> Page:
    """Wrap already-validated items in a pagination envelope."""
    pages = max(1, math.ceil(total / pagination.page_size)) if total else 0
    return Page[schema](  # type: ignore[index]
        items=list(items),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=pages,
        has_more=pagination.offset + len(items) < total,
    )
