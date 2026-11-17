"""Resource network graph tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import MaterialCategory, ProposalStatus, TransactionStatus
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


def test_network_marks_confirmed_only_after_verification(client: TestClient, db: Session) -> None:
    supplier = make_organization(db, name="Network Supplier", slug="network-supplier")
    consumer = make_organization(db, name="Network Consumer", slug="network-consumer")

    confirmed_material = make_material(db, supplier, name="Confirmed stream")
    add_specification(db, confirmed_material)
    confirmed_demand = make_demand(db, consumer, title="Confirmed demand")
    confirmed_opportunity = make_opportunity(
        db, confirmed_material, confirmed_demand, supplier, consumer
    )
    confirmed_proposal = make_proposal(
        db, confirmed_opportunity, status=ProposalStatus.APPROVED
    )
    make_transaction(
        db, confirmed_proposal, status=TransactionStatus.VERIFIED, verified_quantity=95
    )

    # A different material category produces a separate lane, so the graph can
    # show a modelled link that has no verified transfer yet.
    potential_material = make_material(
        db, supplier, name="Potential stream", category=MaterialCategory.POLYMERS
    )
    add_specification(db, potential_material)
    potential_demand = make_demand(
        db, consumer, title="Potential demand", category=MaterialCategory.POLYMERS
    )
    make_opportunity(db, potential_material, potential_demand, supplier, consumer)
    db.commit()

    response = client.get("/api/v1/network", headers=PLATFORM)
    assert response.status_code == 200
    body = response.json()

    statuses = {edge["status"] for edge in body["edges"]}
    assert statuses == {"confirmed", "potential"}
    assert body["summary"]["confirmed_links"] == 1
    assert body["summary"]["potential_links"] == 2
    assert body["summary"]["organizations"] == 2

    confirmed = next(edge for edge in body["edges"] if edge["status"] == "confirmed")
    assert confirmed["confirmed_transactions"] == 1
    assert confirmed["source"] == str(supplier.id)
    assert confirmed["target"] == str(consumer.id)

    node = next(node for node in body["nodes"] if node["id"] == str(supplier.id))
    assert node["outbound_links"] == 2
    assert node["material_streams"] == 2


def test_network_reports_unlinked_organizations(client: TestClient, db: Session) -> None:
    make_organization(db, name="Isolated Co", slug="isolated-co")
    db.commit()
    body = client.get("/api/v1/network", headers=PLATFORM).json()
    assert body["summary"]["unlinked_organizations"] == 1
    assert body["edges"] == []
