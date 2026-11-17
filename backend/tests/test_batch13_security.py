"""Batch 13 adversarial coverage: shared limits, key rotation, audit and recovery."""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core import mfa as mfa_core
from app.core import security_limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.rate_limit import RateLimitExceeded, account_key, client_key
from app.db.base import Base
from app.db.models.audit import AuditEvent, AuditIntegrityState
from app.db.models.identity import AuthSession
from app.db.models.security import AuditArchiveBatch
from app.main import app
from app.services import audit as audit_service
from app.services import mfa as mfa_service
from app.services import mfa_recovery
from tests.conftest import login_client, make_user

API = "/api/v1"
PASSWORD = "StrongPass!2345"
OLD_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _mfa_environment(monkeypatch):
    monkeypatch.setattr(settings, "mfa_encryption_key", OLD_KEY)
    monkeypatch.setattr(settings, "mfa_encryption_previous_keys", "")
    mfa_core.reset_mfa_key_cache()
    yield
    mfa_core.reset_mfa_key_cache()


def _enrolled_user(db: Session, *, platform: bool = False):
    user = make_user(db, is_platform_admin=platform)
    secret, _ = mfa_service.start_enrollment(user)
    codes = mfa_service.confirm_enrollment(db, user, mfa_core.totp_at(secret))
    assert codes is not None
    db.commit()
    return user, secret


def _switch_key(monkeypatch, *, primary: str | None, previous: str = "") -> None:
    monkeypatch.setattr(settings, "mfa_encryption_key", primary)
    monkeypatch.setattr(settings, "mfa_encryption_previous_keys", previous)
    mfa_core.reset_mfa_key_cache()


# ---------------------------------------------------------------------------
# shared limiter
# ---------------------------------------------------------------------------


def test_limits_are_scoped_and_use_pseudonymous_keys(db: Session) -> None:
    from app.core.rate_limit import _principal_digest

    email = "scoped-user@example.com"
    key = account_key("login", email)
    for _ in range(2):
        security_limiter.hit(db, key=key, limit=2, window_seconds=60)
    with pytest.raises(RateLimitExceeded):
        security_limiter.hit(db, key=key, limit=2, window_seconds=60)

    # A different operation or account has its own bucket.
    security_limiter.hit(db, key=account_key("login", "other@example.com"), limit=2, window_seconds=60)
    security_limiter.hit(db, key=account_key("reset", email), limit=2, window_seconds=60)
    rows = db.scalars(select(__import__("app.db.models.security", fromlist=["SecurityRateLimit"]).SecurityRateLimit)).all()
    assert rows
    assert email not in {row.bucket_key for row in rows}
    assert _principal_digest(email) in key


def test_fixed_window_expiry_resets_the_counter(db: Session) -> None:
    key = "login:account:expiry"
    security_limiter.hit(db, key=key, limit=1, window_seconds=60, now_epoch=1000)
    with pytest.raises(RateLimitExceeded):
        security_limiter.hit(db, key=key, limit=1, window_seconds=60, now_epoch=1010)
    decision = security_limiter.hit(
        db, key=key, limit=1, window_seconds=60, now_epoch=1061
    )
    assert decision.count == 1
    assert decision.window_started_at == 1061


def test_limiter_fails_closed_and_recovers(db: Session, monkeypatch) -> None:
    from app.db.models.security import SecurityRateLimit

    original = db.execute

    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database down"))

    monkeypatch.setattr(db, "execute", broken)
    with pytest.raises(security_limiter.SecurityLimiterUnavailable):
        security_limiter.hit(db, key="login:account:down", limit=10, window_seconds=60)
    monkeypatch.setattr(db, "execute", original)

    decision = security_limiter.hit(
        db, key="login:account:down", limit=10, window_seconds=60
    )
    assert decision.count == 1
    assert db.scalar(select(SecurityRateLimit).where(SecurityRateLimit.bucket_key == "login:account:down"))


def test_concurrent_workers_cannot_exceed_the_shared_limit(tmp_path: Path) -> None:
    database = tmp_path / "workers.db"
    engine = create_engine(
        f"sqlite:///{database.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    def attempt(_: int) -> bool:
        with factory() as session:
            try:
                security_limiter.hit(
                    session, key="login:account:concurrent", limit=25, window_seconds=600
                )
                return True
            except RateLimitExceeded:
                return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(60)))

    assert sum(results) == 25
    with factory() as session:
        from app.db.models.security import SecurityRateLimit

        row = session.get(SecurityRateLimit, "login:account:concurrent")
        assert row is not None
        assert row.attempt_count == 60
    engine.dispose()


