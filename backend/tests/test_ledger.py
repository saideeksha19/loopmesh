"""Impact ledger accounting tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import ProposalStatus, TransactionStatus
from tests.conftest import (
    add_specification,
    make_demand,
    make_material,
    make_opportunity,
    make_organization,
    make_proposal,
    make_transaction,
)

PLATFORM = {"X-Actor-Id": "demo-platform-admin"}


def _verified_and_proposed(db: Session):
    supplier = make_organization(db, name="Ledger Supplier", slug="ledger-supplier")
    consumer = make_organization(db, name="Ledger Consumer", slug="ledger-consumer")

    verified_material = make_material(db, supplier, name="Verified stream", quantity_available=100)
    add_specification(db, verified_material)
    verified_demand = make_demand(db, consumer, title="Verified demand")
    verified_opportunity = make_opportunity(
        db, verified_material, verified_demand, supplier, consumer
    )
    verified_proposal = make_proposal(
        db, verified_opportunity, quantity=100, status=ProposalStatus.APPROVED
    )
    make_transaction(
        db,
        verified_proposal,
        status=TransactionStatus.VERIFIED,
        verified_quantity=90,
    )

    pending_material = make_material(db, supplier, name="Pending stream", quantity_available=80)
    add_specification(db, pending_material)
    pending_demand = make_demand(db, consumer, title="Pending demand")
    pending_opportunity = make_opportunity(db, pending_material, pending_demand, supplier, consumer)
    make_proposal(db, pending_opportunity, quantity=80, status=ProposalStatus.SUBMITTED)

    db.commit()


def test_verified_quantity_is_the_only_impact_metric(client: TestClient, db: Session) -> None:
    _verified_and_proposed(db)
    response = client.get("/api/v1/ledger", headers=PLATFORM)
    assert response.status_code == 200
    body = response.json()

    assert body["verified_recovered"] == [{"unit": "tonne", "quantity": 90.0}]
    states = {state["state"]: state for state in body["states"]}
    assert states["verified"]["count"] == 1
    assert states["verified"]["counted_as_impact"] is True
    assert states["proposed"]["count"] == 1
    assert states["proposed"]["counted_as_impact"] is False

    verified_entry = next(entry for entry in body["entries"] if entry["is_verified"])
    assert verified_entry["verified_quantity"] == 90.0
    assert verified_entry["verification_method"] == "weighbridge_ticket"
    assert verified_entry["material_name"] == "Verified stream"


def test_proposed_pipeline_is_reported_separately(client: TestClient, db: Session) -> None:
    _verified_and_proposed(db)
    body = client.get("/api/v1/ledger", headers=PLATFORM).json()
    # Pipeline excludes the verified entry entirely: 80 t proposed is not impact.
    pipeline = {item["unit"]: item["quantity"] for item in body["proposed_pipeline"]}
    assert pipeline["tonne"] == 80.0

    states = {state["state"]: state for state in body["states"]}
    assert states["accepted"]["count"] == 0
    assert states["transported"]["count"] == 0
    assert "Only quantities from verified transactions" in body["accounting_rule"]


def test_database_rejects_verified_without_evidence(db: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    supplier = make_organization(db)
    consumer = make_organization(db)
    material = make_material(db, supplier)
    add_specification(db, material)
    demand = make_demand(db, consumer)
    opportunity = make_opportunity(db, material, demand, supplier, consumer)
    proposal = make_proposal(db, opportunity)
    db.commit()

    try:
        make_transaction(db, proposal, status=TransactionStatus.VERIFIED, verified_quantity=None)
        db.commit()
    except IntegrityError:
        db.rollback()
    else:  # pragma: no cover - the constraint must always fire
        raise AssertionError("verified transaction without evidence was accepted")
