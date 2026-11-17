"""Batch 10 — organisation member lifecycle administration.

Every test drives the real HTTP API through real sessions and real database
rows. Two tenants exist; the second one exists only to prove that member
administration can never reach, enumerate or mutate it.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.enums import MembershipRole, MembershipStatus
from app.db.models.audit import AuditEvent
from app.db.models.identity import OrganizationMembership
from app.main import app
from tests.conftest import (
    login_client,
    make_membership,
    make_organization,
    make_user,
)

API = "/api/v1"
OLD_PASSWORD = "StrongPass!2345"
NEW_PASSWORD = "RotatedPass!9876"
SAFE_FIELDS = {
    "id",
    "user_id",
    "full_name",
    "email",
    "role",
    "scope",
    "status",
    "joined_at",
    "is_self",
}


@pytest.fixture()
def world(client: TestClient, db):
    suffix = uuid.uuid4().hex[:6]
    org_a = make_organization(db, name="Alpha Recovery", slug=f"alpha-{suffix}")
    org_b = make_organization(db, name="Beta Smelting", slug=f"beta-{suffix}")

    users = {
        "admin_a": make_user(db, full_name="Alpha Admin"),
        "second_admin_a": make_user(db, full_name="Alpha Second Admin"),
        "viewer_a": make_user(db, full_name="Alpha Viewer"),
        "coord_a": make_user(db, full_name="Alpha Coordinator"),
        "dual": make_user(db, full_name="Dual Member"),
        "admin_b": make_user(db, full_name="Beta Admin"),
        "viewer_b": make_user(db, full_name="Beta Viewer"),
        "platform": make_user(db, full_name="Platform Operator", is_platform_admin=True),
        "outsider": make_user(db, full_name="No Membership"),
    }

    memberships = {
        "admin_a": make_membership(db, users["admin_a"], org_a, role=MembershipRole.ORG_ADMIN),
        "viewer_a": make_membership(db, users["viewer_a"], org_a, role=MembershipRole.VIEWER),
        "coord_a": make_membership(db, users["coord_a"], org_a, role=MembershipRole.COORDINATOR),
        "dual_a": make_membership(db, users["dual"], org_a, role=MembershipRole.VIEWER),
        "dual_b": make_membership(db, users["dual"], org_b, role=MembershipRole.COORDINATOR),
        "admin_b": make_membership(db, users["admin_b"], org_b, role=MembershipRole.ORG_ADMIN),
        "viewer_b": make_membership(db, users["viewer_b"], org_b, role=MembershipRole.VIEWER),
    }

    return SimpleNamespace(
        db=db,
        org_a=org_a,
        org_b=org_b,
        users=users,
        memberships=memberships,
    )


def _client_for(
    world, key: str, organization_id: uuid.UUID | None = None
) -> tuple[TestClient, dict[str, str]]:
    """A dedicated browser-like client authenticated as one world user."""
    user = world.users[key]
    if organization_id is None:
        membership = world.db.scalar(
            select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)
        )
        organization_id = membership.organization_id if membership else None
    client = TestClient(app)
    headers = login_client(client, world.db, user, organization_id)
    return client, headers


def _roster(client: TestClient, headers: dict[str, str], **params):
    return client.get(f"{API}/organizations/members", headers=headers, params=params)


def _events(db, event_type: str) -> list[AuditEvent]:
    return list(
        db.scalars(select(AuditEvent).where(AuditEvent.event_type == event_type)).all()
    )


# ---------------------------------------------------------------------------
# roster
# ---------------------------------------------------------------------------


def test_roster_requires_authentication(world) -> None:
    anonymous = TestClient(app)
    response = anonymous.get(f"{API}/organizations/members")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_roster_rejects_a_principal_without_membership(world) -> None:
    client, headers = _client_for(world, "outsider")
    response = _roster(client, headers)
    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "member.view"


def test_roster_is_available_to_a_read_only_member(world) -> None:
    client, headers = _client_for(world, "viewer_a")
    response = _roster(client, headers)
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()["items"]}
    assert world.users["admin_a"].email in emails


def test_roster_lists_only_the_active_organisation(world) -> None:
    client, headers = _client_for(world, "admin_a")
    response = _roster(client, headers)
    assert response.status_code == 200
    body = response.json()
    emails = {item["email"] for item in body["items"]}
    assert emails == {
        world.users["admin_a"].email,
        world.users["viewer_a"].email,
        world.users["coord_a"].email,
        world.users["dual"].email,
    }
    assert world.users["admin_b"].email not in emails
    assert body["total"] == 4
    assert body["page_size"] == 25


def test_roster_cannot_enumerate_another_tenant(world) -> None:
    client, headers = _client_for(world, "admin_a")
    response = _roster(client, headers, organization_id=str(world.org_b.id))
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "organisation_scope"
    assert world.users["admin_b"].email not in response.text


def test_roster_exposes_only_safe_fields(world) -> None:
    client, headers = _client_for(world, "admin_a")
    response = _roster(client, headers)
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert set(item) == SAFE_FIELDS
        assert item["status"] in {"invited", "active", "suspended", "removed"}
    lowered = response.text.lower()
    assert "password" not in lowered
    assert "token" not in lowered
    assert "hash" not in lowered


def test_roster_searches_by_name_and_email(world) -> None:
    client, headers = _client_for(world, "admin_a")
    by_name = _roster(client, headers, q="Alpha Viewer")
    assert [item["email"] for item in by_name.json()["items"]] == [
        world.users["viewer_a"].email
    ]
    by_email = _roster(client, headers, q=world.users["coord_a"].email)
    assert [item["email"] for item in by_email.json()["items"]] == [
        world.users["coord_a"].email
    ]


def test_roster_includes_inactive_memberships_but_filters_on_request(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    deactivation = admin.post(
        f"{API}/organizations/members/{world.memberships['dual_a'].id}/deactivate",
        headers=admin_headers,
    )
    assert deactivation.status_code == 200, deactivation.text

    every = _roster(admin, admin_headers).json()
    dual = next(item for item in every["items"] if item["user_id"] == str(world.users["dual"].id))
    assert dual["status"] == "suspended"

    active_only = _roster(admin, admin_headers, status="active").json()
    assert all(item["status"] == "active" for item in active_only["items"])
    assert str(world.users["dual"].id) not in {item["user_id"] for item in active_only["items"]}
    assert active_only["total"] == 3

    suspended_only = _roster(admin, admin_headers, status="suspended").json()
    assert [item["status"] for item in suspended_only["items"]] == ["suspended"]


# ---------------------------------------------------------------------------
# role and scope management
# ---------------------------------------------------------------------------


def test_role_change_is_applied_and_takes_effect_immediately(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    viewer, viewer_headers = _client_for(world, "viewer_a")

    before = viewer.get(f"{API}/auth/me", headers=viewer_headers).json()
    assert "material.create" not in before["permissions"]

    response = admin.patch(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}",
        json={"role": "coordinator"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "coordinator"
    assert response.json()["is_self"] is False

    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].role == MembershipRole.COORDINATOR

    # Authorisation is rebuilt from the membership row on every request, so the
    # change applies to the member's existing session without a new login.
    after = viewer.get(f"{API}/auth/me", headers=viewer_headers).json()
    assert "material.create" in after["permissions"]


def test_role_change_is_audited_with_actor_target_and_previous_role(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.patch(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}",
        json={"role": "reviewer"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    events = _events(world.db, "membership.changed")
    assert len(events) == 1
    event = events[0]
    assert event.actor_id == str(world.users["admin_a"].id)
    assert event.organization_id == world.org_a.id
    assert event.entity_id == world.memberships["viewer_a"].id
    assert event.payload["user_id"] == str(world.users["viewer_a"].id)
    assert event.payload["previous_role"] == "viewer"
    assert event.payload["new_role"] == "reviewer"
    assert event.previous_state == "viewer/organization"
    assert event.new_state == "reviewer/organization"


def test_coordinator_and_viewer_cannot_change_roles(world) -> None:
    target = world.memberships["viewer_a"].id
    for key in ("coord_a", "viewer_a"):
        client, headers = _client_for(world, key)
        response = client.patch(
            f"{API}/organizations/members/{target}",
            json={"role": "org_admin"},
            headers=headers,
        )
        assert response.status_code == 403, key
        assert response.json()["error"]["details"]["required_permission"] == "member.manage"

    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].role == MembershipRole.VIEWER


def test_invalid_role_is_rejected_without_changing_anything(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.patch(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}",
        json={"role": "superuser"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].role == MembershipRole.VIEWER


def test_empty_role_change_payload_is_rejected(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.patch(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}",
        json={},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_cross_tenant_and_unknown_targets_are_indistinguishable(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")

    foreign = admin.patch(
        f"{API}/organizations/members/{world.memberships['viewer_b'].id}",
        json={"role": "coordinator"},
        headers=admin_headers,
    )
    unknown = admin.patch(
        f"{API}/organizations/members/{uuid.uuid4()}",
        json={"role": "coordinator"},
        headers=admin_headers,
    )
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json()["error"]["message"] == unknown.json()["error"]["message"]
    world.db.refresh(world.memberships["viewer_b"])
    assert world.memberships["viewer_b"].role == MembershipRole.VIEWER


def test_a_member_cannot_change_their_own_role_or_scope(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    membership_id = world.memberships["admin_a"].id

    demote = admin.patch(
        f"{API}/organizations/members/{membership_id}",
        json={"role": "viewer"},
        headers=admin_headers,
    )
    promote = admin.patch(
        f"{API}/organizations/members/{membership_id}",
        json={"scope": "platform"},
        headers=admin_headers,
    )
    for response in (demote, promote):
        assert response.status_code == 403
        assert response.json()["error"]["details"]["reason"] == "self_modification"

    world.db.refresh(world.memberships["admin_a"])
    assert world.memberships["admin_a"].role == MembershipRole.ORG_ADMIN
    assert world.memberships["admin_a"].scope.value == "organization"
    # The administrator keeps their authority: the refusal did not half-apply.
    assert _roster(admin, admin_headers).status_code == 200


def test_last_active_administrator_cannot_be_demoted(world) -> None:
    platform, platform_headers = _client_for(world, "platform")
    response = platform.patch(
        f"{API}/organizations/members/{world.memberships['admin_a'].id}",
        json={"role": "viewer"},
        headers=platform_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "last_admin"
    world.db.refresh(world.memberships["admin_a"])
    assert world.memberships["admin_a"].role == MembershipRole.ORG_ADMIN


def test_an_administrator_can_be_demoted_once_a_replacement_exists(world) -> None:
    platform, platform_headers = _client_for(world, "platform")
    make_membership(
        world.db, world.users["second_admin_a"], world.org_a, role=MembershipRole.ORG_ADMIN
    )

    response = platform.patch(
        f"{API}/organizations/members/{world.memberships['admin_a'].id}",
        json={"role": "coordinator"},
        headers=platform_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "coordinator"


def test_organisation_administrator_cannot_grant_platform_scope(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.patch(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}",
        json={"scope": "platform"},
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "privilege_escalation"
    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].scope.value == "organization"


def test_platform_scope_may_change_members_across_organisations(world) -> None:
    platform, platform_headers = _client_for(world, "platform")
    response = platform.patch(
        f"{API}/organizations/members/{world.memberships['viewer_b'].id}",
        json={"role": "auditor"},
        headers=platform_headers,
    )
    assert response.status_code == 200, response.text
    world.db.refresh(world.memberships["viewer_b"])
    assert world.memberships["viewer_b"].role == MembershipRole.AUDITOR
    assert _events(world.db, "membership.changed")[0].organization_id == world.org_b.id


# ---------------------------------------------------------------------------
# deactivation
# ---------------------------------------------------------------------------


def test_deactivation_suspends_the_membership_and_revokes_its_sessions(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    viewer, viewer_headers = _client_for(world, "viewer_a")

    response = admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/deactivate",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["member"]["status"] == "suspended"
    assert body["sessions_revoked"] >= 1

    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].status == MembershipStatus.SUSPENDED

    # The member's next request with the revoked session fails.
    assert viewer.get(f"{API}/auth/me", headers=viewer_headers).status_code == 401


def test_deactivation_is_audited(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/deactivate",
        headers=admin_headers,
    )
    events = _events(world.db, "membership.deactivated")
    assert len(events) == 1
    event = events[0]
    assert event.actor_id == str(world.users["admin_a"].id)
    assert event.organization_id == world.org_a.id
    assert event.payload["user_id"] == str(world.users["viewer_a"].id)
    assert event.payload["scope_of_effect"] == "membership"
    assert event.previous_state == "active"
    assert event.new_state == "suspended"


def test_coordinator_and_viewer_cannot_deactivate_members(world) -> None:
    target = world.memberships["viewer_a"].id
    for key in ("coord_a", "viewer_a"):
        client, headers = _client_for(world, key)
        response = client.post(
            f"{API}/organizations/members/{target}/deactivate", headers=headers
        )
        assert response.status_code == 403, key
    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].status == MembershipStatus.ACTIVE


def test_cross_tenant_deactivation_is_refused(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_b'].id}/deactivate",
        headers=admin_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Member not found."
    world.db.refresh(world.memberships["viewer_b"])
    assert world.memberships["viewer_b"].status == MembershipStatus.ACTIVE


def test_a_member_cannot_deactivate_themselves(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.post(
        f"{API}/organizations/members/{world.memberships['admin_a'].id}/deactivate",
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "self_modification"
    world.db.refresh(world.memberships["admin_a"])
    assert world.memberships["admin_a"].status == MembershipStatus.ACTIVE


def test_last_active_administrator_cannot_be_deactivated(world) -> None:
    platform, platform_headers = _client_for(world, "platform")
    response = platform.post(
        f"{API}/organizations/members/{world.memberships['admin_a'].id}/deactivate",
        headers=platform_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "last_admin"
    world.db.refresh(world.memberships["admin_a"])
    assert world.memberships["admin_a"].status == MembershipStatus.ACTIVE


def test_deactivation_does_not_touch_other_organisations(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.post(
        f"{API}/organizations/members/{world.memberships['dual_a'].id}/deactivate",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    world.db.refresh(world.memberships["dual_a"])
    world.db.refresh(world.memberships["dual_b"])
    assert world.memberships["dual_a"].status == MembershipStatus.SUSPENDED
    assert world.memberships["dual_b"].status == MembershipStatus.ACTIVE
    assert world.users["dual"].is_active is True

    # The other membership still works.
    dual, dual_headers = _client_for(world, "dual", world.org_b.id)
    me = dual.get(f"{API}/auth/me", headers=dual_headers)
    assert me.status_code == 200
    assert me.json()["active_organization_id"] == str(world.org_b.id)
    assert dual.get(f"{API}/materials", headers=dual_headers).status_code == 200

    # Switching into the deactivated organisation is refused.
    switch = dual.post(
        f"{API}/auth/switch-organization",
        json={"organization_id": str(world.org_a.id)},
        headers=dual_headers,
    )
    assert switch.status_code == 403
    assert switch.json()["error"]["details"]["reason"] == "membership_required"


def test_deactivated_member_keeps_no_workspace_access_after_signing_in_again(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/deactivate",
        headers=admin_headers,
    )

    fresh = TestClient(app)
    login = fresh.post(
        f"{API}/auth/login",
        json={"email": world.users["viewer_a"].email, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200, login.text
    me = fresh.get(f"{API}/auth/me")
    assert me.status_code == 200
    assert me.json()["permissions"] == []
    assert fresh.get(f"{API}/materials").status_code == 403


def test_reactivation_restores_the_membership_and_is_audited(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/deactivate",
        headers=admin_headers,
    )
    response = admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/reactivate",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["member"]["status"] == "active"

    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].status == MembershipStatus.ACTIVE
    events = _events(world.db, "membership.reactivated")
    assert events and events[0].actor_id == str(world.users["admin_a"].id)

    viewer, viewer_headers = _client_for(world, "viewer_a")
    assert viewer.get(f"{API}/materials", headers=viewer_headers).status_code == 200


# ---------------------------------------------------------------------------
# operator-initiated password reset
# ---------------------------------------------------------------------------


def test_operator_reset_arms_forced_rotation_and_revokes_sessions(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    viewer, viewer_headers = _client_for(world, "viewer_a")

    response = admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/reset-password",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"member", "sessions_revoked", "must_change_password", "message"}
    assert body["sessions_revoked"] >= 1
    assert body["must_change_password"] is True
    assert body["message"]

    world.db.refresh(world.users["viewer_a"])
    assert world.users["viewer_a"].password_changed_at is None

    world.db.refresh(world.memberships["viewer_a"])
    assert world.memberships["viewer_a"].status == MembershipStatus.ACTIVE

    # No default password is generated, and the old session is dead.
    assert viewer.get(f"{API}/auth/me", headers=viewer_headers).status_code == 401

    events = _events(world.db, "auth.password_reset_issued")
    assert len(events) == 1
    assert events[0].actor_id == str(world.users["admin_a"].id)
    assert events[0].organization_id == world.org_a.id
    assert events[0].payload["delivery"] == "operator_assisted"
    assert events[0].payload["sessions_revoked"] == body["sessions_revoked"]


def test_reset_blocks_the_workspace_until_the_member_rotates_the_password(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/reset-password",
        headers=admin_headers,
    )

    member = TestClient(app)
    login = member.post(
        f"{API}/auth/login",
        json={"email": world.users["viewer_a"].email, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200, login.text
    assert member.get(f"{API}/auth/me").json()["must_change_password"] is True

    blocked = member.get(f"{API}/materials")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"

    csrf = {"X-CSRF-Token": member.cookies.get("lm_csrf")}
    rotation = member.post(
        f"{API}/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=csrf,
    )
    assert rotation.status_code == 200, rotation.text

    relogin = member.post(
        f"{API}/auth/login",
        json={"email": world.users["viewer_a"].email, "password": NEW_PASSWORD},
    )
    assert relogin.status_code == 200, relogin.text
    assert member.get(f"{API}/materials").status_code == 200
    assert member.get(f"{API}/auth/me").json()["must_change_password"] is False


def test_coordinator_cannot_reset_a_password(world) -> None:
    coord, coord_headers = _client_for(world, "coord_a")
    response = coord.post(
        f"{API}/organizations/members/{world.memberships['viewer_a'].id}/reset-password",
        headers=coord_headers,
    )
    assert response.status_code == 403
    world.db.refresh(world.users["viewer_a"])
    assert world.users["viewer_a"].password_changed_at is not None


def test_an_operator_cannot_reset_their_own_password(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.post(
        f"{API}/organizations/members/{world.memberships['admin_a'].id}/reset-password",
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "self_modification"


def test_cross_tenant_password_reset_is_refused(world) -> None:
    admin, admin_headers = _client_for(world, "admin_a")
    response = admin.post(
        f"{API}/organizations/members/{world.memberships['viewer_b'].id}/reset-password",
        headers=admin_headers,
    )
    assert response.status_code == 404
    world.db.refresh(world.users["viewer_b"])
    assert world.users["viewer_b"].password_changed_at is not None
