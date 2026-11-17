"""Deterministic compatibility engine.

Design rules that this module guarantees:

* **No AI verdicts.** Every outcome is produced by explicit, auditable rules
  with numeric thresholds. Gemini is never consulted here.
* **Missing evidence is not a pass.** Absent measurements produce an
  ``unknown`` result, which downgrades the overall verdict to ``unverified``.
* **No silent unit maths.** Quantities are only compared after a dimension-
  checked conversion (see :mod:`app.services.units`).
* **Explainability.** Every rule that ran is returned with the observed value,
  the requirement and a human-readable reason, so the UI can show *why*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.db.enums import (
    CompatibilityStatus,
    MaterialCategory,
    MaterialCondition,
    MaterialUnit,
)
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material
from app.services.units import conversion_factor

PASS = "pass"
WARNING = "warning"
FAIL = "fail"
UNKNOWN = "unknown"

BLOCKING = "blocking"
ADVISORY = "advisory"
EVIDENCE = "evidence"

# Which supply categories a demand category can technically absorb. Anything
# outside this map is a hard category mismatch.
CATEGORY_ACCEPTANCE: dict[MaterialCategory, frozenset[MaterialCategory]] = {
    MaterialCategory.METALS: frozenset({MaterialCategory.METALS}),
    MaterialCategory.POLYMERS: frozenset({MaterialCategory.POLYMERS}),
    # Glass cullet is a recognised cementitious/mineral feedstock substitute.
    MaterialCategory.MINERALS: frozenset({MaterialCategory.MINERALS, MaterialCategory.GLASS}),
    MaterialCategory.ORGANICS: frozenset({MaterialCategory.ORGANICS}),
    # Bio-based streams can displace fossil chemical feedstock after validation.
    MaterialCategory.CHEMICALS: frozenset({MaterialCategory.CHEMICALS, MaterialCategory.ORGANICS}),
    MaterialCategory.GLASS: frozenset({MaterialCategory.GLASS}),
    MaterialCategory.PAPER: frozenset({MaterialCategory.PAPER}),
    MaterialCategory.TEXTILES: frozenset({MaterialCategory.TEXTILES}),
    MaterialCategory.WATER: frozenset({MaterialCategory.WATER}),
    MaterialCategory.ENERGY: frozenset({MaterialCategory.ENERGY, MaterialCategory.ORGANICS}),
    MaterialCategory.OTHER: frozenset({MaterialCategory.OTHER}),
}


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Outcome of a single deterministic check."""

    rule_id: str
    label: str
    status: str
    severity: str
    detail: str
    observed: str
    required: str
    weight: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompatibilityPolicy:
    """Configurable engineering tolerances.

    These are policy knobs, not model parameters: changing them changes the
    verdict deterministically, and every verdict records which rule fired.
    """

    contamination_tolerance_ratio: float = 0.25
    moisture_hard_multiplier: float = 2.0
    weights: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.weights is None:
            object.__setattr__(
                self,
                "weights",
                {
                    "CAT-01": 20,
                    "HAZ-01": 15,
                    "PUR-01": 15,
                    "CON-01": 12,
                    "MOI-01": 6,
                    "QTY-01": 15,
                    "GEO-01": 10,
                    "TIM-01": 4,
                    "COND-01": 3,
                },
            )


DEFAULT_POLICY = CompatibilityPolicy()

RULE_CATALOG: tuple[dict[str, str], ...] = (
    {"rule_id": "CAT-01", "label": "Material category acceptance", "type": "engineering"},
    {"rule_id": "HAZ-01", "label": "Hazard class prohibition", "type": "regulatory"},
    {"rule_id": "PUR-01", "label": "Minimum purity", "type": "engineering"},
    {"rule_id": "CON-01", "label": "Maximum contamination", "type": "engineering"},
    {"rule_id": "MOI-01", "label": "Maximum moisture", "type": "engineering"},
    {"rule_id": "QTY-01", "label": "Quantity sufficiency", "type": "logistics"},
    {"rule_id": "GEO-01", "label": "Transport radius", "type": "logistics"},
    {"rule_id": "TIM-01", "label": "Availability window overlap", "type": "logistics"},
    {"rule_id": "COND-01", "label": "Material condition suitability", "type": "engineering"},
)


