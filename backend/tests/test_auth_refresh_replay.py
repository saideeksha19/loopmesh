"""Refresh replay and expiry behaviour (runs on SQLite).

These do not and cannot prove row-lock correctness - see
``tests/test_refresh_concurrency_pg.py`` for that. They lock the *policy* that
must hold on every backend:

* replaying a rotated refresh token revokes the live successor too,
* an expired token cannot rotate, and its revocation is committed rather than
  discarded with the request.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update

from app.core.sessions import utcnow
from app.db.models.identity import AuthSession
from tests.conftest import make_membership, make_organization, make_user

API = "/api/v1/auth"
PASSWORD = "StrongPass!2345"


def _login(client, db, *, email: str = "refresh-replay@example.com"):
    org = make_organization(db)
    user = make_user(db, email=email, password=PASSWORD)
    make_membership(db, user, org)
    db.commit()

    response = client.post(f"{API}/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert client.cookies.get("lm_refresh")
    return user


def _refresh_with(client, token: str):
    """Send a refresh request carrying only the supplied refresh cookie."""
    client.cookies.clear()
    return client.post(f"{API}/refresh", headers={"Cookie": f"lm_refresh={token}"})


def _sessions(db, user):
    db.expire_all()
    return db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()


def test_replay_revokes_the_live_successor(client, db):
    user = _login(client, db)
    original = client.cookies.get("lm_refresh")

    first = client.post(f"{API}/refresh")
    assert first.status_code == 200, first.text
    successor = client.cookies.get("lm_refresh")
    assert successor and successor != original

    replay = _refresh_with(client, original)
    assert replay.status_code == 401
    assert replay.json()["error"]["details"]["reason"] == "refresh_reused"

    rows = _sessions(db, user)
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows), "replay left a live session behind"

    # The successor minted by the legitimate rotation is dead as well.
    after = _refresh_with(client, successor)
    assert after.status_code == 401
    assert after.json()["error"]["details"]["reason"] in {"refresh_reused", "refresh_invalid"}


def test_expired_token_cannot_rotate_and_revocation_is_committed(client, db):
    user = _login(client, db, email="refresh-expired@example.com")
    token = client.cookies.get("lm_refresh")

    parent = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert parent is not None
    db.execute(
        update(AuthSession)
        .where(AuthSession.id == parent.id)
        # created_at must move too: the schema requires
        # access_expiry > created_at > ... for a coherent backdate.
        .values(
            created_at=utcnow() - timedelta(hours=3),
            access_expires_at=utcnow() - timedelta(hours=2),
            refresh_expires_at=utcnow() - timedelta(hours=1),
        )
    )
    db.commit()

    response = _refresh_with(client, token)
    assert response.status_code == 401
    assert response.json()["error"]["details"]["reason"] == "refresh_invalid"

    rows = _sessions(db, user)
    assert len(rows) == 1, "an expired token must not create a child session"
    assert rows[0].revoked_at is not None
    assert rows[0].revoked_reason == "refresh_expired"
    assert rows[0].replaced_by_session_id is None
