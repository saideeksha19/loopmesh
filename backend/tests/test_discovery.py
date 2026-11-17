"""Deterministic discovery tests."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import OpportunityStatus
from app.db.models.opportunity import RecoveryOpportunity
from app.services.discovery import discover_opportunities
from tests.conftest import (
    TODAY,
    add_specification,
    make_demand,
    make_material,
    make_organization,
)


def _pair(db: Session, **material_overrides):
    supplier = make_organization(db, name="Supplier Co", slug="supplier-co")
    consumer = make_organization(db, name="Consumer Co", slug="consumer-co")
    material = make_material(
        db,
        supplier,
        quantity_available=150,
        availability_end=TODAY + timedelta(days=200),
        **material_overrides,
    )
    add_specification(db, material, purity=94.0, contamination=0.8, moisture=2.0)
    demand = make_demand(
        db,
        consumer,
        min_quantity=50,
        max_quantity=200,
        min_purity_pct=90,
        max_contamination_pct=2,
        max_moisture_pct=5,
    )
    db.commit()
    return supplier, consumer, material, demand


def test_discovery_creates_one_explainable_opportunity(db: Session) -> None:
    _, _, material, demand = _pair(db)
    summary = discover_opportunities(db, min_score=0)
    assert summary.opportunities_created == 1
    assert summary.pairs_evaluated == 1

    opportunity = db.scalar(select(RecoveryOpportunity))
    assert opportunity is not None
    assert opportunity.material_id == material.id
    assert opportunity.resource_demand_id == demand.id
    assert opportunity.compatibility_status.value == "compatible"
    assert opportunity.compatibility_score == 100
    assert opportunity.match_quantity == 150
    assert {rule["rule_id"] for rule in opportunity.compatibility_rules} >= {
        "CAT-01",
        "HAZ-01",
        "PUR-01",
        "QTY-01",
    }
    assert opportunity.is_demo is False


def test_discovery_is_idempotent(db: Session) -> None:
    _pair(db)
    discover_opportunities(db, min_score=0)
    second = discover_opportunities(db, min_score=0)
    assert second.opportunities_created == 0
    assert second.opportunities_updated == 1
    assert db.scalar(select(func.count(RecoveryOpportunity.id))) == 1


def test_discovery_excludes_self_matches(db: Session) -> None:
    organization = make_organization(db)
    material = make_material(db, organization, quantity_available=500)
    add_specification(db, material)
    make_demand(db, organization, min_quantity=10)
    db.commit()

    summary = discover_opportunities(db, min_score=0)
    assert summary.pairs_evaluated == 0
    assert summary.opportunities_created == 0


def test_discovery_preserves_converted_opportunities(db: Session) -> None:
    _, _, _, _ = _pair(db)
    discover_opportunities(db, min_score=0)
    opportunity = db.scalar(select(RecoveryOpportunity))
    assert opportunity is not None
    opportunity.status = OpportunityStatus.CONVERTED
    opportunity.compatibility_score = 12
    db.commit()

    summary = discover_opportunities(db, min_score=0)
    assert summary.skipped_frozen == 1
    assert summary.opportunities_updated == 0
    refreshed = db.get(RecoveryOpportunity, opportunity.id)
    assert refreshed is not None
    assert refreshed.compatibility_score == 12


def test_discovery_skips_incompatible_and_low_scores(db: Session) -> None:
    supplier = make_organization(db)
    consumer = make_organization(db)
    material = make_material(db, supplier, quantity_available=500)
    add_specification(db, material, purity=40.0)
    make_demand(db, consumer, min_purity_pct=95)
    db.commit()

    summary = discover_opportunities(db, min_score=0)
    assert summary.skipped_incompatible == 1
    assert summary.opportunities_created == 0


PLATFORM = {"X-Actor-Id": "demo-platform-admin"}


def test_discovery_endpoint_returns_run_summary(client: TestClient, db: Session) -> None:
    _pair(db)
    response = client.post(
        "/api/v1/opportunities/discovery", json={"min_score": 0}, headers=PLATFORM
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["opportunities_created"] == 1
    assert isinstance(body["created_ids"], list)
    assert len(body["created_ids"]) == 1
