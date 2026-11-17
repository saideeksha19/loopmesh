"""Deterministic compatibility engine tests (no API, no database)."""

from __future__ import annotations

from uuid import uuid4

from app.db.enums import (
    CompatibilityStatus,
    MaterialCategory,
    MaterialCondition,
    MaterialStatus,
    MaterialUnit,
)
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material, MaterialSpecification
from app.services.compatibility import evaluate_compatibility


def build_material(**overrides) -> Material:
    values = {
        "organization_id": uuid4(),
        "reference_code": "LM-TEST",
        "name": "Test stream",
        "category": MaterialCategory.METALS,
        "quantity_available": 100.0,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "status": MaterialStatus.AVAILABLE,
        "hazard_class": "non_hazardous",
        "is_demo": False,
    }
    values.update(overrides)
    return Material(**values)


def build_demand(**overrides) -> ResourceDemand:
    values = {
        "organization_id": uuid4(),
        "title": "Test demand",
        "category": MaterialCategory.METALS,
        "min_quantity": 10.0,
        "max_quantity": 500.0,
        "unit": MaterialUnit.TONNE,
        "prohibited_hazards": [],
        "max_distance_km": 500.0,
        "currency": "EUR",
        "is_demo": False,
    }
    values.update(overrides)
    return ResourceDemand(**values)


def attach_spec(material: Material, **overrides) -> Material:
    values = {"purity_pct": 95.0, "contamination_pct": 0.5, "moisture_pct": 1.0}
    values.update(overrides)
    material.specification = MaterialSpecification(
        material_id=material.id if material.id else uuid4(),
        composition=[],
        contaminants={},
        **values,
    )
    return material


def test_all_rules_pass_is_compatible_with_full_score() -> None:
    material = attach_spec(build_material())
    demand = build_demand()
    assessment = evaluate_compatibility(material, demand, distance_km=42.0)
    assert assessment.status == CompatibilityStatus.COMPATIBLE
    assert assessment.score == 100
    assert assessment.blocking_rule_ids == ()
    assert len(assessment.rules) == 9


def test_prohibited_hazard_blocks_the_match() -> None:
    material = attach_spec(build_material(hazard_class="corrosive"))
    demand = build_demand(prohibited_hazards=["corrosive"])
    assessment = evaluate_compatibility(material, demand, distance_km=42.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    assert "HAZ-01" in assessment.blocking_rule_ids
    hazard_rule = next(rule for rule in assessment.rules if rule.rule_id == "HAZ-01")
    assert hazard_rule.status == "fail"
    assert "prohibited" in hazard_rule.detail


def test_missing_specification_is_unverified_not_a_pass() -> None:
    material = build_material()  # no specification attached
    demand = build_demand(min_purity_pct=80, max_contamination_pct=2, max_moisture_pct=5)
    assessment = evaluate_compatibility(material, demand, distance_km=42.0)
    assert assessment.status == CompatibilityStatus.UNVERIFIED
    unknown_rule_ids = {rule.rule_id for rule in assessment.rules if rule.status == "unknown"}
    assert {"PUR-01", "CON-01", "MOI-01"} <= unknown_rule_ids


def test_purity_below_floor_is_incompatible() -> None:
    material = attach_spec(build_material(), purity_pct=72.0)
    demand = build_demand(min_purity_pct=90)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    assert "PUR-01" in assessment.blocking_rule_ids


def test_contamination_within_tolerance_is_conditional() -> None:
    material = attach_spec(build_material(), contamination_pct=2.4)
    demand = build_demand(max_contamination_pct=2.0)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.CONDITIONAL
    contamination = next(rule for rule in assessment.rules if rule.rule_id == "CON-01")
    assert contamination.status == "warning"
    assert "pre-treatment" in contamination.detail


def test_contamination_beyond_tolerance_fails() -> None:
    material = attach_spec(build_material(), contamination_pct=4.0)
    demand = build_demand(max_contamination_pct=2.0)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    assert "CON-01" in assessment.blocking_rule_ids


def test_incompatible_units_fail_rather_than_silently_convert() -> None:
    material = attach_spec(build_material(unit=MaterialUnit.CUBIC_METRE, quantity_available=900.0))
    demand = build_demand(unit=MaterialUnit.TONNE)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    quantity = next(rule for rule in assessment.rules if rule.rule_id == "QTY-01")
    assert quantity.status == "fail"
    assert "different dimensions" in quantity.detail


def test_mass_unit_conversion_is_supported() -> None:
    material = attach_spec(build_material(unit=MaterialUnit.KILOGRAM, quantity_available=50_000.0))
    demand = build_demand(unit=MaterialUnit.TONNE, min_quantity=10, max_quantity=40)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.CONDITIONAL  # partial allocation warning
    assert assessment.match_quantity == 40.0
    quantity = next(rule for rule in assessment.rules if rule.rule_id == "QTY-01")
    assert quantity.status == "warning"


def test_insufficient_quantity_is_incompatible() -> None:
    material = attach_spec(build_material(quantity_available=5.0))
    demand = build_demand(min_quantity=10.0)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    assert "QTY-01" in assessment.blocking_rule_ids


def test_transport_radius_is_enforced() -> None:
    material = attach_spec(build_material())
    demand = build_demand(max_distance_km=100)
    assessment = evaluate_compatibility(material, demand, distance_km=380.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    assert "GEO-01" in assessment.blocking_rule_ids


def test_missing_coordinates_make_transport_unknown() -> None:
    material = attach_spec(build_material())
    demand = build_demand(max_distance_km=100)
    assessment = evaluate_compatibility(material, demand, distance_km=None)
    assert assessment.status == CompatibilityStatus.UNVERIFIED
    geo = next(rule for rule in assessment.rules if rule.rule_id == "GEO-01")
    assert geo.status == "unknown"


def test_cross_category_substitution_is_conditional() -> None:
    material = attach_spec(build_material(category=MaterialCategory.GLASS))
    demand = build_demand(category=MaterialCategory.MINERALS, min_quantity=10.0)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.CONDITIONAL
    category = next(rule for rule in assessment.rules if rule.rule_id == "CAT-01")
    assert category.status == "warning"


def test_unrelated_category_is_incompatible() -> None:
    material = attach_spec(build_material(category=MaterialCategory.TEXTILES))
    demand = build_demand(category=MaterialCategory.METALS)
    assessment = evaluate_compatibility(material, demand, distance_km=10.0)
    assert assessment.status == CompatibilityStatus.INCOMPATIBLE
    assert "CAT-01" in assessment.blocking_rule_ids
