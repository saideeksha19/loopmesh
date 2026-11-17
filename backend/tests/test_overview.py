"""Overview dashboard aggregate tests."""

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


def test_overview_aggregates_and_activity(client: TestClient, db: Session) -> None:
    supplier = make_organization(db, name="Overview Supplier", slug="overview-supplier")
    consumer = make_organization(db, name="Overview Consumer", slug="overview-consumer")

    material = make_material(
        db, supplier, name="Overview stream", quantity_available=300, is_demo=True
    )
    add_specification(db, material)
    demand = make_demand(db, consumer, title="Overview demand", min_quantity=10)
    opportunity = make_opportunity(db, material, demand, supplier, consumer)
    proposal = make_proposal(db, opportunity, quantity=100, status=ProposalStatus.APPROVED)
    make_transaction(db, proposal, status=TransactionStatus.VERIFIED, verified_quantity=75)
    db.commit()

    response = client.get("/api/v1/overview", headers=PLATFORM)
    assert response.status_code == 200
    body = response.json()

    assert body["organizations"]["total"] == 2
    assert body["organizations"]["suppliers"] == 1
    assert body["organizations"]["consumers"] == 1
    assert body["materials"]["total"] == 1
    assert body["materials"]["available"] == 1
    assert body["opportunities"]["total"] == 1
    assert body["opportunities"]["pending_proposals"] == 0
    assert body["ledger"]["verified_recovered"] == [{"unit": "tonne", "quantity": 75.0}]
    assert body["network"]["confirmed_links"] == 1
    assert body["data_mode"] == "demo"
    assert body["contains_demo_data"] is True


def test_activity_endpoint_returns_journal_entries(client: TestClient, db: Session) -> None:
    response = client.get("/api/v1/overview/activity", headers=PLATFORM)
    assert response.status_code == 200
    assert response.json() == []
