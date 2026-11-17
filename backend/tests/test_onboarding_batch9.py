"""Batch 9: onboarding, invitation acceptance, forced rotation and sessions.

These tests exercise the contracts the frontend depends on, and the security
properties behind them:

* an invitation is single-use, expiring, tenant-scoped and stored as a hash;
* acceptance creates the account and the membership together and marks the
  password as chosen by its owner (so no forced rotation is owed);
* an initial operator-issued password cannot reach workspace data until the
  user replaces it — not through the UI, and not by calling the API directly;
* session listing and revocation never cross the user boundary and a revoked
  session cannot be replayed.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.actors import utcnow
from app.core.security import hash_token
from app.core.sessions import issue_session
from app.db.enums import (
    InvitationStatus,
    MembershipRole,
    MembershipScope,
    MembershipStatus,
)
from app.db.models.identity import (
    AuthSession,
    Invitation,
    OrganizationMembership,
    User,
)
from app.db.models.organization import Organization
from tests.conftest import login_client, make_membership, make_organization, make_user

API = "/api/v1/auth"
PASSWORD = "StrongPass!2345"
ROTATED = "RotatedPass!6789"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("lm_csrf") or ""
    return {"X-CSRF-Token": token}


def _org(db: Session, slug: str, name: str | None = None) -> Organization:
    return make_organization(db, name=name or slug.replace("-", " ").title(), slug=slug)


def _admin(db: Session, org: Organization, email: str | None = None) -> User:
    user = make_user(db, email=email or f"admin-{uuid.uuid4().hex[:8]}@example.com")
    make_membership(db, user, org, role=MembershipRole.ORG_ADMIN)
    db.commit()
    return user


def _invite(client: TestClient, csrf: dict[str, str], org: Organization, email: str, **overrides):
    payload = {
        "email": email,
        "organization_id": str(org.id),
        "role": overrides.get("role", MembershipRole.COORDINATOR.value),
        "scope": overrides.get("scope", MembershipScope.ORGANIZATION.value),
    }
    payload.update({k: v for k, v in overrides.items() if k not in {"role", "scope"}})
    return client.post(f"{API}/invitations", json=payload, headers=csrf)


def _rotation_user(db: Session, org: Organization, *, email: str | None = None) -> User:
    """An account whose password was issued by an operator, never chosen."""
    user = make_user(db, email=email or f"rotate-{uuid.uuid4().hex[:8]}@example.com")
    user.password_changed_at = None
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    db.commit()
    return user


# ---------------------------------------------------------------------------
# invitations: creation, listing, preview
# ---------------------------------------------------------------------------


def test_org_admin_creates_invitation_and_only_the_hash_is_stored(client, db):
    org = _org(db, "batch9-invite-org")
    admin = _admin(db, org)
    csrf = login_client(client, db, admin, organization_id=org.id)

    response = _invite(client, csrf, org, "invitee@example.com", role="reviewer")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["role"] == "reviewer"
    assert body["organization_id"] == str(org.id)
    assert body["organization_name"] == org.name

    token = body["delivery_token"]
    assert token, "development delivery must return a usable link token"

    stored = db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(body["id"])))
    assert stored is not None
    assert stored.token_hash == hash_token(token)
    assert stored.token_hash != token
    assert len(stored.token_hash) == 64


def test_invitation_requires_the_invite_permission(client, db):
    org = _org(db, "batch9-perm-org")
    coordinator = make_user(db, email=f"coord-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, coordinator, org, role=MembershipRole.COORDINATOR)
    csrf = login_client(client, db, coordinator, organization_id=org.id)

    response = _invite(client, csrf, org, "blocked@example.com")

    assert response.status_code == 403, response.text
    assert response.json()["error"]["details"]["required_permission"] == "invitation.manage"
    assert db.scalars(select(Invitation)).all() == []


def test_invitation_rejects_bad_email_role_and_scope(client, db):
    org = _org(db, "batch9-validation-org")
    admin = _admin(db, org)
    csrf = login_client(client, db, admin, organization_id=org.id)

    bad_email = _invite(client, csrf, org, "not-an-email")
    assert bad_email.status_code == 422, bad_email.text

    bad_role = _invite(client, csrf, org, "role@example.com", role="superuser")
    assert bad_role.status_code == 422, bad_role.text
    assert bad_role.json()["error"]["details"]["field"] == "role"

    bad_scope = _invite(client, csrf, org, "scope@example.com", scope="galaxy")
    assert bad_scope.status_code == 422, bad_scope.text
    assert bad_scope.json()["error"]["details"]["field"] == "scope"

    assert db.scalars(select(Invitation)).all() == []


def test_invitation_cannot_target_another_organisation(client, db):
    home = _org(db, "batch9-home-org")
    other = _org(db, "batch9-other-org")
    admin = _admin(db, home)
    csrf = login_client(client, db, admin, organization_id=home.id)

    response = _invite(client, csrf, other, "cross@example.com")

    assert response.status_code == 403, response.text
    assert response.json()["error"]["details"]["reason"] == "organisation_scope"
    assert db.scalars(select(Invitation)).all() == []


def test_invitation_list_is_tenant_scoped_and_hides_tokens(client, db):
    home = _org(db, "batch9-list-home")
    other = _org(db, "batch9-list-other")

    admin = _admin(db, home)
    csrf = login_client(client, db, admin, organization_id=home.id)

    mine = _invite(client, csrf, home, f"member-{uuid.uuid4().hex[:6]}@example.com")
    assert mine.status_code == 201, mine.text

    foreign_admin = _admin(db, other)
    foreign_token = f"foreign-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    db.add(
        Invitation(
            email="foreign@example.com",
            organization_id=other.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(foreign_token),
            expires_at=utcnow() + timedelta(days=3),
            invited_by_user_id=foreign_admin.id,
        )
    )
    db.commit()

    listed = client.get(f"{API}/invitations", headers=csrf)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["organization_id"] for row in rows] == [str(home.id)]
    assert all(row["delivery_token"] is None for row in rows)
    assert all(row["email"] != "foreign@example.com" for row in rows)

    pending_only = client.get(f"{API}/invitations?status=pending", headers=csrf)
    assert pending_only.status_code == 200
    invalid = client.get(f"{API}/invitations?status=bogus", headers=csrf)
    assert invalid.status_code == 422

    # A member without the capability cannot read the register at all.
    viewer = make_user(db, email=f"viewer-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, viewer, home, role=MembershipRole.VIEWER)
    client.cookies.clear()
    viewer_csrf = login_client(client, db, viewer, organization_id=home.id)
    denied = client.get(f"{API}/invitations", headers=viewer_csrf)
    assert denied.status_code == 403


def test_invitation_preview_describes_the_token_without_consuming_it(client, db):
    org = _org(db, "batch9-preview-org", name="Preview Works")
    admin = _admin(db, org)
    csrf = login_client(client, db, admin, organization_id=org.id)
    created = _invite(client, csrf, org, "preview@example.com", role="auditor")
    token = created.json()["delivery_token"]

    client.cookies.clear()
    preview = client.get(f"{API}/invitations/preview", params={"token": token})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["organization_name"] == "Preview Works"
    assert body["role"] == "auditor"
    assert body["email"] == "preview@example.com"
    assert body["status"] == "pending"
    assert body["delivery_token"] is None, "a preview must never re-issue the token"

    unknown = client.get(f"{API}/invitations/preview", params={"token": "z" * 40})
    assert unknown.status_code == 404

    # Previewing does not spend the invitation.
    accepted = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Preview Member", "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text


def test_preview_reports_expiry_and_revocation(client, db):
    org = _org(db, "batch9-preview-state")
    admin = _admin(db, org)
    expired_token = f"expired-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    db.add(
        Invitation(
            email="late@example.com",
            organization_id=org.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(expired_token),
            expires_at=utcnow() - timedelta(hours=1),
            invited_by_user_id=admin.id,
            created_at=utcnow() - timedelta(days=8),
            updated_at=utcnow() - timedelta(days=8),
        )
    )
    revoked_token = f"revoked-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    db.add(
        Invitation(
            email="revoked@example.com",
            organization_id=org.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.REVOKED,
            token_hash=hash_token(revoked_token),
            expires_at=utcnow() + timedelta(days=3),
            invited_by_user_id=admin.id,
        )
    )
    db.commit()

    expired = client.get(f"{API}/invitations/preview", params={"token": expired_token})
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"

    revoked = client.get(f"{API}/invitations/preview", params={"token": revoked_token})
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_revoked_invitation_cannot_be_accepted(client, db):
    org = _org(db, "batch9-revoke-org")
    admin = _admin(db, org)
    csrf = login_client(client, db, admin, organization_id=org.id)

    created = _invite(client, csrf, org, "revoked-target@example.com")
    token = created.json()["delivery_token"]
    revoke = client.post(f"{API}/invitations/{created.json()['id']}/revoke", headers=csrf)
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    client.cookies.clear()
    accepted = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Revoked Person", "password": PASSWORD},
    )
    assert accepted.status_code == 401
    assert accepted.json()["error"]["details"]["reason"] == "invalid_invitation"
    assert db.scalar(select(User).where(User.email == "revoked-target@example.com")) is None


def test_acceptance_creates_account_and_membership_atomically(client, db):
    org = _org(db, "batch9-accept-org")
    admin = _admin(db, org)
    csrf = login_client(client, db, admin, organization_id=org.id)
    created = _invite(client, csrf, org, f"joiner-{uuid.uuid4().hex[:6]}@example.com", role="approver")
    token = created.json()["delivery_token"]
    email = created.json()["email"]

    client.cookies.clear()
    accepted = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Joiner Person", "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["authenticated"] is True
    assert accepted.json()["user"]["active_role"] == "approver"
    # The invitee chose this password, so nothing is owed on first sign-in.
    assert accepted.json()["user"]["must_change_password"] is False

    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.password_changed_at is not None
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org.id,
        )
    )
    assert membership is not None
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.role == MembershipRole.APPROVER
    assert membership.organization_id == org.id, "the invitee must not join another tenant"

    invitation = db.scalar(select(Invitation).where(Invitation.email == email))
    assert invitation.status == InvitationStatus.ACCEPTED
    assert invitation.accepted_by_user_id == user.id

    reuse = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Joiner Person", "password": PASSWORD},
    )
    assert reuse.status_code == 401


def test_acceptance_rejects_a_weak_password_choice(client, db):
    org = _org(db, "batch9-weak-org")
    admin = _admin(db, org)
    csrf = login_client(client, db, admin, organization_id=org.id)
    created = _invite(client, csrf, org, f"weak-{uuid.uuid4().hex[:6]}@example.com")
    token = created.json()["delivery_token"]

    client.cookies.clear()
    rejected = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Weak Person", "password": "password"},
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "weak_password"
    assert db.scalar(select(User).where(User.email == created.json()["email"])) is None

    # The invitation survives the rejected attempt and can still be used.
    retry = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Weak Person", "password": PASSWORD},
    )
    assert retry.status_code == 200, retry.text


def test_existing_account_accepting_a_second_organisation_keeps_one_user(client, db):
    first = _org(db, "batch9-second-first")
    second = _org(db, "batch9-second-second")
    existing = make_user(db, email=f"multi-{uuid.uuid4().hex[:6]}@example.com", password=PASSWORD)
    make_membership(db, existing, first, role=MembershipRole.COORDINATOR)
    admin = _admin(db, second)
    csrf = login_client(client, db, admin, organization_id=second.id)
    created = _invite(client, csrf, second, existing.email, role="auditor")
    token = created.json()["delivery_token"]

    client.cookies.clear()
    wrong_password = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Whatever Name", "password": "AnotherPass!9999"},
    )
    assert wrong_password.status_code == 401

    accepted = client.post(
        f"{API}/invitations/accept",
        json={"token": token, "full_name": "Whatever Name", "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    users = db.scalars(select(User).where(User.email == existing.email)).all()
    assert len(users) == 1
    roles = {
        row.organization_id: row.role
        for row in db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == existing.id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
            )
        ).all()
    }
    assert roles[first.id] == MembershipRole.COORDINATOR
    assert roles[second.id] == MembershipRole.AUDITOR


# ---------------------------------------------------------------------------
# forced password change
# ---------------------------------------------------------------------------


def test_initial_password_blocks_workspace_until_rotated(client, db):
    org = _org(db, "batch9-rotate-org")
    user = _rotation_user(db, org)

    login = client.post(f"{API}/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True

    blocked = client.get("/api/v1/materials?page_size=1")
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert blocked.json()["error"]["details"]["reason"] == "password_change_required"

    # Sign-out and identity stay reachable, so the UI can recover cleanly.
    assert client.get(f"{API}/me").status_code == 200
    assert client.get(f"{API}/sessions").status_code == 200

    wrong_current = client.post(
        f"{API}/change-password",
        json={"current_password": "NotMyPassword!1", "new_password": ROTATED},
        headers=_csrf(client),
    )
    assert wrong_current.status_code == 401

    weak = client.post(
        f"{API}/change-password",
        # Long enough for the request schema, rejected by the policy itself.
        json={"current_password": PASSWORD, "new_password": "lowercaseonlypassword"},
        headers=_csrf(client),
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"

    still_blocked = client.get("/api/v1/materials?page_size=1")
    assert still_blocked.status_code == 403

    changed = client.post(
        f"{API}/change-password",
        json={"current_password": PASSWORD, "new_password": ROTATED},
        headers=_csrf(client),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["authenticated"] is False

    # Every session of that account is closed by the rotation.
    assert client.get(f"{API}/me").status_code == 401
    stored = db.scalar(select(User).where(User.id == user.id))
    assert stored.password_changed_at is not None

    client.cookies.clear()
    again = client.post(f"{API}/login", json={"email": user.email, "password": ROTATED})
    assert again.status_code == 200, again.text
    assert again.json()["user"]["must_change_password"] is False
    assert client.get("/api/v1/materials?page_size=1").status_code == 200


def test_rotation_block_applies_to_api_callers_not_only_the_browser(client, db):
    org = _org(db, "batch9-rotate-api")
    user = _rotation_user(db, org)
    record, bundle = issue_session(db, user, organization_id=org.id)
    db.commit()

    anonymous_style = client.get(
        "/api/v1/proposals?page_size=1",
        headers={"Authorization": f"Bearer {bundle.access_token}"},
    )
    assert anonymous_style.status_code == 403
    assert anonymous_style.json()["error"]["code"] == "password_change_required"

    # The bearer transport bypasses CSRF by design; it does not bypass rotation.
    assert record.id is not None


def test_normal_accounts_are_unaffected_by_the_rotation_rule(client, db):
    org = _org(db, "batch9-normal-org")
    user = make_user(db, email=f"normal-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, user, org, role=MembershipRole.VIEWER)
    db.commit()
    login_client(client, db, user, organization_id=org.id)

    me = client.get(f"{API}/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False
    assert client.get("/api/v1/materials?page_size=1").status_code == 200


# ---------------------------------------------------------------------------
# session management
# ---------------------------------------------------------------------------


def _session_rows(db: Session, user: User) -> list[AuthSession]:
    return list(
        db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id)
            .order_by(AuthSession.created_at)
        ).all()
    )


def test_session_list_shows_only_the_callers_sessions(client, db):
    org = _org(db, "batch9-sessions-org")
    user = make_user(db, email=f"owner-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    other = make_user(db, email=f"stranger-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, other, org, role=MembershipRole.VIEWER)
    db.commit()

    csrf = login_client(client, db, user, organization_id=org.id)
    second_record, _ = issue_session(db, user, organization_id=org.id)
    other_record, _ = issue_session(db, other, organization_id=org.id)
    db.commit()

    listed = client.get(f"{API}/sessions", headers=csrf)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    ids = {row["id"] for row in rows}
    assert str(second_record.id) in ids
    assert str(other_record.id) not in ids
    assert sum(1 for row in rows if row["is_current"]) == 1
    current = next(row for row in rows if row["is_current"])
    assert current["revoked_at"] is None
    assert "token" not in current, "session listings must never carry credentials"


def test_cannot_revoke_a_session_belonging_to_another_user(client, db):
    org = _org(db, "batch9-session-cross")
    user = make_user(db, email=f"a-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    other = make_user(db, email=f"b-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, other, org, role=MembershipRole.VIEWER)
    db.commit()

    csrf = login_client(client, db, user, organization_id=org.id)
    foreign, _ = issue_session(db, other, organization_id=org.id)
    db.commit()

    denied = client.post(f"{API}/sessions/{foreign.id}/revoke", headers=csrf)
    assert denied.status_code == 404
    db.refresh(foreign)
    assert foreign.revoked_at is None


def test_revoke_other_sessions_keeps_the_caller_signed_in(client, db):
    org = _org(db, "batch9-revoke-others")
    user = make_user(db, email=f"multi-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    db.commit()

    csrf = login_client(client, db, user, organization_id=org.id)
    spare, _ = issue_session(db, user, organization_id=org.id)
    db.commit()

    response = client.post(f"{API}/sessions/revoke-others", headers=csrf)
    assert response.status_code == 200, response.text

    db.refresh(spare)
    assert spare.revoked_at is not None
    assert client.get(f"{API}/me").status_code == 200

    rows = client.get(f"{API}/sessions", headers=csrf).json()
    live = [row for row in rows if row["revoked_at"] is None]
    assert len(live) == 1
    assert live[0]["is_current"] is True


def test_revoking_the_current_session_signs_out_and_blocks_replay(client, db):
    org = _org(db, "batch9-revoke-self")
    user = make_user(db, email=f"self-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    db.commit()

    csrf = login_client(client, db, user, organization_id=org.id)
    access_token = client.cookies.get("lm_session")
    current = next(row for row in client.get(f"{API}/sessions", headers=csrf).json() if row["is_current"])

    revoked = client.post(f"{API}/sessions/{current['id']}/revoke", headers=csrf)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["authenticated"] is False
    assert client.get(f"{API}/me").status_code == 401

    # The old access token is dead, not merely forgotten by the client.
    client.cookies.clear()
    client.cookies.set("lm_session", access_token)
    replay = client.get(f"{API}/me")
    assert replay.status_code == 401
    assert replay.json()["error"]["details"]["reason"] == "session_revoked"


def test_revoked_session_row_is_recorded_for_the_account_owner(client, db):
    org = _org(db, "batch9-session-audit")
    user = make_user(db, email=f"audit-{uuid.uuid4().hex[:6]}@example.com")
    make_membership(db, user, org, role=MembershipRole.COORDINATOR)
    db.commit()

    csrf = login_client(client, db, user, organization_id=org.id)
    spare, _ = issue_session(db, user, organization_id=org.id)
    db.commit()

    client.post(f"{API}/sessions/{spare.id}/revoke", headers=csrf)
    db.refresh(spare)
    assert spare.revoked_reason == "user_revoked"
    rows = client.get(f"{API}/sessions", headers=csrf).json()
    revoked_row = next(row for row in rows if row["id"] == str(spare.id))
    assert revoked_row["revoked_reason"] == "user_revoked"
    assert revoked_row["is_current"] is False
