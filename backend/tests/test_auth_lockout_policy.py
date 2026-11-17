"""Login lockout correctness and resistance to targeted account lockout.

Policy under test (Phase 2B Batch 4):

* A lock is *bounded backoff*: it rejects further password guesses, it does not
  deny the account owner, and a guess made while locked never extends it.
* A lapsed lock resets the failure counter, so the next wrong password starts a
  fresh sequence instead of re-locking the account immediately.
* A successful login clears both the counter and the lock.
* Public failure responses stay identical for known and unknown accounts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.sessions import utcnow
from app.db.models.identity import User
from tests.conftest import make_user

API = "/api/v1/auth"
PASSWORD = "StrongPass!2345"
GENERIC = "Invalid email or password."


def _login(client, email: str, password: str = PASSWORD):
    return client.post(f"{API}/login", json={"email": email, "password": password})


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; normalise before comparing."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _threshold() -> int:
    return settings.auth_max_failed_logins


def _set_lock_state(db, user: User, *, attempts: int, locked_until: datetime | None) -> None:
    user.failed_login_attempts = attempts
    user.locked_until = locked_until
    db.commit()


def _make(db, email: str) -> User:
    user = make_user(db, email=email, password=PASSWORD)
    db.commit()
    return user


def test_expired_lock_resets_the_failure_sequence(client, db):
    """First wrong password after a lapsed lock counts as 1, not 6."""
    user = _make(db, "lockout-expired@example.com")
    _set_lock_state(db, user, attempts=_threshold(), locked_until=utcnow() - timedelta(minutes=1))

    res = _login(client, user.email, "wrong-password")
    assert res.status_code == 401
    assert res.json()["error"]["message"] == GENERIC

    db.refresh(user)
    assert user.failed_login_attempts == 1
    assert user.locked_until is None


def test_expired_lock_allows_successful_login(client, db):
    user = _make(db, "lockout-expired-ok@example.com")
    _set_lock_state(db, user, attempts=_threshold(), locked_until=utcnow() - timedelta(minutes=1))

    res = _login(client, user.email)
    assert res.status_code == 200, res.text
    assert res.json()["authenticated"] is True

    db.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_fresh_sequence_locks_again_only_at_the_threshold(client, db):
    user = _make(db, "lockout-rethreshold@example.com")
    _set_lock_state(db, user, attempts=_threshold(), locked_until=utcnow() - timedelta(minutes=1))

    for _ in range(_threshold() - 1):
        assert _login(client, user.email, "wrong-password").status_code == 401
    db.refresh(user)
    assert user.failed_login_attempts == _threshold() - 1
    assert user.locked_until is None

    assert _login(client, user.email, "wrong-password").status_code == 401
    db.refresh(user)
    assert user.failed_login_attempts == _threshold()
    assert _as_utc(user.locked_until) > utcnow()


def test_active_lock_still_rejects_incorrect_password(client, db):
    user = _make(db, "lockout-active@example.com")
    _set_lock_state(db, user, attempts=_threshold(), locked_until=utcnow() + timedelta(minutes=10))
    db.refresh(user)
    locked_at = _as_utc(user.locked_until)

    res = _login(client, user.email, "wrong-password")
    assert res.status_code == 401
    assert res.json()["error"]["message"] == GENERIC

    db.refresh(user)
    assert user.failed_login_attempts == _threshold()
    assert _as_utc(user.locked_until) == locked_at


def test_unauthenticated_attempts_cannot_hold_a_victim_account_closed(client, db):
    """An attacker who knows only the email must not deny the owner access."""
    victim = _make(db, "lockout-victim@example.com")
    _set_lock_state(db, victim, attempts=_threshold(), locked_until=utcnow() + timedelta(minutes=10))
    db.refresh(victim)
    locked_at = _as_utc(victim.locked_until)

    for _ in range(3):
        assert _login(client, victim.email, "attacker-guess").status_code == 401

    db.refresh(victim)
    assert _as_utc(victim.locked_until) == locked_at  # bounded, never extended
    assert victim.failed_login_attempts == _threshold()

    res = _login(client, victim.email)
    assert res.status_code == 200, res.text

    db.refresh(victim)
    assert victim.failed_login_attempts == 0
    assert victim.locked_until is None


def test_unknown_and_known_accounts_share_the_same_failure_shape(client, db):
    _make(db, "shape-known@example.com")

    unknown = _login(client, "shape-unknown@example.com", "wrong-password")
    known = _login(client, "shape-known@example.com", "wrong-password")

    assert unknown.status_code == known.status_code == 401
    for res in (unknown, known):
        body = res.json()["error"]
        assert body["code"] == "unauthenticated"
        assert body["message"] == GENERIC
        assert body["details"] == {"reason": "invalid_credentials"}


def test_successful_login_clears_failures_below_the_threshold(client, db):
    user = _make(db, "lockout-clear@example.com")
    for _ in range(_threshold() - 1):
        assert _login(client, user.email, "wrong-password").status_code == 401

    db.refresh(user)
    assert user.failed_login_attempts == _threshold() - 1
    assert user.locked_until is None

    assert _login(client, user.email).status_code == 200
    db.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_repeated_login_attempts_are_throttled(client, db):
    """The per-client/per-account limiter still bounds online guessing."""
    email = "lockout-throttle@example.com"
    limit = settings.auth_login_attempts_per_hour
    assert limit <= 50, "keep the throttling test cheap"

    for _ in range(limit):
        assert _login(client, email, "wrong-password").status_code == 401

    blocked = _login(client, email, "wrong-password")
    assert blocked.status_code == 429
    body = blocked.json()["error"]
    assert body["code"] == "rate_limited"
    assert body["details"]["retry_after_seconds"] >= 1
