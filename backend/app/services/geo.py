"""Geospatial helpers for transport distance estimation."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    lat_a: float | None,
    lon_a: float | None,
    lat_b: float | None,
    lon_b: float | None,
) -> float | None:
    """Great-circle distance in kilometres, or ``None`` if a coordinate is missing.

    This is a straight-line estimate used for feasibility screening. Real route
    distances belong to the optimisation phase.
    """
    if lat_a is None or lon_a is None or lat_b is None or lon_b is None:
        return None

    lat1, lon1, lat2, lon2 = map(float, (lat_a, lon_a, lat_b, lon_b))
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    a = sin(delta_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * asin(sqrt(a)), 1)
