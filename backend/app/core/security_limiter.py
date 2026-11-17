"""Shared fixed-window security limiter.

The database row is the authority.  A single atomic upsert increments the
counter for the current window, so two application workers cannot both read
"limit - 1" and admit an extra attempt.  The row is intentionally portable to
PostgreSQL and SQLite; no Redis service is required by this deployment.

Failure policy is fail-closed for every caller.  Authentication and platform
MFA are security gates: if the shared counter cannot be read or written, they
refuse rather than silently falling back to a per-process allowance.  Error
messages never reveal whether an account exists.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.rate_limit import RateLimitExceeded
from app.db.models.security import SecurityRateLimit


class SecurityLimiterUnavailable(AppError):
    status_code = 503
    code = "security_limiter_unavailable"


@dataclass(frozen=True, slots=True)
class LimitDecision:
    count: int
    window_started_at: int
    retry_after_seconds: int


def _upsert(session: Session):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - supported databases are PostgreSQL and SQLite
        raise SecurityLimiterUnavailable(
            "The shared security limiter is unavailable.",
            details={"reason": "security_limiter_unsupported_database"},
        )
    return insert(SecurityRateLimit)


def hit(
    session: Session,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    now_epoch: int | None = None,
    commit: bool = True,
) -> LimitDecision:
    """Atomically consume one attempt or raise a bounded 429.

    ``key`` must already be scoped by operation, account and client context.
    The caller must not put a raw email or token in the key; use the hashed
    client/account form produced by :func:`app.core.rate_limit.client_key`.
    """
    if limit < 1 or window_seconds < 1:
        raise ValueError("limit and window_seconds must be positive")

    now = int(time.time()) if now_epoch is None else int(now_epoch)
    cutoff = now - window_seconds
    table = SecurityRateLimit
    statement = _upsert(session).values(
        bucket_key=key,
        window_started_at=now,
        attempt_count=1,
        updated_at_epoch=now,
    )
    update_values = {
        "attempt_count": case(
            (table.window_started_at <= cutoff, 1),
            else_=table.attempt_count + 1,
        ),
        "window_started_at": case(
            (table.window_started_at <= cutoff, now),
            else_=table.window_started_at,
        ),
        "updated_at_epoch": now,
    }
    statement = statement.on_conflict_do_update(
        index_elements=[table.bucket_key],
        set_=update_values,
    ).returning(
        table.attempt_count,
        table.window_started_at,
    )

    try:
        row = session.execute(statement).one()
        # The counter is its own durable transaction. Authentication callers
        # commonly raise immediately after this point (bad password, denied
        # membership, MFA failure), and those exceptions must not roll the
        # consumed attempt back. There are no pending business changes at any
        # call site: every caller consumes a limit before mutating state.
        if commit:
            session.commit()
        else:
            session.flush()
    except SQLAlchemyError as exc:
        session.rollback()
        # Never expose SQL text or connection details to the caller.
        raise SecurityLimiterUnavailable(
            "The shared security limiter is unavailable. Try again shortly.",
            details={"reason": "security_limiter_unavailable"},
        ) from exc

    count, window_started = int(row[0]), int(row[1])
    retry_after = max(1, window_seconds - max(0, now - window_started))
    decision = LimitDecision(
        count=count,
        window_started_at=window_started,
        retry_after_seconds=retry_after,
    )
    if count > limit:
        raise RateLimitExceeded(
            "Too many attempts. Try again later.",
            details={"retry_after_seconds": retry_after},
        )
    return decision


def prune_expired(session: Session, *, retention_seconds: int = 86_400) -> int:
    """Delete stale counter rows; safe to run from an operational job."""
    cutoff = int(time.time()) - retention_seconds
    result = session.execute(
        delete(SecurityRateLimit).where(SecurityRateLimit.updated_at_epoch < cutoff)
    )
    session.commit()
    return int(result.rowcount or 0)


def count_rows(session: Session) -> int:
    """Operational helper used by health checks and tests."""
    return int(session.scalar(select(func.count()).select_from(SecurityRateLimit)) or 0)
