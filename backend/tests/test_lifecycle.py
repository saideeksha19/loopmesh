"""Proposal and transaction lifecycle tests.

These exercise the public API (not the service directly) so the tests prove the
whole path: request schema -> actor resolution -> state machine -> database
constraint -> audit record -> response.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import (
    ProposalStatus,
    TransactionStatus,
    TransitionEntity,
    VerificationMethod,
)
from app.db.models.audit import AuditEvent
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.db.models.transition import StatusTransition
from app.services import audit
from app.services.lifecycle import (
    PROPOSAL_TRANSITIONS,
    TERMINAL_PROPOSAL_STATES,
    TERMINAL_TRANSACTION_STATES,
    TRANSACTION_TRANSITIONS,
)
from tests.conftest import (
    add_specification,
    make_demand,
    make_material,
    make_opportunity,
    make_organization,
    make_proposal,
    make_transaction,
)

API = "/api/v1"

ADMIN = {"X-Actor-Id": "demo-platform-admin"}
COORDINATOR = {"X-Actor-Id": "aurelia-coordinator"}
REVIEWER = {"X-Actor-Id": "meridian-reviewer"}
APPROVER = {"X-Actor-Id": "helios-approver"}
AUDITOR = {"X-Actor-Id": "northgate-auditor"}
VIEWER = {"X-Actor-Id": "readonly-observer"}


def _cluster(db: Session, *, supplier_slug: str = "aurelia-chemicals", consumer_slug: str = "meridian-steel"):
    supplier = make_organization(db, name="Aurelia Chemicals", slug=supplier_slug)
    consumer = make_organization(db, name="Meridian Steel", slug=consumer_slug)
    material = make_material(db, supplier, name="Spent pickling acid", quantity_available=200)
    add_specification(db, material)
    demand = make_demand(db, consumer, title="Recovered acid for pickling line")
    opportunity = make_opportunity(
        db, material, demand, supplier, consumer, match_quantity=100
    )
    db.commit()
    return SimpleNamespace(
        supplier=supplier,
        consumer=consumer,
        material=material,
        demand=demand,
        opportunity=opportunity,
    )


def _create(client: TestClient, opportunity_id: UUID, *, quantity: float = 100, headers=None):
    return client.post(
        f"{API}/proposals",
        json={"opportunity_id": str(opportunity_id), "quantity": quantity},
        headers=headers or ADMIN,
    )


def _action(
    client: TestClient, proposal_id: str, action: str, *, headers=None, **body
) -> object:
    return client.post(
        f"{API}/proposals/{proposal_id}/{action}", json=body, headers=headers or ADMIN
    )


def _approved(client: TestClient, opportunity_id: UUID) -> str:
    created = _create(client, opportunity_id)
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    assert _action(client, proposal_id, "submit", headers=COORDINATOR).status_code == 200
    assert _action(client, proposal_id, "review", headers=REVIEWER).status_code == 200
    approved = _action(
        client,
        proposal_id,
        "approve",
        headers=APPROVER,
        approval_reference="DEMO-APPR-9001",
        evidence={"decision": "approved", "note": "test approval"},
    )
    assert approved.status_code == 200, approved.text
    return proposal_id


def _transaction(client: TestClient, proposal_id: str, *, headers=None) -> dict:
    response = client.post(
        f"{API}/transactions",
        json={"proposal_id": proposal_id, "carrier_name": "Test Haulage"},
        headers=headers or COORDINATOR,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _transfer(client: TestClient, transaction_id: str, *, quantity: float = 100, headers=None):
    return client.post(
        f"{API}/transactions/{transaction_id}/record-transfer",
        json={
            "transferred_quantity": quantity,
            "transfer_reference": "WB-2026-0001",
            "material_identification": "Batch A-17",
        },
        headers=headers or COORDINATOR,
    )


def _verify(client: TestClient, transaction_id: str, *, quantity: float = 98, headers=None):
    return client.post(
        f"{API}/transactions/{transaction_id}/verify",
        json={
            "verified_quantity": quantity,
            "verification_method": "weighbridge_ticket",
            "evidence_reference": "WB-2026-0001-VERIFIED",
            "evidence": {"ticket_mass_kg": quantity * 1000},
        },
        headers=headers or AUDITOR,
    )


# ---------------------------------------------------------------------------
# state machine definition
# ---------------------------------------------------------------------------


def test_canonical_proposal_path_is_defined() -> None:
    edges = {(rule.from_state, rule.to_state) for rule in PROPOSAL_TRANSITIONS}
    expected = [
        (ProposalStatus.DRAFT, ProposalStatus.SUBMITTED),
        (ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW),
        (ProposalStatus.UNDER_REVIEW, ProposalStatus.APPROVED),
        (ProposalStatus.APPROVED, ProposalStatus.IN_PROGRESS),
        (ProposalStatus.IN_PROGRESS, ProposalStatus.COMPLETED),
    ]
    for edge in expected:
        assert edge in edges
    for state in TERMINAL_PROPOSAL_STATES:
        assert not [rule for rule in PROPOSAL_TRANSITIONS if rule.from_state == state]


def test_terminal_transaction_states_have_no_outgoing_rules() -> None:
    for state in TERMINAL_TRANSACTION_STATES:
        assert not [rule for rule in TRANSACTION_TRANSITIONS if rule.from_state == state]


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_full_lifecycle_reaches_verified_and_completed(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)

    transaction = _transaction(client, proposal_id)
    assert transaction["status"] == "created"

    # Creating the transaction moves the proposal into execution.
    detail = client.get(f"{API}/proposals/{proposal_id}", headers=ADMIN).json()
    assert detail["status"] == "in_progress"
    assert detail["started_at"] is not None

    transferred = _transfer(client, transaction["id"])
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["status"] == "transferred"
    assert transferred.json()["transferred_quantity"] == 100.0
    assert transferred.json()["transfer_recorded_by"] == "aurelia-coordinator"

    verified = _verify(client, transaction["id"])
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["status"] == "verified"
    assert body["verified_quantity"] == 98.0
    assert body["verified_by"] == "northgate-auditor"
    assert body["verified_at"] is not None
    assert body["evidence"]["verification_reference"] == "WB-2026-0001-VERIFIED"

    completed = client.get(f"{API}/proposals/{proposal_id}", headers=ADMIN).json()
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None

    actions = {
        row["action"] for row in completed["history"]
    }
    assert {"submit", "review", "approve", "start", "complete"} <= actions
    assert completed["transaction"]["status"] == "verified"
    assert {row["action"] for row in completed["transaction"]["history"]} == {
        "record_transfer",
        "verify",
    }

    ledger = client.get(f"{API}/ledger", headers=ADMIN).json()
    assert ledger["verified_recovered"] == [{"unit": "tonne", "quantity": 98.0}]
    stages = {stage["stage"]: stage for stage in ledger["stages"]}
    assert stages["verified"]["count"] == 1
    assert stages["verified"]["counted_as_impact"] is True
    # The same record is not counted anywhere else.
    assert sum(stage["count"] for stage in ledger["stages"]) == 1


def test_proposal_detail_exposes_available_actions_per_actor(
    client: TestClient, db: Session
) -> None:
    cluster = _cluster(db)
    created = _create(client, cluster.opportunity.id)
    proposal_id = created.json()["id"]

    as_coordinator = client.get(f"{API}/proposals/{proposal_id}", headers=COORDINATOR).json()
    assert "submit" in as_coordinator["available_actions"]

    as_viewer = client.get(f"{API}/proposals/{proposal_id}", headers=VIEWER).json()
    assert as_viewer["available_actions"] == []


# ---------------------------------------------------------------------------
# invalid transitions
# ---------------------------------------------------------------------------


def test_approving_a_draft_is_rejected_with_allowed_actions(
    client: TestClient, db: Session
) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]

    response = _action(
        client, proposal_id, "approve", headers=APPROVER, approval_reference="DEMO-1"
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_transition"
    assert error["details"]["status"] == "draft"
    assert "submit" in error["details"]["allowed_actions"]


def test_duplicate_submission_is_rejected(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]
    assert _action(client, proposal_id, "submit", headers=COORDINATOR).status_code == 200

    duplicate = _action(client, proposal_id, "submit", headers=COORDINATOR)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "invalid_transition"


def test_terminal_state_cannot_be_reopened(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]
    assert _action(client, proposal_id, "withdraw", headers=COORDINATOR).status_code == 200

    reopened = _action(client, proposal_id, "submit", headers=COORDINATOR)
    assert reopened.status_code == 409
    assert reopened.json()["error"]["details"]["status"] == "withdrawn"


def test_generic_patch_status_update_is_not_exposed(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]

    for method in ("patch", "put"):
        response = getattr(client, method)(
            f"{API}/proposals/{proposal_id}", json={"status": "approved"}, headers=ADMIN
        )
        assert response.status_code in {404, 405}


# ---------------------------------------------------------------------------
# evidence requirements
# ---------------------------------------------------------------------------


def test_approval_requires_evidence_reference(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]
    _action(client, proposal_id, "submit", headers=COORDINATOR)
    _action(client, proposal_id, "review", headers=REVIEWER)

    response = _action(client, proposal_id, "approve", headers=APPROVER)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "evidence_required"

    db.expire_all()
    proposal = db.get(RecoveryProposal, UUID(proposal_id))
    assert proposal is not None and proposal.status == ProposalStatus.UNDER_REVIEW


def test_rejection_requires_reason(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]
    _action(client, proposal_id, "submit", headers=COORDINATOR)

    response = _action(client, proposal_id, "reject", headers=REVIEWER)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "evidence_required"

    rejected = _action(
        client, proposal_id, "reject", headers=REVIEWER, reason="Contamination too high"
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Contamination too high"
    assert rejected.json()["rejected_by"] == "meridian-reviewer"


def test_verification_requires_transfer_evidence(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)

    # Nothing transferred yet: verification has no evidence to stand on.
    early = _verify(client, transaction["id"])
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "invalid_transition"

    _transfer(client, transaction["id"])
    missing_reference = client.post(
        f"{API}/transactions/{transaction['id']}/verify",
        json={
            "verified_quantity": 90,
            "verification_method": "weighbridge_ticket",
            "evidence_reference": "",
        },
        headers=AUDITOR,
    )
    assert missing_reference.status_code == 422
    assert missing_reference.json()["error"]["code"] == "validation_error"


def test_zero_and_negative_quantities_are_rejected(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    for quantity in (0, -5):
        response = client.post(
            f"{API}/proposals",
            json={"opportunity_id": str(cluster.opportunity.id), "quantity": quantity},
            headers=ADMIN,
        )
        assert response.status_code == 422

    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    zero_transfer = _transfer(client, transaction["id"], quantity=0)
    assert zero_transfer.status_code == 422

    _transfer(client, transaction["id"])
    zero_verify = _verify(client, transaction["id"], quantity=0)
    assert zero_verify.status_code == 422


def test_verified_quantity_cannot_exceed_transferred_quantity(
    client: TestClient, db: Session
) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    _transfer(client, transaction["id"], quantity=90)

    response = _verify(client, transaction["id"], quantity=95)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "quantity_exceeds_transfer"


# ---------------------------------------------------------------------------
# authorization
# ---------------------------------------------------------------------------


def test_viewer_cannot_submit_and_attempt_is_audited(
    client: TestClient, db: Session
) -> None:
    cluster = _cluster(db)
    proposal_id = _create(client, cluster.opportunity.id).json()["id"]

    response = _action(client, proposal_id, "submit", headers=VIEWER)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    db.expire_all()
    denied = db.scalars(
        select(AuditEvent).where(AuditEvent.event_type == "authorization.denied")
    ).all()
    assert len(denied) == 1
    assert denied[0].payload["operation"] == "submit"
    assert denied[0].actor_id == "readonly-observer"

    proposal = db.get(RecoveryProposal, UUID(proposal_id))
    assert proposal is not None and proposal.status == ProposalStatus.DRAFT


def test_coordinator_cannot_act_on_unrelated_records(client: TestClient, db: Session) -> None:
    cluster = _cluster(
        db, supplier_slug="circulus-glass", consumer_slug="limburg-aggregates"
    )
    created = _create(client, cluster.opportunity.id, headers=ADMIN)
    assert created.status_code == 201
    proposal_id = created.json()["id"]

    hidden = client.get(f"{API}/proposals/{proposal_id}", headers=COORDINATOR)
    assert hidden.status_code == 404

    denied = _action(client, proposal_id, "submit", headers=COORDINATOR)
    assert denied.status_code == 404


def test_coordinator_list_is_scoped_to_own_organisation(
    client: TestClient, db: Session
) -> None:
    own = _cluster(db)
    other = _cluster(db, supplier_slug="solvane-polymers", consumer_slug="helios-cement")
    mine = _create(client, own.opportunity.id).json()["id"]
    theirs = _create(client, other.opportunity.id, headers=ADMIN).json()["id"]

    body = client.get(f"{API}/proposals", headers=COORDINATOR).json()
    ids = {item["id"] for item in body["items"]}
    assert mine in ids
    assert theirs not in ids

    filtered = client.get(
        f"{API}/proposals", params={"organization_id": str(other.supplier.id)}, headers=COORDINATOR
    )
    assert filtered.status_code == 403


def test_recorder_cannot_verify_own_transfer(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    # The platform admin records the transfer, then tries to verify it.
    assert _transfer(client, transaction["id"], headers=ADMIN).status_code == 200

    response = _verify(client, transaction["id"], headers=ADMIN)
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "segregation_of_duties"

    db.expire_all()
    stored = db.get(RecoveryTransaction, UUID(transaction["id"]))
    assert stored is not None and stored.status == TransactionStatus.TRANSFERRED


def test_submitter_cannot_approve_own_proposal(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    created = _create(client, cluster.opportunity.id, headers=ADMIN)
    proposal_id = created.json()["id"]
    # Admin submits, then tries to approve as admin: blocked by segregation of duties.
    assert _action(client, proposal_id, "submit", headers=ADMIN).status_code == 200
    assert _action(client, proposal_id, "review", headers=ADMIN).status_code == 200

    response = _action(
        client, proposal_id, "approve", headers=ADMIN, approval_reference="DEMO-APPR-77"
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "segregation_of_duties"

    allowed = _action(
        client, proposal_id, "approve", headers=APPROVER, approval_reference="DEMO-APPR-77"
    )
    assert allowed.status_code == 200


def test_unknown_actor_is_unauthenticated(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    response = client.get(
        f"{API}/proposals", headers={"X-Actor-Id": "not-a-real-actor"}
    )
    assert response.status_code == 401


def test_audit_journal_is_read_only(client: TestClient, db: Session) -> None:
    for method in ("post", "patch", "put"):
        response = getattr(client, method)(f"{API}/audit", json={}, headers=ADMIN)
        assert response.status_code in {404, 405}
    assert client.delete(f"{API}/audit", headers=ADMIN).status_code in {404, 405}


def test_audit_timeline_lists_entity_events(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)

    timeline = client.get(
        f"{API}/audit/proposal/{proposal_id}", headers=ADMIN
    ).json()
    actions = [row["new_state"] for row in timeline]
    assert actions == ["draft", "submitted", "under_review", "approved"]
    assert all(row["actor_id"] for row in timeline)

    filtered = client.get(
        f"{API}/audit", params={"entity_type": "proposal", "entity_id": proposal_id}, headers=ADMIN
    ).json()
    assert filtered["total"] == 4


# ---------------------------------------------------------------------------
# duplicates, concurrency, rollback
# ---------------------------------------------------------------------------


def test_transaction_is_unique_per_proposal(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    _transaction(client, proposal_id)

    duplicate = client.post(
        f"{API}/transactions",
        json={"proposal_id": proposal_id},
        headers=COORDINATOR,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"

    db.expire_all()
    count = len(
        db.scalars(
            select(RecoveryTransaction).where(
                RecoveryTransaction.proposal_id == UUID(proposal_id)
            )
        ).all()
    )
    assert count == 1


def test_transaction_requires_approved_proposal(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    created = _create(client, cluster.opportunity.id)
    response = client.post(
        f"{API}/transactions",
        json={"proposal_id": created.json()["id"]},
        headers=COORDINATOR,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


def test_stale_version_is_rejected(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    created = _create(client, cluster.opportunity.id)
    proposal_id = created.json()["id"]
    version = created.json()["version"]

    assert _action(client, proposal_id, "submit", headers=COORDINATOR).status_code == 200

    stale = _action(
        client, proposal_id, "review", headers=REVIEWER, expected_version=version
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert stale.json()["error"]["details"]["current_version"] == version + 1


def test_failed_audit_write_rolls_back_the_transition(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.workflow import WorkflowService

    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    _transfer(client, transaction["id"])

    def explode(*args, **kwargs):
        raise RuntimeError("audit journal unavailable")

    monkeypatch.setattr(audit, "record_event", explode)
    from dataclasses import replace
    from tests.conftest import _legacy_actor_for_header

    actor = _legacy_actor_for_header(db, AUDITOR["X-Actor-Id"])
    assert actor is not None
    actor = replace(actor, actor_id=AUDITOR["X-Actor-Id"])
    service = WorkflowService(db, actor)
    with pytest.raises(RuntimeError):
        service.verify_transaction(
            UUID(transaction["id"]),
            verified_quantity=90,
            verification_method=VerificationMethod.WEIGHBRIDGE_TICKET,
            evidence_reference="WB-ROLLBACK-1",
        )

    # A request-scoped session that never commits discards the whole unit of work.
    db.rollback()
    db.expire_all()
    stored = db.get(RecoveryTransaction, UUID(transaction["id"]))
    assert stored is not None
    assert stored.status == TransactionStatus.TRANSFERRED
    assert stored.verified_quantity is None
    assert not db.scalars(
        select(StatusTransition).where(
            StatusTransition.entity_type == TransitionEntity.TRANSACTION,
            StatusTransition.entity_id == UUID(transaction["id"]),
            StatusTransition.action == "verify",
        )
    ).all()


# ---------------------------------------------------------------------------
# accounting integrity
# ---------------------------------------------------------------------------


def test_unverified_transfer_never_counts_as_recovered(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    _transfer(client, transaction["id"], quantity=100)

    ledger = client.get(f"{API}/ledger", headers=ADMIN).json()
    assert ledger["verified_recovered"] == []
    stages = {stage["stage"]: stage for stage in ledger["stages"]}
    assert stages["completed_unverified"]["count"] == 1
    assert stages["completed_unverified"]["counted_as_impact"] is False
    assert stages["verified"]["count"] == 0
    pipeline = {item["unit"]: item["quantity"] for item in ledger["proposed_pipeline"]}
    assert pipeline["tonne"] == 100.0


def test_verification_does_not_double_count(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    _transfer(client, transaction["id"], quantity=100)
    assert _verify(client, transaction["id"], quantity=80).status_code == 200

    ledger = client.get(f"{API}/ledger", headers=ADMIN).json()
    assert ledger["verified_recovered"] == [{"unit": "tonne", "quantity": 80.0}]
    pipeline = {item["unit"]: item["quantity"] for item in ledger["proposed_pipeline"]}
    assert "tonne" not in pipeline or pipeline["tonne"] == 0.0
    # Verified quantities are never counted again as pipeline.
    assert sum(stage["count"] for stage in ledger["stages"]) == 1


def test_cancelling_a_transaction_releases_the_proposal(
    client: TestClient, db: Session
) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)

    cancelled = client.post(
        f"{API}/transactions/{transaction['id']}/cancel",
        json={"reason": "Carrier cancelled the collection"},
        headers=COORDINATOR,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    detail = client.get(f"{API}/proposals/{proposal_id}", headers=ADMIN).json()
    assert detail["status"] == "cancelled"
    assert "Carrier cancelled" in detail["cancellation_reason"]

    ledger = client.get(f"{API}/ledger", headers=ADMIN).json()
    stages = {stage["stage"]: stage for stage in ledger["stages"]}
    assert stages["rejected_cancelled"]["count"] == 1
    assert ledger["verified_recovered"] == []


def test_rejecting_a_transaction_fails_the_proposal(client: TestClient, db: Session) -> None:
    cluster = _cluster(db)
    proposal_id = _approved(client, cluster.opportunity.id)
    transaction = _transaction(client, proposal_id)
    _transfer(client, transaction["id"])

    rejected = client.post(
        f"{API}/transactions/{transaction['id']}/reject",
        json={"reason": "Weighbridge ticket does not match the load"},
        headers=AUDITOR,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    detail = client.get(f"{API}/proposals/{proposal_id}", headers=ADMIN).json()
    assert detail["status"] == "failed"
    assert "Weighbridge ticket" in detail["failure_reason"]


def test_database_blocks_verification_without_verifying_actor(db: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    cluster = _cluster(db)
    proposal = make_proposal(
        db, cluster.opportunity, status=ProposalStatus.APPROVED
    )
    proposal_id = proposal.id
    db.commit()

    with pytest.raises(IntegrityError):
        make_transaction(
            db,
            proposal,
            status=TransactionStatus.VERIFIED,
            verified_quantity=10,
            verified_by=None,
        )
        db.commit()
    db.rollback()
    assert db.get(RecoveryProposal, proposal_id) is not None


def test_database_blocks_approval_without_evidence(db: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    cluster = _cluster(db)
    db.commit()
    with pytest.raises(IntegrityError):
        make_proposal(
            db,
            cluster.opportunity,
            status=ProposalStatus.APPROVED,
            approved_at=None,
            approved_by=None,
            approval_reference=None,
        )
        db.commit()
    db.rollback()
