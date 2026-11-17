"""PostgreSQL-only concurrency proofs for two-person approval.

Skipped unless ``LOOPMESH_PG_URL`` names a disposable PostgreSQL database. The
schema is built by the Alembic chain, so row locking and the conditional
execution claim are exercised against the deployed table definitions.

    LOOPMESH_PG_URL=postgresql+psycopg://loopmesh_test@127.0.0.1:55432/loopmesh_b12 \
        pytest -o addopts="" -q tests/test_platform_batch12_pg.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.actors import ActorContext
from app.core.exceptions import ConflictError
from app.db.enums import (
    ActorRole,
    ApprovalAction,
    ApprovalStatus,
    OrganizationSector,
    OrganizationStatus,
)
from app.db.models.identity import User
from app.db.models.organization import Organization
from app.db.models.platform_approval import PlatformApprovalRequest
from app.services import platform_approvals as approvals

PG_URL = os.environ.get("LOOPMESH_PG_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="set LOOPMESH_PG_URL to a disposable PostgreSQL database for approval concurrency tests",
)


@pytest.fixture(scope="module")
def engine():
    assert PG_URL is not None
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": PG_URL},
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_engine(PG_URL, pool_pre_ping=True, pool_size=4, max_overflow=4)
    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar()
    yield engine
    engine.dispose()


@pytest.fixture()
def factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _actor(user: User) -> ActorContext:
    return ActorContext(
        actor_id=str(user.id),
        display_name=user.full_name,
        role=ActorRole.ADMIN,
        user_id=user.id,
        email=user.email,
        is_platform_admin=True,
    )


def _seed(factory, *, status=OrganizationStatus.ACTIVE):
    db = factory()
    try:
        suffix = uuid.uuid4().hex[:10]
        organisation = Organization(
            name=f"Approval Tenant {suffix}",
            slug=f"approval-tenant-{suffix}",
            sector=OrganizationSector.OTHER,
            country="Germany",
            region="Saxony",
            city="Leipzig",
            status=status,
        )
        requester = User(
            email=f"requester-{suffix}@example.com",
            full_name="Requester",
            password_hash="x",
            is_active=True,
            is_platform_admin=True,
        )
        first = User(
            email=f"approver-one-{suffix}@example.com",
            full_name="Approver One",
            password_hash="x",
            is_active=True,
            is_platform_admin=True,
        )
        second = User(
            email=f"approver-two-{suffix}@example.com",
            full_name="Approver Two",
            password_hash="x",
            is_active=True,
            is_platform_admin=True,
        )
        db.add_all([organisation, requester, first, second])
        db.commit()
        approval = approvals.create_approval(
            db,
            actor=_actor(requester),
            organization_id=organisation.id,
            action=ApprovalAction.SUSPEND,
            reason="Concurrent review",
            now=datetime.now(timezone.utc),
        )
        db.commit()
        return organisation.id, approval.id, first.id, second.id
    finally:
        db.close()


def _run_concurrently(factory, approval_id, user_ids, operation):
    barrier = threading.Barrier(len(user_ids))
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(user_id):
        db = factory()
        try:
            user = db.get(User, user_id)
            barrier.wait(timeout=5)
            try:
                operation(db, _actor(user), approval_id)
                db.commit()
                result = "ok"
            except ConflictError:
                db.rollback()
                result = "conflict"
        except Exception as exc:  # pragma: no cover - surfaced by the assertion
            result = f"error:{type(exc).__name__}"
        finally:
            db.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker, args=(user_id,)) for user_id in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    return outcomes


def test_concurrent_approvals_have_exactly_one_winner(factory):
    _, approval_id, first, second = _seed(factory)

    outcomes = _run_concurrently(
        factory,
        approval_id,
        [first, second],
        lambda db, actor, target: approvals.approve(
            db, actor=actor, approval_id=target
        ),
    )
    assert sorted(outcomes) == ["conflict", "ok"], outcomes

    db = factory()
    try:
        row = db.get(PlatformApprovalRequest, approval_id)
        assert row.status == ApprovalStatus.APPROVED
        assert row.decided_by_user_id in {first, second}
    finally:
        db.close()


def test_concurrent_execution_runs_once(factory):
    organisation_id, approval_id, first, second = _seed(factory)

    db = factory()
    try:
        approvals.approve(db, actor=_actor(db.get(User, first)), approval_id=approval_id)
        db.commit()
    finally:
        db.close()

    outcomes = _run_concurrently(
        factory,
        approval_id,
        [first, second],
        lambda db, actor, target: approvals.execute(
            db, actor=actor, approval_id=target
        ),
    )
    assert sorted(outcomes) == ["conflict", "ok"], outcomes

    db = factory()
    try:
        row = db.get(PlatformApprovalRequest, approval_id)
        organisation = db.get(Organization, organisation_id)
        assert row.status == ApprovalStatus.EXECUTED
        assert row.execution_attempts == 1
        assert organisation.status == OrganizationStatus.SUSPENDED
    finally:
        db.close()
