"""Unit handling for quantities.

Conversion only happens between compatible dimensions; anything else is a hard
failure rather than a silent assumption. This keeps compatibility decisions and
ledger totals trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.enums import MaterialUnit

# Canonical factor to the base unit of each dimension.
_FACTORS: dict[MaterialUnit, tuple[str, float]] = {
    MaterialUnit.KILOGRAM: ("mass", 1.0),
    MaterialUnit.TONNE: ("mass", 1000.0),
    MaterialUnit.CUBIC_METRE: ("volume", 1.0),
    MaterialUnit.LITRE: ("volume", 0.001),
    MaterialUnit.MEGAWATT_HOUR: ("energy", 1.0),
}


@dataclass(frozen=True, slots=True)
class UnitConversion:
    supported: bool
    factor: float
    reason: str


def conversion_factor(source: MaterialUnit, target: MaterialUnit) -> UnitConversion:
    """Return the multiplier that converts ``source`` into ``target``."""
    source_dimension, source_factor = _FACTORS[source]
    target_dimension, target_factor = _FACTORS[target]
    if source_dimension != target_dimension:
        return UnitConversion(
            supported=False,
            factor=0.0,
            reason=(
                f"{source.value} and {target.value} measure different dimensions "
                f"({source_dimension} vs {target_dimension}) and cannot be converted."
            ),
        )
    return UnitConversion(supported=True, factor=source_factor / target_factor, reason="")


def convert_quantity(quantity: float, source: MaterialUnit, target: MaterialUnit) -> float | None:
    """Convert a quantity, or return ``None`` when the units are incompatible."""
    conversion = conversion_factor(source, target)
    if not conversion.supported:
        return None
    return round(quantity * conversion.factor, 6)
