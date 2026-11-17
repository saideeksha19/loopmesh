"""Authentication, invitations and session endpoints.

Cookie-based sessions are the primary browser transport; bearer access tokens are
also accepted by request dependencies. Passwords and raw tokens are never
returned, logged or stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select

from app.api.deps import ActorDep, DbSession
from app.core.actors import active_memberships, build_principal
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import Permission
from app.core import security_limiter
from app.core.rate_limit import account_key, client_key
from app.core.security import (
    CSRF_TOKEN_BYTES,
    hash_password,
    hash_token,
    generate_token,
    normalise_email,
    tokens_match,
    validate_password_strength,
    verify_password,
)
from app.core.sessions import (
    clear_session_cookies,
    find_by_access_token,
    issue_session,
    revoke,
    revoke_all_for_user,
    rotate,
    set_session_cookies,
    utcnow,
)
from app.db.enums import (
    AuditSeverity,
    InvitationStatus,
    MembershipRole,
    MembershipScope,
    MembershipStatus,
    OrganizationStatus,
)
from app.db.models.identity import AuthSession, Invitation, OrganizationMembership, PasswordResetToken, User
from app.db.models.organization import Organization
from app.schemas.auth import (
    AuthMessage,
    ChangePasswordRequest,
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationRead,
    LoginRequest,
    MeResponse,
    MembershipRead,
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaDisableRequest,
    MfaEnrollRequest,
    MfaEnrollResponse,
    MfaRegenerateRequest,
    MfaRegenerateResponse,
    MfaStatus,
    MfaFactorRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequested,
    SessionRead,
    SwitchOrganizationRequest,
)
from app.services import audit
from app.services import mfa as mfa_service

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_RESET_MESSAGE = "If the account exists, password reset instructions have been issued."


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _me_payload(
    session, user: User, auth_session, memberships, *, csrf_token: str | None = None
) -> MeResponse:
    principal = build_principal(
        session, user=user, auth_session=auth_session, memberships=memberships
    )
    membership_rows = []
    org_ids = [m.organization_id for m in memberships]
    orgs = (
        {
            row.id: row
            for row in session.scalars(
                select(Organization).where(Organization.id.in_(org_ids))
            ).all()
        }
        if org_ids
        else {}
    )
    for membership in memberships:
        org = orgs.get(membership.organization_id)
        membership_rows.append(
            MembershipRead(
                id=membership.id,
                organization_id=membership.organization_id,
                role=membership.role.value,
                scope=membership.scope.value,
                status=membership.status.value,
                organization_name=org.name if org else None,
                organization_slug=org.slug if org else None,
            )
        )
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        is_development=principal.is_development,
        must_change_password=principal.must_change_password,
        active_organization_id=principal.organization_id,
        active_role=principal.role.value,
        memberships=membership_rows,
        permissions=sorted(permission.value for permission in principal.permissions),
        session_expires_at=principal.session_expires_at,
        mfa_enrolled=user.mfa_enrolled_at is not None,
        mfa_verified=principal.mfa_verified,
        mfa_required=principal.is_platform_admin,
        mfa_enrollment_required=bool(
            principal.is_platform_admin and user.mfa_enrolled_at is None
        ),
        csrf_token=csrf_token,
    )


def _audit_auth(
    db,
    *,
    event_type: str,
    summary: str,
    actor: str = "system",
    actor_id: str | None = None,
    entity_type: str = "user",
    entity_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    severity: str | AuditSeverity = AuditSeverity.INFO,
    payload: dict | None = None,
) -> None:
    if isinstance(severity, str):
        try:
            severity = AuditSeverity(severity)
        except ValueError:
            severity = AuditSeverity.INFO
    audit.record_event(
        db,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        actor_id=actor_id,
        organization_id=organization_id,
        summary=summary,
        severity=severity,
        payload=payload or {},
    )


def _locked_until_as_utc(user: User) -> datetime | None:
    """``locked_until`` as an aware datetime (SQLite returns naive values)."""
    locked_until = user.locked_until
    if locked_until is None:
        return None
    if locked_until.tzinfo is None:
        return locked_until.replace(tzinfo=timezone.utc)
    return locked_until


def _is_locked(user: User, now: datetime) -> bool:
    locked_until = _locked_until_as_utc(user)
    return locked_until is not None and locked_until > now


def _reset_expired_lock(user: User, now: datetime) -> bool:
    """Clear a lock whose window has elapsed, so the next failure starts at one.

    The counter is only cleared on a successful login and when a lock expires
    here. Without the expiry reset it stays at the threshold, so the first wrong
    password after a lock lapses immediately re-locks the account for another
    full window.
    """
    locked_until = _locked_until_as_utc(user)
    if locked_until is None or locked_until > now:
        return False
    user.failed_login_attempts = 0
    user.locked_until = None
    return True


def _register_failure(db, user: User, *, email: str, now: datetime) -> None:
    user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
    locked = False
    if user.failed_login_attempts >= settings.auth_max_failed_logins:
        user.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
        locked = True
    _audit_auth(
        db,
        event_type="auth.login_failed",
        summary="Authentication failed.",
        actor=email,
        entity_id=user.id,
        severity="warning",
        payload={"outcome": "denied", "locked": locked},
    )


def _clear_failures(user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None


def _require_authz(actor, permission: Permission, *, operation: str, organization_id: uuid.UUID | None = None) -> None:
    if actor.has(permission):
        # Platform admins and platform-scoped principals may act across orgs when permitted;
        # org-scoped principals must act within their active organisation.
        if organization_id is not None and not actor.platform_scope:
            if actor.organization_id != organization_id and organization_id not in actor.organization_ids:
                raise ForbiddenError(
                    "You do not have access to this organisation.",
                    details={"reason": "organisation_scope"},
                )
        return
    raise ForbiddenError(
        "You do not have permission to perform this action.",
        details={"required_permission": permission.value, "operation": operation},
    )


def _load_invitation_by_token(db, token: str) -> Invitation | None:
    if not token:
        return None
    return db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))


#: Environments allowed to receive a raw invitation or password-reset token.
#: Staging is deliberately absent: it carries production-shaped data, so a
#: token returned there is a real credential. Anything not listed fails closed,
#: including environments this code has never heard of.
_DEV_DELIVERY_ENVIRONMENTS = frozenset({"development", "test"})


def _dev_delivery_allowed() -> bool:
    """Whether the local delivery adapter may return raw tokens.

    This is an allow-list, not ``not settings.is_production``: the latter
    silently grants the development convenience to every environment nobody
    thought about (staging most of all).
    """
    return settings.environment in _DEV_DELIVERY_ENVIRONMENTS


# ---------------------------------------------------------------------------
# login / logout / refresh / me / password / org switch
# ---------------------------------------------------------------------------

@router.post("/login", response_model=AuthMessage, summary="Authenticate and start a session")
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> AuthMessage:
    email = normalise_email(str(payload.email))
    now = utcnow()
    security_limiter.hit(
        db,
        key=account_key("login", email),
        limit=settings.auth_login_attempts_per_hour,
        window_seconds=3600,
    )
    security_limiter.hit(
        db,
        key=client_key(request, scope="login", principal=email),
        limit=settings.auth_login_attempts_per_hour,
        window_seconds=3600,
    )

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        _audit_auth(
            db,
            event_type="auth.login_failed",
            summary="Authentication failed.",
            actor=email,
            severity="warning",
            payload={"outcome": "denied", "known_account": False},
        )
        db.commit()
        raise AuthenticationError(GENERIC_LOGIN_ERROR, details={"reason": "invalid_credentials"})

    if not user.is_active:
        _audit_auth(
            db,
            event_type="auth.login_failed",
            summary="Authentication failed.",
            actor=email,
            entity_id=user.id,
            severity="warning",
            payload={"outcome": "denied", "reason": "account_inactive"},
        )
        db.commit()
        raise AuthenticationError(GENERIC_LOGIN_ERROR, details={"reason": "invalid_credentials"})

    # A lapsed lock is cleared before a new failure is counted, otherwise the
    # stale counter re-locks on the very next wrong password.
    _reset_expired_lock(user, now)

    locked = _is_locked(user, now)
    password_ok = verify_password(user.password_hash, payload.password)

    if not password_ok:
        if locked:
            # Bounded backoff: reject the guess, audit it, but never extend the
            # lock. An unauthenticated third party must not be able to hold an
            # account closed by spraying wrong passwords.
            _audit_auth(
                db,
                event_type="auth.login_failed",
                summary="Authentication failed.",
                actor=email,
                entity_id=user.id,
                severity="warning",
                payload={"outcome": "denied", "reason": "lockout_active"},
            )
        else:
            _register_failure(db, user, email=email, now=now)
        db.commit()
        raise AuthenticationError(GENERIC_LOGIN_ERROR, details={"reason": "invalid_credentials"})

    memberships = active_memberships(db, user.id)
    chosen_org = payload.organization_id
    if chosen_org is not None and all(m.organization_id != chosen_org for m in memberships):
        # Do not reveal org existence details beyond membership requirement.
        raise ForbiddenError(
            "You are not a member of the selected organisation.",
            details={"reason": "membership_required"},
        )

    _clear_failures(user)
    record, bundle = issue_session(
        db,
        user,
        organization_id=chosen_org or (memberships[0].organization_id if memberships else None),
        user_agent=request.headers.get("User-Agent"),
        ip=_client_ip(request),
        now=now,
    )
    user.last_login_at = now
    _audit_auth(
        db,
        event_type="auth.login_succeeded",
        summary="User signed in.",
        actor=str(user.id),
        actor_id=str(user.id),
        entity_id=user.id,
        organization_id=record.organization_id,
        payload={"session_id": str(record.id)},
    )
    db.commit()
    set_session_cookies(response, bundle)
    memberships = active_memberships(db, user.id)
    me = _me_payload(db, user, record, memberships, csrf_token=bundle.csrf_token)
    return AuthMessage(message="Signed in.", authenticated=True, user=me)


@router.post("/logout", response_model=AuthMessage, summary="Revoke the current session")
def logout(request: Request, response: Response, db: DbSession) -> AuthMessage:
    token = request.cookies.get(settings.auth_session_cookie)
    if token:
        record = find_by_access_token(db, token)
        if record is not None and record.revoked_at is None:
            revoke(db, record, reason="logout")
            _audit_auth(
                db,
                event_type="auth.logout",
                summary="User signed out.",
                actor=str(record.user_id),
                actor_id=str(record.user_id),
                entity_id=record.user_id,
                organization_id=record.organization_id,
                payload={"session_id": str(record.id)},
            )
            db.commit()
    clear_session_cookies(response)
    return AuthMessage(message="Signed out.", authenticated=False)


@router.post("/refresh", response_model=AuthMessage, summary="Rotate the session using the refresh cookie")
def refresh(request: Request, response: Response, db: DbSession) -> AuthMessage:
    refresh_token = request.cookies.get(settings.auth_refresh_cookie)
    if not refresh_token:
        raise AuthenticationError("Refresh token required.", details={"reason": "refresh_required"})

    result = rotate(
        db,
        refresh_token=refresh_token,
        user_agent=request.headers.get("User-Agent"),
        ip=_client_ip(request),
    )
    if not result.rotated:
        # Persist the decision (replay family revocation, expiry, inactive
        # account) before failing the request: a security state change must not
        # be discarded with the request transaction.
        db.commit()
        clear_session_cookies(response)
        raise AuthenticationError(
            "Your session can no longer be refreshed. Sign in again.",
            details={
                "reason": "refresh_reused" if result.reason == "replay" else "refresh_invalid"
            },
        )
    session_row, bundle = result.session, result.bundle
    _audit_auth(
        db,
        event_type="auth.refresh",
        summary="Session refreshed.",
        actor=str(session_row.user_id),
        actor_id=str(session_row.user_id),
        entity_id=session_row.user_id,
        organization_id=session_row.organization_id,
        payload={"session_id": str(session_row.id), "rotated": True},
    )
    db.commit()
    set_session_cookies(response, bundle)
    user = db.get(User, session_row.user_id)
    if user is None:
        raise AuthenticationError("Account not found.")
    memberships = active_memberships(db, user.id)
    me = _me_payload(db, user, session_row, memberships, csrf_token=bundle.csrf_token)
    return AuthMessage(message="Session refreshed.", authenticated=True, user=me)


@router.get("/me", response_model=MeResponse, summary="Current authenticated principal")
def me(actor: ActorDep, db: DbSession, request: Request) -> MeResponse:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    memberships = active_memberships(db, user.id)
    auth_session = db.get(AuthSession, actor.session_id) if actor.session_id else None
    csrf = request.cookies.get(settings.auth_csrf_cookie)
    return _me_payload(db, user, auth_session, memberships, csrf_token=csrf)


@router.post("/change-password", response_model=AuthMessage, summary="Change the current password")
def change_password(
    payload: ChangePasswordRequest, actor: ActorDep, response: Response, db: DbSession
) -> AuthMessage:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    if not verify_password(user.password_hash, payload.current_password):
        raise AuthenticationError("Current password is incorrect.", details={"field": "current_password"})
    validate_password_strength(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow()
    revoke_all_for_user(db, user.id, reason="password_changed")
    _audit_auth(
        db,
        event_type="auth.password_changed",
        summary="Password changed.",
        actor=str(user.id),
        actor_id=str(user.id),
        entity_id=user.id,
        organization_id=actor.organization_id,
    )
    db.commit()
    clear_session_cookies(response)
    return AuthMessage(message="Password changed. Sign in again.", authenticated=False)


@router.post("/switch-organization", response_model=MeResponse, summary="Set the active organisation for this session")
def switch_organization(
    payload: SwitchOrganizationRequest, actor: ActorDep, request: Request, db: DbSession
) -> MeResponse:
    if actor.session_id is None or actor.user_id is None:
        raise AuthenticationError("Session required.")
    memberships = active_memberships(db, actor.user_id)
    if all(m.organization_id != payload.organization_id for m in memberships):
        raise ForbiddenError(
            "You are not a member of that organisation.",
            details={"reason": "membership_required"},
        )
    auth_session = db.get(AuthSession, actor.session_id)
    if auth_session is None:
        raise AuthenticationError("Session not found.")
    auth_session.organization_id = payload.organization_id
    _audit_auth(
        db,
        event_type="auth.organization_switched",
        summary="Active organisation changed.",
        actor=str(actor.user_id),
        actor_id=str(actor.user_id),
        entity_id=actor.user_id,
        organization_id=payload.organization_id,
    )
    db.commit()
    user = db.get(User, actor.user_id)
    csrf = request.cookies.get(settings.auth_csrf_cookie)
    return _me_payload(db, user, auth_session, memberships, csrf_token=csrf)


# ---------------------------------------------------------------------------
# session management
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[SessionRead], summary="List sessions for the authenticated user")
def list_sessions(actor: ActorDep, db: DbSession) -> list[SessionRead]:
    if actor.user_id is None:
        raise AuthenticationError("Authentication required.")
    rows = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == actor.user_id)
        .order_by(AuthSession.created_at.desc())
    ).all()
    out: list[SessionRead] = []
    for row in rows:
        out.append(
            SessionRead(
                id=row.id,
                organization_id=row.organization_id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                access_expires_at=row.access_expires_at,
                refresh_expires_at=row.refresh_expires_at,
                revoked_at=row.revoked_at,
                revoked_reason=row.revoked_reason,
                is_current=(row.id == actor.session_id),
                user_agent=row.user_agent,
                mfa_verified_at=row.mfa_verified_at,
            )
        )
    return out


@router.post("/sessions/{session_id}/revoke", response_model=AuthMessage, summary="Revoke a specific session")
def revoke_session(session_id: uuid.UUID, actor: ActorDep, request: Request, response: Response, db: DbSession) -> AuthMessage:
    if actor.user_id is None:
        raise AuthenticationError("Authentication required.")
    row = db.get(AuthSession, session_id)
    if row is None or row.user_id != actor.user_id:
        # Do not reveal existence of another user's session.
        raise NotFoundError("Session not found.")
    if row.revoked_at is None:
        revoke(db, row, reason="user_revoked")
        _audit_auth(
            db,
            event_type="auth.session_revoked",
            summary="Session revoked.",
            actor=str(actor.user_id),
            actor_id=str(actor.user_id),
            entity_id=actor.user_id,
            organization_id=row.organization_id,
            payload={"session_id": str(row.id)},
        )
        db.commit()
    # If the current session was revoked, clear cookies.
    if row.id == actor.session_id:
        clear_session_cookies(response)
        return AuthMessage(message="Current session revoked.", authenticated=False)
    return AuthMessage(message="Session revoked.", authenticated=True)


@router.post("/sessions/revoke-others", response_model=AuthMessage, summary="Revoke all other sessions")
def revoke_other_sessions(actor: ActorDep, db: DbSession) -> AuthMessage:
    if actor.user_id is None or actor.session_id is None:
        raise AuthenticationError("Authentication required.")
    rows = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == actor.user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.id != actor.session_id,
        )
    ).all()
    for row in rows:
        revoke(db, row, reason="revoked_other_sessions")
    _audit_auth(
        db,
        event_type="auth.session_revoked",
        summary="Other sessions revoked.",
        actor=str(actor.user_id),
        actor_id=str(actor.user_id),
        entity_id=actor.user_id,
        organization_id=actor.organization_id,
        payload={"revoked_count": len(rows), "kept_session_id": str(actor.session_id)},
    )
    db.commit()
    return AuthMessage(message="Other sessions revoked.", authenticated=True)


# ---------------------------------------------------------------------------
# platform operator MFA
# ---------------------------------------------------------------------------

def _mfa_status(actor: ActorDep, db: DbSession) -> MfaStatus:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    payload = mfa_service.status(db, user, session_verified=actor.mfa_verified)
    payload["method"] = actor.mfa_method
    return MfaStatus(**payload)


def _mfa_limiter_hit(db: DbSession, actor: ActorDep, request: Request, *, operation: str) -> None:
    """Consume one shared MFA attempt for this account and operation.

    The shared table is authoritative across workers. If it is unavailable the
    endpoint fails closed; there is no per-process allowance for platform MFA.
    """
    principal = str(actor.user_id) if actor.user_id else "anonymous"
    security_limiter.hit(
        db,
        key=account_key(f"mfa:{operation}", principal),
        limit=settings.mfa_attempts_per_5_minutes,
        window_seconds=300,
    )
    security_limiter.hit(
        db,
        key=client_key(request, scope=f"mfa:{operation}", principal=principal),
        limit=settings.mfa_attempts_per_5_minutes,
        window_seconds=300,
    )


def _audit_mfa(
    db,
    actor: ActorDep,
    *,
    event_type: str,
    summary: str,
    severity: AuditSeverity = AuditSeverity.INFO,
    reason: str | None = None,
    method: str | None = None,
) -> None:
    _audit_auth(
        db,
        event_type=event_type,
        summary=summary,
        actor=str(actor.user_id),
        actor_id=str(actor.user_id) if actor.user_id else None,
        entity_id=actor.user_id,
        organization_id=actor.organization_id,
        severity=severity,
        # Never include the submitted code, the TOTP secret or a recovery code.
        payload={
            "session_id": str(actor.session_id) if actor.session_id else None,
            "reason": reason,
            "method": method,
        },
    )


@router.get("/mfa/status", response_model=MfaStatus, summary="Platform MFA status")
def mfa_status(actor: ActorDep, db: DbSession) -> MfaStatus:
    return _mfa_status(actor, db)


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    summary="Begin TOTP enrolment for a platform operator",
)
def mfa_enroll(
    payload: MfaEnrollRequest,
    actor: ActorDep,
    request: Request,
    response: Response,
    db: DbSession,
) -> MfaEnrollResponse:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    if not (user.is_platform_admin and Permission.PLATFORM_ADMIN in actor.permissions):
        raise ForbiddenError(
            "Only platform operators can enrol a platform second factor.",
            details={"reason": "platform_scope_required"},
        )
    if not verify_password(user.password_hash, payload.current_password):
        _audit_mfa(
            db,
            actor,
            event_type="auth.mfa.enrollment_failed",
            summary="MFA enrolment refused: password re-authentication failed.",
            severity=AuditSeverity.WARNING,
            reason="invalid_password",
        )
        db.commit()
        raise AuthenticationError(
            "Current password is incorrect.", details={"field": "current_password"}
        )
    if user.mfa_enrolled_at is not None:
        raise ConflictError(
            "A confirmed second factor already exists. Remove it before enrolling again.",
            details={"reason": "already_enrolled"},
        )
    _mfa_limiter_hit(db, actor, request, operation="enroll")

    secret, uri = mfa_service.start_enrollment(user)
    _audit_mfa(
        db,
        actor,
        event_type="auth.mfa.enrollment_started",
        summary="Platform operator started TOTP enrolment.",
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return MfaEnrollResponse(
        secret=secret,
        provisioning_uri=uri,
        message=(
            "Add the secret to an authenticator app, then confirm with a current code. "
            "The secret is shown only during enrolment."
        ),
    )


@router.post(
    "/mfa/confirm",
    response_model=MfaConfirmResponse,
    summary="Confirm TOTP enrolment and issue recovery codes",
)
def mfa_confirm(
    payload: MfaConfirmRequest,
    actor: ActorDep,
    request: Request,
    response: Response,
    db: DbSession,
) -> MfaConfirmResponse:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    _mfa_limiter_hit(db, actor, request, operation="confirm")

    now = utcnow()
    if user.mfa_enrolled_at is not None:
        raise ConflictError(
            "This account already has a confirmed second factor.",
            details={"reason": "already_enrolled"},
        )
    codes = mfa_service.confirm_enrollment(db, user, payload.code, now=now)
    if codes is None:
        _audit_mfa(
            db,
            actor,
            event_type="auth.mfa.enrollment_failed",
            summary="MFA enrolment confirmation failed.",
            severity=AuditSeverity.WARNING,
            reason="invalid_code",
        )
        db.commit()
        raise AuthenticationError(
            "That code is not valid. Check the authenticator clock and try again.",
            details={"reason": "invalid_code"},
        )

    mfa_service.mark_session_verified(db, actor.session_id, mfa_service.MfaMethod.TOTP, now=now)
    _audit_mfa(
        db,
        actor,
        event_type="auth.mfa.enrolled",
        summary="Platform operator confirmed TOTP enrolment.",
        method="totp",
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return MfaConfirmResponse(
        message=(
            "Second factor confirmed. Store these recovery codes now; they are shown only once."
        ),
        recovery_codes=codes,
        enrolled_at=now,
    )


@router.post(
    "/mfa/verify",
    response_model=MfaStatus,
    summary="Verify a second factor for this session",
)
def mfa_verify(
    payload: MfaFactorRequest,
    actor: ActorDep,
    request: Request,
    db: DbSession,
) -> MfaStatus:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    if actor.session_id is None:
        raise AuthenticationError(
            "Sign in with a browser session to verify a second factor.",
            details={"reason": "session_required"},
        )
    if actor.mfa_verified:
        return _mfa_status(actor, db)
    _mfa_limiter_hit(db, actor, request, operation="verify")

    now = utcnow()
    result = mfa_service.verify_factor(
        db,
        user,
        code=payload.code,
        recovery_code=payload.recovery_code,
        now=now,
    )
    if not result.ok:
        _audit_mfa(
            db,
            actor,
            event_type="auth.mfa.verification_failed",
            summary="Platform MFA verification failed.",
            severity=AuditSeverity.WARNING,
            reason=result.reason,
            method="recovery" if payload.recovery_code else "totp",
        )
        # Failure counters and lockout must survive the rejected request.
        db.commit()
        if result.locked:
            raise AuthenticationError(
                "Too many invalid codes. This account is temporarily locked.",
                details={
                    "reason": "mfa_locked",
                    "locked_until": mfa_service.as_utc(user.mfa_locked_until).isoformat()
                    if user.mfa_locked_until
                    else None,
                },
            )
        raise AuthenticationError(
            "That second factor was not accepted.",
            details={"reason": result.reason},
        )

    mfa_service.mark_session_verified(db, actor.session_id, result.method, now=now)
    _audit_mfa(
        db,
        actor,
        event_type=(
            "auth.mfa.recovery_used"
            if result.method == mfa_service.MfaMethod.RECOVERY
            else "auth.mfa.verified"
        ),
        summary=(
            "Platform operator signed in with a recovery code."
            if result.method == mfa_service.MfaMethod.RECOVERY
            else "Platform operator verified a second factor."
        ),
        severity=(
            AuditSeverity.WARNING
            if result.method == mfa_service.MfaMethod.RECOVERY
            else AuditSeverity.INFO
        ),
        method=result.method.value if result.method else None,
    )
    db.commit()
    actor = build_principal(
        db,
        user=user,
        auth_session=db.get(AuthSession, actor.session_id),
        memberships=active_memberships(db, user.id),
    )
    return _mfa_status(actor, db)


@router.post(
    "/mfa/recovery-codes/regenerate",
    response_model=MfaRegenerateResponse,
    summary="Replace recovery codes after re-authentication",
)
def mfa_regenerate_recovery_codes(
    payload: MfaRegenerateRequest,
    actor: ActorDep,
    request: Request,
    response: Response,
    db: DbSession,
) -> MfaRegenerateResponse:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    if not verify_password(user.password_hash, payload.current_password):
        raise AuthenticationError(
            "Current password is incorrect.", details={"field": "current_password"}
        )
    _mfa_limiter_hit(db, actor, request, operation="regenerate")
    result = mfa_service.verify_factor(
        db,
        user,
        code=payload.code,
        recovery_code=payload.recovery_code,
    )
    if not result.ok:
        _audit_mfa(
            db,
            actor,
            event_type="auth.mfa.recovery_regeneration_failed",
            summary="Recovery-code regeneration refused.",
            severity=AuditSeverity.WARNING,
            reason=result.reason,
        )
        db.commit()
        raise AuthenticationError(
            "That second factor was not accepted.", details={"reason": result.reason}
        )
    codes = mfa_service.regenerate_recovery_codes(db, user)
    _audit_mfa(
        db,
        actor,
        event_type="auth.mfa.recovery_regenerated",
        summary="Recovery codes replaced.",
        severity=AuditSeverity.WARNING,
        method=result.method.value if result.method else None,
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return MfaRegenerateResponse(
        message="Previous recovery codes are now invalid. Store the new codes securely.",
        recovery_codes=codes,
    )


@router.post(
    "/mfa/disable",
    response_model=AuthMessage,
    summary="Remove MFA after password and factor re-authentication",
)
def mfa_disable(
    payload: MfaDisableRequest,
    actor: ActorDep,
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthMessage:
    user = db.get(User, actor.user_id) if actor.user_id else None
    if user is None:
        raise AuthenticationError("Account not found.")
    if not verify_password(user.password_hash, payload.current_password):
        raise AuthenticationError(
            "Current password is incorrect.", details={"field": "current_password"}
        )
    _mfa_limiter_hit(db, actor, request, operation="disable")
    result = mfa_service.verify_factor(
        db,
        user,
        code=payload.code,
        recovery_code=payload.recovery_code,
    )
    if not result.ok:
        _audit_mfa(
            db,
            actor,
            event_type="auth.mfa.disable_failed",
            summary="MFA removal refused.",
            severity=AuditSeverity.WARNING,
            reason=result.reason,
        )
        db.commit()
        raise AuthenticationError(
            "That second factor was not accepted.", details={"reason": result.reason}
        )

    mfa_service.clear_enrollment(db, user)
    revoked = revoke_all_for_user(db, user.id, reason="mfa_disabled")
    _audit_mfa(
        db,
        actor,
        event_type="auth.mfa.disabled",
        summary="Platform MFA removed; all sessions were revoked.",
        severity=AuditSeverity.WARNING,
        method=result.method.value if result.method else None,
    )
    db.commit()
    clear_session_cookies(response)
    return AuthMessage(
        message=(
            "Second factor removed and every session revoked. Sign in again; "
            f"{revoked} session(s) were revoked."
        ),
        authenticated=False,
    )


# ---------------------------------------------------------------------------
# invitations
# ---------------------------------------------------------------------------

def _invitation_to_read(db, invitation: Invitation, *, token: str | None = None) -> InvitationRead:
    org = db.get(Organization, invitation.organization_id)
    return InvitationRead(
        id=invitation.id,
        email=invitation.email,
        organization_id=invitation.organization_id,
        organization_name=org.name if org else None,
        role=invitation.role.value,
        scope=invitation.scope.value,
        status=invitation.status.value,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        invited_by_user_id=invitation.invited_by_user_id,
        accepted_at=invitation.accepted_at,
        note=invitation.note,
        delivery_token=token if token and _dev_delivery_allowed() else None,
    )


@router.post(
    "/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organisation invitation",
)
def create_invitation(
    payload: InvitationCreateRequest, actor: ActorDep, db: DbSession
) -> InvitationRead:
    # Only platform administrators or org administrators (within their org) may invite.
    if not (actor.is_platform_admin or actor.has(Permission.INVITATION_MANAGE)):
        raise ForbiddenError(
            "You do not have permission to invite members.",
            details={"required_permission": Permission.INVITATION_MANAGE.value},
        )

    org = db.get(Organization, payload.organization_id)
    if org is None:
        raise NotFoundError("Organisation not found.")

    # A suspended tenant must not grow its roster: invitations created during a
    # suspension would become live links the moment it is reactivated, without
    # anyone reviewing them.
    if org.status != OrganizationStatus.ACTIVE:
        raise ConflictError(
            "This organisation is suspended. Reactivate it before inviting members.",
            details={"reason": "organization_suspended", "organization_id": str(org.id)},
        )

    if not actor.platform_scope and actor.organization_id != payload.organization_id:
        raise ForbiddenError(
            "You cannot invite members into another organisation.",
            details={"reason": "organisation_scope"},
        )

    try:
        role = MembershipRole(payload.role)
    except ValueError as exc:
        raise ValidationError("Invalid membership role.", details={"field": "role"}) from exc
    try:
        scope = MembershipScope(payload.scope)
    except ValueError as exc:
        raise ValidationError("Invalid membership scope.", details={"field": "scope"}) from exc

    # Prevent privilege escalation: non-platform actors cannot grant platform scope
    # or create platform-admin-equivalent grants. Org admins may only invite roles
    # they are permitted to manage within their organisation.
    if scope == MembershipScope.PLATFORM and not actor.is_platform_admin:
        raise ForbiddenError(
            "Only a platform administrator can grant platform scope.",
            details={"reason": "privilege_escalation"},
        )
    if not actor.is_platform_admin and role == MembershipRole.ORG_ADMIN and not actor.has(Permission.MEMBER_MANAGE):
        raise ForbiddenError(
            "You cannot assign this role.",
            details={"reason": "privilege_escalation"},
        )

    email = normalise_email(str(payload.email))
    now = utcnow()
    expires_at = now + timedelta(days=settings.auth_invitation_ttl_days)

    # Revoke any existing pending invitation for the same email+org to avoid ambiguity.
    existing = db.scalars(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.organization_id == payload.organization_id,
            Invitation.status == InvitationStatus.PENDING,
        )
    ).all()
    for row in existing:
        row.status = InvitationStatus.REVOKED

    token = generate_token(48)
    invitation = Invitation(
        email=email,
        organization_id=payload.organization_id,
        role=role,
        scope=scope,
        status=InvitationStatus.PENDING,
        token_hash=hash_token(token),
        expires_at=expires_at,
        invited_by_user_id=actor.user_id,
        note=payload.note,
    )
    db.add(invitation)
    db.flush()

    _audit_auth(
        db,
        event_type="invitation.created",
        summary="Invitation created.",
        actor=str(actor.user_id) if actor.user_id else actor.actor_id,
        actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
        entity_type="invitation",
        entity_id=invitation.id,
        organization_id=invitation.organization_id,
        payload={"role": role.value, "scope": scope.value, "expires_at": expires_at.isoformat()},
    )
    db.commit()
    return _invitation_to_read(db, invitation, token=token)


@router.get(
    "/invitations",
    response_model=list[InvitationRead],
    summary="List invitations the caller may administer",
)
def list_invitations(
    actor: ActorDep,
    db: DbSession,
    invitation_status: str | None = Query(default=None, alias="status", max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[InvitationRead]:
    """Organisation-scoped invitation register.

    Only an administrator of the organisation may read it, and never across
    tenants: a platform-scoped principal is the single documented exception.
    """
    if not (actor.is_platform_admin or actor.has(Permission.INVITATION_MANAGE)):
        raise ForbiddenError(
            "You do not have permission to view invitations.",
            details={"required_permission": Permission.INVITATION_MANAGE.value},
        )
    if not actor.platform_scope and actor.organization_id is None:
        raise ForbiddenError(
            "Select an organisation before managing invitations.",
            details={"reason": "organization_context_required"},
        )

    statement = select(Invitation).order_by(Invitation.created_at.desc()).limit(limit)
    if not actor.platform_scope:
        statement = statement.where(Invitation.organization_id == actor.organization_id)
    if invitation_status:
        try:
            wanted = InvitationStatus(invitation_status)
        except ValueError as exc:
            raise ValidationError(
                "Unknown invitation status.", details={"field": "status"}
            ) from exc
        statement = statement.where(Invitation.status == wanted)
    return [_invitation_to_read(db, row) for row in db.scalars(statement).all()]


@router.get(
    "/invitations/preview",
    response_model=InvitationRead,
    summary="Preview an invitation from its emailed token",
)
def preview_invitation(db: DbSession, token: str = Query(min_length=16, max_length=512)) -> InvitationRead:
    """Describe an invitation to the person holding its token.

    Unauthenticated by necessity — the invitee has no account yet — and
    deliberately silent about anything but the invitation the token names. The
    token is never echoed back and the invitation is not consumed here.
    """
    invitation = _load_invitation_by_token(db, token)
    if invitation is None:
        raise NotFoundError("Invitation not found.", details={"reason": "invalid_invitation"})

    read = _invitation_to_read(db, invitation)
    expires = read.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if read.status == InvitationStatus.PENDING.value and expires <= utcnow():
        read.status = "expired"
    return read


@router.post(
    "/invitations/accept",
    response_model=AuthMessage,
    summary="Accept an invitation and create/activate membership",
)
def accept_invitation(
    payload: InvitationAcceptRequest, request: Request, response: Response, db: DbSession
) -> AuthMessage:
    now = utcnow()
    invitation = _load_invitation_by_token(db, payload.token)
    if invitation is None:
        raise AuthenticationError("Invitation is invalid or has expired.", details={"reason": "invalid_invitation"})

    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if invitation.status != InvitationStatus.PENDING or expires <= now:
        if invitation.status == InvitationStatus.PENDING and expires <= now:
            invitation.status = InvitationStatus.REVOKED
            db.commit()
        raise AuthenticationError("Invitation is invalid or has expired.", details={"reason": "invalid_invitation"})

    organisation = db.get(Organization, invitation.organization_id)
    if organisation is not None and organisation.status != OrganizationStatus.ACTIVE:
        # The invitee holds a valid token but the tenant is not open. Do not
        # create the account or membership: reactivation should restore access
        # deliberately, not through an invitation consumed while suspended.
        raise ConflictError(
            "This organisation is not accepting members at the moment.",
            details={"reason": "organization_suspended"},
        )

    validate_password_strength(payload.password)
    full_name = " ".join(payload.full_name.split()).strip()
    if len(full_name) < 2:
        raise ValidationError("A full name is required.", details={"field": "full_name"})

    email = normalise_email(invitation.email)
    user = db.scalar(select(User).where(User.email == email))
    created_user = False
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(payload.password),
            is_active=True,
            is_platform_admin=False,
            # The invitee chose this password, so no forced rotation applies.
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        created_user = True
    else:
        # Existing user: allow joining an additional organisation; do not create a duplicate.
        # Password in acceptance is required for proof-of-possession when creating a new account only.
        if not user.is_active:
            raise AuthenticationError("This account is not active.", details={"reason": "account_inactive"})
        # If user exists, keep their existing password/name; acceptance still grants membership.
        if not verify_password(user.password_hash, payload.password):
            # For existing users, require their current password to accept.
            raise AuthenticationError(
                "Invitation acceptance requires your current account password.",
                details={"reason": "invalid_credentials"},
            )

    # Create or activate membership for this organisation.
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == invitation.organization_id,
        )
    )
    accept_ts = utcnow()
    if membership is None:
        membership = OrganizationMembership(
            user_id=user.id,
            organization_id=invitation.organization_id,
            role=invitation.role,
            scope=invitation.scope,
            status=MembershipStatus.ACTIVE,
            invited_by_user_id=invitation.invited_by_user_id,
            invitation_id=invitation.id,
            accepted_at=accept_ts,
            created_at=accept_ts,
            updated_at=accept_ts,
        )
        db.add(membership)
    else:
        # Do not self-escalate beyond the invitation; apply invited role/scope.
        membership.role = invitation.role
        membership.scope = invitation.scope
        membership.status = MembershipStatus.ACTIVE
        membership.invited_by_user_id = invitation.invited_by_user_id
        membership.invitation_id = invitation.id
        membership.accepted_at = accept_ts

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_by_user_id = user.id
    invitation.accepted_at = now

    if created_user:
        _audit_auth(
            db,
            event_type="membership.created",
            summary="User account and membership created via invitation.",
            actor=str(user.id),
            actor_id=str(user.id),
            entity_id=user.id,
            entity_type="membership",
            organization_id=invitation.organization_id,
            payload={"invitation_id": str(invitation.id), "role": invitation.role.value},
        )
    else:
        _audit_auth(
            db,
            event_type="membership.changed",
            summary="Membership activated via invitation.",
            actor=str(user.id),
            actor_id=str(user.id),
            entity_id=membership.id,
            entity_type="membership",
            organization_id=invitation.organization_id,
            payload={"invitation_id": str(invitation.id), "role": invitation.role.value},
        )

    _audit_auth(
        db,
        event_type="invitation.accepted",
        summary="Invitation accepted.",
        actor=str(user.id),
        actor_id=str(user.id),
        entity_type="invitation",
        entity_id=invitation.id,
        organization_id=invitation.organization_id,
    )

    record, bundle = issue_session(
        db,
        user,
        organization_id=invitation.organization_id,
        user_agent=request.headers.get("User-Agent"),
        ip=_client_ip(request),
        now=now,
    )
    db.commit()
    set_session_cookies(response, bundle)
    memberships = active_memberships(db, user.id)
    me = _me_payload(db, user, record, memberships, csrf_token=bundle.csrf_token)
    return AuthMessage(message="Invitation accepted.", authenticated=True, user=me)


@router.post(
    "/invitations/{invitation_id}/revoke",
    response_model=InvitationRead,
    summary="Revoke a pending invitation",
)
def revoke_invitation(invitation_id: uuid.UUID, actor: ActorDep, db: DbSession) -> InvitationRead:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")

    if not (actor.is_platform_admin or actor.has(Permission.INVITATION_MANAGE)):
        raise ForbiddenError("You do not have permission to revoke invitations.")
    if not actor.platform_scope and actor.organization_id != invitation.organization_id:
        raise ForbiddenError("You cannot revoke invitations for another organisation.")

    if invitation.status == InvitationStatus.PENDING:
        invitation.status = InvitationStatus.REVOKED
        _audit_auth(
            db,
            event_type="invitation.revoked",
            summary="Invitation revoked.",
            actor=str(actor.user_id) if actor.user_id else actor.actor_id,
            actor_id=str(actor.user_id) if actor.user_id else actor.actor_id,
            entity_type="invitation",
            entity_id=invitation.id,
            organization_id=invitation.organization_id,
        )
        db.commit()
    return _invitation_to_read(db, invitation)


# ---------------------------------------------------------------------------
# password reset
# ---------------------------------------------------------------------------

@router.post("/forgot-password", response_model=PasswordResetRequested, summary="Request a password reset")
def forgot_password(payload: PasswordResetRequest, request: Request, db: DbSession) -> PasswordResetRequested:
    email = normalise_email(str(payload.email))
    security_limiter.hit(
        db,
        key=account_key("password_reset", email),
        limit=settings.auth_reset_attempts_per_hour,
        window_seconds=3600,
    )
    security_limiter.hit(
        db,
        key=client_key(request, scope="password_reset", principal=email),
        limit=settings.auth_reset_attempts_per_hour,
        window_seconds=3600,
    )

    now = utcnow()
    user = db.scalar(select(User).where(User.email == email))
    delivery_token: str | None = None

    # Always record the request attempt in a non-identifying way is handled by generic response;
    # only persist/audit a token when the account exists.
    if user is not None and user.is_active:
        token = generate_token(48)
        row = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(minutes=settings.auth_reset_ttl_minutes),
            requested_ip_hash=None,
        )
        db.add(row)
        _audit_auth(
            db,
            event_type="auth.password_reset_requested",
            summary="Password reset requested.",
            actor=str(user.id),
            actor_id=str(user.id),
            entity_id=user.id,
            payload={"reset_token_id": str(row.id)},
        )
        if _dev_delivery_allowed():
            # Development-only delivery adapter: token returned for local testing,
            # never in production and never logged.
            delivery_token = token
    else:
        _audit_auth(
            db,
            event_type="auth.password_reset_requested",
            summary="Password reset requested.",
            actor=email,
            severity="info",
            payload={"known_account": False},
        )

    db.commit()
    return PasswordResetRequested(message=GENERIC_RESET_MESSAGE, delivery_token=delivery_token)


@router.post("/reset-password", response_model=AuthMessage, summary="Reset a password with a token")
def reset_password(payload: PasswordResetConfirm, request: Request, response: Response, db: DbSession) -> AuthMessage:
    now = utcnow()
    security_limiter.hit(
        db,
        key=client_key(request, scope="password_reset_confirm"),
        limit=settings.auth_reset_attempts_per_hour,
        window_seconds=3600,
    )

    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(payload.token))
    )
    if row is None:
        raise AuthenticationError("Reset token is invalid or has expired.", details={"reason": "invalid_reset_token"})

    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if row.used_at is not None or expires <= now:
        raise AuthenticationError("Reset token is invalid or has expired.", details={"reason": "invalid_reset_token"})

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Reset token is invalid or has expired.", details={"reason": "invalid_reset_token"})

    validate_password_strength(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = now
    row.used_at = now
    revoke_all_for_user(db, user.id, reason="password_reset")

    _audit_auth(
        db,
        event_type="auth.password_reset_completed",
        summary="Password reset completed.",
        actor=str(user.id),
        actor_id=str(user.id),
        entity_id=user.id,
        payload={"reset_token_id": str(row.id)},
    )
    db.commit()
    clear_session_cookies(response)
    return AuthMessage(message="Password has been reset. Sign in again.", authenticated=False)
