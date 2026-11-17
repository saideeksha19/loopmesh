"""Batch 11 — platform administration, tenant operations and audit review.

The tests drive the real HTTP API through real sessions. Every platform route is
exercised both by a platform operator and by an organisation administrator, so
the negative path is proved rather than assumed. Organisation suspension tests
use live sessions to show the documented effect on existing sessions, new
logins, organisation switching and unrelated memberships.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.permissions import (
    ALL_PERMISSIONS,
    PLATFORM_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from app.core.security import hash_token
from app.db.enums import (
    AuditSeverity,
    InvitationStatus,
    MembershipRole,
    MembershipScope,
    MembershipStatus,
    OrganizationStatus,
)
from app.db.models.audit import AuditEvent
from app.db.models.identity import Invitation, OrganizationMembership
from app.db.models.organization import Organization
from app.main import app
from app.services import audit as audit_service
from tests.conftest import (
    login_client,
    make_membership,
    make_organization,
    make_user,
)

API = "/api/v1"
PLATFORM_GET_ROUTES = [
    "/platform/dashboard",
    "/platform/organizations",
    "/platform/audit",
    "/platform/health",
]


def _operator(db, *, email: str | None = None):
    return make_user(
        db,
        email=email or f"operator-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Platform Operator",
        is_platform_admin=True,
    )


def _headers(client: TestClient, db, user) -> dict[str, str]:
    return login_client(client, db, user)


def _org(db, **overrides):
    return make_organization(db, **overrides)


def _member(db, org, *, role=MembershipRole.VIEWER, email_prefix="member", **kwargs):
    user = make_user(db, email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com", **kwargs)
    membership = make_membership(db, user, org, role=role)
    db.commit()
    return user, membership


def _approved_request(client, db, headers, org, *, status: str, reason: str | None):
    """Create and have a second operator approve a protected action."""
    action = "suspend" if status == "suspended" else "reactivate"
    created = client.post(
        f"{API}/platform/approvals",
        json={
            "organization_id": str(org.id),
            "action": action,
            "reason": reason,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    approval_id = created.json()["id"]

    approver = _operator(db)
    approver_client = TestClient(app)
    approver_headers = login_client(approver_client, db, approver)
    approved = approver_client.post(
        f"{API}/platform/approvals/{approval_id}/approve",
        json={},
        headers=approver_headers,
    )
    assert approved.status_code == 200, approved.text
    return approval_id


def _patch_status(client, db, headers, org, *, status: str, reason: str | None = None):
    """Suspend/reactivate through the two-person approval workflow."""
    approval_id = _approved_request(client, db, headers, org, status=status, reason=reason)
    body: dict[str, str] = {"status": status, "approval_id": approval_id}
    if reason is not None:
        body["reason"] = reason
    return client.patch(
        f"{API}/platform/organizations/{org.id}",
        json=body,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Permission model
# ---------------------------------------------------------------------------


def test_platform_permissions_are_disjoint_from_every_organisation_role() -> None:
    assert PLATFORM_PERMISSIONS <= ALL_PERMISSIONS
    for role, permissions in ROLE_PERMISSIONS.items():
        leaked = permissions & PLATFORM_PERMISSIONS
        assert leaked == set(), (role, leaked)


def test_platform_catalogue_is_the_documented_set() -> None:
    # Batch 13 adds explicit audit integrity verification and archive capabilities.
    assert {
        "platform.admin",
        "platform.dashboard.view",
        "platform.organizations.view",
        "platform.organizations.manage",
        "platform.audit.view",
        "platform.audit.export",
        "platform.audit.verify",
        "platform.audit.archive",
        "platform.health.view",
        "platform.approvals.view",
        "platform.approvals.request",
        "platform.approvals.decide",
        "platform.approvals.execute",
        "platform.sessions.manage",
    } == {permission.value for permission in PLATFORM_PERMISSIONS}


def test_organisation_admin_session_never_reports_platform_capabilities(client, db) -> None:
    org = _org(db)
    admin, _ = _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="orgadmin")
    login_client(client, db, admin, org.id)

    payload = client.get(f"{API}/auth/me").json()
    assert payload["is_platform_admin"] is False
    assert not [value for value in payload["permissions"] if value.startswith("platform.")]


# ---------------------------------------------------------------------------
# Platform authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", PLATFORM_GET_ROUTES)
def test_unauthenticated_platform_requests_are_rejected(client, db, path) -> None:
    anonymous = TestClient(app)
    response = anonymous.get(f"{API}{path}")
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("path", PLATFORM_GET_ROUTES)
def test_organisation_administrator_cannot_reach_platform_endpoints(client, db, path) -> None:
    org = _org(db)
    admin, _ = _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="orgadmin")
    login_client(client, db, admin, org.id)

    response = client.get(f"{API}{path}")
    assert response.status_code == 403, response.text
    assert response.json()["error"]["details"]["reason"] == "platform_scope_required"


@pytest.mark.parametrize("role", [MembershipRole.COORDINATOR, MembershipRole.AUDITOR])
def test_non_admin_roles_cannot_reach_platform_endpoints(client, db, role) -> None:
    org = _org(db)
    user, _ = _member(db, org, role=role, email_prefix=role.value)
    login_client(client, db, user, org.id)

    for path in PLATFORM_GET_ROUTES:
        response = client.get(f"{API}{path}")
        assert response.status_code == 403, (role, path, response.text)
        assert response.json()["error"]["details"]["reason"] == "platform_scope_required"


def test_platform_scoped_membership_is_not_platform_administration(client, db) -> None:
    """Cross-tenant reach is not console access: only the flag grants that."""
    org = _org(db)
    user = make_user(db, email=f"scoped-{uuid.uuid4().hex[:8]}@example.com")
    make_membership(db, user, org, role=MembershipRole.AUDITOR, scope=MembershipScope.PLATFORM)
    db.commit()
    login_client(client, db, user, org.id)

    response = client.get(f"{API}/platform/dashboard")
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "platform_scope_required"


def test_platform_operator_can_reach_permitted_endpoints(client, db) -> None:
    operator = _operator(db)
    _headers(client, db, operator)
    for path in PLATFORM_GET_ROUTES:
        response = client.get(f"{API}{path}")
        assert response.status_code == 200, (path, response.text)


def test_inactive_operator_account_is_rejected(client, db) -> None:
    operator = make_user(
        db,
        email=f"disabled-{uuid.uuid4().hex[:8]}@example.com",
        is_platform_admin=True,
        is_active=False,
    )
    login_client(client, db, operator)
    response = client.get(f"{API}/platform/dashboard")
    assert response.status_code == 401
    assert response.json()["error"]["details"]["reason"] == "account_inactive"


def test_invalid_session_cookie_cannot_reach_platform(client, db) -> None:
    anonymous = TestClient(app)
    anonymous.cookies.set("lm_session", "not-a-real-token")
    response = anonymous.get(f"{API}/platform/dashboard")
    assert response.status_code == 401


def test_organisation_administrator_cannot_mutate_tenant_status(client, db) -> None:
    target = _org(db)
    home = _org(db)
    admin, _ = _member(db, home, role=MembershipRole.ORG_ADMIN, email_prefix="orgadmin")
    headers = login_client(client, db, admin, home.id)

    response = client.patch(
        f"{API}/platform/organizations/{target.id}",
        json={"status": "suspended", "reason": "Attempted by a tenant"},
        headers=headers,
    )
    assert response.status_code == 403
    db.refresh(target)
    assert target.status == OrganizationStatus.ACTIVE


# ---------------------------------------------------------------------------
# Organisation register
# ---------------------------------------------------------------------------


def test_register_lists_organisations_with_only_safe_fields(client, db) -> None:
    operator = _operator(db)
    first = _org(db, name="Aurelia Chemicals", slug="aurelia-chemicals")
    second = _org(db, name="Meridian Steel", slug="meridian-steel")
    _member(db, first, role=MembershipRole.ORG_ADMIN)
    _member(db, second, role=MembershipRole.COORDINATOR)
    db.commit()
    _headers(client, db, operator)

    response = client.get(f"{API}/platform/organizations", params={"page_size": 100})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    slugs = {row["slug"] for row in body["items"]}
    assert {"aurelia-chemicals", "meridian-steel"} <= slugs

    row = next(item for item in body["items"] if item["slug"] == "aurelia-chemicals")
    assert set(row) == {
        "id",
        "name",
        "slug",
        "sector",
        "country",
        "city",
        "status",
        "is_demo",
        "created_at",
        "suspended_at",
        "active_members",
        "suspended_members",
        "pending_invitations",
    }
    assert row["status"] == "active"
    assert row["active_members"] == 1
    lowered = response.text.lower()
    for forbidden in ("password", "token", "contact_email", "description", "material"):
        assert forbidden not in lowered


def test_register_search_and_status_filters(client, db) -> None:
    operator = _operator(db)
    active = _org(db, name="Alpha Circular", slug="alpha-circular")
    suspended = _org(db, name="Beta Works", slug="beta-works")
    suspended.status = OrganizationStatus.SUSPENDED
    db.commit()
    _headers(client, db, operator)

    by_name = client.get(f"{API}/platform/organizations", params={"q": "alpha"})
    assert [row["slug"] for row in by_name.json()["items"]] == ["alpha-circular"]

    by_slug = client.get(f"{API}/platform/organizations", params={"q": "beta-works"})
    assert [row["slug"] for row in by_slug.json()["items"]] == ["beta-works"]

    suspended_only = client.get(f"{API}/platform/organizations", params={"status": "suspended"})
    assert [row["slug"] for row in suspended_only.json()["items"]] == ["beta-works"]
    assert suspended_only.json()["total"] == 1

    active_only = client.get(f"{API}/platform/organizations", params={"status": "active"})
    assert all(row["status"] == "active" for row in active_only.json()["items"])


def test_register_search_wildcards_are_escaped(client, db) -> None:
    operator = _operator(db)
    _org(db, name="Literal Percent", slug="literal-percent")
    db.commit()
    _headers(client, db, operator)

    response = client.get(f"{API}/platform/organizations", params={"q": "%"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_register_rejects_unknown_status_filter(client, db) -> None:
    operator = _operator(db)
    _headers(client, db, operator)
    response = client.get(f"{API}/platform/organizations", params={"status": "deleted"})
    assert response.status_code == 422


def test_register_paginates_with_a_stable_order(client, db) -> None:
    operator = _operator(db)
    for index in range(5):
        _org(db, name=f"Paged Tenant {index}", slug=f"paged-tenant-{index}")
    db.commit()
    _headers(client, db, operator)

    first = client.get(f"{API}/platform/organizations", params={"page": 1, "page_size": 2})
    second = client.get(f"{API}/platform/organizations", params={"page": 2, "page_size": 2})
    assert first.json()["page_size"] == 2
    assert first.json()["has_more"] is True
    assert second.json()["page"] == 2
    first_ids = {row["id"] for row in first.json()["items"]}
    second_ids = {row["id"] for row in second.json()["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert first.json()["total"] == second.json()["total"] == 5


def test_register_page_size_is_bounded(client, db) -> None:
    operator = _operator(db)
    _headers(client, db, operator)
    assert client.get(f"{API}/platform/organizations", params={"page_size": 5000}).status_code == 422


def test_unknown_organisation_detail_is_404(client, db) -> None:
    operator = _operator(db)
    _headers(client, db, operator)
    response = client.get(f"{API}/platform/organizations/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_organisation_detail_reports_operational_counts(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="admin")
    _member(db, org, role=MembershipRole.COORDINATOR, email_prefix="coordinator")
    suspended_user, suspended_membership = _member(db, org, role=MembershipRole.VIEWER)
    suspended_membership.status = MembershipStatus.SUSPENDED
    invited_user, invited_membership = _member(db, org, role=MembershipRole.VIEWER)
    invited_membership.status = MembershipStatus.INVITED
    now = datetime.now(timezone.utc)
    db.add(
        Invitation(
            email="pending@example.com",
            organization_id=org.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(f"token-{uuid.uuid4().hex}"),
            expires_at=now + timedelta(days=3),
        )
    )
    db.add(
        Invitation(
            email="expired@example.com",
            organization_id=org.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(f"token-{uuid.uuid4().hex}"),
            created_at=now - timedelta(days=10),
            expires_at=now - timedelta(days=1),
        )
    )
    db.commit()
    _headers(client, db, operator)

    body = client.get(f"{API}/platform/organizations/{org.id}").json()
    assert body["members"] == {"active": 2, "suspended": 1, "invited": 1, "removed": 0}
    assert body["invitations"] == {"pending": 1, "expired": 1, "accepted": 0, "revoked": 0}
    assert body["administrators"]["active"] == 1
    assert body["state"] == "ok"
    assert body["warnings"] == []
    assert body["checks"] == [
        "tenant_active",
        "membership_present",
        "active_administrator_present",
    ]
    # Operational only: no tenant business content.
    for forbidden in ("materials", "proposals", "transactions", "demands", "password"):
        assert forbidden not in body


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_suspension_requires_a_written_reason(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _headers(client, db, operator)

    response = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={"status": "suspended", "reason": "short"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["reason"] == "reason_required"
    db.refresh(org)
    assert org.status == OrganizationStatus.ACTIVE


def test_suspension_and_reactivation_are_audited(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _headers(client, db, operator)

    suspended = _patch_status(
        client, db, headers, org, status="suspended", reason="Repeated policy breach"
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["suspended_at"] is not None
    assert suspended.json()["state"] == "suspended"

    event = db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "platform.organization.suspended")
    )
    assert event is not None
    assert event.actor_id == str(operator.id)
    assert event.organization_id == org.id
    assert event.previous_state == "active"
    assert event.new_state == "suspended"
    assert event.reason == "Repeated policy breach"
    assert event.severity == AuditSeverity.WARNING
    assert event.payload["slug"] == org.slug

    reactivated = _patch_status(client, db, headers, org, status="active")
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "active"
    assert reactivated.json()["suspended_at"] is None

    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.event_type == "platform.organization.reactivated")
        .order_by(AuditEvent.created_at.asc())
    ).all()
    assert len(events) == 1
    assert events[0].previous_state == "suspended"
    assert events[0].new_state == "active"


def test_repeating_the_current_status_is_rejected(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _headers(client, db, operator)

    response = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={"status": "active", "reason": "No change intended"},
        headers=headers,
    )
    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["reason"] == "invalid_state_transition"
    assert details["current_status"] == "active"


def test_status_endpoint_cannot_be_used_to_edit_other_fields(client, db) -> None:
    operator = _operator(db)
    org = _org(db, name="Immutable Name", slug="immutable-name")
    db.commit()
    headers = _headers(client, db, operator)

    response = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={"status": "suspended", "reason": "Policy review", "name": "Renamed"},
        headers=headers,
    )
    assert response.status_code == 422
    db.refresh(org)
    assert org.name == "Immutable Name"
    assert org.status == OrganizationStatus.ACTIVE


def test_status_endpoint_rejects_unknown_organisation(client, db) -> None:
    operator = _operator(db)
    headers = _headers(client, db, operator)
    response = client.patch(
        f"{API}/platform/organizations/{uuid.uuid4()}",
        json={"status": "suspended", "reason": "Policy review"},
        headers=headers,
    )
    assert response.status_code == 404


def test_status_mutation_requires_csrf_for_cookie_sessions(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    db.commit()
    login_client(client, db, operator)

    response = client.patch(
        f"{API}/platform/organizations/{org.id}",
        json={"status": "suspended", "reason": "Policy review"},
    )
    assert response.status_code == 403
    db.refresh(org)
    assert org.status == OrganizationStatus.ACTIVE


# ---------------------------------------------------------------------------
# Suspension semantics
# ---------------------------------------------------------------------------


def test_suspension_does_not_delete_memberships_or_sessions(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    user, membership = _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="admin")
    member_client = TestClient(app)
    login_client(member_client, db, user, org.id)
    db.commit()
    headers = _headers(client, db, operator)

    before_sessions = member_client.cookies.get("lm_session")

    response = _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )
    assert response.status_code == 200
    db.expire_all()

    db.refresh(membership)
    assert membership.status == MembershipStatus.ACTIVE
    assert db.get(OrganizationMembership, membership.id) is not None
    assert db.get(Organization, org.id) is not None
    # The session is not revoked; it simply stops granting this tenant.
    assert member_client.cookies.get("lm_session") == before_sessions
    me = member_client.get(f"{API}/auth/me")
    assert me.status_code == 200
    assert me.json()["permissions"] == []
    assert me.json()["active_organization_id"] is None
    assert member_client.get(f"{API}/materials").status_code == 403


def test_suspension_blocks_new_logins_but_not_the_account(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    user, _ = _member(db, org, role=MembershipRole.COORDINATOR, email_prefix="coordinator")
    db.commit()
    headers = _headers(client, db, operator)

    _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )

    sign_in = client.post(
        f"{API}/auth/login",
        json={"email": user.email, "password": "StrongPass!2345"},
    )
    assert sign_in.status_code == 200, sign_in.text
    assert client.get(f"{API}/materials").status_code == 403

    explicit = client.post(
        f"{API}/auth/login",
        json={
            "email": user.email,
            "password": "StrongPass!2345",
            "organization_id": str(org.id),
        },
    )
    assert explicit.status_code == 403
    assert explicit.json()["error"]["details"]["reason"] == "membership_required"


def test_organisation_switching_cannot_bypass_suspension(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    other = _org(db)
    user = make_user(db, email=f"switcher-{uuid.uuid4().hex[:8]}@example.com")
    make_membership(db, user, org, role=MembershipRole.VIEWER)
    make_membership(db, user, other, role=MembershipRole.COORDINATOR)
    db.commit()
    headers = _headers(client, db, operator)

    _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )
    user_headers = login_client(client, db, user, other.id)

    response = client.post(
        f"{API}/auth/switch-organization",
        json={"organization_id": str(org.id)},
        headers=user_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "membership_required"


def test_other_memberships_survive_tenant_suspension(client, db) -> None:
    operator = _operator(db)
    suspended_org = _org(db, slug="tenant-suspended")
    healthy_org = _org(db, slug="tenant-healthy")
    user = make_user(db, email=f"multi-{uuid.uuid4().hex[:8]}@example.com")
    first = make_membership(db, user, suspended_org, role=MembershipRole.VIEWER)
    second = make_membership(db, user, healthy_org, role=MembershipRole.COORDINATOR)
    db.commit()
    headers = _headers(client, db, operator)

    _patch_status(
        client, db, headers, suspended_org, status="suspended", reason="Commercial review"
    )

    login_client(client, db, user)
    me = client.get(f"{API}/auth/me").json()
    assert me["active_organization_id"] == str(healthy_org.id)
    assert [row["organization_id"] for row in me["memberships"]] == [str(healthy_org.id)]
    assert client.get(f"{API}/materials").status_code == 200

    db.expire_all()
    assert db.get(OrganizationMembership, first.id).status == MembershipStatus.ACTIVE
    assert db.get(OrganizationMembership, second.id).status == MembershipStatus.ACTIVE


def test_reactivation_restores_access_without_rebuilding_the_roster(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    user, membership = _member(db, org, role=MembershipRole.COORDINATOR, email_prefix="member")
    member_client = TestClient(app)
    login_client(member_client, db, user, org.id)
    db.commit()
    headers = _headers(client, db, operator)

    _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )
    assert member_client.get(f"{API}/materials").status_code == 403

    reactivated = _patch_status(client, db, headers, org, status="active")
    assert reactivated.status_code == 200
    db.expire_all()
    assert db.get(OrganizationMembership, membership.id).status == MembershipStatus.ACTIVE

    restored = member_client.get(f"{API}/auth/me")
    assert restored.status_code == 200
    assert restored.json()["active_organization_id"] == str(org.id)
    assert member_client.get(f"{API}/materials").status_code == 200


def test_suspended_tenant_cannot_grow_its_roster(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    admin, _ = _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="admin")
    db.commit()

    admin_client = TestClient(app)
    admin_headers = login_client(admin_client, db, admin, org.id)
    before = admin_client.post(
        f"{API}/auth/invitations",
        json={"email": "first-person@example.com", "organization_id": str(org.id), "role": "viewer"},
        headers=admin_headers,
    )
    assert before.status_code == 201, before.text

    headers = _headers(client, db, operator)
    _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )

    # The tenant administrator loses the capability entirely once the tenant is
    # closed, and a platform operator is refused too: suspension is a tenant
    # state, not a matter of who is asking.
    admin_after = admin_client.post(
        f"{API}/auth/invitations",
        json={"email": "second-person@example.com", "organization_id": str(org.id), "role": "viewer"},
        headers=admin_headers,
    )
    assert admin_after.status_code == 403

    operator_invite = client.post(
        f"{API}/auth/invitations",
        json={"email": "third-person@example.com", "organization_id": str(org.id), "role": "viewer"},
        headers=headers,
    )
    assert operator_invite.status_code == 409
    assert operator_invite.json()["error"]["details"]["reason"] == "organization_suspended"


def test_pending_invitation_cannot_be_accepted_while_suspended(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    token = f"invitation-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    db.add(
        Invitation(
            email="invitee@example.com",
            organization_id=org.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
    )
    db.commit()
    headers = _headers(client, db, operator)

    _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )
    anonymous = TestClient(app)
    response = anonymous.post(
        f"{API}/auth/invitations/accept",
        json={"token": token, "full_name": "Invited Person", "password": "InviteePass!2026"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "organization_suspended"


# ---------------------------------------------------------------------------
# Tenant health
# ---------------------------------------------------------------------------


def test_health_reports_accurate_counts_and_warnings(client, db) -> None:
    operator = _operator(db)
    healthy = _org(db, slug="healthy-tenant")
    _member(db, healthy, role=MembershipRole.ORG_ADMIN, email_prefix="healthy-admin")
    _member(db, healthy, role=MembershipRole.VIEWER, email_prefix="healthy-member")
    unmanaged = _org(db, slug="unmanaged-tenant")
    _member(db, unmanaged, role=MembershipRole.COORDINATOR, email_prefix="unmanaged")
    suspended = _org(db, slug="suspended-tenant")
    suspended.status = OrganizationStatus.SUSPENDED
    db.commit()
    _headers(client, db, operator)

    response = client.get(f"{API}/platform/health", params={"page_size": 100})
    assert response.status_code == 200
    rows = {row["organization"]["slug"]: row for row in response.json()["items"]}

    assert rows["healthy-tenant"]["state"] == "ok"
    assert rows["healthy-tenant"]["active_members"] == 2
    assert rows["healthy-tenant"]["active_administrators"] == 1

    assert rows["unmanaged-tenant"]["state"] == "attention"
    assert "no_active_administrator" in rows["unmanaged-tenant"]["warnings"]

    assert rows["suspended-tenant"]["state"] == "suspended"
    assert "organization_suspended" in rows["suspended-tenant"]["warnings"]
    assert rows["healthy-tenant"]["checks"] == [
        "tenant_active",
        "membership_present",
        "active_administrator_present",
    ]


def test_health_never_exposes_tenant_business_content(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="admin")
    db.commit()
    _headers(client, db, operator)

    response = client.get(f"{API}/platform/health")
    lowered = response.text.lower()
    for forbidden in (
        "material_id",
        "proposal",
        "transaction",
        "supplier",
        "consumer",
        "password",
        "token",
    ):
        assert forbidden not in lowered


def test_health_paginates(client, db) -> None:
    operator = _operator(db)
    for index in range(3):
        _org(db, slug=f"health-tenant-{index}")
    db.commit()
    _headers(client, db, operator)

    first = client.get(f"{API}/platform/health", params={"page": 1, "page_size": 2}).json()
    second = client.get(f"{API}/platform/health", params={"page": 2, "page_size": 2}).json()
    assert first["total"] == 3
    assert first["has_more"] is True
    assert {row["organization"]["id"] for row in first["items"]}.isdisjoint(
        {row["organization"]["id"] for row in second["items"]}
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_reports_real_aggregates(client, db) -> None:
    operator = _operator(db)
    active = _org(db, slug="dash-active")
    suspended = _org(db, slug="dash-suspended")
    suspended.status = OrganizationStatus.SUSPENDED
    _member(db, active, role=MembershipRole.ORG_ADMIN, email_prefix="dash-admin")
    _member(db, active, role=MembershipRole.VIEWER, email_prefix="dash-viewer")
    db.add(
        Invitation(
            email="pending-dash@example.com",
            organization_id=active.id,
            role=MembershipRole.VIEWER,
            scope=MembershipScope.ORGANIZATION,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(f"dash-{uuid.uuid4().hex}"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        )
    )
    db.commit()
    _headers(client, db, operator)

    body = client.get(f"{API}/platform/dashboard").json()
    assert body["organisations"]["total"] == 2
    assert body["organisations"]["active"] == 1
    assert body["organisations"]["suspended"] == 1
    assert body["users"]["total"] == 3
    assert body["memberships"]["active"] == 2
    assert body["pending_invitations"] == 1
    assert body["failed_logins_window"] == 0
    assert body["window_days"] == 30
    assert {row["slug"] for row in body["recent_organisations"]} >= {"dash-active", "dash-suspended"}


def test_dashboard_handles_an_empty_database(client, db) -> None:
    operator = _operator(db)
    db.commit()
    _headers(client, db, operator)

    body = client.get(f"{API}/platform/dashboard").json()
    assert body["organisations"] == {
        "total": 0,
        "active": 0,
        "suspended": 0,
        "created_in_window": 0,
    }
    assert body["users"]["total"] == 1
    assert body["memberships"]["active"] == 0
    assert body["recent_organisations"] == []
    assert body["recent_events"] == []


def test_dashboard_recent_events_include_platform_changes_without_payloads(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    db.commit()
    headers = _headers(client, db, operator)
    _patch_status(
        client, db, headers, org, status="suspended", reason="Commercial review"
    )

    body = client.get(f"{API}/platform/dashboard").json()
    events = body["recent_events"]
    assert any(event["event_type"] == "platform.organization.suspended" for event in events)
    for event in events:
        assert "payload" not in event
        assert "reason" not in event
        assert event["organization_name"] == org.name


# ---------------------------------------------------------------------------
# Platform audit journal
# ---------------------------------------------------------------------------


def _event(db, *, event_type="membership.changed", org=None, actor="ops@example.com", **kwargs):
    event = audit_service.record_event(
        db,
        event_type=event_type,
        entity_type=kwargs.pop("entity_type", "organization_membership"),
        entity_id=kwargs.pop("entity_id", None),
        organization_id=org.id if org else None,
        actor=actor,
        actor_id=kwargs.pop("actor_id", None),
        summary=kwargs.pop("summary", "Test event."),
        payload=kwargs.pop("payload", {"note": "safe"}),
        severity=kwargs.pop("severity", AuditSeverity.INFO),
        **kwargs,
    )
    db.commit()
    return event


def test_platform_audit_lists_events_across_tenants(client, db) -> None:
    operator = _operator(db)
    first = _org(db, slug="audit-first")
    second = _org(db, slug="audit-second")
    _event(db, org=first, summary="First tenant event.")
    _event(db, org=second, summary="Second tenant event.")
    db.commit()
    _headers(client, db, operator)

    body = client.get(f"{API}/platform/audit", params={"page_size": 100}).json()
    orgs = {row["organization_id"] for row in body["items"]}
    assert {str(first.id), str(second.id)} <= orgs
    names = {row["organization_name"] for row in body["items"]}
    assert {first.name, second.name} <= names


def test_organisation_administrator_cannot_query_platform_audit(client, db) -> None:
    org = _org(db)
    admin, _ = _member(db, org, role=MembershipRole.ORG_ADMIN, email_prefix="audit-admin")
    login_client(client, db, admin, org.id)
    response = client.get(f"{API}/platform/audit")
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "platform_scope_required"


def test_platform_audit_filters(client, db) -> None:
    operator = _operator(db)
    first = _org(db, slug="filter-first")
    second = _org(db, slug="filter-second")
    target = make_user(db, email="target@example.com", full_name="Target Person")
    target_membership = make_membership(db, target, first)
    db.commit()

    matching = _event(db, org=first, event_type="membership.changed", entity_id=target_membership.id)
    _event(db, org=second, event_type="auth.password_reset_issued")
    _headers(client, db, operator)

    def items(**params):
        response = client.get(f"{API}/platform/audit", params={"page_size": 100, **params})
        assert response.status_code == 200, response.text
        return response.json()["items"]

    by_event = items(event_type="membership.changed")
    assert {row["id"] for row in by_event} == {str(matching.id)}

    by_org = items(organization_id=str(second.id))
    assert all(row["organization_id"] == str(second.id) for row in by_org)
    assert len(by_org) == 1

    by_target = items(target_user_id=str(target.id))
    assert {row["id"] for row in by_target} == {str(matching.id)}

    by_actor = items(actor="OPS@")
    assert by_actor and all("ops@" in row["actor"].lower() for row in by_actor)

    by_actor_id = items(actor_id=str(operator.id))
    assert by_actor_id == []


def test_platform_audit_date_range_and_pagination(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    old = _event(db, org=org, summary="Old event.")
    old.created_at = datetime(2026, 1, 1, 12, 0, 0)
    recent = _event(db, org=org, summary="Recent event.")
    recent.created_at = datetime(2026, 6, 1, 12, 0, 0)
    db.commit()
    _headers(client, db, operator)

    response = client.get(
        f"{API}/platform/audit",
        params={
            "created_from": "2026-05-01T00:00:00",
            "created_to": "2026-07-01T00:00:00",
            "page_size": 100,
        },
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["items"]} == {str(recent.id)}

    inverted = client.get(
        f"{API}/platform/audit",
        params={"created_from": "2026-07-01T00:00:00", "created_to": "2026-05-01T00:00:00"},
    )
    assert inverted.status_code == 422
    assert inverted.json()["error"]["details"]["reason"] == "invalid_range"

    page_one = client.get(f"{API}/platform/audit", params={"page": 1, "page_size": 1}).json()
    page_two = client.get(f"{API}/platform/audit", params={"page": 2, "page_size": 1}).json()
    assert page_one["items"][0]["id"] != page_two["items"][0]["id"]
    assert page_one["has_more"] is True


def test_platform_audit_redacts_sensitive_payload_fields(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    event = _event(
        db,
        org=org,
        payload={
            "password": "hunter2-secret",
            "note": "safe-value",
            "nested": {"api_token": "abc123", "count": 2},
        },
    )
    _headers(client, db, operator)

    response = client.get(f"{API}/platform/audit", params={"page_size": 100})
    assert response.status_code == 200
    row = next(item for item in response.json()["items"] if item["id"] == str(event.id))
    assert row["payload"]["password"] == "[redacted]"
    assert row["payload"]["nested"]["api_token"] == "[redacted]"
    assert row["payload"]["nested"]["count"] == 2
    assert row["payload"]["note"] == "safe-value"
    assert "password" in row["redacted_fields"]
    assert "nested.api_token" in row["redacted_fields"]
    assert "hunter2-secret" not in response.text
    assert "abc123" not in response.text


def test_auth_audit_payloads_keep_only_the_allow_list(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    event = _event(
        db,
        event_type="auth.login_failed",
        org=org,
        payload={
            "outcome": "denied",
            "reason": "invalid_credentials",
            "session_id": "session-abc",
            "reset_link": "https://example.test/reset?token=leak",
        },
    )
    _headers(client, db, operator)

    row = next(
        item
        for item in client.get(f"{API}/platform/audit", params={"page_size": 100}).json()["items"]
        if item["id"] == str(event.id)
    )
    assert row["payload"] == {"outcome": "denied", "reason": "invalid_credentials"}
    assert "session_id" in row["redacted_fields"]
    assert "reset_link" in row["redacted_fields"]
    assert "leak" not in client.get(f"{API}/platform/audit", params={"page_size": 100}).text


def test_audit_events_are_immutable_across_platform_reads(client, db) -> None:
    operator = _operator(db)
    org = _org(db)
    event = _event(db, org=org, payload={"note": "immutable", "session_token": "secret"})
    original_payload = dict(event.payload)
    _headers(client, db, operator)

    client.get(f"{API}/platform/audit")
    client.get(f"{API}/platform/audit")
    db.expire_all()
    stored = db.get(AuditEvent, event.id)
    assert stored is not None
    assert stored.payload == original_payload
    assert stored.event_type == "membership.changed"
    assert stored.organization_id == org.id


def test_organisation_audit_journal_stays_tenant_scoped(client, db) -> None:
    first = _org(db, slug="scoped-first")
    second = _org(db, slug="scoped-second")
    admin, _ = _member(db, first, role=MembershipRole.ORG_ADMIN, email_prefix="scoped-admin")
    _event(db, org=first, summary="Visible to the tenant.")
    _event(db, org=second, summary="Visible only to the platform.")
    db.commit()
    login_client(client, db, admin, first.id)

    response = client.get(f"{API}/audit", params={"page_size": 100})
    assert response.status_code == 200
    summaries = {row["summary"] for row in response.json()["items"]}
    assert "Visible to the tenant." in summaries
    assert "Visible only to the platform." not in summaries


def test_platform_audit_requires_a_permission_the_role_never_has(client, db) -> None:
    """A platform-scoped coordinator still cannot read the platform journal."""
    org = _org(db)
    user = make_user(db, email=f"scoped-coord-{uuid.uuid4().hex[:8]}@example.com")
    make_membership(db, user, org, role=MembershipRole.COORDINATOR, scope=MembershipScope.PLATFORM)
    db.commit()
    login_client(client, db, user, org.id)

    response = client.get(f"{API}/platform/audit")
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "platform_scope_required"


# ---------------------------------------------------------------------------
# Migration-facing model behaviour
# ---------------------------------------------------------------------------


def test_new_organisations_default_to_active(db) -> None:
    org = _org(db)
    db.commit()
    assert org.status == OrganizationStatus.ACTIVE
    assert org.suspended_at is None
    assert Permission.PLATFORM_ORGANIZATIONS_MANAGE in PLATFORM_PERMISSIONS