@dataclass(frozen=True, slots=True)
class CompatibilityAssessment:
    status: CompatibilityStatus
    score: int
    rules: tuple[RuleResult, ...]
    match_quantity: float
    unit: MaterialUnit
    distance_km: float | None
    blocking_rule_ids: tuple[str, ...]

    def rules_as_dicts(self) -> list[dict[str, Any]]:
        return [rule.as_dict() for rule in self.rules]

    @property
    def matched(self) -> bool:
        return self.status in {CompatibilityStatus.COMPATIBLE, CompatibilityStatus.CONDITIONAL}


def _num(value: Any) -> float | None:
    """Normalise Numeric/Decimal/str values coming out of the database."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _fmt(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "not declared"
    return f"{value:,.2f}{suffix}"


def _status_for(rules: list[RuleResult]) -> CompatibilityStatus:
    if any(rule.status == FAIL and rule.severity == BLOCKING for rule in rules):
        return CompatibilityStatus.INCOMPATIBLE
    if any(rule.status == UNKNOWN for rule in rules):
        return CompatibilityStatus.UNVERIFIED
    if any(rule.status == WARNING for rule in rules):
        return CompatibilityStatus.CONDITIONAL
    return CompatibilityStatus.COMPATIBLE


def _score_for(rules: list[RuleResult], weights: dict[str, int]) -> int:
    credit = {PASS: 1.0, WARNING: 0.5, UNKNOWN: 0.4, FAIL: 0.0}
    total_weight = sum(weights.get(rule.rule_id, rule.weight) for rule in rules)
    if total_weight == 0:  # pragma: no cover - defensive
        return 0
    earned = sum(
        weights.get(rule.rule_id, rule.weight) * credit.get(rule.status, 0.0) for rule in rules
    )
    return int(round(100 * earned / total_weight))


def evaluate_compatibility(
    material: Material,
    demand: ResourceDemand,
    *,
    distance_km: float | None = None,
    policy: CompatibilityPolicy | None = None,
) -> CompatibilityAssessment:
    """Run every deterministic rule for one supply/demand pair."""
    policy = policy or DEFAULT_POLICY
    weights = policy.weights
    spec = material.specification
    rules: list[RuleResult] = []

    # --- CAT-01: category acceptance ---------------------------------------
    accepted = CATEGORY_ACCEPTANCE.get(demand.category, frozenset({demand.category}))
    if material.category == demand.category:
        cat_status, cat_detail = PASS, (
            f"{material.category.value} supply matches the required {demand.category.value} category."
        )
    elif material.category in accepted:
        cat_status, cat_detail = WARNING, (
            f"{material.category.value} is an accepted substitute for {demand.category.value}; "
            "process validation is required before use."
        )
    else:
        cat_status, cat_detail = FAIL, (
            f"{material.category.value} supply is outside the accepted categories for a "
            f"{demand.category.value} demand."
        )
    rules.append(
        RuleResult(
            "CAT-01",
            "Material category acceptance",
            cat_status,
            BLOCKING,
            cat_detail,
            material.category.value,
            demand.category.value,
            weights["CAT-01"],
        )
    )

    # --- HAZ-01: hazard prohibition ----------------------------------------
    hazard = (material.hazard_class or "").strip().lower()
    prohibited = {str(item).strip().lower() for item in (demand.prohibited_hazards or [])}
    if not hazard or hazard == "unknown":
        rules.append(
            RuleResult(
                "HAZ-01",
                "Hazard class prohibition",
                UNKNOWN,
                BLOCKING,
                "Supplier has not declared a hazard class; regulatory clearance cannot be confirmed.",
                "not declared",
                "declared hazard class",
                weights["HAZ-01"],
            )
        )
    elif hazard in prohibited:
        rules.append(
            RuleResult(
                "HAZ-01",
                "Hazard class prohibition",
                FAIL,
                BLOCKING,
                f"Hazard class '{hazard}' is explicitly prohibited for this receiving process.",
                hazard,
                "hazard class outside prohibited list",
                weights["HAZ-01"],
            )
        )
    else:
        rules.append(
            RuleResult(
                "HAZ-01",
                "Hazard class prohibition",
                PASS,
                BLOCKING,
                f"Hazard class '{hazard}' is not prohibited by this demand.",
                hazard,
                "not in prohibited list",
                weights["HAZ-01"],
            )
        )

    # --- PUR-01: minimum purity -------------------------------------------
    min_purity = _num(demand.min_purity_pct)
    purity = _num(spec.purity_pct) if spec else None
    if min_purity is None:
        rules.append(
            RuleResult(
                "PUR-01",
                "Minimum purity",
                PASS,
                BLOCKING,
                "No purity floor is declared for this demand.",
                _fmt(purity, "%"),
                "no minimum",
                weights["PUR-01"],
            )
        )
    elif purity is None:
        rules.append(
            RuleResult(
                "PUR-01",
                "Minimum purity",
                UNKNOWN,
                BLOCKING,
                "Material specification has no purity measurement; suitability is unverified.",
                "not declared",
                f"≥ {min_purity:.2f}%",
                weights["PUR-01"],
            )
        )
    elif purity >= min_purity:
        rules.append(
            RuleResult(
                "PUR-01",
                "Minimum purity",
                PASS,
                BLOCKING,
                f"Declared purity {purity:.2f}% meets the {min_purity:.2f}% floor.",
                _fmt(purity, "%"),
                f"≥ {min_purity:.2f}%",
                weights["PUR-01"],
            )
        )
    else:
        rules.append(
            RuleResult(
                "PUR-01",
                "Minimum purity",
                FAIL,
                BLOCKING,
                f"Declared purity {purity:.2f}% is below the {min_purity:.2f}% floor for this process.",
                _fmt(purity, "%"),
                f"≥ {min_purity:.2f}%",
                weights["PUR-01"],
            )
        )

    # --- CON-01: maximum contamination ------------------------------------
    max_contamination = _num(demand.max_contamination_pct)
    contamination = _num(spec.contamination_pct) if spec else None
    if max_contamination is None:
        rules.append(
            RuleResult(
                "CON-01",
                "Maximum contamination",
                PASS,
                BLOCKING,
                "No contamination ceiling is declared for this demand.",
                _fmt(contamination, "%"),
                "no maximum",
                weights["CON-01"],
            )
        )
    elif contamination is None:
        rules.append(
            RuleResult(
                "CON-01",
                "Maximum contamination",
                UNKNOWN,
                BLOCKING,
                "Contamination has not been assayed; the acceptance ceiling cannot be verified.",
                "not declared",
                f"≤ {max_contamination:.2f}%",
                weights["CON-01"],
            )
        )
    elif contamination <= max_contamination:
        rules.append(
            RuleResult(
                "CON-01",
                "Maximum contamination",
                PASS,
                BLOCKING,
                f"Contamination {contamination:.2f}% is within the {max_contamination:.2f}% ceiling.",
                _fmt(contamination, "%"),
                f"≤ {max_contamination:.2f}%",
                weights["CON-01"],
            )
        )
    else:
        overshoot = (contamination - max_contamination) / max_contamination
        if overshoot <= policy.contamination_tolerance_ratio:
            rules.append(
                RuleResult(
                    "CON-01",
                    "Maximum contamination",
                    WARNING,
                    ADVISORY,
                    (
                        f"Contamination {contamination:.2f}% exceeds the {max_contamination:.2f}% ceiling "
                        f"by {overshoot * 100:.0f}%; pre-treatment is required and must be validated."
                    ),
                    _fmt(contamination, "%"),
                    f"≤ {max_contamination:.2f}%",
                    weights["CON-01"],
                )
            )
        else:
            rules.append(
                RuleResult(
                    "CON-01",
                    "Maximum contamination",
                    FAIL,
                    BLOCKING,
                    (
                        f"Contamination {contamination:.2f}% exceeds the {max_contamination:.2f}% ceiling "
                        f"by {overshoot * 100:.0f}%, beyond the configured tolerance."
                    ),
                    _fmt(contamination, "%"),
                    f"≤ {max_contamination:.2f}%",
                    weights["CON-01"],
                )
            )

    # --- MOI-01: maximum moisture -----------------------------------------
    max_moisture = _num(demand.max_moisture_pct)
    moisture = _num(spec.moisture_pct) if spec else None
    if max_moisture is None:
        rules.append(
            RuleResult(
                "MOI-01",
                "Maximum moisture",
                PASS,
                ADVISORY,
                "No moisture ceiling is declared for this demand.",
                _fmt(moisture, "%"),
                "no maximum",
                weights["MOI-01"],
            )
        )
    elif moisture is None:
        rules.append(
            RuleResult(
                "MOI-01",
                "Maximum moisture",
                UNKNOWN,
                ADVISORY,
                "Moisture content has not been declared.",
                "not declared",
                f"≤ {max_moisture:.2f}%",
                weights["MOI-01"],
            )
        )
    elif moisture <= max_moisture:
        rules.append(
            RuleResult(
                "MOI-01",
                "Maximum moisture",
                PASS,
                ADVISORY,
                f"Moisture {moisture:.2f}% is within the {max_moisture:.2f}% limit.",
                _fmt(moisture, "%"),
                f"≤ {max_moisture:.2f}%",
                weights["MOI-01"],
            )
        )
    elif moisture <= max_moisture * policy.moisture_hard_multiplier:
        rules.append(
            RuleResult(
                "MOI-01",
                "Maximum moisture",
                WARNING,
                ADVISORY,
                (
                    f"Moisture {moisture:.2f}% exceeds the {max_moisture:.2f}% limit; "
                    "drying is required before the material can be charged."
                ),
                _fmt(moisture, "%"),
                f"≤ {max_moisture:.2f}%",
                weights["MOI-01"],
            )
        )
    else:
        rules.append(
            RuleResult(
                "MOI-01",
                "Maximum moisture",
                FAIL,
                BLOCKING,
                (
                    f"Moisture {moisture:.2f}% is more than "
                    f"{policy.moisture_hard_multiplier:.1f}× the {max_moisture:.2f}% limit."
                ),
                _fmt(moisture, "%"),
                f"≤ {max_moisture:.2f}%",
                weights["MOI-01"],
            )
        )

    # --- QTY-01: quantity sufficiency (dimension-checked) ------------------
    available = _num(material.quantity_available) or 0.0
    conversion = conversion_factor(material.unit, demand.unit)
    min_quantity = _num(demand.min_quantity) or 0.0
    max_quantity = _num(demand.max_quantity)
    match_quantity = 0.0
    if not conversion.supported:
        rules.append(
            RuleResult(
                "QTY-01",
                "Quantity sufficiency",
                FAIL,
                BLOCKING,
                conversion.reason,
                f"{available:,.2f} {material.unit.value}",
                f"≥ {min_quantity:,.2f} {demand.unit.value}",
                weights["QTY-01"],
            )
        )
    else:
        available_in_demand_units = available * conversion.factor
        usable = available_in_demand_units
        if max_quantity is not None:
            usable = min(usable, max_quantity)
        match_quantity = round(max(usable, 0.0), 3)
        if available_in_demand_units < min_quantity:
            rules.append(
                RuleResult(
                    "QTY-01",
                    "Quantity sufficiency",
                    FAIL,
                    BLOCKING,
                    (
                        f"Only {available_in_demand_units:,.2f} {demand.unit.value} is available, "
                        f"below the {min_quantity:,.2f} {demand.unit.value} minimum intake."
                    ),
                    f"{available_in_demand_units:,.2f} {demand.unit.value}",
                    f"≥ {min_quantity:,.2f} {demand.unit.value}",
                    weights["QTY-01"],
                )
            )
        elif max_quantity is not None and available_in_demand_units > max_quantity:
            rules.append(
                RuleResult(
                    "QTY-01",
                    "Quantity sufficiency",
                    WARNING,
                    ADVISORY,
                    (
                        f"Supply of {available_in_demand_units:,.2f} {demand.unit.value} exceeds the "
                        f"{max_quantity:,.2f} intake limit; only {match_quantity:,.2f} is allocated."
                    ),
                    f"{available_in_demand_units:,.2f} {demand.unit.value}",
                    f"≤ {max_quantity:,.2f} {demand.unit.value}",
                    weights["QTY-01"],
                )
            )
        else:
            rules.append(
                RuleResult(
                    "QTY-01",
                    "Quantity sufficiency",
                    PASS,
                    BLOCKING,
                    (
                        f"{available_in_demand_units:,.2f} {demand.unit.value} available against a "
                        f"{min_quantity:,.2f} minimum."
                    ),
                    f"{available_in_demand_units:,.2f} {demand.unit.value}",
                    f"≥ {min_quantity:,.2f} {demand.unit.value}",
                    weights["QTY-01"],
                )
            )

    # --- GEO-01: transport radius -----------------------------------------
    max_distance = _num(demand.max_distance_km)
    if max_distance is None:
        rules.append(
            RuleResult(
                "GEO-01",
                "Transport radius",
                PASS,
                ADVISORY,
                "This demand declares no transport radius.",
                "—",
                "no limit",
                weights["GEO-01"],
            )
        )
    elif distance_km is None:
        rules.append(
            RuleResult(
                "GEO-01",
                "Transport radius",
                UNKNOWN,
                BLOCKING,
                "One of the organisations has no coordinates, so transport feasibility is unknown.",
                "not available",
                f"≤ {max_distance:,.0f} km",
                weights["GEO-01"],
            )
        )
    elif distance_km <= max_distance:
        rules.append(
            RuleResult(
                "GEO-01",
                "Transport radius",
                PASS,
                BLOCKING,
                f"Estimated distance {distance_km:,.1f} km is inside the {max_distance:,.0f} km radius.",
                f"{distance_km:,.1f} km",
                f"≤ {max_distance:,.0f} km",
                weights["GEO-01"],
            )
        )
    else:
        rules.append(
            RuleResult(
                "GEO-01",
                "Transport radius",
                FAIL,
                BLOCKING,
                (
                    f"Estimated distance {distance_km:,.1f} km exceeds the {max_distance:,.0f} km "
                    "procurement radius."
                ),
                f"{distance_km:,.1f} km",
                f"≤ {max_distance:,.0f} km",
                weights["GEO-01"],
            )
        )

    # --- TIM-01: availability window --------------------------------------
    rules.append(_timing_rule(material, demand, weights["TIM-01"]))

    # --- COND-01: condition suitability -----------------------------------
    if material.condition in {MaterialCondition.DEGRADED, MaterialCondition.MIXED}:
        rules.append(
            RuleResult(
                "COND-01",
                "Material condition suitability",
                WARNING,
                ADVISORY,
                (
                    f"Material condition '{material.condition.value}' requires an incoming inspection "
                    "and may reduce yield."
                ),
                material.condition.value,
                "as_generated or processed",
                weights["COND-01"],
            )
        )
    elif material.condition == MaterialCondition.UNKNOWN:
        rules.append(
            RuleResult(
                "COND-01",
                "Material condition suitability",
                UNKNOWN,
                EVIDENCE,
                "Material condition is not declared.",
                "unknown",
                "declared condition",
                weights["COND-01"],
            )
        )
    else:
        rules.append(
            RuleResult(
                "COND-01",
                "Material condition suitability",
                PASS,
                EVIDENCE,
                f"Condition '{material.condition.value}' is acceptable for this intake.",
                material.condition.value,
                "as_generated or processed",
                weights["COND-01"],
            )
        )

    blocking = tuple(
        rule.rule_id for rule in rules if rule.status == FAIL and rule.severity == BLOCKING
    )
    return CompatibilityAssessment(
        status=_status_for(rules),
        score=_score_for(rules, weights),
        rules=tuple(rules),
        match_quantity=match_quantity,
        unit=demand.unit,
        distance_km=distance_km,
        blocking_rule_ids=blocking,
    )


def _timing_rule(material: Material, demand: ResourceDemand, weight: int) -> RuleResult:
    """Check overlap between the supply availability window and the need window."""
    need_from, need_until = demand.needed_from, demand.needed_until
    have_from, have_until = material.availability_start, material.availability_end

    required = (
        f"{need_from.isoformat() if need_from else 'open'} → "
        f"{need_until.isoformat() if need_until else 'open'}"
    )
    observed = (
        f"{have_from.isoformat() if have_from else 'undeclared'} → "
        f"{have_until.isoformat() if have_until else 'undeclared'}"
    )

    if need_from is None and need_until is None:
        return RuleResult(
            "TIM-01",
            "Availability window overlap",
            PASS,
            BLOCKING,
            "No required delivery window is declared.",
            observed,
            "no constraint",
            weight,
        )
    if have_from is None and have_until is None:
        return RuleResult(
            "TIM-01",
            "Availability window overlap",
            UNKNOWN,
            BLOCKING,
            "Supplier has not declared an availability window.",
            observed,
            required,
            weight,
        )

    # Treat an open-ended supply window as unbounded on that side.
    supply_start = have_from
    supply_end = have_until
    window_start = need_from
    window_end = need_until

    starts_before_end = (
        supply_start is None or window_end is None or supply_start <= window_end
    )
    ends_after_start = supply_end is None or window_start is None or supply_end >= window_start
    overlaps = starts_before_end and ends_after_start
    if not overlaps:
        return RuleResult(
            "TIM-01",
            "Availability window overlap",
            FAIL,
            BLOCKING,
            "The supply availability window does not overlap the required delivery window.",
            observed,
            required,
            weight,
        )

    fully_covered = (
        (window_start is None or (supply_start is not None and supply_start <= window_start))
        and (window_end is None or (supply_end is not None and supply_end >= window_end))
    )
    if fully_covered:
        return RuleResult(
            "TIM-01",
            "Availability window overlap",
            PASS,
            BLOCKING,
            "Supply window covers the required delivery window.",
            observed,
            required,
            weight,
        )
    return RuleResult(
        "TIM-01",
        "Availability window overlap",
        WARNING,
        ADVISORY,
        "Supply window only partially covers the required delivery window; scheduling is needed.",
        observed,
        required,
        weight,
    )
