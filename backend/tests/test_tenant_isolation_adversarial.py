"""Checkpoint C adversarial tenant-isolation tests.

Every test drives the real HTTP API through real sessions (cookies + CSRF), with
genuine database records across three organisations. Two of them (Alpha and
Beta) run a legitimate cross-organisation recovery deal; the third (Gamma) is an
unrelated tenant that must never see it.

Coverage is intentionally adversarial: a hostile tenant guessing identifiers,
forging organisation ids in payloads and query strings, replaying another
tenant's session ids, or reaching through a legitimate participant relationship.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.enums import (
    MembershipRole,
    MembershipStatus,
    TransactionStatus,
)
from app.db.models.audit import AuditEvent
from app.db.models.identity import AuthSession, OrganizationMembership
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.main import app
from tests.conftest import (
    TODAY,
    add_specification,
    login_client,
    make_demand,
    make_material,
    make_membership,
    make_opportunity,
    make_organization,
    make_user,
)

API = "/api/v1"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _session_client(db, user, organization) -> tuple[TestClient, dict[str, str]]:
    """A dedicated browser-like client authenticated as one user."""
    client = TestClient(app)
    headers = login_client(client, db, user, organization.id)
    return client, headers


@pytest.fixture()
def world(client: TestClient, db):
    """Three tenants, seven users and one shared Alpha->Beta opportunity."""
    org_a = make_organization(db, name="Alpha Recovery", slug="alpha-recovery")
    org_b = make_organization(db, name="Beta Smelting", slug="beta-smelting")
    org_c = make_organization(db, name="Gamma Glass", slug="gamma-glass")

    users = {
        "coord_a": (make_user(db, full_name="Alpha Coordinator"), org_a, MembershipRole.COORDINATOR),
        "viewer_a": (make_user(db, full_name="Alpha Viewer"), org_a, MembershipRole.VIEWER),
        "admin_a": (make_user(db, full_name="Alpha Admin"), org_a, MembershipRole.ORG_ADMIN),
        "reviewer_b": (make_user(db, full_name="Beta Reviewer"), org_b, MembershipRole.REVIEWER),
        "approver_b": (make_user(db, full_name="Beta Approver"), org_b, MembershipRole.APPROVER),
        "admin_b": (make_user(db, full_name="Beta Admin"), org_b, MembershipRole.ORG_ADMIN),
        "coord_c": (make_user(db, full_name="Gamma Coordinator"), org_c, MembershipRole.COORDINATOR),
        "admin_c": (make_user(db, full_name="Gamma Admin"), org_c, MembershipRole.ORG_ADMIN),
        "viewer_c": (make_user(db, full_name="Gamma Viewer"), org_c, MembershipRole.VIEWER),
    }
    for user, org, role in users.values():
        make_membership(db, user, org, role=role)

    material_a = make_material(db, org_a, name="Alpha pickling sludge", quantity_available=100.0)
    add_specification(db, material_a, purity=95.0, contamination=0.5, moisture=1.0)
    material_b = make_material(db, org_b, name="Beta mill scale", quantity_available=60.0)
    add_specification(db, material_b, purity=90.0)
    material_c = make_material(db, org_c, name="Gamma cullet", quantity_available=40.0)
    add_specification(db, material_c, purity=92.0)

    demand_a = make_demand(db, org_a, title="Alpha internal demand")
    demand_b = make_demand(db, org_b, title="Beta furnace feed")
    demand_c = make_demand(db, org_c, title="Gamma batch demand")

    opp_ab = make_opportunity(
        db, material_a, demand_b, org_a, org_b, compatibility_score=95, match_quantity=100.0
    )
    # Beta and Gamma have their own deal. Alpha is a participant in a *different*
    # deal and must never inherit visibility of this one.
    opp_bc = make_opportunity(
        db, material_b, demand_c, org_b, org_c, compatibility_score=88, match_quantity=40.0
    )
    db.commit()

    clients = {
        name: _session_client(db, user, org) for name, (user, org, _role) in users.items()
    }

    coord_a, coord_a_headers = clients["coord_a"]
    created = coord_a.post(
        f"{API}/proposals",
        json={"opportunity_id": str(opp_ab.id), "quantity": 40.0},
        headers=coord_a_headers,
    )
    assert created.status_code == 201, created.text
    proposal_ab = created.json()

    return SimpleNamespace(
        db=db,
        org_a=org_a,
        org_b=org_b,
        org_c=org_c,
        users=users,
        clients=clients,
        material_a=material_a,
        material_b=material_b,
        material_c=material_c,
        demand_a=demand_a,
        demand_b=demand_b,
        demand_c=demand_c,
        opp_ab=opp_ab,
        opp_bc=opp_bc,
        proposal_ab=proposal_ab,
    )


def _client_for(world, name: str) -> tuple[TestClient, dict[str, str]]:
    return world.clients[name]


def _submit_and_approve(world) -> dict:
    """Drive the shared proposal to ``approved`` through the real API."""
    coord_a, coord_a_headers = _client_for(world, "coord_a")
    reviewer_b, reviewer_b_headers = _client_for(world, "reviewer_b")
    approver_b, approver_b_headers = _client_for(world, "approver_b")
    proposal_id = world.proposal_ab["id"]

    assert coord_a.post(
        f"{API}/proposals/{proposal_id}/submit", json={}, headers=coord_a_headers
    ).status_code == 200
    assert reviewer_b.post(
        f"{API}/proposals/{proposal_id}/review", json={}, headers=reviewer_b_headers
    ).status_code == 200
    approved = approver_b.post(
        f"{API}/proposals/{proposal_id}/approve",
        json={"approval_reference": "DECISION-ALPHA-BETA-1"},
        headers=approver_b_headers,
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


@pytest.fixture()
def approved_deal(world):
    world.approved_proposal = _submit_and_approve(world)
    return world


@pytest.fixture()
def transferred_deal(approved_deal):
    """A deal with a recorded physical transfer but no verification yet."""
    coord_a, headers = _client_for(approved_deal, "coord_a")
    created = coord_a.post(
        f"{API}/transactions",
        json={"proposal_id": approved_deal.proposal_ab["id"], "carrier_name": "Lowland Freight"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    transaction = created.json()
    moved = coord_a.post(
        f"{API}/transactions/{transaction['id']}/record-transfer",
        json={
            "transferred_quantity": 39.5,
            "transfer_reference": "WB-ALPHA-0001",
            "material_identification": "Loosely packed iron oxide sludge",
            "evidence": {"weighbridge_ticket": "WB-ALPHA-0001", "vehicle": "NL-AB-01"},
        },
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    approved_deal.transaction = moved.json()
    return approved_deal


# ---------------------------------------------------------------------------
# 1. cross-tenant list access
# ---------------------------------------------------------------------------


def test_cross_tenant_lists_return_only_own_records(world) -> None:
    coord_c, headers = _client_for(world, "coord_c")

    materials = coord_c.get(f"{API}/materials", headers=headers).json()
    assert materials["total"] == 1
    assert [item["id"] for item in materials["items"]] == [str(world.material_c.id)]

    demands = coord_c.get(f"{API}/demands", headers=headers).json()
    assert demands["total"] == 1
    assert [item["id"] for item in demands["items"]] == [str(world.demand_c.id)]

    opportunities = coord_c.get(f"{API}/opportunities", headers=headers).json()
    assert {item["id"] for item in opportunities["items"]} == {str(world.opp_bc.id)}

    proposals = coord_c.get(f"{API}/proposals", headers=headers).json()
    assert proposals["total"] == 0

    transactions = coord_c.get(f"{API}/transactions", headers=headers).json()
    assert transactions["total"] == 0

    # The counterparty organisation is visible in the shared Gamma deal but the
    # Alpha deal is not.
    coord_a, a_headers = _client_for(world, "coord_a")
    a_opportunities = coord_a.get(f"{API}/opportunities", headers=a_headers).json()
    assert {item["id"] for item in a_opportunities["items"]} == {str(world.opp_ab.id)}
    a_proposals = coord_a.get(f"{API}/proposals", headers=a_headers).json()
    assert {item["id"] for item in a_proposals["items"]} == {world.proposal_ab["id"]}


def test_client_supplied_organization_filters_are_not_trusted(world) -> None:
    coord_a, headers = _client_for(world, "coord_a")
    for path, params in (
        ("/materials", {"organization_id": str(world.org_c.id)}),
        ("/demands", {"organization_id": str(world.org_c.id)}),
        ("/opportunities", {"organization_id": str(world.org_c.id)}),
        ("/proposals", {"organization_id": str(world.org_c.id)}),
    ):
        response = coord_a.get(f"{API}{path}", params=params, headers=headers)
        assert response.status_code == 403, (path, response.text)


# ---------------------------------------------------------------------------
# 2. guessed identifiers
# ---------------------------------------------------------------------------


def test_guessed_resource_ids_do_not_resolve_across_tenants(world) -> None:
    coord_c, headers = _client_for(world, "coord_c")
    for path in (
        f"/materials/{world.material_a.id}",
        f"/demands/{world.demand_b.id}",
        f"/opportunities/{world.opp_ab.id}",
        f"/proposals/{world.proposal_ab['id']}",
        f"/proposals/{world.proposal_ab['id']}/history",
    ):
        response = coord_c.get(f"{API}{path}", headers=headers)
        assert response.status_code == 404, (path, response.status_code, response.text)

    coord_a, a_headers = _client_for(world, "coord_a")
    for path in (
        f"/materials/{world.material_c.id}",
        f"/demands/{world.demand_c.id}",
        f"/opportunities/{world.opp_bc.id}",
        f"/transactions/{world.opp_bc.id}",
    ):
        response = coord_a.get(f"{API}{path}", headers=a_headers)
        assert response.status_code == 404, (path, response.status_code, response.text)


def test_unknown_identifiers_and_foreign_identifiers_are_indistinguishable(world) -> None:
    """A 404 must not reveal whether a foreign record exists."""
    coord_c, headers = _client_for(world, "coord_c")
    existing_foreign = coord_c.get(f"{API}/materials/{world.material_a.id}", headers=headers)
    missing = coord_c.get(f"{API}/materials/{uuid.uuid4()}", headers=headers)
    assert existing_foreign.status_code == missing.status_code == 404
    assert existing_foreign.json()["error"]["code"] == missing.json()["error"]["code"]


# ---------------------------------------------------------------------------
# 3. cross-tenant mutations
# ---------------------------------------------------------------------------


def test_cross_tenant_mutations_are_refused(world) -> None:
    coord_c, headers = _client_for(world, "coord_c")

    # There is no generic update/delete surface for tenant records at all.
    assert coord_c.patch(
        f"{API}/materials/{world.material_a.id}", json={"name": "defaced"}, headers=headers
    ).status_code == 405
    assert coord_c.delete(
        f"{API}/materials/{world.material_a.id}", headers=headers
    ).status_code == 405

    for action, body in (
        ("submit", {}),
        ("review", {}),
        ("reject", {"reason": "hostile tenant"}),
        ("cancel", {"reason": "hostile tenant"}),
    ):
        response = coord_c.post(
            f"{API}/proposals/{world.proposal_ab['id']}/{action}", json=body, headers=headers
        )
        assert response.status_code == 404, (action, response.status_code, response.text)

    world.db.expire_all()
    proposal = world.db.get(RecoveryProposal, uuid.UUID(world.proposal_ab["id"]))
    assert proposal.status.value == "draft"
    assert proposal.version == 0


# ---------------------------------------------------------------------------
# 4. forged organization ids
# ---------------------------------------------------------------------------


def test_forged_organization_in_write_payload_binds_to_active_organization(world) -> None:
    coord_a, headers = _client_for(world, "coord_a")
    response = coord_a.post(
        f"{API}/materials",
        json={
            "organization_id": str(world.org_c.id),
            "reference_code": "FORGED-ORG-1",
            "name": "Forged ownership attempt",
            "category": "metals",
            "quantity_available": 5.0,
            "unit": "tonne",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["organization"]["id"] == str(world.org_a.id)

    # And the hostile tenant cannot plant a record in Alpha either.
    coord_c, c_headers = _client_for(world, "coord_c")
    planted = coord_c.post(
        f"{API}/materials",
        json={
            "organization_id": str(world.org_a.id),
            "reference_code": "FORGED-ORG-2",
            "name": "Hostile ownership attempt",
            "category": "metals",
            "quantity_available": 5.0,
            "unit": "tonne",
        },
        headers=c_headers,
    )
    assert planted.status_code == 201, planted.text
    assert planted.json()["organization"]["id"] == str(world.org_c.id)


def test_proposal_cannot_be_created_from_another_tenants_opportunity(world) -> None:
    coord_c, headers = _client_for(world, "coord_c")
    response = coord_c.post(
        f"{API}/proposals",
        json={"opportunity_id": str(world.opp_ab.id), "quantity": 10.0},
        headers=headers,
    )
    assert response.status_code == 404, response.text

    # Same answer whether or not the opportunity exists.
    missing = coord_c.post(
        f"{API}/proposals",
        json={"opportunity_id": "00000000-0000-0000-0000-000000000000", "quantity": 10.0},
        headers=headers,
    )
    assert missing.status_code == 404
    assert response.json()["error"]["code"] == missing.json()["error"]["code"]

    # The denied attempt is still auditable for the tenant.
    world.db.expire_all()
    denied = world.db.scalars(
        select(AuditEvent).where(
            AuditEvent.event_type == "authorization.denied",
            AuditEvent.organization_id == world.org_c.id,
        )
    ).all()
    assert denied, "cross-tenant proposal attempt must be recorded"

    # Alpha may not start a proposal on Beta's unrelated Gamma deal either.
    coord_a, a_headers = _client_for(world, "coord_a")
    other = coord_a.post(
        f"{API}/proposals",
        json={"opportunity_id": str(world.opp_bc.id), "quantity": 10.0},
        headers=a_headers,
    )
    assert other.status_code == 404, other.text


# ---------------------------------------------------------------------------
# 5/6. related object ids and evidence
# ---------------------------------------------------------------------------


def test_transaction_evidence_is_hidden_from_unrelated_tenants(transferred_deal) -> None:
    world = transferred_deal
    coord_c, c_headers = _client_for(world, "coord_c")
    assert coord_c.get(
        f"{API}/transactions/{world.transaction['id']}", headers=c_headers
    ).status_code == 404
    assert coord_c.get(
        f"{API}/transactions/{world.transaction['id']}/history", headers=c_headers
    ).status_code == 404


def test_participants_can_read_shared_transaction_evidence(transferred_deal) -> None:
    world = transferred_deal
    for name in ("coord_a", "approver_b", "admin_b"):
        client, headers = _client_for(world, name)
        response = client.get(f"{API}/transactions/{world.transaction['id']}", headers=headers)
        assert response.status_code == 200, (name, response.text)
        body = response.json()
        assert body["transfer_reference"] == "WB-ALPHA-0001"
        assert body["evidence"]["weighbridge_ticket"] == "WB-ALPHA-0001"
        assert body["material_identification"] == "Loosely packed iron oxide sludge"


# ---------------------------------------------------------------------------
# 7. audit timelines
# ---------------------------------------------------------------------------


def test_audit_journal_and_entity_timelines_are_tenant_scoped(approved_deal) -> None:
    world = approved_deal
    proposal_id = world.proposal_ab["id"]

    admin_c, c_headers = _client_for(world, "admin_c")
    journal = admin_c.get(f"{API}/audit", headers=c_headers)
    assert journal.status_code == 200, journal.text
    assert all(
        item["organization_id"] in (None, str(world.org_c.id))
        for item in journal.json()["items"]
    )
    assert journal.json()["items"] == []

    assert admin_c.get(
        f"{API}/audit/proposal/{proposal_id}", headers=c_headers
    ).status_code == 404
    filtered = admin_c.get(
        f"{API}/audit",
        params={"entity_type": "proposal", "entity_id": proposal_id},
        headers=c_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0

    # A participant sees the full timeline, including events recorded under the
    # other participant organisation.
    admin_b, b_headers = _client_for(world, "admin_b")
    timeline = admin_b.get(f"{API}/audit/proposal/{proposal_id}", headers=b_headers)
    assert timeline.status_code == 200, timeline.text
    events = timeline.json()
    assert {event["event_type"] for event in events} >= {
        "proposal.created",
        "proposal.submit",
        "proposal.review",
        "proposal.approve",
    }
    assert {event["organization_id"] for event in events} >= {
        str(world.org_a.id),
        str(world.org_b.id),
    }

    # Roles without the audit capability cannot read the journal at all.
    coord_a, a_headers = _client_for(world, "coord_a")
    assert coord_a.get(f"{API}/audit", headers=a_headers).status_code == 403
    viewer_c, vc_headers = _client_for(world, "viewer_c")
    assert viewer_c.get(f"{API}/audit", headers=vc_headers).status_code == 403


# ---------------------------------------------------------------------------
# 8. inactive membership
# ---------------------------------------------------------------------------


def test_inactive_membership_loses_access_immediately(client, world) -> None:
    coord_a, headers = _client_for(world, "coord_a")
    assert coord_a.get(f"{API}/materials", headers=headers).status_code == 200

    membership = world.db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == world.users["coord_a"][0].id,
            OrganizationMembership.organization_id == world.org_a.id,
        )
    )
    membership.status = MembershipStatus.SUSPENDED
    world.db.commit()

    # The capability set collapses to empty as soon as the membership is not
    # active, so the very next request loses every tenant read and write.
    listing = coord_a.get(f"{API}/materials", headers=headers)
    assert listing.status_code == 403, listing.text
    assert coord_a.get(
        f"{API}/materials/{world.material_a.id}", headers=headers
    ).status_code == 403
    assert coord_a.post(
        f"{API}/materials",
        json={
            "organization_id": str(world.org_a.id),
            "reference_code": "SUSPENDED-1",
            "name": "Suspended write",
            "category": "metals",
            "quantity_available": 1.0,
            "unit": "tonne",
        },
        headers=headers,
    ).status_code == 403
    # Workflow records are participant-scoped: with no active membership the
    # proposal no longer resolves at all.
    assert coord_a.get(
        f"{API}/proposals/{world.proposal_ab['id']}", headers=headers
    ).status_code == 404


# ---------------------------------------------------------------------------
# 9. organization switching
# ---------------------------------------------------------------------------


def test_organization_switch_scopes_writes_and_never_widens_membership(world) -> None:
    dual = make_user(world.db, full_name="Dual Member")
    make_membership(world.db, dual, world.org_a, role=MembershipRole.COORDINATOR)
    make_membership(world.db, dual, world.org_b, role=MembershipRole.COORDINATOR)
    world.db.commit()

    client, headers = _session_client(world.db, dual, world.org_a)
    me = client.get(f"{API}/auth/me", headers=headers).json()
    assert me["active_organization_id"] == str(world.org_a.id)

    # Read reach is the union of the principal's active memberships - never a
    # tenant the user is not a member of.
    alpha = client.get(f"{API}/materials", headers=headers).json()
    assert {item["id"] for item in alpha["items"]} == {
        str(world.material_a.id),
        str(world.material_b.id),
    }
    assert client.get(f"{API}/materials/{world.material_c.id}", headers=headers).status_code == 404

    # Writes bind to the server-side active organisation, not the payload.
    created_in_a = client.post(
        f"{API}/materials",
        json={
            "organization_id": str(world.org_a.id),
            "reference_code": "SWITCH-A-1",
            "name": "Written under Alpha",
            "category": "metals",
            "quantity_available": 3.0,
            "unit": "tonne",
        },
        headers=headers,
    )
    assert created_in_a.status_code == 201, created_in_a.text
    assert created_in_a.json()["organization"]["id"] == str(world.org_a.id)

    switched = client.post(
        f"{API}/auth/switch-organization",
        json={"organization_id": str(world.org_b.id)},
        headers=headers,
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["active_organization_id"] == str(world.org_b.id)

    created_in_b = client.post(
        f"{API}/materials",
        json={
            "organization_id": str(world.org_a.id),
            "reference_code": "SWITCH-B-1",
            "name": "Written under Beta",
            "category": "metals",
            "quantity_available": 3.0,
            "unit": "tonne",
        },
        headers=headers,
    )
    assert created_in_b.status_code == 201, created_in_b.text
    assert created_in_b.json()["organization"]["id"] == str(world.org_b.id)

    # Switching to a tenant the user is not a member of is refused.
    forbidden = client.post(
        f"{API}/auth/switch-organization",
        json={"organization_id": str(world.org_c.id)},
        headers=headers,
    )
    assert forbidden.status_code == 403
    assert client.get(f"{API}/materials/{world.material_c.id}", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# 10. workflow transitions
# ---------------------------------------------------------------------------


def test_workflow_transitions_require_role_party_and_membership(world) -> None:
    coord_a, a_headers = _client_for(world, "coord_a")
    admin_b, b_headers = _client_for(world, "admin_b")
    viewer_a, va_headers = _client_for(world, "viewer_a")
    coord_c, c_headers = _client_for(world, "coord_c")
    approver_b, ab_headers = _client_for(world, "approver_b")
    proposal_id = world.proposal_ab["id"]

    assert coord_a.post(
        f"{API}/proposals/{proposal_id}/submit", json={}, headers=a_headers
    ).status_code == 200
    # Org admins administer the tenant; they do not inherit workflow powers.
    assert admin_b.post(
        f"{API}/proposals/{proposal_id}/review", json={}, headers=b_headers
    ).status_code == 403
    # Viewers cannot act at all.
    assert viewer_a.post(
        f"{API}/proposals/{proposal_id}/review", json={}, headers=va_headers
    ).status_code == 403
    # Unrelated tenants cannot even see the record they are acting on.
    assert coord_c.post(
        f"{API}/proposals/{proposal_id}/review", json={}, headers=c_headers
    ).status_code == 404
    # Approving before review is a state-machine conflict, not a silent pass.
    assert approver_b.post(
        f"{API}/proposals/{proposal_id}/approve",
        json={"approval_reference": "DECISION-EARLY"},
        headers=ab_headers,
    ).status_code == 409
    # Unauthenticated callers are refused before any tenant logic runs.
    anonymous = TestClient(app)
    assert anonymous.post(f"{API}/proposals/{proposal_id}/review", json={}).status_code == 401


# ---------------------------------------------------------------------------
# 11. discovery
# ---------------------------------------------------------------------------


def test_discovery_requires_capability_and_stays_inside_the_tenant(world) -> None:
    viewer_a, va_headers = _client_for(world, "viewer_a")
    assert viewer_a.post(
        f"{API}/opportunities/discovery", json={"min_score": 0}, headers=va_headers
    ).status_code == 403

    coord_c, c_headers = _client_for(world, "coord_c")
    run = coord_c.post(
        f"{API}/opportunities/discovery", json={"min_score": 0}, headers=c_headers
    )
    assert run.status_code == 200, run.text

    created_ids = [uuid.UUID(value) for value in run.json()["created_ids"]]
    world.db.expire_all()
    created = [
        world.db.get(RecoveryOpportunity, opportunity_id) for opportunity_id in created_ids
    ]
    for opportunity in created:
        parties = {opportunity.supplier_organization_id, opportunity.consumer_organization_id}
        assert world.org_c.id in parties, (
            "an organisation-scoped discovery run created an opportunity for two "
            f"unrelated tenants: {parties}"
        )
    # Alpha supply x Alpha demand is the same tenant (skipped); a pair owned by
    # two unrelated tenants must never be manufactured by Gamma's run. The
    # fixture seeds no Beta-material/Alpha-demand pair, so any row here would be
    # one Gamma created.
    unrelated = world.db.scalar(
        select(RecoveryOpportunity).where(
            RecoveryOpportunity.material_id == world.material_b.id,
            RecoveryOpportunity.resource_demand_id == world.demand_a.id,
        )
    )
    assert unrelated is None
    assert world.opp_ab.compatibility_score == 95

    run_events = world.db.scalars(
        select(AuditEvent).where(AuditEvent.event_type == "discovery.run")
    ).all()
    assert [event.organization_id for event in run_events] == [world.org_c.id]


# ---------------------------------------------------------------------------
# 12. legitimate cross-organisation workflow (positive)
# ---------------------------------------------------------------------------


def test_cross_organization_participants_complete_the_full_lifecycle(transferred_deal) -> None:
    world = transferred_deal
    approver_b, b_headers = _client_for(world, "approver_b")
    coord_a, a_headers = _client_for(world, "coord_a")
    transaction_id = world.transaction["id"]
    proposal_id = world.proposal_ab["id"]

    verified = approver_b.post(
        f"{API}/transactions/{transaction_id}/verify",
        json={
            "verified_quantity": 39.5,
            "verification_method": "weighbridge_ticket",
            "evidence_reference": "AUDIT-BETA-77",
            "evidence": {"audit_report": "AUDIT-BETA-77"},
        },
        headers=b_headers,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == TransactionStatus.VERIFIED.value

    # Both participants see the completed deal and count the recovered material.
    for name in ("coord_a", "admin_b"):
        client, headers = _client_for(world, name)
        detail = client.get(f"{API}/proposals/{proposal_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"
        ledger = client.get(f"{API}/ledger", headers=headers)
        assert ledger.status_code == 200
        body = ledger.json()
        assert body["verified_recovered"] == [{"unit": "tonne", "quantity": 39.5}]
        assert [entry["proposal_id"] for entry in body["entries"]] == [proposal_id]

    # The unrelated tenant sees none of it.
    coord_c, c_headers = _client_for(world, "coord_c")
    assert coord_c.get(f"{API}/ledger", headers=c_headers).json()["entries"] == []
    assert coord_c.get(f"{API}/proposals/{proposal_id}", headers=c_headers).status_code == 404
    assert coord_c.get(f"{API}/transactions/{transaction_id}", headers=c_headers).status_code == 404


# ---------------------------------------------------------------------------
# 13. participant relationships do not widen access
# ---------------------------------------------------------------------------


def test_participant_relationship_does_not_grant_unrelated_record_access(transferred_deal) -> None:
    world = transferred_deal
    coord_a, a_headers = _client_for(world, "coord_a")
    approver_b, b_headers = _client_for(world, "approver_b")

    # Both sides see the shared deal...
    assert coord_a.get(
        f"{API}/opportunities/{world.opp_ab.id}", headers=a_headers
    ).status_code == 200
    assert approver_b.get(
        f"{API}/opportunities/{world.opp_ab.id}", headers=b_headers
    ).status_code == 200

    # ...but neither side gets the other tenant's private catalogue.
    assert coord_a.get(f"{API}/materials/{world.material_b.id}", headers=a_headers).status_code == 404
    assert coord_a.get(f"{API}/demands/{world.demand_b.id}", headers=a_headers).status_code == 404
    assert approver_b.get(f"{API}/materials/{world.material_a.id}", headers=b_headers).status_code == 404
    assert approver_b.get(f"{API}/demands/{world.demand_a.id}", headers=b_headers).status_code == 404

    # Beta's *other* deal with Gamma stays invisible to Alpha.
    assert coord_a.get(f"{API}/opportunities/{world.opp_bc.id}", headers=a_headers).status_code == 404
    assert coord_a.get(f"{API}/materials/{world.material_c.id}", headers=a_headers).status_code == 404

    # Neither participant can read audit events recorded against the other
    # tenant's unrelated records.
    admin_a, aa_headers = _client_for(world, "admin_a")
    gamma_material_events = admin_a.get(
        f"{API}/materials/{world.material_c.id}", headers=aa_headers
    )
    assert gamma_material_events.status_code == 404


# ---------------------------------------------------------------------------
# 14. aggregates
# ---------------------------------------------------------------------------


def test_aggregates_are_tenant_scoped(approved_deal) -> None:
    world = approved_deal
    viewer_c, vc_headers = _client_for(world, "viewer_c")

    overview = viewer_c.get(f"{API}/overview", headers=vc_headers)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["materials"]["total"] == 1
    assert body["opportunities"]["total"] == 1
    assert body["ledger"]["verified_recovered"] == []

    network = viewer_c.get(f"{API}/network", headers=vc_headers)
    assert network.status_code == 200
    node_ids = {node["id"] for node in network.json()["nodes"]}
    assert str(world.org_a.id) not in node_ids
    assert str(world.org_c.id) in node_ids

    # Recent activity never mixes tenants.
    _, a_headers = _client_for(world, "admin_a")
    activity_a = viewer_c.get(f"{API}/overview/activity", headers=vc_headers).json()
    audit_a = _client_for(world, "admin_a")[0].get(f"{API}/audit", headers=a_headers).json()
    alpha_ids = {item["id"] for item in audit_a["items"]}
    assert not ({item["id"] for item in activity_a} & alpha_ids)


# ---------------------------------------------------------------------------
# 15/16. session and membership administration
# ---------------------------------------------------------------------------


def test_session_administration_cannot_touch_other_users(world) -> None:
    coord_a, a_headers = _client_for(world, "coord_a")
    coord_c, c_headers = _client_for(world, "coord_c")

    alpha_sessions = coord_a.get(f"{API}/auth/sessions", headers=a_headers).json()
    assert alpha_sessions and all(session["organization_id"] == str(world.org_a.id) for session in alpha_sessions)

    foreign_session_id = alpha_sessions[0]["id"]
    response = coord_c.post(
        f"{API}/auth/sessions/{foreign_session_id}/revoke", headers=c_headers
    )
    assert response.status_code == 404

    # The session is still usable and Gamma's own listing is unaffected.
    assert coord_a.get(f"{API}/auth/me", headers=a_headers).status_code == 200
    gamma_sessions = coord_c.get(f"{API}/auth/sessions", headers=c_headers).json()
    assert all(session["id"] != foreign_session_id for session in gamma_sessions)

    # Revoking a session must only ever target the caller's own identity.
    other_user_sessions = world.db.scalars(
        select(AuthSession).where(AuthSession.user_id == world.users["coord_a"][0].id)
    ).all()
    assert other_user_sessions


def test_invitations_cannot_escalate_roles_or_cross_tenants(world) -> None:
    coord_a, a_headers = _client_for(world, "coord_a")
    admin_c, c_headers = _client_for(world, "admin_c")
    admin_a, aa_headers = _client_for(world, "admin_a")

    assert coord_a.post(
        f"{API}/auth/invitations",
        json={"email": "new@example.com", "organization_id": str(world.org_a.id), "role": "viewer"},
        headers=a_headers,
    ).status_code == 403

    assert admin_c.post(
        f"{API}/auth/invitations",
        json={"email": "new@example.com", "organization_id": str(world.org_a.id), "role": "viewer"},
        headers=c_headers,
    ).status_code == 403

    assert admin_a.post(
        f"{API}/auth/invitations",
        json={
            "email": "new@example.com",
            "organization_id": str(world.org_a.id),
            "role": "viewer",
            "scope": "platform",
        },
        headers=aa_headers,
    ).status_code == 403

    # Membership administration has no mutation endpoint: role changes cannot be
    # performed through an unaudited payload.
    membership = world.db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == world.users["viewer_a"][0].id
        )
    )
    assert admin_a.patch(
        f"{API}/auth/memberships/{membership.id}", json={"role": "org_admin"}, headers=aa_headers
    ).status_code in {404, 405}


# ---------------------------------------------------------------------------
# 17. architectural guards (route surface)
# ---------------------------------------------------------------------------

#: Routes that are deliberately callable without an authenticated principal.
PUBLIC_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/reset-password"),
    ("POST", "/api/v1/auth/invitations/accept"),
    # Token-gated and deliberately anonymous: an invitee has no account yet, so
    # the preview names only the invitation its token hash resolves to.
    ("GET", "/api/v1/auth/invitations/preview"),
}


def _api_routes():
    """Yield (methods, path, dependant) for every real API route."""
    from fastapi.routing import APIRoute

    def walk(router, prefix=""):
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield route, prefix + (route.path or "/")
            elif type(route).__name__ == "_IncludedRouter":
                context = route.include_context
                yield from walk(context.included_router, prefix + context.prefix)
            elif hasattr(route, "routes"):
                yield from walk(route, prefix + getattr(route, "prefix", ""))

    yield from walk(app)


def _dependency_names(dependant, acc: set[str] | None = None) -> set[str]:
    acc = acc if acc is not None else set()
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            acc.add(getattr(dependency.call, "__name__", str(dependency.call)))
        _dependency_names(dependency, acc)
    return acc


def test_every_business_route_requires_authentication() -> None:
    unauthenticated = []
    for route, path in _api_routes():
        for method in route.methods:
            if (method, path) in PUBLIC_ROUTES:
                continue
            if "get_actor" not in _dependency_names(route.dependant):
                unauthenticated.append((method, path))
    assert unauthenticated == [], unauthenticated


#: Explicit exceptions to the action-style rule below. A Batch 10 requirement
#: names ``PATCH /organizations/members/{id}`` for role and scope changes; it is
#: a single-record administration route with a validated body, its own audit
#: event and no client-supplied organisation. Anything else added here would
#: need the same review, so the guard stays a closed allow-list rather than a
#: blanket permission for PATCH.
AUDITED_RESOURCE_ROUTES = {
    ("PATCH", "/api/v1/organizations/members/{membership_id}"),
    # Batch 11 requires a platform-only tenant lifecycle transition. It is not a
    # generic record edit: the body is a closed enum (extra fields are rejected),
    # the route is unreachable without the platform operator flag, and the change
    # is written to the audit journal inside the same transaction.
    ("PATCH", "/api/v1/platform/organizations/{organization_id}"),
}


def test_no_generic_cross_tenant_mutation_surface_exists() -> None:
    """No PUT/PATCH/DELETE route may exist: every change is an audited action."""
    generic = [
        (method, path)
        for route, path in _api_routes()
        for method in route.methods
        if method in {"PUT", "PATCH", "DELETE"}
        and (method, path) not in AUDITED_RESOURCE_ROUTES
    ]
    assert generic == [], generic
