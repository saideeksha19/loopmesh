"""Checkpoint B/D authentication and identity foundation tests."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.actors import utcnow
from app.core.exceptions import AuthenticationError
from app.core.security import hash_password, hash_token
from app.core.sessions import as_utc, find_by_access_token
from app.db.enums import (
    AuditSeverity,
    InvitationStatus,
    MembershipRole,
    MembershipScope,
    MembershipStatus,
)
from app.db.models.audit import AuditEvent
from app.db.models.identity import (
    AuthSession,
    Invitation,
    OrganizationMembership,
    PasswordResetToken,
    User,
)
from app.db.models.organization import Organization
from tests.conftest import login_client, make_membership, make_organization, make_user

API = "/api/v1/auth"
ROLE = MembershipRole
ORG_ADMIN = MembershipRole.ORG_ADMIN


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("lm_csrf")
    if not token:
        for cookie in client.cookies.jar:
            if cookie.name == "lm_csrf":
                token = cookie.value
    return {"X-CSRF-Token": token or ""}


def _make_org(db: Session, slug: str = "acme-cooperative") -> Organization:
    return make_organization(db, name="Acme Cooperative", slug=slug)


def _register_active_user(
    db: Session, org: Organization, *, password: str = "StrongPass!2345", role: MembershipRole = ORG_ADMIN
) -> User:
    user = make_user(db, email=f"{uuid.uuid4().hex[:8]}@example.com", password=password)
    make_membership(db, user, org, role=role)
    db.commit()
    return user


def _production_request(token: str, *, path: str = "/api/v1/auth/me"):
    """Build a real Starlette Request carrying a session cookie."""
    from starlette.requests import Request as StarletteRequest

    from app.core.config import settings

    return StarletteRequest(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"cookie", f"{settings.auth_session_cookie}={token}".encode())],
            "client": ("testclient", 49999),
            "server": ("testserver", 80),
        }
    )


def test_provisioning_cli_refuses_when_user_exists(db, tmp_path):
    make_user(db, email="existing@example.com")
    db.commit()
    users = db.scalars(select(User)).all()
    assert len(users) >= 1


def test_login_logout_refresh_me_and_session_listing(client, db):
    org = _make_org(db)
    password = "StrongPass!2345"
    user = make_user(db, email="member@example.com", password=password)
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    db.commit()

    res = client.post(f"{API}/login", json={"email": user.email, "password": password})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == user.email
    assert client.cookies.get("lm_session")
    assert client.cookies.get("lm_refresh")
    assert client.cookies.get("lm_csrf")

    me = client.get(f"{API}/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)

    sessions = client.get(f"{API}/sessions")
    assert sessions.status_code == 200
    rows = sessions.json()
    assert len(rows) >= 1
    assert any(r["is_current"] for r in rows)

    old_access = client.cookies.get("lm_session")
    ref = client.post(f"{API}/refresh")
    assert ref.status_code == 200, ref.text
    assert client.cookies.get("lm_session") != old_access

    out = client.post(f"{API}/logout", headers=_csrf(client))
    assert out.status_code == 200
    assert out.json()["authenticated"] is False


def test_login_failure_generic_and_lockout(client, db, monkeypatch):
    org = _make_org(db, "lock-org")
    password = "StrongPass!2345"
    user = make_user(db, email="lock@example.com", password=password)
    make_membership(db, user, org)
    db.commit()

    r1 = client.post(f"{API}/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert r1.status_code == 401
    assert r1.json()["error"]["message"] == "Invalid email or password."

    r2 = client.post(f"{API}/login", json={"email": user.email, "password": "wrong-password"})
    assert r2.status_code == 401
    assert r2.json()["error"]["message"] == "Invalid email or password."

    db.refresh(user)
    user.failed_login_attempts = 100
    user.locked_until = utcnow() + timedelta(minutes=30)
    db.commit()

    # Policy change (Phase 2B Batch 4): a lock is bounded backoff, so it rejects
    # further *guesses* but must not block the owner's correct password --
    # otherwise anyone knowing the email could deny access indefinitely.
    db.refresh(user)
    locked_at = user.locked_until

    r3 = client.post(f"{API}/login", json={"email": user.email, "password": "wrong-password"})
    assert r3.status_code == 401
    assert r3.json()["error"]["message"] == "Invalid email or password."
    db.refresh(user)
    assert user.locked_until == locked_at  # an attempt made while locked never extends the lock
    assert user.failed_login_attempts == 100  # nor is it counted towards a longer lock

    r4 = client.post(f"{API}/login", json={"email": user.email, "password": password})
    assert r4.status_code == 200, r4.text
    db.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_csrf_required_for_cookie_authenticated_mutation(client, db):
    org = _make_org(db, "csrf-org")
    user = make_user(db, email="csrf@example.com")
    make_membership(db, user, org, role=MembershipRole.ORG_ADMIN)
    login_client(client, db, user, organization_id=org.id)

    res = client.post(f"{API}/switch-organization", json={"organization_id": str(org.id)})
    assert res.status_code in {401, 403}

    ok = client.post(
        f"{API}/switch-organization",
        json={"organization_id": str(org.id)},
        headers=_csrf(client),
    )
    assert ok.status_code == 200, ok.text


def test_invitation_create_accept_revoke_and_reuse_prevented(client, db):
    org = _make_org(db, "invite-org")
    admin = make_user(db, email="admin-invite@example.com", is_platform_admin=True)
    make_membership(db, admin, org, role=MembershipRole.ORG_ADMIN)
    csrf = login_client(client, db, admin, organization_id=org.id)

    create = client.post(
        f"{API}/invitations",
        json={
            "email": "newmember@example.com",
            "organization_id": str(org.id),
            "role": MembershipRole.COORDINATOR.value,
            "scope": MembershipScope.ORGANIZATION.value,
        },
        headers=csrf,
    )
    assert create.status_code == 201, create.text
    inv = create.json()
    assert inv["status"] == "pending"
    token = inv.get("delivery_token")
    assert token

    bad = client.post(
        f"{API}/invitations/accept",
        json={
            "token": "x" * 32,
            "full_name": "New Member",
            "password": "StrongPass!2345",
        },
    )
    assert bad.status_code == 401

    accept = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "New Member", "password": "StrongPass!2345"},
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["authenticated"] is True

    reuse = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "New Member", "password": "StrongPass!2345"},
    )
    assert reuse.status_code == 401

    client.cookies.clear()
    csrf = login_client(client, db, admin, organization_id=org.id)
    create2 = client.post(
        f"{API}/invitations",
        json={
            "email": "revoked@example.com",
            "organization_id": str(org.id),
            "role": "viewer",
            "scope": "organization",
        },
        headers=csrf,
    )
    inv2 = create2.json()
    revoked = client.post(f"{API}/invitations/{inv2['id']}/revoke", headers=csrf)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    denied = client.post(
        f"{API}/invitations/accept",
        json={
            "token": inv2["delivery_token"],
            "full_name": "Revoked User",
            "password": "StrongPass!2345",
        },
    )
    assert denied.status_code == 401


def test_expired_invitation_rejected(client, db):
    org = _make_org(db, "exp-invite-org")
    admin = make_user(db, email="admin-exp@example.com", is_platform_admin=True)
    token = f"tok-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    now = utcnow()
    inv = Invitation(
        email="late@example.com",
        organization_id=org.id,
        role=MembershipRole.VIEWER,
        scope=MembershipScope.ORGANIZATION,
        status=InvitationStatus.PENDING,
        token_hash=hash_token(token),
        expires_at=now - timedelta(minutes=5),
        invited_by_user_id=admin.id,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    db.add(inv)
    db.commit()
    res = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Late User", "password": "StrongPass!2345"},
    )
    assert res.status_code == 401


def test_existing_user_can_accept_additional_membership(client, db):
    org1 = _make_org(db, "org-one")
    org2 = make_organization(db, name="Org Two", slug="org-two")
    password = "StrongPass!2345"
    user = make_user(db, email="multi@example.com", password=password)
    make_membership(db, user, org1, role=MembershipRole.COORDINATOR)
    admin = make_user(db, email="admin-multi@example.com", is_platform_admin=True)
    token = f"tok-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    inv = Invitation(
        email=user.email,
        organization_id=org2.id,
        role=MembershipRole.REVIEWER,
        scope=MembershipScope.ORGANIZATION,
        status=InvitationStatus.PENDING,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=7),
        invited_by_user_id=admin.id,
    )
    db.add(inv)
    db.commit()

    res = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": user.full_name, "password": password},
    )
    assert res.status_code == 200, res.text

    memberships = db.scalars(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
    ).all()
    org_ids = {m.organization_id for m in memberships}
    assert org1.id in org_ids and org2.id in org_ids

    users = db.scalars(select(User).where(User.email == user.email)).all()
    assert len(users) == 1


def test_role_escalation_prevented_for_non_platform_inviter(client, db):
    org = _make_org(db, "esc-org")

    org_admin = make_user(db, email="orgadmin@example.com", is_platform_admin=False)
    make_membership(
        db, user=org_admin, organization=org, role=MembershipRole.ORG_ADMIN
    )
    csrf = login_client(client, db, org_admin, organization_id=org.id)

    res = client.post(
        f"{API}/invitations",
        json={
            "email": "victim@example.com",
            "organization_id": str(org.id),
            "role": "viewer",
            "scope": "platform",
        },
        headers=csrf,
    )
    assert res.status_code == 403


def test_password_reset_request_generic_and_completion_revokes_sessions(client, db):
    org = _make_org(db, "reset-org")
    password = "StrongPass!2345"
    user = make_user(db, email="reset@example.com", password=password)
    make_membership(db, user, org)
    login_client(client, db, user, organization_id=org.id)
    db.commit()

    r1 = client.post(f"{API}/forgot-password", json={"email": "nobody-reset@example.com"})
    r2 = client.post(f"{API}/forgot-password", json={"email": user.email})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["message"] == r2.json()["message"]
    token = r2.json().get("delivery_token")
    assert token

    done = client.post(
        f"{API}/reset-password",
        json={"token": token, "new_password": "NewStrongPass!6789"},
    )
    assert done.status_code == 200, done.text

    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id)
    ).all()
    assert sessions and all(s.revoked_at is not None for s in sessions)

    reuse = client.post(
        f"{API}/reset-password",
        json={"token": token, "new_password": "AnotherStrong!999"},
    )
    assert reuse.status_code == 401

    login = client.post(f"{API}/login", json={"email": user.email, "password": "NewStrongPass!6789"})
    assert login.status_code == 200


def test_expired_reset_token_rejected(client, db):
    org = _make_org(db, "exp-reset-org")
    user = make_user(db, email="expreset@example.com")
    make_membership(db, user, org)
    token = f"rst-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    now = utcnow()
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    db.add(row)
    db.commit()
    res = client.post(
        f"{API}/reset-password",
        json={"token": token, "new_password": "NewStrongPass!6789"},
    )
    assert res.status_code == 401


def test_session_revoke_specific_and_revoke_others(client, db):
    org = _make_org(db, "sess-org")
    user = make_user(db, email="sess@example.com")
    make_membership(db, user, org)
    csrf = login_client(client, db, user, organization_id=org.id)

    from app.core.sessions import issue_session

    other, _bundle = issue_session(db, user, organization_id=org.id)
    db.commit()

    listed = client.get(f"{API}/sessions").json()
    assert len(listed) >= 2

    revoked_others = client.post(f"{API}/sessions/revoke-others", headers=csrf)
    assert revoked_others.status_code == 200
    db.refresh(other)
    assert other.revoked_at is not None

    other_user = make_user(db, email="other@example.com")
    make_membership(db, other_user, org)
    foreign, _ = issue_session(db, other_user, organization_id=org.id)
    db.commit()
    nope = client.post(f"{API}/sessions/{foreign.id}/revoke", headers=csrf)
    assert nope.status_code == 404


def test_password_change_invalidates_sessions(client, db):
    org = _make_org(db, "pw-org")
    password = "StrongPass!2345"
    user = make_user(db, email="pw@example.com", password=password)
    make_membership(db, user, org)
    csrf = login_client(client, db, user, organization_id=org.id)

    res = client.post(
        f"{API}/change-password",
        json={"current_password": password, "new_password": "EvenStronger!6789"},
        headers=csrf,
    )
    assert res.status_code == 200, res.text

    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id)
    ).all()
    assert sessions and all(s.revoked_at is not None for s in sessions)


def test_auth_audit_events_recorded(client, db):
    org = _make_org(db, "audit-org")
    password = "StrongPass!2345"
    user = make_user(db, email="audit@example.com", password=password)
    make_membership(db, user, org)
    db.commit()

    client.post(f"{API}/login", json={"email": user.email, "password": "wrong"})
    client.post(f"{API}/login", json={"email": user.email, "password": password})
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == user.id)).all()
    types = [e.event_type for e in events]
    assert any(e.event_type == "auth.login_failed" for e in events)
    assert "auth.login_succeeded" in types

    for e in db.scalars(select(AuditEvent)).all():
        payload = e.payload
        blob = str(payload).lower()
        assert "password" not in blob and e.event_type not in {
            "password_changed",
            "password_reset",
        }
        assert "lm_session" not in blob
        assert "token_hash" not in blob


def test_actor_dependency_override_receives_real_request_object(client, db):
    org = _make_org(db, "req-obj-org")
    user = make_user(db, email="reqobj@example.com")
    make_membership(db, user, org, role=MembershipRole.VIEWER)
    login_client(client, db, user, organization_id=org.id)

    res = client.get(f"{API}/me")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == user.email
    assert "error" not in body
    # A dependency declared over the Request object must not be treated as a
    # query/model parameter (that would surface as a 422).
    assert res.status_code != 422


def test_existing_user_invitation_acceptance_sets_membership_timestamps_in_order(client, db):
    org1 = _make_org(db, "ts-org-one")
    org2 = make_organization(db, name="TS Org Two", slug="ts-org-two")
    password = "StrongPass!2345"
    user = make_user(db, email="ts-multi@example.com", password=password)
    make_membership(db, user, org1, role=MembershipRole.COORDINATOR)
    admin = make_user(db, email="ts-admin@example.com", is_platform_admin=True)
    token = f"tok-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    inv = Invitation(
        email=user.email,
        organization_id=org2.id,
        role=MembershipRole.REVIEWER,
        scope=MembershipScope.ORGANIZATION,
        status=InvitationStatus.PENDING,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=7),
        invited_by_user_id=admin.id,
    )
    db.add(inv)
    db.commit()

    res = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": user.full_name, "password": password},
    )
    assert res.status_code == 200, res.text

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org2.id,
        )
    )
    assert membership
    assert membership.accepted_at is not None
    assert membership.created_at is not None
    assert membership.accepted_at >= membership.created_at
    assert membership.status == MembershipStatus.ACTIVE

    reuse = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": user.full_name, "password": password},
    )
    assert reuse.status_code == 401


def test_existing_membership_reactivation_on_invitation_acceptance_preserves_timestamp_invariant(
    client, db
):
    org = _make_org(db, "react-org")
    password = "StrongPass!2345"
    user = make_user(db, email="react@example.com", password=password)
    existing = make_membership(
        db, user=user, organization=org, role=MembershipRole.VIEWER, status=MembershipStatus.SUSPENDED
    )
    db.commit()
    original_created_at = existing.created_at

    admin = make_user(db, email="react-admin@example.com", is_platform_admin=True)
    token = f"tok-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    inv = Invitation(
        email=user.email,
        organization_id=org.id,
        role=MembershipRole.REVIEWER,
        scope=MembershipScope.ORGANIZATION,
        status=InvitationStatus.PENDING,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=7),
        invited_by_user_id=admin.id,
    )
    db.add(inv)
    db.commit()

    res = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": user.full_name, "password": password},
    )
    assert res.status_code == 200, res.text

    db.refresh(existing)
    assert existing.status == MembershipStatus.ACTIVE
    assert existing.role == MembershipRole.REVIEWER
    assert existing.accepted_at is not None
    assert existing.created_at is not None

    orig = original_created_at.replace(tzinfo=None)
    curr = existing.created_at.replace(tzinfo=None)
    assert curr == orig
    assert existing.accepted_at >= existing.created_at


def test_production_actor_dependency_rejects_legacy_actor_header(db):
    from starlette.requests import Request as StarletteRequest

    from app.api import deps as production_deps

    production_get_actor = production_deps.get_actor
    AuthenticationError = production_deps.AuthenticationError

    request = StarletteRequest(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/proposals",
            "raw_path": b"/api/v1/proposals",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"x-actor-id", b"demo-platform-admin")],
            "client": ("testclient", 49999),
            "server": ("testserver", 80),
        }
    )
    with pytest.raises(AuthenticationError) as excinfo:
        production_get_actor(request, db)
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "legacy_actor_header_rejected"


def test_production_actor_dependency_requires_a_session(db):
    from starlette.requests import Request as StarletteRequest

    from app.api import deps as production_deps

    production_get_actor = production_deps.get_actor
    AuthenticationError = production_deps.AuthenticationError

    request = StarletteRequest(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/proposals",
            "raw_path": b"/api/v1/proposals",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("testclient", 49999),
            "server": ("testserver", 80),
        }
    )
    with pytest.raises(AuthenticationError) as excinfo:
        production_get_actor(request, db)
    assert excinfo.value.status_code == 401
    assert excinfo.value.details["reason"] == "session_required"


def test_production_actor_dependency_rejects_unknown_session_token(db):
    from starlette.requests import Request as StarletteRequest

    from app.api import deps as production_deps
    from app.core.config import settings

    production_get_actor = production_deps.get_actor
    AuthenticationError = production_deps.AuthenticationError

    request = StarletteRequest(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/auth/me",
            "raw_path": b"/api/v1/auth/me",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (
                    b"cookie",
                    f"{settings.auth_session_cookie}=forged-token-value".encode(),
                )
            ],
            "client": ("testclient", 49999),
            "server": ("testserver", 80),
        }
    )
    with pytest.raises(AuthenticationError) as excinfo:
        production_get_actor(request, db)
    assert excinfo.value.status_code == 401
    assert excinfo.value.details["reason"] == "session_unknown"


def test_production_dependency_resolves_principal_after_database_round_trip(
    client, db, session_factory
):
    """A real SQLite row must not break the session touch.

    SQLite hands back naive datetimes, so the production dependency has to
    normalise ``last_seen_at`` before subtracting it from an aware ``utcnow()``.
    """

    org = _make_org(db, "roundtrip-org")
    user = make_user(db, email="roundtrip@example.com", password="StrongPass!2345")
    make_membership(db, user, org, role=MembershipRole.ORG_ADMIN)
    login_client(client, db, user, organization_id=org.id)
    token = client.cookies.get("lm_session")
    assert token

    stale = utcnow() - timedelta(minutes=5)
    with session_factory() as fresh:
        record = find_by_access_token(fresh, token)
        assert record is not None
        record.last_seen_at = stale
        fresh.commit()

    from app.api.deps import get_actor as production_get_actor

    with session_factory() as fresh:
        actor = production_get_actor(_production_request(token), fresh)
    assert actor.user_id == user.id
    assert actor.organization_id == org.id
    assert actor.role == MembershipRole.ORG_ADMIN

    with session_factory() as fresh:
        record = find_by_access_token(fresh, token)
        assert record is not None
        assert as_utc(record.last_seen_at) > stale


def test_production_dependency_rejects_revoked_session_immediately(client, db, session_factory):
    org = _make_org(db, "revoked-org")
    user = make_user(db, email="revoked-path@example.com", password="StrongPass!2345")
    make_membership(db, user, org)
    login_client(client, db, user, organization_id=org.id)
    token = client.cookies.get("lm_session")
    assert token

    with session_factory() as fresh:
        record = find_by_access_token(fresh, token)
        assert record is not None
        record.revoked_at = utcnow()
        fresh.commit()

    from app.api.deps import get_actor as production_get_actor

    with session_factory() as fresh, pytest.raises(AuthenticationError) as excinfo:
        production_get_actor(_production_request(token), fresh)
    assert excinfo.value.status_code == 401
    assert excinfo.value.details["reason"] == "session_revoked"
