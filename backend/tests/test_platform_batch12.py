"""Batch 12 — two-person approval, operator MFA, sessions and audit export.

Every test drives the production HTTP stack with real sessions. MFA is tested
against an actual TOTP implementation (no stubbed verifier), approvals are
executed through the same route a deployment uses, and the export tests parse
the returned bytes rather than inspecting a helper.

The suite also proves the negative paths that matter most: an unverified
operator cannot reach any platform route, a requester cannot decide their own
approval, an approval cannot execute twice, and no secret appears in an audit
payload or export.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import mfa as mfa_core
from app.core.config import settings

from app.core.security import hash_token
from app.db.enums import (
    ApprovalAction,
    ApprovalStatus,
    AuditSeverity,
    MembershipRole,
    OrganizationStatus,
)
from app.db.models.audit import AuditEvent
from app.db.models.identity import MfaRecoveryCode
from app.db.models.organization import Organization
from app.db.models.platform_approval import PlatformApprovalRequest
from app.main import app
from app.services import audit as audit_service
from app.services import platform_approvals as approval_service
from tests.conftest import login_client, make_membership, make_organization, make_user

API = "/api/v1"
PASSWORD = "StrongPass!2345"
MFA_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _mfa_environment(monkeypatch):
    monkeypatch.setattr(settings, "mfa_encryption_key", MFA_KEY)
    mfa_core.reset_mfa_key_cache()
    yield
    mfa_core.reset_mfa_key_cache()


def _operator(db, *, email: str | None = None):
    return make_user(
        db,
        email=email or f"operator-{uuid.uuid4().hex[:10]}@example.com",
        full_name="Platform Operator",
        is_platform_admin=True,
    )


def _org(db, **overrides):
    return make_organization(db, **overrides)


def _member(db, org, *, role=MembershipRole.ORG_ADMIN, prefix="member"):
    user = make_user(db, email=f"{prefix}-{uuid.uuid4().hex[:10]}@example.com")
    membership = make_membership(db, user, org, role=role)
    db.commit()
    return user, membership


def _verified_login(client, db, user, organization_id=None):
    return login_client(client, db, user, organization_id)


def _unverified_login(client, db, user, organization_id=None):
    return login_client(client, db, user, organization_id, mfa_verified=False)


def _fresh_client() -> TestClient:
    return TestClient(app)


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("lm_csrf") or ""}


def _future_code(secret: str) -> str:
    """A code for the next time step, addressed by counter rather than clock.

    ``now + 31s`` lands two steps ahead whenever the current step is within the
    last second of its window, which the verifier's +/-1 skew window rightly
    rejects. Advancing exactly one counter keeps the intent (a newer code) and
    removes the flake without weakening the assertion.
    """
    return mfa_core.hotp(secret, mfa_core.counter_for() + 1)


def _complete_enrollment(client, db, operator) -> tuple[str, list[str]]:
    enrolled = client.post(
        f"{API}/auth/mfa/enroll",
        json={"current_password": PASSWORD},
        headers=_csrf(client),
    )
    assert enrolled.status_code == 200, enrolled.text
    assert "secret" in enrolled.json()
    secret = enrolled.json()["secret"]
    confirmed = client.post(
        f"{API}/auth/mfa/confirm",
        json={"code": mfa_core.totp_at(secret)},
        headers=_csrf(client),
    )
    assert confirmed.status_code == 200, confirmed.text
    return secret, confirmed.json()["recovery_codes"]


def _new_approval(client, headers, org, *, action="suspend", reason="Policy review"):
    response = client.post(
        f"{API}/platform/approvals",
        json={"organization_id": str(org.id), "action": action, "reason": reason},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _second_operator_headers(db):
    approver = _operator(db)
    approver_client = _fresh_client()
    headers = _verified_login(approver_client, db, approver)
    return approver, approver_client, headers


# ---------------------------------------------------------------------------
# MFA
# ---------------------------------------------------------------------------


def test_unenrolled_operator_is_stopped_by_the_real_platform_gate(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)

    status = client.get(f"{API}/auth/mfa/status")
    assert status.status_code == 200
    assert status.json()["enrolled"] is False
    assert status.json()["enrollment_required"] is True
    assert status.json()["required"] is True

    blocked = client.get(f"{API}/platform/dashboard")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["details"]["reason"] == "mfa_required"


def test_enrollment_confirm_activates_platform_access_and_returns_codes_once(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)

    secret, codes = _complete_enrollment(client, db, operator)
    assert len(codes) == 10
    assert len(set(codes)) == 10

    status = client.get(f"{API}/auth/mfa/status")
    assert status.status_code == 200
    assert status.json()["enrolled"] is True
    assert status.json()["verified"] is True
    assert status.json()["recovery_codes_remaining"] == 10
    assert "secret" not in status.text
    assert secret not in status.text

    # Confirm activated the session that completed the ceremony.
    assert client.get(f"{API}/platform/dashboard").status_code == 200

    db.expire_all()
    stored = db.get(type(operator), operator.id)
    assert stored.mfa_secret_encrypted is not None
    assert stored.mfa_secret_encrypted != secret
    assert stored.mfa_enrolled_at is not None
    hashes = db.scalars(
        select(MfaRecoveryCode.code_hash).where(MfaRecoveryCode.user_id == operator.id)
    ).all()
    assert len(hashes) == 10
    for recovery in codes:
        assert recovery not in hashes
        assert hash_token(recovery) not in hashes

    # A fresh login starts unverified; a new code upgrades it.
    fresh = _fresh_client()
    _unverified_login(fresh, db, operator)
    assert fresh.get(f"{API}/platform/dashboard").status_code == 403
    verified = fresh.post(
        f"{API}/auth/mfa/verify",
        json={"code": _future_code(secret)},
        headers=_csrf(fresh),
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True
    assert fresh.get(f"{API}/platform/dashboard").status_code == 200


def test_invalid_code_is_refused_and_audited_without_the_code(client, db):
    operator = _operator(db)
    db.commit()
    client = _fresh_client()
    _unverified_login(client, db, operator)
    secret, _ = _complete_enrollment(client, db, operator)

    fresh = _fresh_client()
    _unverified_login(fresh, db, operator)
    response = fresh.post(
        f"{API}/auth/mfa/verify", json={"code": "000000"}, headers=_csrf(fresh)
    )
    assert response.status_code == 401
    assert response.json()["error"]["details"]["reason"] == "invalid_code"
    assert fresh.get(f"{API}/platform/dashboard").status_code == 403

    db.expire_all()
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == "auth.mfa.verification_failed"
        )
    )
    assert event is not None
    assert event.severity == AuditSeverity.WARNING
    serialised = json.dumps(event.payload)
    assert "000000" not in serialised
    assert secret not in serialised


def test_stale_and_replayed_codes_are_rejected(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)
    secret, _ = _complete_enrollment(client, db, operator)

    first = _fresh_client()
    _unverified_login(first, db, operator)
    stale = mfa_core.totp_at(secret, datetime.now(timezone.utc) - timedelta(seconds=95))
    assert first.post(
        f"{API}/auth/mfa/verify", json={"code": stale}, headers=_csrf(first)
    ).status_code == 401

    # Consume the next valid step on one session.
    code = _future_code(secret)
    accepted = first.post(
        f"{API}/auth/mfa/verify", json={"code": code}, headers=_csrf(first)
    )
    assert accepted.status_code == 200, accepted.text

    second = _fresh_client()
    _unverified_login(second, db, operator)
    replay = second.post(
        f"{API}/auth/mfa/verify", json={"code": code}, headers=_csrf(second)
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["details"]["reason"] == "invalid_code"


def test_recovery_code_works_once_and_is_audited(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)
    _, codes = _complete_enrollment(client, db, operator)

    first = _fresh_client()
    _unverified_login(first, db, operator)
    used = first.post(
        f"{API}/auth/mfa/verify",
        json={"recovery_code": codes[0]},
        headers=_csrf(first),
    )
    assert used.status_code == 200, used.text
    assert first.get(f"{API}/platform/dashboard").status_code == 200

    second = _fresh_client()
    _unverified_login(second, db, operator)
    replay = second.post(
        f"{API}/auth/mfa/verify",
        json={"recovery_code": codes[0]},
        headers=_csrf(second),
    )
    assert replay.status_code == 401

    status = second.get(f"{API}/auth/mfa/status").json()
    assert status["recovery_codes_remaining"] == 9

    db.expire_all()
    event = db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "auth.mfa.recovery_used")
    )
    assert event is not None
    assert codes[0] not in json.dumps(event.payload)


def test_brute_force_locks_the_factor_even_for_a_valid_code(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)
    secret, _ = _complete_enrollment(client, db, operator)

    fresh = _fresh_client()
    _unverified_login(fresh, db, operator)
    for _ in range(settings.mfa_max_failed_attempts):
        attempt = fresh.post(
            f"{API}/auth/mfa/verify", json={"code": "111111"}, headers=_csrf(fresh)
        )
        assert attempt.status_code == 401

    db.expire_all()
    stored = db.get(type(operator), operator.id)
    assert stored.mfa_locked_until is not None
    assert stored.mfa_failed_attempts >= settings.mfa_max_failed_attempts

    locked = fresh.post(
        f"{API}/auth/mfa/verify",
        json={"code": _future_code(secret)},
        headers=_csrf(fresh),
    )
    assert locked.status_code in {401, 429}
    assert fresh.get(f"{API}/platform/dashboard").status_code == 403


def test_enrollment_and_confirmation_never_store_a_plaintext_secret(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)

    enrolled = client.post(
        f"{API}/auth/mfa/enroll",
        json={"current_password": PASSWORD},
        headers=_csrf(client),
    )
    assert enrolled.status_code == 200
    secret = enrolled.json()["secret"]
    assert secret in enrolled.text  # shown once, to the enrolled operator
    assert "otpauth://totp/" in enrolled.json()["provisioning_uri"]

    db.expire_all()
    stored = db.get(type(operator), operator.id)
    assert stored.mfa_secret_encrypted != secret

    confirmed = client.post(
        f"{API}/auth/mfa/confirm",
        json={"code": mfa_core.totp_at(secret)},
        headers=_csrf(client),
    )
    assert confirmed.status_code == 200
    assert secret not in confirmed.text

    events = db.scalars(
        select(AuditEvent).where(AuditEvent.event_type.like("auth.mfa.%"))
    ).all()
    assert events
    dump = json.dumps([event.payload for event in events])
    assert secret not in dump
    for value in confirmed.json()["recovery_codes"]:
        assert value not in dump


def test_mfa_disable_requires_password_and_factor_and_revokes_sessions(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)
    secret, _ = _complete_enrollment(client, db, operator)
    # The confirmation consumed the current step; use the next one.
    code = _future_code(secret)

    wrong = client.post(
        f"{API}/auth/mfa/disable",
        json={"current_password": "WrongPass!2345", "code": code},
        headers=_csrf(client),
    )
    assert wrong.status_code == 401

    disabled = client.post(
        f"{API}/auth/mfa/disable",
        json={"current_password": PASSWORD, "code": code},
        headers=_csrf(client),
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["authenticated"] is False
    assert client.get(f"{API}/platform/dashboard").status_code == 401

    db.expire_all()
    stored = db.get(type(operator), operator.id)
    assert stored.mfa_enrolled_at is None
    assert stored.mfa_secret_encrypted is None
    assert db.scalars(
        select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == operator.id)
    ).all() == []


def test_missing_encryption_key_fails_closed(client, db, monkeypatch):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)
    monkeypatch.setattr(settings, "mfa_encryption_key", None)
    mfa_core.reset_mfa_key_cache()

    enrolled = client.post(
        f"{API}/auth/mfa/enroll",
        json={"current_password": PASSWORD},
        headers=_csrf(client),
    )
    assert enrolled.status_code == 503
    assert enrolled.json()["error"]["code"] == "mfa_unavailable"
    # A configuration fault never becomes an authentication bypass.
    blocked = client.get(f"{API}/platform/dashboard")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["details"]["reason"] == "mfa_required"


def test_refresh_rotation_preserves_the_second_factor(client, db):
    operator = _operator(db)
    db.commit()
    _unverified_login(client, db, operator)
    secret, _ = _complete_enrollment(client, db, operator)

    unverified_client = _fresh_client()
    _unverified_login(unverified_client, db, operator)
    unverified_client.post(f"{API}/auth/refresh")
    assert unverified_client.get(f"{API}/platform/dashboard").status_code == 403

    verified_client = _fresh_client()
    _unverified_login(verified_client, db, operator)
    upgraded = verified_client.post(
        f"{API}/auth/mfa/verify",
        json={"code": _future_code(secret)},
        headers=_csrf(verified_client),
    )
    assert upgraded.status_code == 200
    refreshed = verified_client.post(f"{API}/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert verified_client.get(f"{API}/platform/dashboard").status_code == 200


def test_ordinary_user_login_is_unaffected_by_operator_mfa(client, db):
    org = _org(db)
    user, _ = _member(db, org, role=MembershipRole.COORDINATOR, prefix="ordinary")
    db.commit()

    signed_in = client.post(
        f"{API}/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    body = signed_in.json()["user"]
    assert body["mfa_required"] is False
    assert body["mfa_enrollment_required"] is False
    assert client.get(f"{API}/materials").status_code == 200
    assert client.get(f"{API}/platform/dashboard").status_code == 403


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def test_operator_requests_and_a_second_operator_executes(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)

    approval = _new_approval(client, headers, org, reason="Repeated policy breach")
    assert approval["status"] == "pending"
    assert approval["requested_by"] == operator.email
    assert approval["can_decide"] is False  # requester cannot decide
    assert approval["can_execute"] is False

    approver, approver_client, approver_headers = _second_operator_headers(db)
    approved = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve",
        json={"reason": "Verified with compliance"},
        headers=approver_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by"] == approver.email

    executed = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/execute",
        headers=approver_headers,
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["approval"]["status"] == "executed"
    assert executed.json()["organization"]["status"] == "suspended"

    db.expire_all()
    db.refresh(org)
    assert org.status == OrganizationStatus.SUSPENDED
    event_types = set(
        db.scalars(
            select(AuditEvent.event_type).where(
                AuditEvent.entity_type == "platform_approval"
            )
        ).all()
    )
    assert {
        "platform.approval.requested",
        "platform.approval.approved",
        "platform.approval.executed",
    } <= event_types


def test_requester_cannot_approve_or_reject_their_own_request(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org)

    approve = client.post(
        f"{API}/platform/approvals/{approval['id']}/approve", json={}, headers=headers
    )
    assert approve.status_code == 403
    assert approve.json()["error"]["details"]["reason"] == "self_approval_forbidden"

    reject = client.post(
        f"{API}/platform/approvals/{approval['id']}/reject", json={}, headers=headers
    )
    assert reject.status_code == 403

    db.expire_all()
    row = db.get(PlatformApprovalRequest, uuid.UUID(approval["id"]))
    assert row.status == ApprovalStatus.PENDING


def test_organisation_administrator_cannot_request_or_see_approvals(client, db):
    org = _org(db)
    admin, _ = _member(db, org, prefix="orgadmin")
    db.commit()
    headers = _verified_login(client, db, admin, org.id)

    create = client.post(
        f"{API}/platform/approvals",
        json={
            "organization_id": str(org.id),
            "action": "suspend",
            "reason": "Tenant self-suspension",
        },
        headers=headers,
    )
    assert create.status_code == 403
    assert client.get(f"{API}/platform/approvals").status_code == 403


def test_rejection_is_terminal_and_cannot_be_revived(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org)

    approver, approver_client, approver_headers = _second_operator_headers(db)
    rejected = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/reject",
        json={"reason": "Not justified"},
        headers=approver_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    again = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve",
        json={},
        headers=approver_headers,
    )
    assert again.status_code == 409
    assert again.json()["error"]["details"]["status"] == "rejected"

    execute = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/execute",
        headers=approver_headers,
    )
    assert execute.status_code == 409


def test_expired_request_is_refused_and_audited(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org)

    row = db.get(PlatformApprovalRequest, uuid.UUID(approval["id"]))
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    approver, approver_client, approver_headers = _second_operator_headers(db)
    expired = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve",
        json={},
        headers=approver_headers,
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["details"]["reason"] == "approval_expired"

    db.expire_all()
    row = db.get(PlatformApprovalRequest, uuid.UUID(approval["id"]))
    assert row.status == ApprovalStatus.EXPIRED
    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == "platform.approval.expired"
        )
    ) is not None


def test_duplicate_approval_and_execution_are_impossible(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org)

    approver, approver_client, approver_headers = _second_operator_headers(db)
    first = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve", json={}, headers=approver_headers
    )
    assert first.status_code == 200
    second = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve", json={}, headers=approver_headers
    )
    assert second.status_code == 409

    executed = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/execute", headers=approver_headers
    )
    assert executed.status_code == 200
    duplicate = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/execute", headers=approver_headers
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["reason"] == "approval_already_executed"

    db.expire_all()
    assert db.get(PlatformApprovalRequest, uuid.UUID(approval["id"])).status == ApprovalStatus.EXECUTED


def test_execution_rolls_back_when_the_audit_write_fails(client, db, monkeypatch):
    """Tenant state and approval claim must share the audit transaction."""
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org, reason="Rollback evidence")

    _, approver_client, approver_headers = _second_operator_headers(db)
    approved = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve",
        json={"reason": "Independent review"},
        headers=approver_headers,
    )
    assert approved.status_code == 200, approved.text

    def _fail_audit(*args, **kwargs):
        raise RuntimeError("forced audit failure")

    monkeypatch.setattr(approval_service, "_audit", _fail_audit)
    with pytest.raises(RuntimeError, match="forced audit failure"):
        approver_client.post(
            f"{API}/platform/approvals/{approval['id']}/execute",
            headers=approver_headers,
        )

    db.rollback()
    db.expire_all()
    stored_org = db.get(Organization, org.id)
    stored_approval = db.get(PlatformApprovalRequest, uuid.UUID(approval["id"]))
    assert stored_org.status == OrganizationStatus.ACTIVE
    assert stored_approval.status == ApprovalStatus.APPROVED
    assert (
        db.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "platform.approval.executed"
            )
        )
        is None
    )

def test_modified_reason_or_target_invalidates_the_approval(client, db):
    operator = _operator(db)
    org = _org(db)
    other = _org(db, slug="other-target")
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org, reason="Original reason")

    approver, approver_client, approver_headers = _second_operator_headers(db)
    approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve", json={}, headers=approver_headers
    )

    changed_reason = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={
            "status": "suspended",
            "reason": "Different reason",
            "approval_id": approval["id"],
        },
        headers=headers,
    )
    assert changed_reason.status_code == 409
    assert changed_reason.json()["error"]["details"]["reason"] == "approval_mismatch"
    db.expire_all()
    db.refresh(org)
    assert org.status == OrganizationStatus.ACTIVE

    wrong_target = client.patch(
        f"{API}/platform/organizations/{other.id}",
        json={
            "status": "suspended",
            "reason": "Original reason",
            "approval_id": approval["id"],
        },
        headers=headers,
    )
    assert wrong_target.status_code == 409
    assert wrong_target.json()["error"]["details"]["field"] == "organization_id"
    db.expire_all()
    db.refresh(other)
    assert other.status == OrganizationStatus.ACTIVE

    exact = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={
            "status": "suspended",
            "reason": "Original reason",
            "approval_id": approval["id"],
        },
        headers=headers,
    )
    assert exact.status_code == 200, exact.text


def test_patch_requires_an_approved_request(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)

    missing = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={"status": "suspended", "reason": "Policy review"},
        headers=headers,
    )
    assert missing.status_code == 409
    assert missing.json()["error"]["details"]["reason"] == "approval_required"

    # A pending request is not enough.
    approval = _new_approval(client, headers, org)
    pending = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={
            "status": "suspended",
            "reason": "Policy review",
            "approval_id": approval["id"],
        },
        headers=headers,
    )
    assert pending.status_code == 409
    assert pending.json()["error"]["details"]["reason"] == "approval_not_approved"


def test_cancellation_is_requester_only_and_terminal(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org)

    approver, approver_client, approver_headers = _second_operator_headers(db)
    denied = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/cancel", headers=approver_headers
    )
    assert denied.status_code == 403

    cancelled = client.post(
        f"{API}/platform/approvals/{approval['id']}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    approve = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve", json={}, headers=approver_headers
    )
    assert approve.status_code == 409


def test_target_state_drift_invalidates_an_approved_request(client, db):
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    approval = _new_approval(client, headers, org)

    approver, approver_client, approver_headers = _second_operator_headers(db)
    approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/approve", json={}, headers=approver_headers
    )

    org.status = OrganizationStatus.SUSPENDED
    org.suspended_at = datetime.now(timezone.utc)
    db.commit()

    drift = approver_client.post(
        f"{API}/platform/approvals/{approval['id']}/execute", headers=approver_headers
    )
    assert drift.status_code == 409
    assert drift.json()["error"]["details"]["reason"] == "approval_invalidated"

    db.expire_all()
    assert db.get(PlatformApprovalRequest, uuid.UUID(approval["id"])).status == ApprovalStatus.CANCELLED
    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == "platform.approval.invalidated"
        )
    ) is not None


# ---------------------------------------------------------------------------
# Session governance
# ---------------------------------------------------------------------------


def test_platform_operator_session_can_be_revoked_and_is_audited(client, db):
    operator = _operator(db)
    other = _operator(db)
    db.commit()
    _verified_login(client, db, operator)

    other_client = _fresh_client()
    _verified_login(other_client, db, other)
    other_session = other_client.cookies.get("lm_session")

    listing = client.get(f"{API}/platform/sessions")
    assert listing.status_code == 200
    rows = listing.json()["items"]
    assert any(row["is_current"] for row in rows)
    target = next(row for row in rows if row["user_email"] == other.email)
    assert target["mfa_verified_at"] is not None
    assert "lm_session" not in json.dumps(target)

    revoked = client.post(
        f"{API}/platform/sessions/{target['id']}/revoke", headers=_csrf(client)
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_count"] == 1

    denied = other_client.get(f"{API}/platform/dashboard")
    assert denied.status_code == 401
    assert denied.json()["error"]["details"]["reason"] == "session_revoked"
    assert other_client.cookies.get("lm_session") == other_session

    event = db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "platform.session.revoked")
    )
    assert event is not None
    assert event.severity == AuditSeverity.WARNING


def test_current_platform_session_cannot_be_revoked_through_governance(client, db):
    operator = _operator(db)
    db.commit()
    _verified_login(client, db, operator)
    current = client.get(f"{API}/platform/sessions").json()["items"][0]

    response = client.post(
        f"{API}/platform/sessions/{current['id']}/revoke", headers=_csrf(client)
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "cannot_revoke_current"


def test_revoke_all_keeps_the_calling_session_and_denies_the_rest(client, db):
    operator = _operator(db)
    other = _operator(db)
    db.commit()
    _verified_login(client, db, operator)
    other_client = _fresh_client()
    _verified_login(other_client, db, other)

    revoked = client.post(
        f"{API}/platform/sessions/revoke-all", headers=_csrf(client)
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_count"] >= 1
    assert client.get(f"{API}/platform/dashboard").status_code == 200
    assert other_client.get(f"{API}/platform/dashboard").status_code == 401

    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == "platform.session.revoked_all"
        )
    ) is not None


def test_platform_session_absolute_limit_and_privilege_removal(client, db):
    operator = _operator(db)
    db.commit()
    _verified_login(client, db, operator)

    session_row = db.scalar(
        select(__import__("app.db.models.identity", fromlist=["AuthSession"]).AuthSession).where(
            __import__("app.db.models.identity", fromlist=["AuthSession"]).AuthSession.user_id
            == operator.id
        )
    )
    session_row.mfa_verified_at = datetime.now(timezone.utc) - timedelta(
        hours=settings.platform_session_absolute_hours + 1
    )
    db.commit()
    expired = client.get(f"{API}/platform/dashboard")
    assert expired.status_code == 401
    assert expired.json()["error"]["details"]["limit"] == "absolute"

    # A fresh verified session is refused as soon as the operator flag is gone.
    fresh = _fresh_client()
    _verified_login(fresh, db, operator)
    assert fresh.get(f"{API}/platform/dashboard").status_code == 200
    operator.is_platform_admin = False
    db.commit()
    removed = fresh.get(f"{API}/platform/dashboard")
    assert removed.status_code == 403
    assert removed.json()["error"]["details"]["reason"] == "platform_scope_required"


def test_idle_platform_session_expires_without_affecting_organisation_membership(client, db):
    org = _org(db)
    operator = _operator(db)
    member, _ = _member(db, org, role=MembershipRole.COORDINATOR, prefix="bystander")
    db.commit()
    _verified_login(client, db, operator)
    member_client = _fresh_client()
    _verified_login(member_client, db, member, org.id)

    from app.db.models.identity import AuthSession

    row = db.scalar(select(AuthSession).where(AuthSession.user_id == operator.id))
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.platform_session_idle_minutes + 1
    )
    db.commit()

    idle = client.get(f"{API}/platform/dashboard")
    assert idle.status_code == 401
    assert idle.json()["error"]["details"]["limit"] == "idle"

    # The ordinary organisation session is untouched by a platform policy.
    assert member_client.get(f"{API}/materials").status_code == 200


# ---------------------------------------------------------------------------
# Audit export
# ---------------------------------------------------------------------------


def _export(client, *, headers, format="csv", **params):
    query = {
        "created_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "created_to": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
        "format": format,
    }
    query.update(params)
    return client.get(f"{API}/platform/audit/export", params=query, headers=headers)


def _seed_export_events(db):
    audit_service.record_event(
        db,
        event_type="test.export",
        entity_type="test",
        actor="=HYPERLINK(\"http://evil\")",
        actor_id="formula",
        summary="@SUM(1,1)",
        payload={"token": "super-secret-token", "password": "hash-value", "note": "safe"},
    )
    audit_service.record_event(
        db,
        event_type="test.export",
        entity_type="test",
        actor="operator@example.com",
        actor_id="operator",
        summary="Second event",
        payload={"nested": {"recovery_code": "LM-AAAA-BBBB"}},
    )
    db.commit()


def test_csv_export_is_bounded_redacted_and_formula_safe(client, db):
    operator = _operator(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    _seed_export_events(db)

    response = _export(client, headers=headers, format="csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"loopmesh-audit-" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"

    text = response.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) >= 2
    event = next(row for row in rows if row["actor_id"] == "formula")
    assert event["summary"].startswith("'@")
    assert event["actor"].startswith("'=")
    assert "super-secret-token" not in text
    assert "hash-value" not in text
    assert "LM-AAAA-BBBB" not in text
    assert "[redacted]" in text

    db.expire_all()
    exported = db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "platform.audit.exported")
    )
    assert exported is not None
    assert exported.payload["format"] == "csv"
    assert exported.payload["row_count"] == len(rows)
    assert exported.payload["filters"]["event_type"] is None

    # Source records are unchanged: the original sensitive payload still exists
    # in the journal, proving export is read-only and redaction is presentational.
    source = db.scalar(select(AuditEvent).where(AuditEvent.actor_id == "formula"))
    assert source.payload["token"] == "super-secret-token"


def test_json_export_is_valid_and_deterministic(client, db):
    operator = _operator(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    _seed_export_events(db)

    first = _export(client, headers=headers, format="json")
    second = _export(client, headers=headers, format="json")
    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"].startswith("application/json")

    body = first.json()
    assert body["row_count"] == len(body["events"])
    assert body["row_count"] >= 2
    assert "super-secret-token" not in first.text
    assert [row["created_at"] for row in body["events"]] == sorted(
        row["created_at"] for row in body["events"]
    )
    # Each export records its own audit event, so compare the seeded source rows
    # by their stable, filterable identity rather than the whole journal.
    first_ids = [row["id"] for row in body["events"] if row["event_type"] == "test.export"]
    second_ids = [
        row["id"]
        for row in second.json()["events"]
        if row["event_type"] == "test.export"
    ]
    assert first_ids == second_ids
    assert len(first_ids) == 2


def test_export_enforces_permissions_and_explicit_bounded_range(client, db):
    org = _org(db)
    admin, _ = _member(db, org, prefix="exportadmin")
    operator = _operator(db)
    db.commit()

    admin_headers = _verified_login(client, db, admin, org.id)
    assert _export(client, headers=admin_headers).status_code == 403

    unverified = _operator(db)
    db.commit()
    unverified_client = _fresh_client()
    _unverified_login(unverified_client, db, unverified)
    assert _export(unverified_client, headers={}).status_code == 403

    headers = _verified_login(client, db, operator)
    missing = client.get(f"{API}/platform/audit/export", headers=headers)
    assert missing.status_code == 422
    assert missing.json()["error"]["details"]["reason"] == "export_range_required"

    too_wide = client.get(
        f"{API}/platform/audit/export",
        params={
            "created_from": (datetime.now(timezone.utc) - timedelta(days=120)).isoformat(),
            "created_to": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    assert too_wide.status_code == 422
    assert too_wide.json()["error"]["details"]["reason"] == "export_range_too_large"


def test_export_row_limit_is_enforced_without_materialising_unbounded_rows(
    client, db, monkeypatch
):
    operator = _operator(db)
    db.commit()
    headers = _verified_login(client, db, operator)
    monkeypatch.setattr(settings, "platform_audit_export_max_rows", 1)
    _seed_export_events(db)
    response = _export(client, headers=headers)
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["reason"] == "export_too_large"
    assert details["max_rows"] == 1
    assert details["matching_rows"] > 1


def test_export_cannot_be_triggered_by_an_org_admin_even_with_filters(client, db):
    org = _org(db)
    admin, _ = _member(db, org, prefix="nosyadmin")
    db.commit()
    headers = _verified_login(client, db, admin, org.id)
    response = _export(
        client,
        headers=headers,
        organization_id=str(org.id),
        event_type="platform.organization.suspended",
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "platform_scope_required"
