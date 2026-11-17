"""Legacy development actor endpoints removed in Phase 2B.

Real authentication is provided by ``/api/v1/auth/*``. This module is kept as
an empty router only to avoid import breakage in environments that still
reference it; it registers no routes.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/actors", tags=["system"])