def test_auth_endpoints_use_the_shared_limiter(client: TestClient, db: Session) -> None:
    user = make_user(db, email="limited-login@example.com")
    db.commit()
    for _ in range(settings.auth_login_attempts_per_hour):
        response = client.post(
            f"{API}/auth/login",
            json={"email": user.email, "password": "WrongPassword!2345"},
        )
        assert response.status_code == 401, response.text
    blocked = client.post(
        f"{API}/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert blocked.status_code == 429
    body = blocked.json()
    code = body.get("code") or body.get("error", {}).get("code")
    assert code == "rate_limited"
    from app.db.models.security import SecurityRateLimit

    assert db.scalar(
        select(SecurityRateLimit).where(
            SecurityRateLimit.bucket_key == account_key("login", user.email)
        )
    ) is not None


# ---------------------------------------------------------------------------
# MFA rotation and recovery
# ---------------------------------------------------------------------------


def test_rotation_preserves_verification_and_then_removes_old_key(
    db: Session, monkeypatch
) -> None:
    user, secret = _enrolled_user(db)
    old_envelope = user.mfa_secret_encrypted
    assert old_envelope.startswith("v1.")

    new_key = Fernet.generate_key().decode()
    _switch_key(monkeypatch, primary=new_key, previous=OLD_KEY)
    assert mfa_core.decrypt_secret(old_envelope) == secret
    status = mfa_core.rotation_status(db)
    assert status.previous == 1 and status.active == 0

    result = mfa_core.rotate_mfa_secrets(db, batch_size=10)
    assert result.rotated == 1
    status = mfa_core.rotation_status(db)
    assert status.complete is True and status.active == 1
    assert user.mfa_secret_encrypted != old_envelope
    assert mfa_core.decrypt_secret(user.mfa_secret_encrypted) == secret

    later = datetime.now(timezone.utc) + timedelta(seconds=45)
    verified = mfa_service.verify_factor(db, user, code=mfa_core.totp_at(secret, later), now=later)
    assert verified.ok is True and verified.method.value == "totp"

    _switch_key(monkeypatch, primary=new_key, previous="")
    assert mfa_core.decrypt_secret(user.mfa_secret_encrypted) == secret


def test_interrupted_rotation_is_resumable_and_never_rewrites_bad_rows(
    db: Session, monkeypatch
) -> None:
    first, _ = _enrolled_user(db)
    second, _ = _enrolled_user(db)
    new_key = Fernet.generate_key().decode()
    _switch_key(monkeypatch, primary=new_key, previous=OLD_KEY)

    real_encrypt = mfa_core.encrypt_secret
    calls = {"count": 0}

    def fail_second(secret: str) -> str:
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated worker interruption")
        return real_encrypt(secret)

    monkeypatch.setattr(mfa_core, "encrypt_secret", fail_second)
    with pytest.raises(mfa_core.MfaKeyRotationError):
        mfa_core.rotate_mfa_secrets(db, batch_size=1)
    monkeypatch.setattr(mfa_core, "encrypt_secret", real_encrypt)

    status = mfa_core.rotation_status(db)
    assert status.total_secrets == 2
    assert status.active == 1 and status.previous == 1

    resumed = mfa_core.rotate_mfa_secrets(db, batch_size=1)
    assert resumed.rotated == 1
    assert mfa_core.rotation_status(db).complete is True


def test_wrong_missing_and_corrupted_keys_fail_closed(db: Session, monkeypatch) -> None:
    user, secret = _enrolled_user(db)
    envelope = user.mfa_secret_encrypted

    new_key = Fernet.generate_key().decode()
    _switch_key(monkeypatch, primary=new_key, previous="")
    with pytest.raises(mfa_core.MfaUnavailableError):
        mfa_core.decrypt_secret(envelope)

    _switch_key(monkeypatch, primary=None, previous="")
    with pytest.raises(mfa_core.MfaUnavailableError):
        mfa_core.active_key_id()

    _switch_key(monkeypatch, primary=OLD_KEY, previous="")
    user.mfa_secret_encrypted = f"v1.{mfa_core.active_key_id()}.not-a-fernet-token"
    db.commit()
    with pytest.raises(mfa_core.MfaUnavailableError):
        mfa_service.verify_factor(db, user, code=mfa_core.totp_at(secret))
    db.rollback()
    assert user.mfa_secret_encrypted.endswith("not-a-fernet-token")


def test_legacy_and_mixed_version_records_rotate(db: Session, monkeypatch) -> None:
    legacy_secret = mfa_core.generate_totp_secret()
    legacy_user = make_user(db)
    legacy_user.mfa_secret_encrypted = Fernet(OLD_KEY.encode()).encrypt(
        legacy_secret.encode()
    ).decode()
    legacy_user.mfa_enrolled_at = datetime.now(timezone.utc)
    active_user, active_secret = _enrolled_user(db)

    new_key = Fernet.generate_key().decode()
    _switch_key(monkeypatch, primary=new_key, previous=OLD_KEY)
    status = mfa_core.rotation_status(db)
    assert status.legacy == 1 and status.previous == 1
    result = mfa_core.rotate_mfa_secrets(db, batch_size=10)
    assert result.rotated >= 1
    assert mfa_core.rotation_status(db).complete is True
    assert mfa_core.decrypt_secret(legacy_user.mfa_secret_encrypted) == legacy_secret
    assert mfa_core.decrypt_secret(active_user.mfa_secret_encrypted) == active_secret


# ---------------------------------------------------------------------------
# audit chain, export and archive
# ---------------------------------------------------------------------------


def _platform_headers(client: TestClient, db: Session):
    operator = make_user(db, is_platform_admin=True)
    db.commit()
    return login_client(client, db, operator)


def test_audit_integrity_endpoint_detects_tampering(client: TestClient, db: Session) -> None:
    audit_service.record_event(
        db, event_type="test.integrity", entity_type="test", summary="one"
    )
    audit_service.record_event(
        db, event_type="test.integrity", entity_type="test", summary="two"
    )
    db.commit()
    headers = _platform_headers(client, db)

    response = client.get(f"{API}/platform/audit/integrity", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True
    assert response.json()["checked"] >= 2

    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE audit_events SET summary = 'altered' "
            "WHERE event_type = 'test.integrity'"
        )
    )
    db.commit()
    bad = client.get(f"{API}/platform/audit/integrity", headers=headers)
    assert bad.status_code == 200
    assert bad.json()["valid"] is False
    assert bad.json()["reason"] == "event_hash_mismatch"
    verification = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.event_type == "platform.audit.integrity_verified")
        .order_by(AuditEvent.integrity_sequence.desc())
    )
    assert verification is not None
    assert verification.severity.value == "warning"


