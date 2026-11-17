"""Server-side session lifecycle.

A session is a row in ``auth_sessions`` holding three hashed secrets:

* an **access token** (15 minutes) identifying the session on every request,
* a **refresh token** (30 days) that can be exchanged exactly once,
* a **CSRF token** used for double-submit validation of cookie-authenticated
  state-changing requests.

Rotation and reuse detection
---------------------------
Refreshing revokes the old row and links it to its replacement through
``replaced_by_session_id``. Presenting an already-revoked refresh token is
treated as theft: every descendant session of that row is revoked, which logs
the attacker out as well as the victim. This is the standard mitigation for
refresh-token replay and it is why the old hash is never cleared.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_BYTES,
    CSRF_TOKEN_BYTES,
    REFRESH_TOKEN_BYTES,
    generate_token,
    hash_client_ip,
    hash_token,
)
from app.db.models.identity import AuthSession, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise before comparing."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class RotationResult:
    """Outcome of a refresh attempt.

    ``rotated`` is true for exactly one caller per refresh token: rotation is a
    single conditional ``UPDATE`` guarded by ``revoked_at IS NULL AND
    replaced_by_session_id IS NULL``, so concurrent callers cannot both win.
    """

    rotated: bool
    session: AuthSession | None = None
    bundle: TokenBundle | None = None
    reason: str = "unknown_token"
    revoked_count: int = 0


@dataclass(frozen=True, slots=True)
class TokenBundle:
    """Plaintext tokens handed to the browser exactly once."""

    session_id: uuid.UUID
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def issue_session(
    db: Session,
    user: User,
    *,
    organization_id: uuid.UUID | None,
    user_agent: str | None = None,
    ip: str | None = None,
    now: datetime | None = None,
    mfa_verified_at: datetime | None = None,
    mfa_method: str | None = None,
) -> tuple[AuthSession, TokenBundle]:
    """Create a fresh session and return its plaintext tokens."""
    issued = now or utcnow()
    access_token = generate_token(ACCESS_TOKEN_BYTES)
    refresh_token = generate_token(REFRESH_TOKEN_BYTES)
    csrf_token = generate_token(CSRF_TOKEN_BYTES)
    access_expires_at = issued + timedelta(minutes=settings.auth_access_ttl_minutes)
    refresh_expires_at = issued + timedelta(days=settings.auth_refresh_ttl_days)

    record = AuthSession(
        user_id=user.id,
        organization_id=organization_id,
        access_token_hash=hash_token(access_token),
        access_expires_at=access_expires_at,
        refresh_token_hash=hash_token(refresh_token),
        refresh_expires_at=refresh_expires_at,
        csrf_token_hash=hash_token(csrf_token),
        user_agent=(user_agent or "")[:255] or None,
        ip_hash=hash_client_ip(ip),
        last_seen_at=issued,
        mfa_verified_at=mfa_verified_at,
        mfa_method=mfa_method,
    )
    db.add(record)
    db.flush()

    bundle = TokenBundle(
        session_id=record.id,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )
    return record, bundle


def find_by_access_token(db: Session, access_token: str | None) -> AuthSession | None:
    """Look a session up by its access token hash (indexed, single query)."""
    if not access_token:
        return None
    return db.scalar(
        select(AuthSession).where(AuthSession.access_token_hash == hash_token(access_token))
    )


def find_by_refresh_token(db: Session, refresh_token: str | None) -> AuthSession | None:
    if not refresh_token:
        return None
    return db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == hash_token(refresh_token))
    )


def access_is_valid(record: AuthSession, now: datetime | None = None) -> bool:
    moment = now or utcnow()
    if record.revoked_at is not None:
        return False
    expires = as_utc(record.access_expires_at)
    return expires is not None and expires > moment


def refresh_is_valid(record: AuthSession, now: datetime | None = None) -> bool:
    moment = now or utcnow()
    if record.revoked_at is not None:
        return False
    expires = as_utc(record.refresh_expires_at)
    return expires is not None and expires > moment


def revoke(db: Session, record: AuthSession, *, reason: str, now: datetime | None = None) -> None:
    if record.revoked_at is None:
        record.revoked_at = now or utcnow()
        record.revoked_reason = reason[:64]
        db.flush()


def revoke_descendants(
    db: Session, record: AuthSession, *, reason: str = "refresh_token_reuse"
) -> int:
    """Revoke a session and every session rotated out of it.

    Used when a rotated refresh token is presented again: either the token was
    stolen or the client replayed it, and in both cases the whole family is
    untrustworthy.

    ``replaced_by_session_id`` points *forward*, from a rotated parent to its
    replacement, so the walk follows that pointer. Searching for rows whose
    ``replaced_by_session_id`` equals the presented id would walk towards the
    already-revoked ancestors and leave the live successor - the session an
    attacker holds - untouched.
    """
    revoked = 0
    pending = [record.id]
    seen: set[uuid.UUID] = set()
    while pending:
        current_id = pending.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        current = db.get(AuthSession, current_id)
        if current is None:
            continue
        revoke(db, current, reason=reason)
        revoked += 1
        if current.replaced_by_session_id is not None:
            pending.append(current.replaced_by_session_id)
    return revoked


def revoke_all_for_user(db: Session, user_id: uuid.UUID, *, reason: str) -> int:
    records = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
        )
    ).all()
    for record in records:
        revoke(db, record, reason=reason)
    return len(records)


def rotate(
    db: Session,
    *,
    refresh_token: str,
    user_agent: str | None,
    ip: str | None,
    now: datetime | None = None,
) -> RotationResult:
    """Exchange a refresh token for a new session, exactly once.

    The caller owns the transaction: it must commit on success and on any
    outcome that changed state (replay revocation, expiry, inactive account).

    Ordering matters and is deliberate:

    1. ``SELECT ... FOR UPDATE`` locks the parent row for the whole rotation.
       A competing request blocks here until the winner commits, then re-reads
       the committed row and takes the replay path instead of minting a second
       child. SQLite ignores the clause and serialises writers itself.
    2. The child is created before the parent is claimed, so the parent is never
       marked rotated without a valid replacement; if the claim fails the whole
       transaction rolls back and no orphan child survives.
    3. The claim is a conditional ``UPDATE`` with a row-count check, which is
       what makes the winner unique even if the row lock were bypassed.
    """
    moment = now or utcnow()

    record = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == hash_token(refresh_token))
        .with_for_update()
    )
    if record is None:
        return RotationResult(rotated=False, reason="unknown_token")

    if record.revoked_at is not None:
        # Reuse of an already-rotated token: revoke the family, including any
        # child the winning request committed.
        revoked = revoke_descendants(db, record)
        return RotationResult(rotated=False, reason="replay", revoked_count=revoked)

    if not refresh_is_valid(record, moment):
        revoke(db, record, reason="refresh_expired", now=moment)
        return RotationResult(rotated=False, reason="expired")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        revoke(db, record, reason="user_inactive", now=moment)
        return RotationResult(rotated=False, reason="user_inactive")

    replacement, bundle = issue_session(
        db,
        user,
        organization_id=record.organization_id,
        user_agent=user_agent,
        ip=ip,
        now=moment,
        # A refresh continues the same authentication ceremony; it must never
        # become a way to drop the second factor.
        mfa_verified_at=record.mfa_verified_at,
        mfa_method=record.mfa_method,
    )

    claimed = db.execute(
        update(AuthSession)
        .where(
            AuthSession.id == record.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.replaced_by_session_id.is_(None),
        )
        .values(
            revoked_at=moment,
            revoked_reason="rotated",
            replaced_by_session_id=replacement.id,
        )
        .execution_options(synchronize_session=False)
    ).rowcount

    if claimed != 1:  # pragma: no cover - unreachable while the row lock holds
        db.rollback()
        return RotationResult(rotated=False, reason="rotation_lost")

    # The bulk UPDATE bypassed the ORM; drop the stale identity-map copy so no
    # later read mistakes this parent for a live session.
    db.expire(record)
    return RotationResult(rotated=True, session=replacement, bundle=bundle)


# --- cookie helpers --------------------------------------------------------


def cookie_kwargs(*, path: str = "/") -> dict[str, object]:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.same_site,
        "path": path,
        "domain": settings.auth_cookie_domain,
    }


def set_session_cookies(response, bundle: TokenBundle, *, now: datetime | None = None) -> None:
    """Attach the access, refresh and CSRF cookies to a response."""
    moment = now or utcnow()
    access_max_age = max(0, int((bundle.access_expires_at - moment).total_seconds()))
    refresh_max_age = max(0, int((bundle.refresh_expires_at - moment).total_seconds()))

    response.set_cookie(
        settings.auth_session_cookie,
        bundle.access_token,
        max_age=access_max_age,
        **cookie_kwargs(),
    )
    response.set_cookie(
        settings.auth_refresh_cookie,
        bundle.refresh_token,
        max_age=refresh_max_age,
        **cookie_kwargs(path="/api/v1/auth"),
    )
    # Readable by JavaScript by design: double-submit CSRF needs the value in a
    # header. It is a nonce, never a credential on its own.
    response.set_cookie(
        settings.auth_csrf_cookie,
        bundle.csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.same_site,
        path="/",
        domain=settings.auth_cookie_domain,
    )


def clear_session_cookies(response) -> None:
    for name, path in (
        (settings.auth_session_cookie, "/"),
        (settings.auth_refresh_cookie, "/api/v1/auth"),
        (settings.auth_csrf_cookie, "/"),
    ):
        response.delete_cookie(
            name,
            path=path,
            domain=settings.auth_cookie_domain,
            secure=settings.cookie_secure,
            httponly=name != settings.auth_csrf_cookie,
            samesite=settings.same_site,
        )
