"""PostgreSQL-only refresh-rotation tests.

Skipped unless ``LOOPMESH_PG_URL`` points at a disposable PostgreSQL database.
SQLite cannot prove row-lock behaviour, so these tests are kept separate from
the SQLite suite on purpose.

Run::

    LOOPMESH_PG_URL=postgresql+psycopg://loopmesh_test@127.0.0.1:55432/loopmesh_test \
        pytest -o addopts="" -q -p no:cacheprovider tests/test_refresh_concurrency_pg.py

The schema comes from the Alembic migration chain, never from
``Base.metadata.create_all``, so the rotation behaviour is proven against
exactly the objects a deployment would create. The module runs
``alembic upgrade head`` against the disposable database before the first test
and fails loudly if the chain cannot build the schema.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.api import deps as api_deps
from app.core.security import hash_password
from app.core.sessions import RotationResult, issue_session, revoke, rotate, utcnow
from app.db.models.identity import AuthSession, User
from app.db.session import get_db
from app.main import app

PG_URL = os.environ.get("LOOPMESH_PG_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="set LOOPMESH_PG_URL to a disposable PostgreSQL database to run rotation concurrency tests",
)

API = "/api/v1/auth"
PASSWORD = "StrongPass!2345"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_engine():
    assert PG_URL is not None
    # Build (or confirm) the schema through the migration chain only. Running
    # ``upgrade head`` on an already-migrated database is a no-op.
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": PG_URL},
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, f"alembic upgrade head failed:\n{upgrade.stderr}"

    engine = create_engine(PG_URL, pool_pre_ping=True, pool_size=4, max_overflow=4, future=True)
    with engine.connect() as connection:
        revision = connection.execute(text("select version_num from alembic_version")).scalar()
    assert revision, "the database was not created by Alembic migrations"
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_factory(pg_engine) -> sessionmaker:
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture()
def pg_client(pg_factory: sessionmaker):
    """A TestClient whose request sessions are PostgreSQL sessions.

    Only ``get_db`` is overridden, so the production ``get_actor`` path runs.
    """

    def override_get_db():
        session = pg_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_user(factory: sessionmaker, *, email: str | None = None) -> uuid.UUID:
    db = factory()
    try:
        user = User(
            email=(email or f"pg-{uuid.uuid4().hex[:10]}@example.com").lower(),
            full_name="PG Concurrency User",
            password_hash=hash_password(PASSWORD),
            is_active=True,
            is_platform_admin=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _seed_session(factory: sessionmaker, *, user_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    """Create one session for ``user_id``; returns (session_id, refresh_token)."""
    db = factory()
    try:
        user = db.get(User, user_id)
        record, bundle = issue_session(db, user, organization_id=None, user_agent="pg-test")
        db.commit()
        return record.id, bundle.refresh_token
    finally:
        db.close()


def _seed(factory: sessionmaker) -> tuple[uuid.UUID, uuid.UUID, str]:
    user_id = _seed_user(factory)
    parent_id, token = _seed_session(factory, user_id=user_id)
    return user_id, parent_id, token


def _rows(factory: sessionmaker, user_id: uuid.UUID) -> dict[uuid.UUID, AuthSession]:
    db = factory()
    try:
        records = db.scalars(
            select(AuthSession).where(AuthSession.user_id == user_id)
        ).all()
        # Materialise before the session closes (expire_on_commit is off).
        return {record.id: record for record in records}
    finally:
        db.close()


def _race(factory: sessionmaker, token: str) -> tuple[list[RotationResult], list[BaseException]]:
    """Run two rotations of ``token`` with maximal overlap on separate sessions."""
    barrier = threading.Barrier(2, timeout=30)
    results: list[RotationResult] = []
    errors: list[BaseException] = []
    guard = threading.Lock()

    def worker() -> None:
        db = factory()
        try:
            barrier.wait()
            outcome = rotate(db, refresh_token=token, user_agent="pg-race", ip="127.0.0.1")
            db.commit()
        except BaseException as exc:  # noqa: BLE001 - surfaced as a test failure
            db.rollback()
            with guard:
                errors.append(exc)
            return
        finally:
            db.close()
        with guard:
            results.append(outcome)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "rotation deadlocked"
    return results, errors


# ---------------------------------------------------------------------------
# concurrency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("attempt", range(5))
def test_concurrent_rotation_has_exactly_one_winner(pg_factory, attempt):
    user_id, parent_id, token = _seed(pg_factory)

    results, errors = _race(pg_factory, token)
    assert errors == []
    assert len(results) == 2

    winners = [result for result in results if result.rotated]
    losers = [result for result in results if not result.rotated]
    assert len(winners) == 1, f"attempt {attempt}: {[r.reason for r in results]}"
    assert len(losers) == 1
    # The blocked request must observe the committed parent and take the replay
    # path - not mint a second child and not invent a new failure mode.
    assert losers[0].reason == "replay"

    rows = _rows(pg_factory, user_id)
    # Parent plus exactly one child: a second child would mean two winners.
    assert len(rows) == 2, "a second child session was created"

    parent = rows[parent_id]
    assert parent.revoked_at is not None
    assert parent.revoked_reason == "rotated"
    assert parent.replaced_by_session_id == winners[0].session.id

    # Replay detection in the losing request revokes the family, including the
    # child that the winning request already committed.
    child = rows[winners[0].session.id]
    assert child.revoked_at is not None
    assert child.revoked_reason == "refresh_token_reuse"
    assert all(row.revoked_at is not None for row in rows.values())


def test_concurrent_rotation_never_leaves_two_live_children(pg_factory):
    user_id, parent_id, token = _seed(pg_factory)

    results, errors = _race(pg_factory, token)
    assert errors == []

    rows = _rows(pg_factory, user_id)
    live = [row for row in rows.values() if row.revoked_at is None]
    assert live == []
    assert len(rows) == 2
    assert rows[parent_id].replaced_by_session_id in rows


def test_rolled_back_rotation_leaves_no_child_and_no_rotation(pg_factory):
    """The child is only durable together with the parent's claim.

    A request that fails after ``rotate()`` but before commit must leave the
    parent unrotated and must not leave an orphan child behind.
    """
    user_id, parent_id, token = _seed(pg_factory)

    db = pg_factory()
    try:
        outcome = rotate(db, refresh_token=token, user_agent="pg-rollback", ip="127.0.0.1")
        assert outcome.rotated
        assert outcome.session.id != parent_id
        db.rollback()  # the request failed after rotation, before commit
    finally:
        db.close()

    rows = _rows(pg_factory, user_id)
    assert set(rows) == {parent_id}, "a rolled-back rotation left a child session behind"
    parent = rows[parent_id]
    assert parent.revoked_at is None
    assert parent.revoked_reason is None
    assert parent.replaced_by_session_id is None

    # Nothing rotated, so the token is still usable exactly once.
    db = pg_factory()
    try:
        retry = rotate(db, refresh_token=token, user_agent="pg-rollback", ip="127.0.0.1")
        assert retry.rotated
        db.commit()
    finally:
        db.close()

    assert len(_rows(pg_factory, user_id)) == 2


# ---------------------------------------------------------------------------
# endpoint-level replay behaviour
# ---------------------------------------------------------------------------


def test_replay_after_successful_refresh_is_rejected(pg_client, pg_factory):
    email = f"pg-replay-{uuid.uuid4().hex[:8]}@example.com"
    user_id = _seed_user(pg_factory, email=email)

    login = pg_client.post(f"{API}/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text

    original = pg_client.cookies.get("lm_refresh")
    assert original

    first = pg_client.post(f"{API}/refresh")
    assert first.status_code == 200, first.text
    rotated = pg_client.cookies.get("lm_refresh")
    assert rotated and rotated != original

    # Replay the pre-rotation token as the sole cookie.
    pg_client.cookies.clear()
    replay = pg_client.post(f"{API}/refresh", headers={"Cookie": f"lm_refresh={original}"})
    assert replay.status_code == 401
    assert replay.json()["error"]["details"]["reason"] == "refresh_reused"

    rows = _rows(pg_factory, user_id)
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows.values())

    # The token minted by the winning rotation is dead as well.
    pg_client.cookies.clear()
    after = pg_client.post(f"{API}/refresh", headers={"Cookie": f"lm_refresh={rotated}"})
    assert after.status_code == 401
    assert after.json()["error"]["details"]["reason"] in {"refresh_reused", "refresh_invalid"}


def test_deleted_cookie_returns_refresh_required(pg_client):
    pg_client.cookies.clear()
    response = pg_client.post(f"{API}/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["details"]["reason"] == "refresh_required"


# ---------------------------------------------------------------------------
# invalid tokens
# ---------------------------------------------------------------------------


def test_expired_token_cannot_rotate_and_revocation_persists(pg_factory):
    user_id, parent_id, token = _seed(pg_factory)

    db = pg_factory()
    try:
        # ``created_at`` moves too: the schema enforces
        # access_expires_at > created_at > ... so only a coherent backdate is legal.
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == parent_id)
            .values(
                created_at=utcnow() - timedelta(hours=3),
                access_expires_at=utcnow() - timedelta(hours=2),
                refresh_expires_at=utcnow() - timedelta(hours=1),
            )
        )
        db.commit()
    finally:
        db.close()

    db = pg_factory()
    try:
        result = rotate(db, refresh_token=token, user_agent="pg-test", ip="127.0.0.1")
        db.commit()
    finally:
        db.close()

    assert result.rotated is False
    assert result.reason == "expired"

    rows = _rows(pg_factory, user_id)
    assert len(rows) == 1, "an expired token must not create a child session"
    parent = rows[parent_id]
    assert parent.revoked_at is not None
    assert parent.revoked_reason == "refresh_expired"
    assert parent.replaced_by_session_id is None


def test_revoked_token_cannot_rotate(pg_factory):
    user_id, parent_id, token = _seed(pg_factory)

    db = pg_factory()
    try:
        revoke(db, db.get(AuthSession, parent_id), reason="test_revoked")
        db.commit()
    finally:
        db.close()

    db = pg_factory()
    try:
        result = rotate(db, refresh_token=token, user_agent="pg-test", ip="127.0.0.1")
        db.commit()
    finally:
        db.close()

    assert result.rotated is False
    assert result.reason == "replay"
    assert result.revoked_count >= 1
    assert len(_rows(pg_factory, user_id)) == 1


def test_unknown_token_creates_nothing(pg_factory):
    user_id = _seed_user(pg_factory)
    db = pg_factory()
    try:
        result = rotate(db, refresh_token="not-a-real-token", user_agent="pg-test", ip=None)
        db.commit()
    finally:
        db.close()
    assert result.rotated is False
    assert result.reason == "unknown_token"
    assert _rows(pg_factory, user_id) == {}


# ---------------------------------------------------------------------------
# sequential behaviour
# ---------------------------------------------------------------------------


def test_sequential_rotation_builds_a_chain(pg_factory):
    user_id, parent_id, token = _seed(pg_factory)

    db = pg_factory()
    try:
        first = rotate(db, refresh_token=token, user_agent="pg-test", ip=None)
        db.commit()
        assert first.rotated is True
        child_bundle = first.bundle
    finally:
        db.close()

    db = pg_factory()
    try:
        second = rotate(db, refresh_token=child_bundle.refresh_token, user_agent="pg-test", ip=None)
        db.commit()
    finally:
        db.close()

    assert second.rotated is True

    rows = _rows(pg_factory, user_id)
    assert len(rows) == 3
    parent = rows[parent_id]
    child = rows[first.session.id]
    grandchild = rows[second.session.id]
    assert parent.replaced_by_session_id == child.id
    assert child.replaced_by_session_id == grandchild.id
    assert parent.revoked_reason == "rotated"
    assert child.revoked_reason == "rotated"
    assert grandchild.revoked_at is None


def test_refreshing_one_session_leaves_others_untouched(pg_factory):
    user_id = _seed_user(pg_factory)
    first_id, first_token = _seed_session(pg_factory, user_id=user_id)
    second_id, second_token = _seed_session(pg_factory, user_id=user_id)

    db = pg_factory()
    try:
        result = rotate(db, refresh_token=first_token, user_agent="pg-test", ip=None)
        db.commit()
    finally:
        db.close()
    assert result.rotated is True

    rows = _rows(pg_factory, user_id)
    assert rows[first_id].revoked_at is not None
    assert rows[second_id].revoked_at is None, "unrelated session was revoked"

    db = pg_factory()
    try:
        other = rotate(db, refresh_token=second_token, user_agent="pg-test", ip=None)
        db.commit()
    finally:
        db.close()
    assert other.rotated is True
