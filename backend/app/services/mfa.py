"""Operator MFA lifecycle: enrolment, verification, recovery and lockout.

The service owns the security decisions; endpoints own HTTP shape and audit
events. Nothing here returns a stored secret, a decrypted secret after
enrolment, or a recovery-code hash.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import mfa as mfa_core
from app.core.config import settings
from app.db.enums import MfaMethod
from app.db.models.identity import AuthSession, MfaRecoveryCode, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class FactorResult:
    ok: bool
    method: MfaMethod | None = None
    reason: str = "invalid_code"
    locked: bool = False


def is_locked(user: User, now: datetime | None = None) -> bool:
    locked_until = as_utc(user.mfa_locked_until)
    return locked_until is not None and locked_until > (now or utcnow())


def reset_expired_lock(user: User, now: datetime | None = None) -> bool:
    locked_until = as_utc(user.mfa_locked_until)
    moment = now or utcnow()
    if locked_until is None or locked_until > moment:
        return False
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    return True


def register_failure(user: User, now: datetime | None = None) -> bool:
    """Count a failed factor attempt; return whether the account is locked."""
    moment = now or utcnow()
    user.mfa_failed_attempts = int(user.mfa_failed_attempts or 0) + 1
    if user.mfa_failed_attempts >= settings.mfa_max_failed_attempts:
        user.mfa_locked_until = moment + timedelta(minutes=settings.mfa_lockout_minutes)
        return True
    return False


def clear_failures(user: User) -> None:
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None


def recovery_codes_remaining(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user_id,
                MfaRecoveryCode.used_at.is_(None),
            )
        )
        or 0
    )


def _consume_recovery_code(
    db: Session, user: User, code: str, now: datetime
) -> bool:
    normalised = mfa_core.normalise_recovery_code(code)
    if len(normalised) < 8:
        return False
    record = db.scalar(
        select(MfaRecoveryCode)
        .where(
            MfaRecoveryCode.user_id == user.id,
            MfaRecoveryCode.code_hash == mfa_core.hash_recovery_code(code),
            MfaRecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    )
    if record is None:
        return False
    record.used_at = now
    db.flush()
    return True


def verify_factor(
    db: Session,
    user: User,
    *,
    code: str | None = None,
    recovery_code: str | None = None,
    now: datetime | None = None,
) -> FactorResult:
    """Verify one factor with durable lockout and one-time-code semantics."""
    moment = now or utcnow()
    if user.mfa_enrolled_at is None or not user.mfa_secret_encrypted:
        return FactorResult(ok=False, reason="not_enrolled")
    if is_locked(user, moment):
        return FactorResult(ok=False, reason="locked", locked=True)
    reset_expired_lock(user, moment)

    if recovery_code:
        if _consume_recovery_code(db, user, recovery_code, moment):
            clear_failures(user)
            return FactorResult(ok=True, method=MfaMethod.RECOVERY)
        locked = register_failure(user, moment)
        return FactorResult(ok=False, reason="invalid_recovery_code", locked=locked)

    if not code:
        locked = register_failure(user, moment)
        return FactorResult(ok=False, reason="invalid_code", locked=locked)

    secret = mfa_core.decrypt_secret(user.mfa_secret_encrypted)
    counter = mfa_core.verify_totp(
        secret,
        code,
        moment=moment,
        last_counter=user.mfa_last_counter,
    )
    if counter is None:
        locked = register_failure(user, moment)
        return FactorResult(ok=False, reason="invalid_code", locked=locked)

    user.mfa_last_counter = counter
    clear_failures(user)
    db.flush()
    return FactorResult(ok=True, method=MfaMethod.TOTP)


def start_enrollment(user: User) -> tuple[str, str]:
    """Create (or replace) an unconfirmed TOTP secret.

    The encrypted secret is stored immediately but ``mfa_enrolled_at`` stays
    null until a valid code proves the authenticator was configured. Nothing is
    activated by generating a secret.
    """
    secret = mfa_core.generate_totp_secret()
    user.mfa_secret_encrypted = mfa_core.encrypt_secret(secret)
    user.mfa_enrolled_at = None
    user.mfa_last_counter = None
    clear_failures(user)
    uri = mfa_core.provisioning_uri(secret, account=user.email)
    return secret, uri


def confirm_enrollment(
    db: Session, user: User, code: str, *, now: datetime | None = None
) -> list[str] | None:
    """Activate enrolment and issue recovery codes exactly once."""
    moment = now or utcnow()
    if not user.mfa_secret_encrypted:
        return None
    secret = mfa_core.decrypt_secret(user.mfa_secret_encrypted)
    counter = mfa_core.verify_totp(secret, code, moment=moment, last_counter=None)
    if counter is None:
        register_failure(user, moment)
        return None

    user.mfa_enrolled_at = moment
    user.mfa_last_counter = counter
    clear_failures(user)

    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = mfa_core.generate_recovery_codes()
    for code_value in codes:
        db.add(
            MfaRecoveryCode(
                user_id=user.id,
                code_hash=mfa_core.hash_recovery_code(code_value),
            )
        )
    db.flush()
    return codes


def regenerate_recovery_codes(db: Session, user: User) -> list[str]:
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = mfa_core.generate_recovery_codes()
    for code_value in codes:
        db.add(
            MfaRecoveryCode(
                user_id=user.id,
                code_hash=mfa_core.hash_recovery_code(code_value),
            )
        )
    db.flush()
    return codes


def clear_enrollment(db: Session, user: User) -> None:
    user.mfa_secret_encrypted = None
    user.mfa_enrolled_at = None
    user.mfa_last_counter = None
    clear_failures(user)
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    db.flush()


def mark_session_verified(
    db: Session,
    session_id: uuid.UUID | None,
    method: MfaMethod,
    *,
    now: datetime | None = None,
) -> AuthSession | None:
    if session_id is None:
        return None
    record = db.get(AuthSession, session_id)
    if record is None or record.revoked_at is not None:
        return None
    record.mfa_verified_at = now or utcnow()
    record.mfa_method = method.value
    db.flush()
    return record


def status(db: Session, user: User, *, session_verified: bool) -> dict:
    return {
        "enrolled": user.mfa_enrolled_at is not None,
        "verified": session_verified,
        "required": bool(user.is_platform_admin),
        "enrollment_required": bool(user.is_platform_admin and user.mfa_enrolled_at is None),
        "recovery_codes_remaining": recovery_codes_remaining(db, user.id),
        "locked_until": as_utc(user.mfa_locked_until),
        "method": None,
    }