def test_audit_integrity_requires_verify_permission(client: TestClient, db: Session) -> None:
    from tests.conftest import make_membership, make_organization

    org = make_organization(db)
    user = make_user(db)
    make_membership(db, user, org)
    db.commit()
    headers = login_client(client, db, user, org.id)
    response = client.get(f"{API}/platform/audit/integrity", headers=headers)
    assert response.status_code == 403


def test_archive_copies_without_deleting_source(db: Session, tmp_path: Path) -> None:
    events = []
    for index in range(3):
        events.append(
            audit_service.record_event(
                db,
                event_type="test.archive",
                entity_type="test",
                summary=f"archive {index}",
                payload={"token": "must-be-redacted", "index": index},
            )
        )
    db.commit()
    start = events[0].created_at - timedelta(seconds=1)
    end = events[-1].created_at + timedelta(seconds=1)
    destination = tmp_path / "audit.jsonl"
    batch = audit_service.archive_events(
        db,
        destination=destination,
        created_from=start,
        created_to=end,
        created_by="infra-operator",
        approval_reference="CHG-1301",
    )
    assert batch.event_count >= 3
    assert destination.exists()
    assert destination.with_name("audit.jsonl.sha256").exists()
    assert db.query(AuditEvent).filter(AuditEvent.event_type == "test.archive").count() == 3
    lines = destination.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 3
    assert "must-be-redacted" not in destination.read_text(encoding="utf-8")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    assert digest == batch.archive_sha256
    with pytest.raises(ValidationError):
        audit_service.archive_events(
            db,
            destination=destination,
            created_from=start,
            created_to=end,
            created_by="infra-operator",
            approval_reference="CHG-1302",
        )
    archived_event = db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "platform.audit.archived")
    )
    assert archived_event is not None
    assert db.query(AuditArchiveBatch).count() == 1


# ---------------------------------------------------------------------------
# break-glass
# ---------------------------------------------------------------------------


def test_break_glass_requires_evidence_and_clears_only_the_target(
    db: Session, tmp_path: Path
) -> None:
    target, _ = _enrolled_user(db, platform=True)
    other, other_secret = _enrolled_user(db, platform=True)
    record, _ = __import__("app.core.sessions", fromlist=["issue_session"]).issue_session(
        db, target, organization_id=None
    )
    db.commit()
    assert target.mfa_enrolled_at is not None

    evidence = tmp_path / "approval.txt"
    evidence.write_text("approved by security council", encoding="utf-8")

    with pytest.raises(ValidationError):
        mfa_recovery.break_glass_reset(
            db,
            email=target.email,
            performed_by="infra",
            approval_reference="",
            evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
            reason="lost device",
        )
    with pytest.raises(NotFoundError):
        mfa_recovery.break_glass_reset(
            db,
            email="missing@example.com",
            performed_by="infra",
            approval_reference="CHG-1",
            evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
            reason="lost device",
        )

    result = mfa_recovery.break_glass_reset(
        db,
        email=target.email,
        performed_by="infra",
        approval_reference="CHG-1",
        evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
        reason="lost device",
    )
    assert result["revoked_sessions"] == 1
    assert target.mfa_secret_encrypted is None
    assert target.mfa_enrolled_at is None
    assert target.is_platform_admin is True
    assert db.get(AuthSession, record.id).revoked_at is not None
    assert mfa_core.decrypt_secret(other.mfa_secret_encrypted) == other_secret
    event = db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "platform.mfa.break_glass")
    )
    assert event is not None
    assert event.severity.value == "critical"
    assert event.payload["approval_reference"] == "CHG-1"
    assert "secret" not in json.dumps(event.payload).lower()
